"""
Date created: Jun 14
Author: Kane Weng

Average Centipawn Loss (ACL): a move-quality metric for the eschess engines,
scored against a strong reference engine (Stockfish by default).

For every move played in a PGN, the reference engine evaluates the position
before the move (its best line) and after the move; the centipawn loss is how
much worse the played move was than the reference's best, from the mover's
point of view. ACL is the mean loss, reported overall and split by game phase
(opening / middlegame / endgame) and by player.

Our match PGNs use UCI coordinate move text (e.g. "e2e4"), which this script
replays directly with the Python board. Lower ACL = better play.

The reference engine is Stockfish, which is only bundled in the Docker image, so
run ACL there. 

    # in Docker: play a game, then rate move quality against Stockfish
    docker run --rm -v "$PWD/harness/results:/app/harness/results" eschess bash -c '
        python harness/match.py --engine1 cpp/build/uci --name1 eschess-cpp \
            --engine2 stockfish --name2 SF-1350 --opt2 UCI_LimitStrength=true \
            --opt2 UCI_Elo=1350 --games 4 --movetime 100 --pgn /tmp/g.pgn && \
        python harness/acl.py /tmp/g.pgn --ref stockfish --ref-depth 14'

    # score only one engine's moves
    ... python harness/acl.py <pgn> --player eschess-cpp --ref-depth 16

Needs a reference UCI engine on PATH (or via --ref). Any UCI engine works for a
smoke test, but Stockfish gives meaningful numbers.
"""

import argparse
import csv
import shlex
import subprocess
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _REPO_ROOT / "harness" / "results"
sys.path.insert(0, str(_REPO_ROOT / "python"))

from engine.board import CBoard, Color, PieceType, name_to_square  # noqa: E402

# Non-pawn material (pawn units) under which a position counts as endgame
# (the same threshold the engine's ComplexEvaluate uses to switch king tables).
_ENDGAME_MATERIAL = 14.0
_PHASE_MATERIAL = {
    PieceType.KNIGHT: 3.2, PieceType.BISHOP: 3.3,
    PieceType.ROOK: 5.0, PieceType.QUEEN: 9.0,
}


