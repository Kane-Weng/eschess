"""
Date created: Jun 15
Author: Kane Weng

AlphaZero-style self-play reinforcement-learning loop. Each generation:

  1. play self-play games with the current best networks (MCTS-driven),
  2. train candidate networks on a replay buffer of recent games
     (soft cross-entropy to the MCTS visit policy, MSE to the game result),
  3. gate the candidate against the best in an in-process MCTS match, and
  4. promote the candidate to best only if it scores above a threshold.

Networks are warm-started from the supervised checkpoints (training from random
weights is infeasible in pure Python).

Run as a module from the python/ directory:

  python -m nn.rl --generations 5 --games-per-gen 20 --sims 80
"""

import argparse
import copy
import csv
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from engine.board import CBoard, Color, PieceType
from engine_backend import _WEIGHTS_DIR, _latest_weights

from .encoding import POLICY_SIZE
from .mcts import MCTS, select_move
from .metrics import MetricsWriter
from .native import HAS_NATIVE, NativeSelfPlay
from .network import PolicyNet, ValueNet
from .selfplay import SelfPlaySample, game_outcome, play_game

_RESULTS_DIR = Path(__file__).resolve().parents[2] / "harness" / "results"
_RL_DIR = _WEIGHTS_DIR / "rl"


# -- Dataset -----------------------------------------------------------------


class SelfPlayDataset(Dataset):
    """Self-play samples as (planes, dense policy target, value) tensors."""

    def __init__(self, samples: list[SelfPlaySample]):
        self._samples = samples

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int):
        sample = self._samples[idx]
        target = np.zeros(POLICY_SIZE, dtype=np.float32)
        for index, prob in sample.policy_target:
            target[index] = prob
        return (
            torch.from_numpy(sample.planes),
            torch.from_numpy(target),
            torch.tensor(sample.value, dtype=torch.float32),
        )


# -- Training steps ----------------------------------------------------------


def train_policy_soft(
    net: PolicyNet,
    dataset: SelfPlayDataset,
    epochs: int,
    batch_size: int,
    lr: float,
    device: str,
    on_epoch: Callable[[int, float], None] | None = None,
) -> float:
    """Soft cross-entropy to the MCTS visit distribution. Returns last-epoch loss."""
    net = net.to(device).train()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)

    last = 0.0
    for epoch in range(epochs):
        total = 0.0
        for planes, policy_target, _value in loader:
            planes, policy_target = planes.to(device), policy_target.to(device)
            log_probs = F.log_softmax(net(planes), dim=1)
            loss = -(policy_target * log_probs).sum(dim=1).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * planes.size(0)
        last = total / len(dataset)
        print(f"[rl/policy] epoch {epoch + 1}/{epochs}  loss {last:.4f}", flush=True)
        if on_epoch is not None:
            on_epoch(epoch + 1, last)
    net.eval()
    return last


def train_value(
    net: ValueNet,
    dataset: SelfPlayDataset,
    epochs: int,
    batch_size: int,
    lr: float,
    device: str,
    on_epoch: Callable[[int, float], None] | None = None,
) -> float:
    """MSE to the game result (White perspective). Returns last-epoch loss."""
    net = net.to(device).train()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()

    last = 0.0
    for epoch in range(epochs):
        total = 0.0
        for planes, _policy_target, value in loader:
            planes, value = planes.to(device), value.to(device)
            loss = loss_fn(net(planes), value)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * planes.size(0)
        last = total / len(dataset)
        print(f"[rl/value]  epoch {epoch + 1}/{epochs}  loss {last:.4f}", flush=True)
        if on_epoch is not None:
            on_epoch(epoch + 1, last)
    net.eval()
    return last


# -- Acceptance gating -------------------------------------------------------


def _play_match_game(white: MCTS, black: MCTS, max_moves: int) -> float:
    """Two MCTS agents play one deterministic game; White-perspective result."""
    board = CBoard()
    rep_counts: dict[int, int] = {board.zobrist_key: 1}
    for _ in range(max_moves):
        outcome = game_outcome(board, rep_counts)
        if outcome is not None:
            return outcome
        agent = white if board.turn == Color.WHITE else black
        from_square, to_square = select_move(agent.run(board, add_noise=False), temperature=0.0)
        promotion = PieceType.QUEEN if board.needs_promotion(from_square, to_square) else None
        board.make_move(from_square, to_square, promotion)
        rep_counts[board.zobrist_key] = rep_counts.get(board.zobrist_key, 0) + 1
    return 0.0  # over-long game adjudicated as a draw


