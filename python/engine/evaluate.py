"""
Date created: Jun 14
Author: Kane Weng

Evaluation functions. three levels behind a common interface.

  SimpleEvaluate  : material + doubled-pawn penalty + tiny positional bonuses
  MediumEvaluate  : material + piece-square tables (PST)
  ComplexEvaluate : PST + pawn structure + bishop pair + mobility + king safety

Constant tables (PIECE_VALUES, the piece-square tables, PASSED_BONUS) come from
the shared schema via engine/_generated.py — see schema/engine.toml.
"""

from abc import ABC, abstractmethod

from ._generated import (
    KING_EG_PST,
    KING_MG_PST,
    PASSED_BONUS,
    PIECE_VALUES,
    PST_MAP,
)
from .board import (
    FILE_A,
    FULL_BOARD,
    CBoard,
    Color,
    PieceType,
    bits_to_squares,
)

_FILE_MASKS = [FILE_A << f for f in range(8)]


def _mirror(sq: int) -> int:
    """Vertical flip for Black PST lookup (maps sq to the equivalent White index)."""
    return (7 - sq // 8) * 8 + sq % 8


def _pst_val(pst: list[int], sq: int, color: Color) -> float:
    idx = sq if color == Color.WHITE else _mirror(sq)
    raw = pst[idx]
    return (raw if color == Color.WHITE else -raw) / 100.0


def _is_passed(sq: int, color: Color, white_pawns: int, black_pawns: int) -> bool:
    file_idx = sq % 8
    rank_idx = sq // 8
    fm = _FILE_MASKS[file_idx]
    if file_idx > 0:
        fm |= _FILE_MASKS[file_idx - 1]
    if file_idx < 7:
        fm |= _FILE_MASKS[file_idx + 1]
    if color == Color.WHITE:
        ahead = fm & (FULL_BOARD << ((rank_idx + 1) * 8)) & FULL_BOARD
        return not (black_pawns & ahead)
    else:
        ahead = fm & ((1 << (rank_idx * 8)) - 1)
        return not (white_pawns & ahead)


# ── Abstract base ────────────────────────────────────────────────────────────


class BaseEvaluate(ABC):
    @abstractmethod
    def evaluate(self, board: CBoard) -> float:
        """Score from White's perspective; positive = White winning."""
        pass


# ── Level 1: Simple ──────────────────────────────────────────────────────────


class SimpleEvaluate(BaseEvaluate):
    """Material + doubled-pawn penalty + basic knight/king positional bonuses."""

    def evaluate(self, board: CBoard) -> float:
        score = 0.0
        for color in Color:
            sign = 1 if color == Color.WHITE else -1
            for pt in PieceType:
                for sq in bits_to_squares(board.get_specific_pieces(color, pt)):
                    score += PIECE_VALUES[pt] * sign
                    rank, file = sq // 8, sq % 8

                    if pt == PieceType.PAWN:
                        behind = sq - 8 if color == Color.WHITE else sq + 8
                        if 0 <= behind <= 63:
                            if board.get_specific_pieces(color, PieceType.PAWN) & (1 << behind):
                                score -= 0.5 * sign

                    elif pt == PieceType.KNIGHT:
                        if rank in (3, 4) and file in (3, 4):
                            score += 0.50 * sign
                        elif rank in (2, 5) and file in (2, 5):
                            score += 0.25 * sign
                        elif rank in (0, 7) or file in (0, 7):
                            score -= 0.50 * sign

                    elif pt == PieceType.KING:
                        if color == Color.WHITE and rank == 0 and file in (2, 6):
                            score += 0.75
                        elif color == Color.BLACK and rank == 7 and file in (2, 6):
                            score -= 0.75

        return score


# ── Level 2: Medium ──────────────────────────────────────────────────────────


class MediumEvaluate(BaseEvaluate):
    """Material + piece-square tables."""

    def evaluate(self, board: CBoard) -> float:
        score = 0.0
        for color in Color:
            for pt in PieceType:
                pst = PST_MAP[pt]
                for sq in bits_to_squares(board.get_specific_pieces(color, pt)):
                    score += PIECE_VALUES[pt] * (1 if color == Color.WHITE else -1)
                    score += _pst_val(pst, sq, color)
        return score


# ── Level 3: Complex ─────────────────────────────────────────────────────────


class ComplexEvaluate(BaseEvaluate):
    """PST + pawn structure (doubled, isolated, passed) + bishop pair + mobility."""

    def evaluate(self, board: CBoard) -> float:
        score = 0.0
        white_pawns = board.get_specific_pieces(Color.WHITE, PieceType.PAWN)
        black_pawns = board.get_specific_pieces(Color.BLACK, PieceType.PAWN)

        # Switch king to endgame PST when major/minor material drops
        minor_major = sum(
            bin(board.get_specific_pieces(c, pt)).count("1") * PIECE_VALUES[pt]
            for c in Color
            for pt in (PieceType.KNIGHT, PieceType.BISHOP, PieceType.ROOK, PieceType.QUEEN)
        )
        king_pst = KING_EG_PST if minor_major < 14.0 else KING_MG_PST

        for color in Color:
            sign = 1 if color == Color.WHITE else -1

            for pt in PieceType:
                pst = king_pst if pt == PieceType.KING else PST_MAP[pt]
                for sq in bits_to_squares(board.get_specific_pieces(color, pt)):
                    score += PIECE_VALUES[pt] * sign
                    score += _pst_val(pst, sq, color)

                    if pt == PieceType.PAWN:
                        file_idx = sq % 8
                        rank_idx = sq // 8
                        file_mask = _FILE_MASKS[file_idx]
                        friendly = board.get_specific_pieces(color, PieceType.PAWN)

                        if bin(friendly & file_mask).count("1") > 1:
                            score -= 0.20 * sign  # doubled

                        neighbor = 0
                        if file_idx > 0:
                            neighbor |= _FILE_MASKS[file_idx - 1]
                        if file_idx < 7:
                            neighbor |= _FILE_MASKS[file_idx + 1]
                        if not (friendly & neighbor):
                            score -= 0.25 * sign  # isolated

                        if _is_passed(sq, color, white_pawns, black_pawns):
                            adv = rank_idx if color == Color.WHITE else 7 - rank_idx
                            score += PASSED_BONUS[adv] / 100.0 * sign

            if bin(board.get_specific_pieces(color, PieceType.BISHOP)).count("1") >= 2:
                score += 0.50 * sign  # bishop pair

            # Rough mobility: number of squares attacked
            score += bin(board.get_attacks(color)).count("1") * 0.005 * sign

        return score
