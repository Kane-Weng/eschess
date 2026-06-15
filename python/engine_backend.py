"""
Engine backend selection for the pygame GUI.

The GUI keeps the Python 'CBoard' for rendering and legality, but the bot's
"brain" is pluggable. main.py picks it through command line args:

    --lang py    in-process Python engine (default)
    --lang cpp   drive the external C++ UCI binary over stdin/stdout
    --lang rust  drive the external Rust UCI binary over stdin/stdout

For the Python engine, the move source and evaluation are also selectable:

    --search alphabeta   alpha-beta tree search (default)
    --search policy      take the move straight from the policy network

    --eval simple | medium | complex | nn   (used only by alpha-beta search)

The 'nn' evaluation wraps the trained value network; 'policy' search uses the
trained policy network. Both load the most recent weights from nn/weights unless
an explicit path is given.
"""

import subprocess
from pathlib import Path

from engine.board import PieceType, name_to_square

_PYTHON_DIR  = Path(__file__).resolve().parent
_REPO_ROOT   = _PYTHON_DIR.parent
_WEIGHTS_DIR = _PYTHON_DIR / "nn" / "weights"

DEFAULT_CPP_COMMAND = str(_REPO_ROOT / "cpp" / "build" / "uci")
DEFAULT_RUST_COMMAND = str(_REPO_ROOT / "rust" / "target" / "release" / "uci")

_CHAR_TO_PROMO = {
    'n': PieceType.KNIGHT, 'b': PieceType.BISHOP,
    'r': PieceType.ROOK,   'q': PieceType.QUEEN,
}


def _uci_to_move(text: str):
    """'e2e4' / 'e7e8q' to (from_square, to_square, promotion | None)."""
    from_square = name_to_square(text[0:2])
    to_square = name_to_square(text[2:4])
    promotion = _CHAR_TO_PROMO[text[4]] if len(text) > 4 else None
    return from_square, to_square, promotion


# -- External UCI engine (e.g. the C++ port) ---------------------------------

class UCIBackend:
    """Drives an external UCI engine as the bot brain."""

    def __init__(self, command: str):
        self.command = command
        self._proc = subprocess.Popen(
            command, shell=True, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._send("uci")
        self._wait_for("uciok")
        self._send("isready")
        self._wait_for("readyok")

    def _send(self, line: str) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _wait_for(self, token: str) -> None:
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            if raw.strip() == token:
                return
        raise RuntimeError(f"UCI engine {self.command!r} closed before '{token}'")

    def get_best_move(self, board, depth: int = 3):
        """Return (from, to, promo|None) for the side to move, via UCI."""
        assert self._proc.stdout is not None
        self._send(f"position fen {board.to_fen()}")
        self._send(f"go depth {depth}")
        for raw in self._proc.stdout:
            line = raw.strip()
            if line.startswith("bestmove"):
                token = line.split()[1]
                return None if token == "0000" else _uci_to_move(token)
        raise RuntimeError(f"UCI engine {self.command!r} closed before 'bestmove'")

    def close(self) -> None:
        try:
            self._send("quit")
            self._proc.wait(timeout=2)
        except Exception:
            self._proc.kill()


# -- Policy-network move source ----------------------------------------------

class PolicyBackend:
    """Picks the highest-probability legal move from the policy network."""

    def __init__(self, net, device: str = "cpu"):
        self._net = net
        self._device = device

    def get_best_move(self, board, depth: int = 3):
        """Return (from, to, promo|None); depth is unused (no tree search)."""
        from nn.inference import policy_priors

        priors = policy_priors(self._net, board, self._device)
        if not priors:
            return None
        (from_square, to_square), _ = max(priors.items(), key=lambda kv: kv[1])
        promotion = PieceType.QUEEN if board.needs_promotion(from_square, to_square) else None
        return from_square, to_square, promotion


# -- Weight loading ----------------------------------------------------------

def _latest_weights(kind: str) -> Path:
    """Most recent nn/weights/*_<kind>.pt (timestamped names sort by recency)."""
    matches = sorted(_WEIGHTS_DIR.glob(f"*_{kind}.pt"))
    if not matches:
        raise FileNotFoundError(
            f"no '{kind}' weights in {_WEIGHTS_DIR}. Train one first, e.g. "
            f"python -m nn.train --mode {kind} --max-games 2000 --epochs 5"
        )
    return matches[-1]


def _load_net(net, weights: Path, device: str):
    import torch

    net.load_state_dict(torch.load(weights, map_location=device))
    return net.to(device).eval()


# -- Factory -----------------------------------------------------------------

def _build_evaluator(name: str, device: str, weights: str | None):
    """Build a BaseEvaluate from a name; 'nn' loads the value network."""
    from engine.evaluate import SimpleEvaluate, MediumEvaluate, ComplexEvaluate

    if name == "simple":
        return SimpleEvaluate()
    if name == "medium":
        return MediumEvaluate()
    if name == "complex":
        return ComplexEvaluate()
    if name == "nn":
        from nn.network import ValueNet
        from nn.inference import NNEvaluate
        path = Path(weights) if weights else _latest_weights("value")
        net = _load_net(ValueNet(), path, device)
        return NNEvaluate(net, device)
    raise ValueError(f"unknown evaluation '{name}'")


def make_engine(lang: str = "py", search: str = "alphabeta", evaluator: str = "medium",
                device: str = "cpu", value_weights: str | None = None,
                policy_weights: str | None = None, cpp_command: str | None = None,
                rust_command: str | None = None, tt_size_mb: int = 32):
    """Build the bot backend chosen by the command line args (see module docstring)."""
    if lang == "cpp":
        return UCIBackend(cpp_command or DEFAULT_CPP_COMMAND)
    if lang == "rust":
        return UCIBackend(rust_command or DEFAULT_RUST_COMMAND)

    if search == "policy":
        from nn.network import PolicyNet
        path = Path(policy_weights) if policy_weights else _latest_weights("policy")
        net = _load_net(PolicyNet(), path, device)
        return PolicyBackend(net, device)

    from engine.search import Search
    return Search(evaluator=_build_evaluator(evaluator, device, value_weights),
                  tt_size_mb=tt_size_mb)
