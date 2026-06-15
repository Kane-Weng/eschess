"""
Date created: Jun 14
Author: Kane Weng

UCI (Universal Chess Interface) protocol wrapper for the Eschess engine.

Supported commands:
  uci                 → id + options + uciok
  isready             → readyok
  ucinewgame          → reset search state
  setoption name ...  → Hash (TT size, MB)
  position startpos [moves ...]
  position fen <FEN>  [moves ...]
  go [depth N] [movetime ms] [wtime ms] [btime ms] [winc ms] [binc ms]
     [movestogo N] [infinite]
  stop / quit

The bot brain is selectable, mirroring main.py (see engine_backend.make_engine):

  python uci.py                    alpha-beta with the medium evaluation (default)
  python uci.py --eval nn          alpha-beta with the value network as evaluation
  python uci.py --search policy     moves straight from the policy network

Run:  python3 uci.py     (or: uv run python uci.py)
"""

import argparse
import sys

from engine.board import CBoard, Color, PieceType, STARTPOS_FEN, square_name, name_to_square
from engine_backend import make_engine

ENGINE_NAME   = "Eschess"
ENGINE_AUTHOR = "Kane Weng"

# Score sentinel: the search returns ±(9000 + depth) pawn-units for forced mate.
_MATE_THRESHOLD = 8_000

_TIME_SAFETY      = 0.85
_MOVE_OVERHEAD_MS = 20.0

def _apply_margin(budget_ms: float) -> float:
    """Shrink a nominal time budget to leave room for overshoot + I/O overhead."""
    return max(10.0, budget_ms * _TIME_SAFETY - _MOVE_OVERHEAD_MS)

_PROMO_TO_CHAR = {
    PieceType.KNIGHT: 'n', PieceType.BISHOP: 'b',
    PieceType.ROOK:   'r', PieceType.QUEEN:  'q',
}
_CHAR_TO_PROMO = {v: k for k, v in _PROMO_TO_CHAR.items()}

Move = tuple[int, int, "PieceType | None"]


def move_to_uci(move: Move) -> str:
    """(from, to, promo) → UCI long algebraic, e.g. (12, 28, None) → 'e2e4'."""
    from_square, to_square, promotion = move
    text = square_name(from_square) + square_name(to_square)
    if promotion is not None:
        text += _PROMO_TO_CHAR[promotion]
    return text


def uci_to_move(text: str) -> Move:
    """UCI long algebraic → (from, to, promo). e.g. 'e7e8q' → (52, 60, QUEEN)."""
    from_square = name_to_square(text[0:2])
    to_square   = name_to_square(text[2:4])
    promotion   = _CHAR_TO_PROMO[text[4]] if len(text) > 4 else None
    return from_square, to_square, promotion


def _score_to_uci(score: float, white_to_move: bool, pv_len: int = 0) -> str:
    """
    Convert a White-relative pawn-unit score to a UCI "score cp/mate" token,
    reported from the side-to-move's perspective (as UCI requires). Mate distance
    is taken from the principal-variation length (the search's mate sentinel only
    encodes remaining depth, not distance to mate).
    """
    stm = score if white_to_move else -score
    if abs(stm) >= _MATE_THRESHOLD:
        moves = (pv_len + 1) // 2 if pv_len else 1
        return f"mate {moves if stm > 0 else -moves}"
    return f"cp {round(stm * 100)}"


