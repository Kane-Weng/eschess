"""
Date created: Jun 14
Author: Kane Weng

Alpha-beta minimax search with:
  - Transposition table (TT) with Zobrist keys
  - Iterative deepening
  - Quiescence search at depth 0 (avoids horizon effect)
  - Move ordering: TT best move > promotions > MVV-LVA captures > killers > history
  - Killer heuristic: 2 quiet moves per ply that caused beta cutoffs
  - History heuristic with gravity formula (self-bounding, aging between searches)
"""

import time
from collections.abc import Callable

from board import CBoard, Color, PieceType, bits_to_squares
from evaluate import BaseEvaluate, MediumEvaluate
from transposition import TranspositionTable, TTFlag

PROMO_PIECES = [PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT]

_MAX_PLY     = 64
_MAX_HISTORY = 16_384   # gravity ceiling; scores are bounded to [-MAX, +MAX]
_QS_DEPTH    = 8        # quiescence safety limit

# Centipawn values for MVV-LVA ordering
_CP = {
    PieceType.PAWN: 100, PieceType.KNIGHT: 320, PieceType.BISHOP: 330,
    PieceType.ROOK: 500, PieceType.QUEEN:  900, PieceType.KING:     0,
}

Move = tuple[int, int, PieceType | None]  # (from_square, to_square, promotion)


def _flat_moves(board: CBoard, captures_only: bool = False) -> list[Move]:
    """
    Expand legal moves into (from, to, promo) triples.
    If captures_only=True, include only captures and queen promotions (for quiescence).
    """
    occ   = board.occupied()
    moves: list[Move] = []
    for from_square, legal_bits in board.get_all_legal_moves():
        for to_square in bits_to_squares(legal_bits):
            is_capture = bool(occ & (1 << to_square))
            is_promo   = board.needs_promotion(from_square, to_square)
            if captures_only and not is_capture and not is_promo:
                continue
            if is_promo:
                # In quiescence only generate queen promotions (under-promos are noise)
                promos = [PieceType.QUEEN] if captures_only else PROMO_PIECES
                for promo in promos:
                    moves.append((from_square, to_square, promo))
            else:
                moves.append((from_square, to_square, None))
    return moves


