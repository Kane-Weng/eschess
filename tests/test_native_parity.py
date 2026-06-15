"""
Parity + self-play tests for the optional `eschess_native` extension.

These assert the native Rust/PyO3 board behaves identically to the pure-Python
`CBoard` (move generation, FEN, perft, board->planes encoding) and that the
native self-play engine returns well-formed, reproducible training batches.

They need only numpy + eschess_native (no torch): nn/encoding.py is loaded
directly to avoid importing the torch-dependent nn package. The whole module is
skipped when the extension is not built.

Run with `uv run --extra ffi pytest tests/` or directly: `python tests/test_native_parity.py`.
"""

import importlib.util
import random
import sys
from pathlib import Path

import numpy as np

_PY_DIR = Path(__file__).resolve().parents[1] / "python"
if str(_PY_DIR) not in sys.path:
    sys.path.insert(0, str(_PY_DIR))

try:
    import eschess_native as en
except ImportError:                      # pragma: no cover - extension not built
    en = None

from engine.board import CBoard, PieceType  # noqa: E402  (after sys.path setup)

# Load nn/encoding.py without triggering nn/__init__ (which imports torch).
_spec = importlib.util.spec_from_file_location("_enc", _PY_DIR / "nn" / "encoding.py")
_enc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_enc)

_FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
]

# (fen, [perft(1..n) references]) from the Chess Programming Wiki.
_PERFT = [
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902, 197281]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039, 97862]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812, 43238]),
]

_skip = en is None


def _require():
    if _skip:
        raise SystemExit("eschess_native not built; skipping native parity tests")


def _py_move_keys(board: CBoard):
    return sorted((f, t) for f, bits in board.get_all_legal_moves()
                  for t in CBoard.bits_to_squares(bits))


def test_perft_references():
    _require()
    for fen, refs in _PERFT:
        for depth, expected in enumerate(refs, start=1):
            assert en.PyBoard(fen).perft(depth) == expected, (fen, depth)


def test_encoding_parity():
    _require()
    for fen in _FENS:
        native = np.asarray(en.PyBoard(fen).board_to_planes())
        python = _enc.board_to_planes(CBoard.from_fen(fen))
        assert native.shape == (18, 8, 8)
        assert np.array_equal(native, python), fen


def test_movegen_fen_parity():
    _require()
    rng = random.Random(0)
    plies = 0
    for _ in range(60):
        nb, cb = en.PyBoard(), CBoard()
        for _ in range(60):
            assert nb.to_fen() == cb.to_fen()
            keys = sorted(tuple(k) for k in nb.legal_move_keys())
            assert keys == _py_move_keys(cb), cb.to_fen()
            if not keys:
                break
            f, t = rng.choice(keys)
            plies += 1
            cb.make_move(f, t, PieceType.QUEEN if cb.needs_promotion(f, t) else None)
            nb.make_move(f, t, 4 if nb.needs_promotion(f, t) else -1)
    assert plies > 1000   # exercised a meaningful number of positions


def test_zobrist_internal_consistency():
    _require()
    rng = random.Random(1)
    nb = en.PyBoard()
    for _ in range(80):
        keys = [tuple(k) for k in nb.legal_move_keys()]
        if not keys:
            break
        f, t = rng.choice(keys)
        before = nb.zobrist_key
        promo = 4 if nb.needs_promotion(f, t) else -1
        nb.make_move(f, t, promo)
        nb.unmake_move()
        assert nb.zobrist_key == before          # unmake restores the key
        nb.make_move(f, t, promo)
    # Equal positions hash equally.
    a = en.PyBoard(_FENS[1]).zobrist_key
    b = en.PyBoard(_FENS[1]).zobrist_key
    assert a == b


def _dummy_eval(states):
    n = states.shape[0]
    assert states.shape == (n, 18, 8, 8) and states.dtype == np.float32
    return np.zeros((n, 4096), dtype=np.float32), np.zeros((n,), dtype=np.float32)


def test_selfplay_shapes_and_determinism():
    _require()
    engine = en.SelfPlayEngine(sims=16, noise_frac=0.0, temp_moves=8, max_moves=30)
    states, values, index, prob, offsets = engine.generate(4, _dummy_eval, 123)

    m = states.shape[0]
    assert states.shape == (m, 18, 8, 8) and states.dtype == np.float32
    assert values.shape == (m,) and len(offsets) == m + 1
    assert offsets[0] == 0 and offsets[-1] == len(index) == len(prob)
    assert np.all(np.diff(offsets) >= 0)
    for row in range(m):                          # each policy row is a distribution
        s, e = offsets[row], offsets[row + 1]
        if e > s:
            assert abs(float(prob[s:e].sum()) - 1.0) < 1e-4

    # Same seed -> identical batch; different seed -> different batch.
    again = engine.generate(4, _dummy_eval, 123)
    assert np.array_equal(states, again[0]) and np.array_equal(values, again[1])
    other = engine.generate(4, _dummy_eval, 999)
    assert not (states.shape == other[0].shape and np.array_equal(states, other[0]))


if __name__ == "__main__":
    if _skip:
        print("eschess_native not built; nothing to test")
        sys.exit(0)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name}: OK")
    print("all native parity tests passed")