class UCIEngine:
    def __init__(self, search: str = "alphabeta", evaluator: str = "medium",
                 device: str = "cpu") -> None:
        self.board   = CBoard()
        self._search  = search
        self._eval    = evaluator
        self._device  = device
        self._hash_mb = 32
        self._build_engine()

    def _build_engine(self) -> None:
        """(Re)build the brain from the stored config; alpha-beta brains expose
        search_position, the policy brain only get_best_move."""
        self.engine = make_engine(
            lang="py", search=self._search, evaluator=self._eval,
            device=self._device, tt_size_mb=self._hash_mb,
        )
        self._is_search = hasattr(self.engine, "search_position")

    # ── Command dispatch ─────────────────────────────────────────────────────

    def run(self) -> None:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            cmd, _, rest = line.partition(' ')

            if cmd == "uci":
                self._cmd_uci()
            elif cmd == "isready":
                print("readyok", flush=True)
            elif cmd == "ucinewgame":
                if self._is_search:
                    self.engine.new_game()
                self.board = CBoard()
            elif cmd == "setoption":
                self._cmd_setoption(rest)
            elif cmd == "position":
                self._cmd_position(rest)
            elif cmd == "go":
                self._cmd_go(rest)
            elif cmd in ("stop", "ponderhit"):
                pass  # synchronous search: nothing in flight to interrupt
            elif cmd == "quit":
                break
            # Unknown commands are ignored, per the UCI spec.

    # ── Individual commands ──────────────────────────────────────────────────

    def _cmd_uci(self) -> None:
        print(f"id name {ENGINE_NAME}")
        print(f"id author {ENGINE_AUTHOR}")
        print("option name Hash type spin default 32 min 1 max 1024")
        print("uciok", flush=True)

    def _cmd_setoption(self, rest: str) -> None:
        tokens = rest.split()
        if len(tokens) >= 4 and tokens[0] == "name" and tokens[-2] == "value":
            name, value = tokens[1], tokens[-1]
            if name.lower() == "hash" and self._is_search:
                self._hash_mb = max(1, int(value))
                self._build_engine()

    def _cmd_position(self, rest: str) -> None:
        tokens = rest.split()
        if not tokens:
            return

        if tokens[0] == "startpos":
            self.board = CBoard.from_fen(STARTPOS_FEN)
            idx = 1
        elif tokens[0] == "fen":
            self.board = CBoard.from_fen(" ".join(tokens[1:7]))
            idx = 7
        else:
            return

        if idx < len(tokens) and tokens[idx] == "moves":
            for text in tokens[idx + 1:]:
                from_square, to_square, promotion = uci_to_move(text)
                self.board.make_move(from_square, to_square, promotion)

    def _cmd_go(self, rest: str) -> None:
        if not self._is_search:
            self._go_policy()
            return

        params = self._parse_go(rest)
        max_depth, time_limit_ms = self._plan_time(params)

        white = self.board.turn == Color.WHITE

        def emit_info(depth: int, score: float, nodes: int, elapsed: float, pv: list) -> None:
            nps = int(nodes / elapsed) if elapsed > 0 else 0
            pv_text = " ".join(move_to_uci(m) for m in pv)
            print(
                f"info depth {depth} score {_score_to_uci(score, white, len(pv))} "
                f"nodes {nodes} nps {nps} time {int(elapsed * 1000)} pv {pv_text}",
                flush=True,
            )

        best_move, _ = self.engine.search_position(
            self.board, max_depth=max_depth, time_limit_ms=time_limit_ms,
            info_callback=emit_info,
        )
        print(f"bestmove {move_to_uci(best_move) if best_move else '0000'}", flush=True)

    def _go_policy(self) -> None:
        """The policy net picks a move directly; there is no tree to search."""
        best_move = self.engine.get_best_move(self.board)
        if best_move is not None:
            print(f"info depth 1 score cp 0 nodes 1 pv {move_to_uci(best_move)}", flush=True)
        print(f"bestmove {move_to_uci(best_move) if best_move else '0000'}", flush=True)

    # ── "go" argument parsing & time allocation ──────────────────────────────

    @staticmethod
    def _parse_go(rest: str) -> dict:
        tokens = rest.split()
        params: dict = {}
        i = 0
        while i < len(tokens):
            key = tokens[i]
            if key in ("depth", "movetime", "wtime", "btime",
                       "winc", "binc", "movestogo", "nodes"):
                params[key] = int(tokens[i + 1])
                i += 2
            elif key == "infinite":
                params["infinite"] = True
                i += 1
            else:
                i += 1
        return params

    def _plan_time(self, params: dict) -> tuple[int, "float | None"]:
        """Resolve a (max_depth, time_limit_ms) pair from the "go" parameters."""
        max_depth = params.get("depth", 64)

        if "movetime" in params:
            return max_depth, _apply_margin(float(params["movetime"]))

        if "wtime" in params or "btime" in params:
            white = self.board.turn == Color.WHITE
            remaining = params.get("wtime" if white else "btime", 1_000)
            increment = params.get("winc"  if white else "binc", 0)
            movestogo = params.get("movestogo", 30)
            # Spend an even slice of the remaining time, plus most of the increment,
            # never risking more than 90% of the clock on a single move.
            budget = remaining / max(1, movestogo) + increment * 0.8
            return max_depth, _apply_margin(min(budget, remaining * 0.9))

        if "depth" in params:
            return max_depth, None        # pure depth search (depth-bounded)

        if params.get("infinite"):
            # No async stop in this synchronous engine, cap so it never hangs.
            return max_depth, 10_000.0

        return max_depth, _apply_margin(1_000.0)   # bare "go" → ~1s


def parse_args():
    parser = argparse.ArgumentParser(description="Eschess UCI engine.")
    parser.add_argument("--search", choices=("alphabeta", "policy"), default="alphabeta",
                        help="move source: alpha-beta tree search or the policy network")
    parser.add_argument("--eval", choices=("simple", "medium", "complex", "nn"), default="medium",
                        help="evaluation for alpha-beta search; 'nn' is the value network "
                             "(ignored when --search policy)")
    parser.add_argument("--device", default="cpu", help="torch device for the networks")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    UCIEngine(search=args.search, evaluator=args.eval, device=args.device).run()