def evaluate_gate(
    candidate: tuple[PolicyNet, ValueNet],
    best: tuple[PolicyNet, ValueNet],
    games: int,
    sims: int,
    c_puct: float,
    max_moves: int,
    device: str,
) -> float:
    """Candidate vs best over `games` alternating-colour games; candidate score in [0, 1]."""
    cand_mcts = MCTS(candidate[0], candidate[1], device, n_simulations=sims, c_puct=c_puct)
    best_mcts = MCTS(best[0], best[1], device, n_simulations=sims, c_puct=c_puct)

    score = 0.0
    for game in range(games):
        cand_is_white = game % 2 == 0
        white, black = (cand_mcts, best_mcts) if cand_is_white else (best_mcts, cand_mcts)
        white_result = _play_match_game(white, black, max_moves)
        cand_result = white_result if cand_is_white else -white_result
        score += (cand_result + 1.0) / 2.0  # win -> 1, draw -> 0.5, loss -> 0
    return score / games


# -- Orchestration -----------------------------------------------------------


def _wdl(game_results: list[float]) -> tuple[int, int, int]:
    """Count White-perspective win / draw / loss from per-game results."""
    wins = sum(1 for r in game_results if r > 0)
    losses = sum(1 for r in game_results if r < 0)
    draws = len(game_results) - wins - losses
    return wins, draws, losses


def _resolve_backend(backend: str) -> bool:
    """Return True to use the native self-play engine, False for pure Python."""
    if backend == "python":
        return False
    if backend == "native":
        if not HAS_NATIVE:
            raise RuntimeError(
                "--backend native requested but eschess_native is not installed. "
                "Build it with `uv run --extra nn maturin develop --release "
                "-m rust-ffi/Cargo.toml` or `uv sync --extra ffi`."
            )
        return True
    return HAS_NATIVE  # auto: prefer native when available


def _load_net(net, path: Path, device: str):
    net.load_state_dict(torch.load(path, map_location=device))
    return net.to(device).eval()


def _save(net, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), path)


