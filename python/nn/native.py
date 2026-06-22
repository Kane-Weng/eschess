"""
Date created: Jun 15
Author: Kane Weng

Bridge to the optional 'eschess_native' extension (Rust/PyO3) for fast self-play.

The native module runs the entire MCTS self-play loop across many games in
parallel at bare-metal speed, calling back into Python only for batched policy +
value inference. This module wraps it so the RL loop can use it interchangeably
with the pure-Python 'play_game':

  HAS_NATIVE      : True when 'eschess_native' is importable (built via maturin).
  NativeSelfPlay  : runs native self-play and adapts its packed output into the
                    same 'SelfPlaySample' records the RL trainer already consumes.

If the extension is not built, 'HAS_NATIVE' is False and callers fall back to the
pure-Python path. Build the extension with
    'uv run --extra nn maturin develop --release -m rust-ffi/Cargo.toml'
    (or 'uv sync --extra ffi').
"""

from __future__ import annotations

import numpy as np

try:
    import eschess_native as _native

    HAS_NATIVE = True
except ImportError:  # extension not built; callers fall back
    _native = None
    HAS_NATIVE = False

# Root-noise defaults mirror the MCTS constructor defaults in nn/mcts.py
_DIRICHLET_ALPHA = 0.3
_NOISE_FRAC = 0.25


def _make_eval_fn(policy_net, value_net, device: str):
    """Build the batched inference callback the native engine invokes.

    Signature expected by the engine:
        eval_fn(states: np.ndarray[(N,18,8,8) f32]) -> (logits[(N,4096) f32],
                                                        values[(N,) f32])
    Values are tanh outputs in [-1, 1] from White's perspective.
    """
    import torch

    def eval_fn(states: np.ndarray):
        with torch.no_grad():
            planes = torch.from_numpy(states).to(device)
            logits = policy_net(planes).detach().cpu().numpy()
            values = value_net(planes).detach().cpu().numpy().reshape(-1)
        return (
            np.ascontiguousarray(logits, dtype=np.float32),
            np.ascontiguousarray(values, dtype=np.float32),
        )

    return eval_fn


class NativeSelfPlay:
    """Native parallel self-play producing 'SelfPlaySample' records."""

    def __init__(
        self,
        policy_net,
        value_net,
        device: str = "cpu",
        *,
        sims: int = 100,
        c_puct: float = 1.5,
        dirichlet_alpha: float = _DIRICHLET_ALPHA,
        noise_frac: float = _NOISE_FRAC,
        temperature: float = 1.0,
        temp_moves: int = 30,
        max_moves: int = 200,
    ):
        if not HAS_NATIVE:
            raise RuntimeError(
                "eschess_native is not installed. Build it with "
                "'uv run --extra nn maturin develop --release -m rust-ffi/Cargo.toml' "
                "or 'uv sync --extra ffi'."
            )
        self._policy = policy_net
        self._value = value_net
        self._device = device
        self._engine = _native.SelfPlayEngine(
            sims=sims,
            c_puct=c_puct,
            dirichlet_alpha=dirichlet_alpha,
            noise_frac=noise_frac,
            temperature=temperature,
            temp_moves=temp_moves,
            max_moves=max_moves,
        )
        # White-perspective result of each game in the most recent generate() call.
        self.last_game_results: list[float] = []

    def generate(self, num_games: int, seed: int = 0) -> list:
        """Play 'num_games' games and return their training samples."""
        from .selfplay import SelfPlaySample

        eval_fn = _make_eval_fn(self._policy, self._value, self._device)
        states, values, index, prob, offsets = self._engine.generate(num_games, eval_fn, seed)

        index = index.tolist()
        prob = prob.tolist()
        offsets = offsets.tolist()
        values = values.tolist()

        samples = []
        for m, value in enumerate(values):
            start, end = offsets[m], offsets[m + 1]
            target = list(zip(index[start:end], prob[start:end]))
            samples.append(SelfPlaySample(states[m], target, float(value)))
        # One value per game (White POV result); offsets index samples per game.
        self.last_game_results = [float(v) for v in values]
        return samples
