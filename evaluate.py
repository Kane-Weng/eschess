"""
Date created: Jun 13
Author: Kane Weng

Traditional Hand-Crafted Evaluation (HCE) to determine the relative value of a position
"""

from board import CBoard, Color, PieceType, bits_to_squares

PIECE_VALUES = {
    PieceType.PAWN:   1,
    PieceType.KNIGHT: 3,
    PieceType.BISHOP: 3,
    PieceType.ROOK:   5,
    PieceType.QUEEN:  9,
    PieceType.KING:   0,
}


class Evaluate:
    def evaluate(self, board: CBoard) -> float:
        """Material + positional score from White's perspective (positive = White winning)."""
        score = 0.0

        for color in Color:
            sign = 1 if color == Color.WHITE else -1

            for piece_type in PieceType:
                for square in bits_to_squares(board.get_specific_pieces(color, piece_type)):
                    rank = CBoard.get_rank_idx(square)
                    file = CBoard.get_file_idx(square)

                    score += PIECE_VALUES[piece_type] * sign

                    if piece_type == PieceType.PAWN:
                        # Doubled pawn: penalise if a same-color pawn is directly behind this one
                        behind = square - 8 if color == Color.WHITE else square + 8
                        if 0 <= behind <= 63:
                            if board.get_specific_pieces(color, PieceType.PAWN) & (1 << behind):
                                score -= 0.5 * sign

                    elif piece_type == PieceType.KNIGHT:
                        if rank in (3, 4) and file in (3, 4):    score += 0.50 * sign  # center
                        elif rank in (2, 5) and file in (2, 5):  score += 0.25 * sign  # semi-center
                        elif rank in (1, 6) and file in (1, 6):  score -= 0.25 * sign  # outer
                        elif rank in (0, 7) and file in (0, 7):  score -= 0.50 * sign  # corners

                    elif piece_type == PieceType.BISHOP:
                        if rank in (3, 4) and file in (3, 4):    score += 0.50 * sign
                        elif rank in (2, 5) and file in (2, 5):  score += 0.25 * sign

                    elif piece_type == PieceType.KING:
                        # Reward castled king positions
                        if color == Color.WHITE:
                            if rank == 0 and file in (2, 6):   score += 0.75  # c1 / g1
                            elif rank == 0 and file in (1, 7): score += 0.25  # b1 / h1
                        else:
                            if rank == 7 and file in (2, 6):   score -= 0.75  # c8 / g8
                            elif rank == 7 and file in (1, 7): score -= 0.25  # b8 / h8

        return score
