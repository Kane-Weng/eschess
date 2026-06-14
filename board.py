"""
Date created: Jun 13
Author: Kane Weng

The script sits the backend of chess programming, the board representation.
"""

from enum import IntEnum, auto
from collections.abc import Iterator

# LERF (Little-Endian Rank-File) Mapping
class Square(IntEnum):
    """
    Square mapping system using LERF-mapping

    Hex Constants:
    - a-file             0x0101010101010101
    - h-file             0x8080808080808080
    - 1st rank           0x00000000000000FF
    - 8th rank           0xFF00000000000000
    - a1-h8 diagonal     0x8040201008040201
    - h1-a8 antidiagonal 0x0102040810204080
    - light squares      0x55AA55AA55AA55AA
    - dark squares       0xAA55AA55AA55AA55
    """
    A1 = 0;      B1 = auto(); C1 = auto(); D1 = auto(); E1 = auto(); F1 = auto(); G1 = auto(); H1 = auto()
    A2 = auto(); B2 = auto(); C2 = auto(); D2 = auto(); E2 = auto(); F2 = auto(); G2 = auto(); H2 = auto()
    A3 = auto(); B3 = auto(); C3 = auto(); D3 = auto(); E3 = auto(); F3 = auto(); G3 = auto(); H3 = auto()
    A4 = auto(); B4 = auto(); C4 = auto(); D4 = auto(); E4 = auto(); F4 = auto(); G4 = auto(); H4 = auto()
    A5 = auto(); B5 = auto(); C5 = auto(); D5 = auto(); E5 = auto(); F5 = auto(); G5 = auto(); H5 = auto()
    A6 = auto(); B6 = auto(); C6 = auto(); D6 = auto(); E6 = auto(); F6 = auto(); G6 = auto(); H6 = auto()
    A7 = auto(); B7 = auto(); C7 = auto(); D7 = auto(); E7 = auto(); F7 = auto(); G7 = auto(); H7 = auto()
    A8 = auto(); B8 = auto(); C8 = auto(); D8 = auto(); E8 = auto(); F8 = auto(); G8 = auto(); H8 = auto()

class Color(IntEnum):
    WHITE = 0
    BLACK = 1

class PieceType(IntEnum):
    PAWN = 0
    KNIGHT = 1
    BISHOP = 2
    ROOK = 3
    QUEEN = 4
    KING = 5

U64 = int   # Type Alias for readability

class CBoard:
    def __init__(self):
        # Two color bitboards + Six piece bitboards
        self.colors: list[U64] = [0 for _ in range(2)]
        self.pieces: list[U64] = [0 for _ in range(6)]

        # Initializes all pieces
        self.set_pieces()

    # -- LSF (Least Significant File) Mapping --
    @staticmethod
    def get_square_index(rank_index: int, file_index: int) -> Square:
        return 8*rank_index + file_index

    @staticmethod
    def get_file_index(square_index: Square) -> int:
        return square_index % 8
    
    @staticmethod
    def get_rank_index(square_index: Square) -> int:
        return square_index // 8
    
    # -- Conversion Utils (0-63 square_index <=> 64-bit mask) --
    @staticmethod
    def square_to_mask(square_index: Square) -> U64:
        """Converts a 0-63 square index into a 64-bit mask."""
        if not (0 <= square_index <= 63):
            raise ValueError(f"Invalid square index: {square_index}")
        return 1 << square_index
    
    @staticmethod
    def mask_to_squares(mask: U64) -> Iterator[int]:
        """Yields all square indices present in the mask (Fast Bit-Twiddling)."""
        while mask:
            lsb = mask & -mask  # Extract lowest "1" bit
            yield lsb.bit_length() - 1
            mask &= mask - 1
    
    def get_specific_pieces(self, color: Color, piece_type: PieceType) -> U64:
        """Returns the U64 bitboard for a specific piece type of a specific color"""
        return self.colors[color] & self.pieces[piece_type]
    
    def set_specific_piece(self, color: Color, piece_type: PieceType, square_index: Square):
        mask = self.square_to_mask(square_index)
        self.colors[color] = self.colors[color] | mask
        self.pieces[piece_type] = self.pieces[piece_type] | mask
    
    def set_pieces(self):
        """Initializes all pieces at start"""
        self.colors[Color.WHITE]      = 0x000000000000FFFF    # 1st, 2nd ranks
        self.colors[Color.BLACK]      = 0xFFFF000000000000    # 7th, 8th ranks
        self.pieces[PieceType.PAWN]   = 0x00FF00000000FF00    # 2nd, 7th ranks
        self.pieces[PieceType.KNIGHT] = 0x4200000000000042  # b1, g1, b8, g8
        self.pieces[PieceType.BISHOP] = 0x2400000000000024  # c1, f1, c8, f8
        self.pieces[PieceType.ROOK]   = 0x8100000000000081  # a1, h1, a8, h8
        self.pieces[PieceType.QUEEN]  = 0x0800000000000008  # d1, d8
        self.pieces[PieceType.KING]   = 0x1000000000000010  # e1, e8