def run_rl(args: argparse.Namespace) -> None:
    device = args.device
    policy_path = Path(args.init_policy) if args.init_policy else _latest_weights("policy")
    value_path = Path(args.init_value) if args.init_value else _latest_weights("value")
    print(f"warm-start policy={policy_path.name}  value={value_path.name}", flush=True)

    best_policy = _load_net(PolicyNet(num_res_blocks=args.res_blocks), policy_path, device)
    best_value = _load_net(ValueNet(num_res_blocks=args.res_blocks), value_path, device)

    use_native = _resolve_backend(args.backend)
    print(f"self-play backend: {'native (eschess_native)' if use_native else 'python'}", flush=True)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = _RESULTS_DIR / f"{stamp}_rl_training.csv"
    with open(csv_path, "w", newline="") as fh:
        csv.writer(fh).writerow(
            ["generation", "samples", "policy_loss", "value_loss", "gate_score", "accepted"]
        )

    # Optional live metrics sink. Default sits next to the CSV so the web
    # dashboard can list/tail it; --metrics-stream overrides the path.
    metrics_path = (
        Path(args.metrics_stream)
        if args.metrics_stream
        else (_RESULTS_DIR / f"{stamp}_rl_training.jsonl")
    )
    metrics = MetricsWriter(metrics_path)
    metrics.emit(
        {
            "type": "run",
            "stamp": stamp,
            "generations": args.generations,
            "games_per_gen": args.games_per_gen,
            "sims": args.sims,
            "backend": "native" if use_native else "python",
        }
    )

    buffer: list[list[SelfPlaySample]] = []
    for generation in range(1, args.generations + 1):
        if use_native:
            native = NativeSelfPlay(
                best_policy,
                best_value,
                device,
                sims=args.sims,
                c_puct=args.c_puct,
                temperature=args.temperature,
                temp_moves=args.temp_moves,
                max_moves=args.max_moves,
            )
            gen_samples = native.generate(
                args.games_per_gen, seed=args.seed + generation * args.games_per_gen
            )
            game_results = native.last_game_results
        else:
            selfplay_mcts = MCTS(
                best_policy, best_value, device, n_simulations=args.sims, c_puct=args.c_puct
            )
            gen_samples = []
            game_results = []
            for _ in range(args.games_per_gen):
                game_samples = play_game(
                    selfplay_mcts,
                    max_moves=args.max_moves,
                    temp_moves=args.temp_moves,
                    temperature=args.temperature,
                )
                # Every sample in a game shares the final result (White POV).
                game_results.append(game_samples[0].value if game_samples else 0.0)
                gen_samples.extend(game_samples)
        wins, draws, losses = _wdl(game_results)
        buffer.append(gen_samples)
        del buffer[: -args.buffer_gens]
        train_samples = [s for gen in buffer for s in gen]
        dataset = SelfPlayDataset(train_samples)
        print(
            f"gen {generation}: {len(gen_samples)} new samples, {len(train_samples)} in buffer",
            flush=True,
        )

        candidate_policy = copy.deepcopy(best_policy)
        candidate_value = copy.deepcopy(best_value)
        policy_loss = train_policy_soft(
            candidate_policy,
            dataset,
            args.epochs,
            args.batch_size,
            args.lr,
            device,
            on_epoch=lambda e, loss: metrics.emit(
                {"type": "epoch", "phase": "policy", "gen": generation, "epoch": e, "loss": loss}
            ),
        )
        value_loss = train_value(
            candidate_value,
            dataset,
            args.epochs,
            args.batch_size,
            args.lr,
            device,
            on_epoch=lambda e, loss: metrics.emit(
                {"type": "epoch", "phase": "value", "gen": generation, "epoch": e, "loss": loss}
            ),
        )

        if args.gate_games > 0:
            gate_score = evaluate_gate(
                (candidate_policy, candidate_value),
                (best_policy, best_value),
                args.gate_games,
                args.sims,
                args.c_puct,
                args.max_moves,
                device,
            )
            accepted = gate_score >= args.gate_threshold
            print(
                f"gen {generation}: gate {gate_score:.3f} "
                f"({'accepted' if accepted else 'rejected'})",
                flush=True,
            )
        else:
            gate_score, accepted = float("nan"), True

        # Always checkpoint the generation's candidate, so a run that never clears
        # the gate still leaves usable artifacts; best_* only tracks the strongest.
        _save(candidate_policy, _RL_DIR / f"{stamp}_rl_gen{generation}_policy.pt")
        _save(candidate_value, _RL_DIR / f"{stamp}_rl_gen{generation}_value.pt")
        _save(candidate_policy, _RL_DIR / "latest_policy.pt")
        _save(candidate_value, _RL_DIR / "latest_value.pt")
        if accepted:
            best_policy, best_value = candidate_policy, candidate_value
            _save(best_policy, _RL_DIR / "best_policy.pt")
            _save(best_value, _RL_DIR / "best_value.pt")

        with open(csv_path, "a", newline="") as fh:
            csv.writer(fh).writerow(
                [
                    generation,
                    len(train_samples),
                    f"{policy_loss:.4f}",
                    f"{value_loss:.4f}",
                    f"{gate_score:.4f}",
                    int(accepted),
                ]
            )

        metrics.emit(
            {
                "type": "gen",
                "gen": generation,
                "samples": len(train_samples),
                "new_samples": len(gen_samples),
                "policy_loss": policy_loss,
                "value_loss": value_loss,
                "gate_score": None if gate_score != gate_score else gate_score,  # NaN -> null
                "accepted": bool(accepted),
                "wins": wins,
                "draws": draws,
                "losses": losses,
            }
        )

    metrics.emit({"type": "done", "generations": args.generations})
    metrics.close()
    print(f"done. best RL nets in {_RL_DIR}; metrics in {csv_path}", flush=True)
    print(f"live metrics stream: {metrics_path}", flush=True)
    print("adopt them for the engine/GUI with: python -m nn.promote", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AlphaZero-style self-play RL for the eschess networks."
    )
    parser.add_argument(
        "--generations", type=int, default=5, help="self-play / train / gate cycles"
    )
    parser.add_argument(
        "--games-per-gen", type=int, default=20, help="self-play games each generation"
    )
    parser.add_argument("--sims", type=int, default=80, help="MCTS simulations per move")
    parser.add_argument("--epochs", type=int, default=2, help="training epochs per generation")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--c-puct", type=float, default=1.5, help="PUCT exploration constant")
    parser.add_argument(
        "--temperature", type=float, default=1.0, help="early-move sampling temperature"
    )
    parser.add_argument(
        "--temp-moves", type=int, default=30, help="plies sampled before going greedy"
    )
    parser.add_argument(
        "--max-moves", type=int, default=200, help="ply cap before a draw is adjudicated"
    )
    parser.add_argument(
        "--buffer-gens", type=int, default=3, help="generations of games kept for training"
    )
    parser.add_argument(
        "--gate-games", type=int, default=10, help="candidate-vs-best games (0 disables gating)"
    )
    parser.add_argument(
        "--gate-threshold", type=float, default=0.55, help="min candidate score to promote"
    )
    parser.add_argument(
        "--init-policy", default=None, help="warm-start policy weights (default: latest supervised)"
    )
    parser.add_argument(
        "--init-value", default=None, help="warm-start value weights (default: latest supervised)"
    )
    parser.add_argument(
        "--res-blocks", type=int, default=4, help="must match the warm-start checkpoints"
    )
    parser.add_argument("--device", default="cpu", help="torch device")
    parser.add_argument(
        "--backend",
        choices=["auto", "native", "python"],
        default="auto",
        help="self-play engine: native eschess_native, pure python, or auto-detect",
    )
    parser.add_argument("--seed", type=int, default=0, help="base RNG seed for native self-play")
    parser.add_argument("--out-dir", default=None, help="override the metrics-CSV directory")
    parser.add_argument(
        "--metrics-stream",
        default=None,
        help="JSONL live-metrics path (default: <out-dir>/<stamp>_rl_training.jsonl)",
    )
    args = parser.parse_args()

    if args.out_dir:
        global _RESULTS_DIR
        _RESULTS_DIR = Path(args.out_dir)

    run_rl(args)


if __name__ == "__main__":
    main()
