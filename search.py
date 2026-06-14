"""
Date created: Jun 14
Author: Kane Weng

Alpha-beta minimax search with:
  - Transposition table (TT) with Zobrist keys
  - Iterative deepening (primes TT for better move ordering at each depth)
  - Move ordering: TT best move > promotions > MVV-LVA captures > killers > history
  - Killer heuristic: 2 quiet moves per ply that caused beta cutoffs
  - History heuristic: accumulated score for quiet moves that caused cutoffs
"""

from board import CBoard, Color, PieceType, bits_to_squares
from evaluate import BaseEvaluate, MediumEvaluate
from transposition import TranspositionTable, TTFlag

PROMO_PIECES = [PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT]

_MAX_PLY = 64

# Centipawn values for MVV-LVA ordering
_CP = {
    PieceType.PAWN: 100, PieceType.KNIGHT: 320, PieceType.BISHOP: 330,
    PieceType.ROOK: 500, PieceType.QUEEN:  900, PieceType.KING:     0,
}

Move = tuple[int, int, PieceType | None]  # (from_square, to_square, promotion)


def _flat_moves(board: CBoard) -> list[Move]:
    """Expand (square, legal_bits) pairs into individual (from, to, promo) triples."""
    moves: list[Move] = []
    for from_square, legal_bits in board.get_all_legal_moves():
        for to_square in bits_to_squares(legal_bits):
            if board.needs_promotion(from_square, to_square):
                for promo in PROMO_PIECES:
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

    def new_game(self) -> None:
        """Reset search state between games (keeps TT for opening book effect)."""
        self._killers = [[None, None] for _ in range(_MAX_PLY)]
        self._history = [[[0] * 64 for _ in range(64)] for _ in range(2)]

    # ── Move ordering ────────────────────────────────────────────────────────

    def _order_key(self, board: CBoard, move: Move, ply: int, tt_move: Move | None) -> int:
        if move == tt_move:
            return 20_000

        from_sq, to_sq, promotion = move

        if promotion == PieceType.QUEEN:
            return 10_000
        if promotion is not None:
            return 9_000

        captured = board.get_piece_at(to_sq)
        if captured is not None:
            aggressor = board.get_piece_at(from_sq)
            agg_val   = _CP.get(aggressor[1], 0) if aggressor else 0
            return 5_000 + _CP.get(captured[1], 0) * 10 - agg_val

        # Quiet move: killers then history
        if self._killers[ply][0] == move: return 4_000
        if self._killers[ply][1] == move: return 3_000
        return self._history[board.turn.value][from_sq][to_sq]

    # ── Core search ──────────────────────────────────────────────────────────

    def minimax(
        self,
        board: CBoard,
        depth: int,
        alpha: float = -99_999,
        beta:  float =  99_999,
        ply:   int   = 0,
    ) -> tuple[float, Move | None]:
        """Alpha-beta minimax. Score is from White's perspective."""
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
            score = self._evaluate.evaluate(board)
            self._tt.store(key, 0, TTFlag.EXACT, score, None)
            return score, None

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
                    self._history[board.turn.value][from_square][to_square] += depth * depth
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
        self._killers = [[None, None] for _ in range(_MAX_PLY)]
        best_move: Move | None = None
        for d in range(1, depth + 1):
            _, move = self.minimax(board, d)
            if move is not None:
                best_move = move
        return best_move
