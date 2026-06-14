"""
Date created: Jun 13
Author: Kane Weng

Algorithms to search game tree efficiently.
"""

from board import CBoard, Color, PieceType, bits_to_squares
from evaluate import Evaluate

PROMO_PIECES = [PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT]

_PIECE_VALUES = {
    PieceType.PAWN: 1, PieceType.KNIGHT: 3, PieceType.BISHOP: 3,
    PieceType.ROOK: 5, PieceType.QUEEN: 9,  PieceType.KING: 0,
}

Move = tuple[int, int, PieceType | None]  # (from_square, to_square, promotion)


def _flat_moves(board: CBoard) -> list[Move]:
    """Expand (square, bits) legal move pairs into individual (from, to, promo) triples."""
    moves: list[Move] = []
    for from_square, legal_bits in board.get_all_legal_moves():
        for to_square in bits_to_squares(legal_bits):
            if board.needs_promotion(from_square, to_square):
                for promo in PROMO_PIECES:
                    moves.append((from_square, to_square, promo))
            else:
                moves.append((from_square, to_square, None))
    return moves


def _move_order_score(board: CBoard, move: Move) -> int:
    _, to_square, promotion = move
    score = 0
    if promotion is not None:
        score += 100
    captured = board.get_piece_at(to_square)
    if captured is not None:
        score += _PIECE_VALUES[captured[1]] * 10
    return score


class Search:
    def __init__(self):
        self._evaluate = Evaluate()

    def minimax(
        self,
        board: CBoard,
        depth: int,
        alpha: float = -99999,
        beta: float = 99999,
    ) -> tuple[float, Move | None]:
        """Alpha-beta minimax. Returns (score, best_move) from White's perspective."""
        legal_moves = _flat_moves(board)

        if not legal_moves:
            if board.is_in_check(board.turn):
                # Faster mates score higher (depth bonus rewards shorter paths)
                return (-1000 - depth, None) if board.turn == Color.WHITE else (1000 + depth, None)
            return 0.0, None  # Stalemate

        if depth == 0:
            return self._evaluate.evaluate(board), None

        legal_moves.sort(key=lambda m: _move_order_score(board, m), reverse=True)

        maximizing = board.turn == Color.WHITE
        best_eval: float | None = None
        best_move: Move | None = None

        for move in legal_moves:
            from_square, to_square, promotion = move
            board.make_move(from_square, to_square, promotion)
            eval_score, _ = self.minimax(board, depth - 1, alpha, beta)
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
                break

        return best_eval, best_move  # type: ignore[return-value]

    def get_best_move(self, board: CBoard, depth: int = 3) -> Move | None:
        """Public entry point: returns the best (from, to, promo) for the current player."""
        _, move = self.minimax(board, depth)
        return move