class Search:
    def __init__(self, evaluator: BaseEvaluate | None = None, tt_size_mb: int = 32):
        self._evaluate  = evaluator or MediumEvaluate()
        self._tt        = TranspositionTable(tt_size_mb)
        self._killers: list[list[Move | None]] = [[None, None] for _ in range(_MAX_PLY)]
        self._history:  list[list[list[int]]]  = [[[0] * 64 for _ in range(64)] for _ in range(2)]
        self._nodes:    int          = 0
        self._deadline: float | None = None
        self._stop:     bool         = False

    def new_game(self) -> None:
        """Reset search state between games (TT persists for transposition reuse)."""
        self._killers = [[None, None] for _ in range(_MAX_PLY)]
        self._history = [[[0] * 64 for _ in range(64)] for _ in range(2)]

    # ── History helpers ──────────────────────────────────────────────────────

    def _update_history(self, color: int, from_square: int, to_square: int, depth: int) -> None:
        """
        Gravity formula: pulls score toward the bonus without overflow.
        The -current * |bonus| / MAX term shrinks updates as score approaches the ceiling.
        """
        bonus   = min(depth * depth, _MAX_HISTORY)
        clamped = max(-_MAX_HISTORY, min(_MAX_HISTORY, bonus))
        cur     = self._history[color][from_square][to_square]
        self._history[color][from_square][to_square] += clamped - cur * abs(clamped) // _MAX_HISTORY

    def _age_history(self) -> None:
        """Halve all history scores so recent cutoffs outweigh stale ones."""
        self._history = [[[v >> 1 for v in row] for row in color] for color in self._history]

    # ── Move ordering ────────────────────────────────────────────────────────

    def _order_key(self, board: CBoard, move: Move, ply: int, tt_move: Move | None) -> int:
        if move == tt_move:
            return 20_000

        from_square, to_square, promotion = move

        if promotion == PieceType.QUEEN:
            return 10_000
        if promotion is not None:
            return 9_000

        captured = board.get_piece_at(to_square)
        if captured is not None:
            aggressor = board.get_piece_at(from_square)
            agg_val   = _CP.get(aggressor[1], 0) if aggressor else 0
            return 5_000 + _CP.get(captured[1], 0) * 10 - agg_val

        # Quiet move: killers then history
        if self._killers[ply][0] == move: return 4_000
        if self._killers[ply][1] == move: return 3_000
        return self._history[board.turn.value][from_square][to_square]

    # ── Quiescence search ────────────────────────────────────────────────────

    def _quiescence(self, board: CBoard, alpha: float, beta: float, qdepth: int = 0) -> float:
        """
        Extend search at depth 0 with captures only until the position is quiet.
        Stand-pat score lets the side to move 'do nothing' (lower bound on the position).
        """
        self._nodes += 1
        if self._deadline is not None and (self._nodes & 255) == 0 and time.time() >= self._deadline:
            self._stop = True
        stand_pat   = self._evaluate.evaluate(board)
        if self._stop:
            return stand_pat
        maximizing  = board.turn == Color.WHITE

        if maximizing:
            if stand_pat >= beta:
                return stand_pat        # beta cutoff: too good for White, Black avoids
            if stand_pat > alpha:
                alpha = stand_pat
        else:
            if stand_pat <= alpha:
                return stand_pat        # alpha cutoff: too bad for White, White avoids
            if stand_pat < beta:
                beta = stand_pat

        if qdepth >= _QS_DEPTH:        # safety valve against tactical explosions
            return stand_pat

        captures = _flat_moves(board, captures_only=True)
        # MVV: order by value of captured piece (no LVA needed in QS)
        captures.sort(
            key=lambda m: _CP.get(board.get_piece_at(m[1])[1], 0) if board.get_piece_at(m[1]) else 0,
            reverse=True,
        )

        for move in captures:
            from_square, to_square, promotion = move
            board.make_move(from_square, to_square, promotion)
            score = self._quiescence(board, alpha, beta, qdepth + 1)
            board.unmake_move()

            if maximizing:
                if score > alpha:
                    alpha = score
                if alpha >= beta:
                    return alpha        # beta cutoff
            else:
                if score < beta:
                    beta = score
                if beta <= alpha:
                    return beta         # alpha cutoff

        return alpha if maximizing else beta

    # ── Core search ──────────────────────────────────────────────────────────

    def minimax(
        self,
        board: CBoard,
        depth: int,
        alpha: float = -99_999,
        beta:  float =  99_999,
        ply:   int   = 0,
    ) -> tuple[float, Move | None]:
        """Alpha-beta minimax. Score is always from White's perspective."""
        if self._stop:
            return 0.0, None

        self._nodes += 1
        if self._deadline is not None and (self._nodes & 255) == 0 and time.time() >= self._deadline:
            self._stop = True
            return 0.0, None

        orig_alpha = alpha

        # TT probe
        key      = board.zobrist_key
        tt_entry = self._tt.probe(key)
        tt_move: Move | None = None
        if tt_entry is not None:
            tt_move = tt_entry.best_move
            if tt_entry.depth >= depth:
                if   tt_entry.flag == TTFlag.EXACT: return tt_entry.score, tt_entry.best_move
                elif tt_entry.flag == TTFlag.LOWER: alpha = max(alpha, tt_entry.score)
                elif tt_entry.flag == TTFlag.UPPER: beta  = min(beta,  tt_entry.score)
                if alpha >= beta:
                    return tt_entry.score, tt_entry.best_move

        legal_moves = _flat_moves(board)

        if not legal_moves:
            if board.is_in_check(board.turn):
                return ((-9_000 - depth), None) if board.turn == Color.WHITE else ((9_000 + depth), None)
            return 0.0, None  # stalemate

        if depth == 0:
            return self._quiescence(board, alpha, beta), None

        legal_moves.sort(key=lambda m: self._order_key(board, m, ply, tt_move), reverse=True)

        maximizing = board.turn == Color.WHITE
        best_eval: float | None = None
        best_move: Move | None  = None

        for move in legal_moves:
            from_square, to_square, promotion = move
            is_quiet = promotion is None and board.get_piece_at(to_square) is None

            board.make_move(from_square, to_square, promotion)
            eval_score, _ = self.minimax(board, depth - 1, alpha, beta, ply + 1)
            board.unmake_move()

            if self._stop:
                return (best_eval if best_eval is not None else 0.0), best_move

            if maximizing:
                if best_eval is None or eval_score > best_eval:
                    best_eval, best_move = eval_score, move
                alpha = max(alpha, best_eval)
            else:
                if best_eval is None or eval_score < best_eval:
                    best_eval, best_move = eval_score, move
                beta = min(beta, best_eval)

            if beta <= alpha:
                if is_quiet and ply < _MAX_PLY:
                    if self._killers[ply][0] != move:
                        self._killers[ply][1] = self._killers[ply][0]
                        self._killers[ply][0] = move
                    self._update_history(board.turn.value, from_square, to_square, depth)
                break

        # Store result in TT
        flag = TTFlag.EXACT
        if   best_eval <= orig_alpha: flag = TTFlag.UPPER
        elif best_eval >= beta:       flag = TTFlag.LOWER
        self._tt.store(key, depth, flag, best_eval, best_move)

        return best_eval, best_move  # type: ignore[return-value]

    # ── Public API ───────────────────────────────────────────────────────────

    def get_best_move(self, board: CBoard, depth: int = 3) -> Move | None:
        """Iterative deepening search; returns (from, to, promo) for the current player."""
        move, _ = self.search_position(board, max_depth=depth)
        return move

    def _first_legal_move(self, board: CBoard) -> Move | None:
        """A guaranteed-legal move, used as a fallback when time runs out at depth 1."""
        for from_square, legal_bits in board.get_all_legal_moves():
            for to_square in bits_to_squares(legal_bits):
                promo = PieceType.QUEEN if board.needs_promotion(from_square, to_square) else None
                return (from_square, to_square, promo)
        return None

    def _extract_pv(self, board: CBoard, max_len: int = _MAX_PLY) -> list[Move]:
        """Walk the TT from the root to recover the principal variation."""
        pv: list[Move] = []
        seen: set[int] = set()
        applied = 0
        for _ in range(max_len):
            if board.zobrist_key in seen:
                break          # repetition guard
            seen.add(board.zobrist_key)
            entry = self._tt.probe(board.zobrist_key)
            if entry is None or entry.best_move is None:
                break
            from_square, to_square, promotion = entry.best_move
            if not (board.get_legal_moves(from_square) & (1 << to_square)):
                break          # stale/illegal TT move
            pv.append(entry.best_move)
            board.make_move(from_square, to_square, promotion)
            applied += 1
        for _ in range(applied):
            board.unmake_move()
        return pv

    def search_position(
        self,
        board: CBoard,
        max_depth: int = _MAX_PLY,
        time_limit_ms: float | None = None,
        info_callback: "Callable[[int, float, int, float, list[Move]], None] | None" = None,
    ) -> tuple[Move | None, float]:
        """
        Iterative-deepening search with optional time budget.

        Returns (best_move, score) where score is in pawn units from White's
        perspective. info_callback(depth, score, nodes, elapsed_s, pv) is
        invoked after each completed depth (for UCI info output).
        """
        self._killers = [[None, None] for _ in range(_MAX_PLY)]
        self._age_history()     # decay stale scores before each new search
        self._nodes = 0
        self._stop  = False

        start  = time.time()
        budget = (time_limit_ms / 1000.0) if time_limit_ms else None
        self._deadline = (start + budget) if budget else None

        best_move:  Move | None = self._first_legal_move(board)
        best_score: float       = 0.0
        completed_any           = False

        for d in range(1, max(1, max_depth) + 1):
            score, move = self.minimax(board, d)
            if self._stop:
                if not completed_any and move is not None:
                    best_move = move
                break
            if move is not None:
                best_move, best_score = move, score
                completed_any = True
            if info_callback is not None:
                info_callback(d, best_score, self._nodes, time.time() - start,
                              self._extract_pv(board, d))
            # Mate found, or not enough time left to begin another (deeper) iteration.
            if abs(best_score) > 8_000:
                break
            if budget is not None and (time.time() - start) >= budget * 0.5:
                break

        return best_move, best_score