class RefEngine:
    """A reference UCI engine used to score positions (centipawns, STM POV)."""

    def __init__(self, command: str, depth: int):
        self.command = command
        self.depth = depth
        try:
            self.proc = subprocess.Popen(
                shlex.split(command), text=True, bufsize=1,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            sys.exit(f"reference engine not found: {command!r} "
                     f"(install Stockfish or pass --ref)")
        self._send("uci")
        self._wait_for("uciok")

    def _send(self, line: str) -> None:
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _wait_for(self, token: str) -> None:
        for raw in self.proc.stdout:
            if raw.strip() == token:
                return
        raise RuntimeError(f"reference engine closed before '{token}'")

    def score_cp(self, fen: str) -> float:
        """Centipawn score of `fen` from the side-to-move's perspective.

        Mate scores collapse to a large magnitude; per-move loss is capped by
        the caller so they do not distort the average.
        """
        self._send("ucinewgame")
        self._send(f"position fen {fen}")
        self._send(f"go depth {self.depth}")
        score = 0.0
        for raw in self.proc.stdout:
            line = raw.strip()
            if line.startswith("info") and " score " in line:
                toks = line.split()
                if "cp" in toks:
                    score = float(toks[toks.index("cp") + 1])
                elif "mate" in toks:
                    m = int(toks[toks.index("mate") + 1])
                    score = (100000.0 - abs(m)) * (1 if m > 0 else -1)
            elif line.startswith("bestmove"):
                break
        return score

    def close(self) -> None:
        try:
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def _parse_pgn(path: Path):
    """Yield (white_name, black_name, start_fen, [uci_moves]) per game in a PGN.

    Honours the [FEN]/[SetUp] tags so games from an opening suite replay from the
    right position (start_fen is None for games that begin at the standard setup).
    """
    white = black = fen = None
    moves: list[str] = []
    in_moves = False

    def flush():
        nonlocal white, black, fen, moves, in_moves
        if moves:
            yield_val = (white or "White", black or "Black", fen, moves)
            white = black = fen = None
            moves = []
            in_moves = False
            return yield_val
        return None

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith("["):
            if in_moves:  # header after movetext → previous game ended
                out = flush()
                if out:
                    yield out
            if line.startswith('[White "'):
                white = line.split('"')[1]
            elif line.startswith('[Black "'):
                black = line.split('"')[1]
            elif line.startswith('[FEN "'):
                fen = line.split('"')[1]
        elif line:
            in_moves = True
            for tok in line.split():
                if tok in ("1-0", "0-1", "1/2-1/2", "*"):
                    continue
                if "." in tok:  # strip "12." or "12...".
                    tok = tok.split(".")[-1]
                if tok and tok[0].isalpha() and tok[0] in "abcdefgh":
                    moves.append(tok)
    out = flush()
    if out:
        yield out


def _uci_to_move(text: str):
    from_sq = name_to_square(text[0:2])
    to_sq = name_to_square(text[2:4])
    promo = {"n": PieceType.KNIGHT, "b": PieceType.BISHOP,
             "r": PieceType.ROOK, "q": PieceType.QUEEN}.get(text[4:5] or "", None)
    return from_sq, to_sq, promo


def _phase(board: CBoard) -> str:
    if board.fullmove <= 12:
        return "opening"
    material = sum(
        bin(board.get_specific_pieces(c, pt)).count("1") * val
        for c in Color
        for pt, val in _PHASE_MATERIAL.items()
    )
    return "endgame" if material < _ENDGAME_MATERIAL else "middlegame"


def main() -> None:
    ap = argparse.ArgumentParser(description="Average Centipawn Loss vs a reference engine.")
    ap.add_argument("pgn", help="PGN file with UCI-coordinate move text")
    ap.add_argument("--ref", default="stockfish", help="reference UCI engine command")
    ap.add_argument("--ref-depth", type=int, default=12, help="reference search depth")
    ap.add_argument("--player", default=None, help="only score this player's moves (PGN name)")
    ap.add_argument("--cap", type=float, default=1000.0, help="clamp per-move loss (centipawns)")
    ap.add_argument("--max-games", type=int, default=None, help="limit games analysed")
    ap.add_argument("--csv", default=None,
                    help="ACL table CSV path (default: harness/results/acl_<ts>.csv)")
    args = ap.parse_args()

    ref = RefEngine(args.ref, args.ref_depth)

    # sums[(player, phase)] = [loss_sum, count]
    sums: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0])

    games = list(_parse_pgn(Path(args.pgn)))
    if args.max_games:
        games = games[: args.max_games]
    print(f"Analysing {len(games)} game(s) with {args.ref} @ depth {args.ref_depth}\n")

    for gi, (white, black, start_fen, moves) in enumerate(games, 1):
        board = CBoard.from_fen(start_fen) if start_fen else CBoard()
        for mv in moves:
            mover = white if board.turn == Color.WHITE else black
            from_sq, to_sq, promo = _uci_to_move(mv)

            if args.player is None or mover == args.player:
                phase = _phase(board)
                best_cp = ref.score_cp(board.to_fen())
                board.make_move(from_sq, to_sq, promo)
                # score after the move is from the opponent's POV → negate.
                played_cp = -ref.score_cp(board.to_fen())
                loss = max(0.0, min(args.cap, best_cp - played_cp))
                entry = sums[(mover, phase)]
                entry[0] += loss
                entry[1] += 1
            else:
                board.make_move(from_sq, to_sq, promo)
        print(f"  game {gi}/{len(games)} done ({white} vs {black}, {len(moves)} plies)")

    ref.close()

    # ── Report ──────────────────────────────────────────────────────────────
    players = sorted({p for (p, _) in sums})
    phases = ["opening", "middlegame", "endgame"]
    print("\nAverage Centipawn Loss (lower = better):\n")
    header = f"{'player':<22}" + "".join(f"{ph:>13}" for ph in phases) + f"{'overall':>13}"
    print(header)
    print("-" * len(header))

    rows = []
    for p in players:
        cells = []
        tot_loss, tot_n = 0.0, 0
        for ph in phases:
            loss, n = sums.get((p, ph), [0.0, 0])
            tot_loss += loss
            tot_n += n
            cells.append(f"{loss / n:>11.1f} ({n})" if n else f"{'-':>13}")
            rows.append({"player": p, "phase": ph,
                         "acl": round(loss / n, 1) if n else None, "moves": n})
        overall = tot_loss / tot_n if tot_n else 0.0
        print(f"{p:<22}" + "".join(cells) + f"{overall:>11.1f} ({tot_n})")
        rows.append({"player": p, "phase": "overall",
                     "acl": round(overall, 1) if tot_n else None, "moves": tot_n})

    # Default the CSV under harness/results/ so output is collected in one place
    # (mount that dir when running in Docker to keep it on the host).
    if args.csv:
        csv_path = Path(args.csv)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = _RESULTS_DIR / f"acl_{ts}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["player", "phase", "acl", "moves"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV written to {csv_path}")


if __name__ == "__main__":
    main()
