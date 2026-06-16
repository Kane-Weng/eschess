"""
Date created: Jun 13
Author: Kane Weng

Chess board backend: representation, move generation, validation, game state.
"""

import random as _random
from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum, auto


class Square(IntEnum):
    """
    Square mapping system using LERF-mapping (Little-Endian Rank-File)

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

    A1 = 0
    B1 = auto()
    C1 = auto()
    D1 = auto()
    E1 = auto()
    F1 = auto()
    G1 = auto()
    H1 = auto()
    A2 = auto()
    B2 = auto()
    C2 = auto()
    D2 = auto()
    E2 = auto()
    F2 = auto()
    G2 = auto()
    H2 = auto()
    A3 = auto()
    B3 = auto()
    C3 = auto()
    D3 = auto()
    E3 = auto()
    F3 = auto()
    G3 = auto()
    H3 = auto()
    A4 = auto()
    B4 = auto()
    C4 = auto()
    D4 = auto()
    E4 = auto()
    F4 = auto()
    G4 = auto()
    H4 = auto()
    A5 = auto()
    B5 = auto()
    C5 = auto()
    D5 = auto()
    E5 = auto()
    F5 = auto()
    G5 = auto()
    H5 = auto()
    A6 = auto()
    B6 = auto()
    C6 = auto()
    D6 = auto()
    E6 = auto()
    F6 = auto()
    G6 = auto()
    H6 = auto()
    A7 = auto()
    B7 = auto()
    C7 = auto()
    D7 = auto()
    E7 = auto()
    F7 = auto()
    G7 = auto()
    H7 = auto()
    A8 = auto()
    B8 = auto()
    C8 = auto()
    D8 = auto()
    E8 = auto()
    F8 = auto()
    G8 = auto()
    H8 = auto()


class Color(IntEnum):
    WHITE = 0
    BLACK = 1

    def opponent(self) -> "Color":
        return Color(1 - self.value)


class PieceType(IntEnum):
    PAWN = 0
    KNIGHT = 1
    BISHOP = 2
    ROOK = 3
    QUEEN = 4
    KING = 5


U64 = int  # Type alias for readability

# ── Castling rights bitmask ─────────────────────────────────────────────────
CR_WK = 0b1000
CR_WQ = 0b0100
CR_BK = 0b0010
CR_BQ = 0b0001

# ── FEN piece characters ────────────────────────────────────────────────────
_PIECE_TO_FEN: dict[PieceType, str] = {
    PieceType.PAWN: "p",
    PieceType.KNIGHT: "n",
    PieceType.BISHOP: "b",
    PieceType.ROOK: "r",
    PieceType.QUEEN: "q",
    PieceType.KING: "k",
}
_FEN_TO_PIECE: dict[str, PieceType] = {v: k for k, v in _PIECE_TO_FEN.items()}

STARTPOS_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# ── Board constants ─────────────────────────────────────────────────────────
FULL_BOARD: U64 = 0xFFFFFFFFFFFFFFFF

FILE_A: U64 = 0x0101010101010101
FILE_H: U64 = 0x8080808080808080
FILE_AB: U64 = FILE_A | (FILE_A << 1)
FILE_GH: U64 = FILE_H | (FILE_H >> 1)

NOT_FILE_A: U64 = FULL_BOARD ^ FILE_A
NOT_FILE_H: U64 = FULL_BOARD ^ FILE_H
NOT_FILE_AB: U64 = FULL_BOARD ^ FILE_AB
NOT_FILE_GH: U64 = FULL_BOARD ^ FILE_GH

RANK_1: U64 = 0x00000000000000FF
RANK_2: U64 = 0x000000000000FF00
RANK_7: U64 = 0x00FF000000000000
RANK_8: U64 = 0xFF00000000000000

# ── Square / bits conversion ────────────────────────────────────────────────


def square_to_bits(square: int) -> U64:
    """Convert a 0-63 square index to a single-bit U64."""
    if not (0 <= square <= 63):
        raise ValueError(f"Invalid square index: {square}")
    return 1 << square


def bits_to_squares(bits: U64) -> Iterator[int]:
    """Yield all square indices set in bits (fast LSB extraction)."""
    while bits:
        lsb = bits & -bits
        yield lsb.bit_length() - 1
        bits &= bits - 1


# ── Square / algebraic name conversion (for UCI / FEN) ──────────────────────
_FILE_CHARS = "abcdefgh"


def square_name(square: int) -> str:
    """0-63 square index → algebraic coordinate, e.g. 12 → 'e2'."""
    return f"{_FILE_CHARS[square % 8]}{square // 8 + 1}"


def name_to_square(name: str) -> int:
    """Algebraic coordinate → 0-63 square index, e.g. 'e2' → 12."""
    file_idx = ord(name[0]) - ord("a")
    rank_idx = int(name[1]) - 1
    return 8 * rank_idx + file_idx


# ── Directional shift functions (wrap-safe) ─────────────────────────────────
"""
== Compass Rose for LERF mapping ==
          +7    +8    +9
              \\  |  /
          -1 <-  0 -> +1
              /  |  \\
          -9    -8    -7
===================================
"""


def shift_n(bits: U64) -> U64:
    return (bits << 8) & FULL_BOARD


def shift_s(bits: U64) -> U64:
    return bits >> 8


def shift_e(bits: U64) -> U64:
    return (bits & NOT_FILE_H) << 1


def shift_w(bits: U64) -> U64:
    return (bits & NOT_FILE_A) >> 1


def shift_ne(bits: U64) -> U64:
    return ((bits & NOT_FILE_H) << 9) & FULL_BOARD


def shift_nw(bits: U64) -> U64:
    return ((bits & NOT_FILE_A) << 7) & FULL_BOARD


def shift_se(bits: U64) -> U64:
    return (bits & NOT_FILE_H) >> 7


def shift_sw(bits: U64) -> U64:
    return (bits & NOT_FILE_A) >> 9


def knight_attacks(bits: U64) -> U64:
    """All squares a knight can reach from any set bit in bits."""
    l1 = (bits >> 1) & NOT_FILE_H
    l2 = (bits >> 2) & NOT_FILE_GH
    r1 = (bits << 1) & NOT_FILE_A
    r2 = (bits << 2) & NOT_FILE_AB
    h1 = l1 | r1
    h2 = l2 | r2
    return ((h1 << 16) | (h1 >> 16) | (h2 << 8) | (h2 >> 8)) & FULL_BOARD


# ── Zobrist hashing ─────────────────────────────────────────────────────────
_rng = _random.Random(0xCAFEBABE)  # fixed seed → reproducible keys


def _r64() -> int:
    return _rng.getrandbits(64)


# Initialization:
# - 1  number for each piece at each square
# - 1  number to indicate the side to move is black
# - 16 numbers to indicate castling rights
# - 8  numbers to indicate the file of a valid en-passant square
_ZOB_PIECE = [[[_r64() for _ in range(64)] for _ in range(6)] for _ in range(2)]
_ZOB_TURN = _r64()
_ZOB_CASTLE = [_r64() for _ in range(16)]
_ZOB_EP = [_r64() for _ in range(8)]

# ── Move record ─────────────────────────────────────────────────────────────


@dataclass
class Move:
    from_square: int
    to_square: int
    captured_piece: PieceType | None = None
    captured_color: Color | None = None
    promotion: PieceType | None = None
    is_en_passant: bool = False
    is_castle: bool = False
    castle_rook_from: int | None = None
    castle_rook_to: int | None = None
    # Saved state for unmake
    prev_en_passant_square: int | None = None
    prev_castling_rights: int = 0b1111
    prev_halfmove_clock: int = 0
    prev_zobrist_key: int = 0


class CBoard:
    """
    Chess board: pure logic layer.
    Board state, move generation, legal filtering, make/unmake, check/mate detection.
    """

    def __init__(self):
        self.colors: list[U64] = [0, 0]
        self.pieces: list[U64] = [0, 0, 0, 0, 0, 0]
        self.set_pieces()

        self.turn: Color = Color.WHITE
        self.en_passant_square: int | None = None
        self.castling_rights: int = 0b1111
        self.halfmove_clock: int = 0
        self.fullmove: int = 1
        self.move_history: list[Move] = []
        self.game_over: bool = False
        self.winner: Color | None = None  # None = stalemate
        self.zobrist_key: int = self._compute_zobrist()

    # ── Square helpers ──────────────────────────────────────────────────────

    @staticmethod
    def get_square_idx(rank_idx: int, file_idx: int) -> int:
        return 8 * rank_idx + file_idx

    @staticmethod
    def get_file_idx(square: int) -> int:
        return square % 8

    @staticmethod
    def get_rank_idx(square: int) -> int:
        return square // 8

    @staticmethod
    def square_to_bits(square: int) -> U64:
        return square_to_bits(square)

    @staticmethod
    def bits_to_squares(bits: U64) -> Iterator[int]:
        return bits_to_squares(bits)

    # ── Board init ──────────────────────────────────────────────────────────

    def set_pieces(self):
        self.colors[Color.WHITE] = 0x000000000000FFFF
        self.colors[Color.BLACK] = 0xFFFF000000000000
        self.pieces[PieceType.PAWN] = 0x00FF00000000FF00
        self.pieces[PieceType.KNIGHT] = 0x4200000000000042
        self.pieces[PieceType.BISHOP] = 0x2400000000000024
        self.pieces[PieceType.ROOK] = 0x8100000000000081
        self.pieces[PieceType.QUEEN] = 0x0800000000000008
        self.pieces[PieceType.KING] = 0x1000000000000010

    # ── FEN serialization ───────────────────────────────────────────────────

    @classmethod
    def from_fen(cls, fen: str) -> "CBoard":
        """Construct a board from a FEN string."""
        board = cls()
        board.set_fen(fen)
        return board

    def set_fen(self, fen: str) -> None:
        """Reset board state to the position described by a FEN string."""
        parts = fen.split()
        if len(parts) < 4:
            raise ValueError(f"Invalid FEN (need ≥4 fields): {fen!r}")
        placement, side, castling, ep = parts[0], parts[1], parts[2], parts[3]

        self.colors = [0, 0]
        self.pieces = [0, 0, 0, 0, 0, 0]
        rank_idx, file_idx = 7, 0
        for ch in placement:
            if ch == "/":
                rank_idx -= 1
                file_idx = 0
            elif ch.isdigit():
                file_idx += int(ch)
            else:
                color = Color.WHITE if ch.isupper() else Color.BLACK
                self._set_piece(color, _FEN_TO_PIECE[ch.lower()], 8 * rank_idx + file_idx)
                file_idx += 1

        self.turn = Color.WHITE if side == "w" else Color.BLACK
        cr = 0
        if "K" in castling:
            cr |= CR_WK
        if "Q" in castling:
            cr |= CR_WQ
        if "k" in castling:
            cr |= CR_BK
        if "q" in castling:
            cr |= CR_BQ
        self.castling_rights = cr
        self.en_passant_square = None if ep == "-" else name_to_square(ep)
        self.halfmove_clock = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1

        self.move_history = []
        self.game_over = False
        self.winner = None
        self.zobrist_key = self._compute_zobrist()

    def to_fen(self) -> str:
        """Serialize the current position to a FEN string."""
        rows: list[str] = []
        for rank_idx in range(7, -1, -1):
            row, empty = "", 0
            for file_idx in range(8):
                info = self.get_piece_at(8 * rank_idx + file_idx)
                if info is None:
                    empty += 1
                    continue
                if empty:
                    row += str(empty)
                    empty = 0
                color, piece_type = info
                ch = _PIECE_TO_FEN[piece_type]
                row += ch.upper() if color == Color.WHITE else ch
            if empty:
                row += str(empty)
            rows.append(row)

        side = "w" if self.turn == Color.WHITE else "b"
        cr = (
            "".join(
                c
                for bit, c in ((CR_WK, "K"), (CR_WQ, "Q"), (CR_BK, "k"), (CR_BQ, "q"))
                if self.castling_rights & bit
            )
            or "-"
        )
        ep = "-" if self.en_passant_square is None else square_name(self.en_passant_square)
        return f"{'/'.join(rows)} {side} {cr} {ep} {self.halfmove_clock} {self.fullmove}"

    def _compute_zobrist(self) -> int:
        """
        Gets the Zobrist hash code of a certain position by
        xoring all random numbers linked to the initial position
        """
        key = 0
        for color in Color:
            for pt in PieceType:
                for sq in bits_to_squares(self.get_specific_pieces(color, pt)):
                    key ^= _ZOB_PIECE[color][pt][sq]
        if self.turn == Color.BLACK:
            key ^= _ZOB_TURN
        key ^= _ZOB_CASTLE[self.castling_rights & 0xF]
        if self.en_passant_square is not None:
            key ^= _ZOB_EP[self.en_passant_square % 8]
        return key

    # ── Piece queries ───────────────────────────────────────────────────────

    def occupied(self) -> U64:
        return self.colors[Color.WHITE] | self.colors[Color.BLACK]

    def get_specific_pieces(self, color: Color, piece_type: PieceType) -> U64:
        return self.colors[color] & self.pieces[piece_type]

    def get_piece_at(self, square: int) -> tuple[Color, PieceType] | None:
        bits = square_to_bits(square)
        for color in Color:
            if self.colors[color] & bits:
                for piece_type in PieceType:
                    if self.pieces[piece_type] & bits:
                        return (color, piece_type)
        return None

    def _king_square(self, color: Color) -> int:
        bits = self.get_specific_pieces(color, PieceType.KING)
        return (bits & -bits).bit_length() - 1

    # ── Low-level bitboard mutators ─────────────────────────────────────────

    def _set_piece(self, color: Color, piece_type: PieceType, square: int):
        bits = square_to_bits(square)
        self.colors[color] |= bits
        self.pieces[piece_type] |= bits

    def _clear_piece(self, color: Color, piece_type: PieceType, square: int):
        bits = ~square_to_bits(square) & FULL_BOARD
        self.colors[color] &= bits
        self.pieces[piece_type] &= bits

    # ── Sliding ray helpers ─────────────────────────────────────────────────

    def _ray(self, square: int, delta: int, edge_mask: U64, occ: U64, friendly: U64) -> U64:
        """Walk one ray direction.

        edge_mask marks squares where the ray must stop before stepping.
        """
        result: U64 = 0
        cur = square
        while True:
            if square_to_bits(cur) & edge_mask:
                break
            cur += delta
            if not (0 <= cur <= 63):
                break
            bits = square_to_bits(cur)
            if bits & friendly:
                break
            result |= bits
            if bits & occ:
                break
        return result

    def _bishop_attacks(self, square: int, occ: U64, friendly: U64) -> U64:
        result = self._ray(square, 9, FILE_H | RANK_8, occ, friendly)
        result |= self._ray(square, 7, FILE_A | RANK_8, occ, friendly)
        result |= self._ray(square, -7, FILE_H | RANK_1, occ, friendly)
        result |= self._ray(square, -9, FILE_A | RANK_1, occ, friendly)
        return result

    def _rook_attacks(self, square: int, occ: U64, friendly: U64) -> U64:
        result = self._ray(square, 8, RANK_8, occ, friendly)
        result |= self._ray(square, -8, RANK_1, occ, friendly)
        result |= self._ray(square, 1, FILE_H, occ, friendly)
        result |= self._ray(square, -1, FILE_A, occ, friendly)
        return result

    # ── Pseudo-legal move generators ────────────────────────────────────────

    def _pawn_pseudo(self, square: int, color: Color) -> U64:
        occ = self.occupied()
        enemy = self.colors[color.opponent()]
        bits = square_to_bits(square)
        result: U64 = 0

        if color == Color.WHITE:
            push1 = shift_n(bits) & ~occ
            result |= push1
            if bits & RANK_2:
                result |= shift_n(push1) & ~occ  # Double push (blocked if rank 3 is occupied)
            result |= shift_nw(bits) & enemy
            result |= shift_ne(bits) & enemy
            if self.en_passant_square is not None:
                ep_bits = square_to_bits(self.en_passant_square)
                result |= (shift_nw(bits) | shift_ne(bits)) & ep_bits
        else:
            push1 = shift_s(bits) & ~occ
            result |= push1
            if bits & RANK_7:
                result |= shift_s(push1) & ~occ
            result |= shift_sw(bits) & enemy
            result |= shift_se(bits) & enemy
            if self.en_passant_square is not None:
                ep_bits = square_to_bits(self.en_passant_square)
                result |= (shift_sw(bits) | shift_se(bits)) & ep_bits

        return result

    def _knight_pseudo(self, square: int, color: Color) -> U64:
        return knight_attacks(square_to_bits(square)) & ~self.colors[color]

    def _bishop_pseudo(self, square: int, color: Color) -> U64:
        return self._bishop_attacks(square, self.occupied(), self.colors[color])

    def _rook_pseudo(self, square: int, color: Color) -> U64:
        return self._rook_attacks(square, self.occupied(), self.colors[color])

    def _queen_pseudo(self, square: int, color: Color) -> U64:
        occ = self.occupied()
        friendly = self.colors[color]
        return self._bishop_attacks(square, occ, friendly) | self._rook_attacks(
            square, occ, friendly
        )

    def _king_pseudo(self, square: int, color: Color) -> U64:
        bits = square_to_bits(square)
        attacks = (
            shift_n(bits)
            | shift_s(bits)
            | shift_e(bits)
            | shift_w(bits)
            | shift_ne(bits)
            | shift_nw(bits)
            | shift_se(bits)
            | shift_sw(bits)
        )
        return attacks & ~self.colors[color]

    def _get_pseudo_legal(self, square: int, color: Color) -> U64:
        info = self.get_piece_at(square)
        if info is None or info[0] != color:
            return 0
        piece_type = info[1]
        if piece_type == PieceType.PAWN:
            return self._pawn_pseudo(square, color)
        if piece_type == PieceType.KNIGHT:
            return self._knight_pseudo(square, color)
        if piece_type == PieceType.BISHOP:
            return self._bishop_pseudo(square, color)
        if piece_type == PieceType.ROOK:
            return self._rook_pseudo(square, color)
        if piece_type == PieceType.QUEEN:
            return self._queen_pseudo(square, color)
        if piece_type == PieceType.KING:
            return self._king_pseudo(square, color)
        return 0

    # ── Attack map (for check/castle validation) ────────────────────────────

    def get_attacks(self, color: Color) -> U64:
        """All squares attacked by color (used for check and castling safety)."""
        occ = self.occupied()
        result: U64 = 0

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.PAWN)):
            bits = square_to_bits(square)
            if color == Color.WHITE:
                result |= shift_nw(bits) | shift_ne(bits)
            else:
                result |= shift_sw(bits) | shift_se(bits)

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.KNIGHT)):
            result |= knight_attacks(square_to_bits(square))

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.BISHOP)):
            result |= self._bishop_attacks(square, occ, 0)

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.ROOK)):
            result |= self._rook_attacks(square, occ, 0)

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.QUEEN)):
            result |= self._bishop_attacks(square, occ, 0) | self._rook_attacks(square, occ, 0)

        for square in bits_to_squares(self.get_specific_pieces(color, PieceType.KING)):
            bits = square_to_bits(square)
            result |= (
                shift_n(bits)
                | shift_s(bits)
                | shift_e(bits)
                | shift_w(bits)
                | shift_ne(bits)
                | shift_nw(bits)
                | shift_se(bits)
                | shift_sw(bits)
            )

        return result

    def is_in_check(self, color: Color) -> bool:
        king_square = self._king_square(color)
        return bool(self.get_attacks(color.opponent()) & square_to_bits(king_square))

    # ── Make / Unmake ───────────────────────────────────────────────────────

    def make_move(self, from_square: int, to_square: int, promotion: PieceType | None = None):
        piece_info = self.get_piece_at(from_square)
        assert piece_info is not None
        color, piece_type = piece_info

        captured_info = self.get_piece_at(to_square)
        captured_piece_type = captured_info[1] if captured_info else None
        captured_piece_color = captured_info[0] if captured_info else None

        move = Move(
            from_square=from_square,
            to_square=to_square,
            captured_piece=captured_piece_type,
            captured_color=captured_piece_color,
            promotion=promotion,
            prev_en_passant_square=self.en_passant_square,
            prev_castling_rights=self.castling_rights,
            prev_halfmove_clock=self.halfmove_clock,
            prev_zobrist_key=self.zobrist_key,
        )

        # Remove captured piece (normal capture)
        if captured_piece_type is not None:
            self._clear_piece(captured_piece_color, captured_piece_type, to_square)

        # En passant capture
        if piece_type == PieceType.PAWN and self.en_passant_square == to_square:
            ep_square = to_square - 8 if color == Color.WHITE else to_square + 8
            self._clear_piece(color.opponent(), PieceType.PAWN, ep_square)
            move.is_en_passant = True

        # Move piece (with optional promotion)
        self._clear_piece(color, piece_type, from_square)
        placed_piece_type = promotion if promotion is not None else piece_type
        self._set_piece(color, placed_piece_type, to_square)

        # Castling: move the rook to the correct square
        if piece_type == PieceType.KING:
            diff = to_square - from_square
            rook_from = rook_to = None
            if diff == 2:  # Kingside
                rook_from = from_square + 3
                rook_to = from_square + 1
            elif diff == -2:  # Queenside
                rook_from = from_square - 4
                rook_to = from_square - 1
            if rook_from is not None:
                self._clear_piece(color, PieceType.ROOK, rook_from)
                self._set_piece(color, PieceType.ROOK, rook_to)
                move.is_castle = True
                move.castle_rook_from = rook_from
                move.castle_rook_to = rook_to

        # Update en passant target square
        if piece_type == PieceType.PAWN and abs(to_square - from_square) == 16:
            self.en_passant_square = (from_square + to_square) // 2
        else:
            self.en_passant_square = None

        # Update castling rights
        if piece_type == PieceType.KING:
            self.castling_rights &= ~(CR_WK | CR_WQ) if color == Color.WHITE else ~(CR_BK | CR_BQ)
        if piece_type == PieceType.ROOK:
            rook_rights = {0: CR_WQ, 7: CR_WK, 56: CR_BQ, 63: CR_BK}
            self.castling_rights &= ~rook_rights.get(from_square, 0)
        if captured_piece_type == PieceType.ROOK:
            rook_rights = {0: CR_WQ, 7: CR_WK, 56: CR_BQ, 63: CR_BK}
            self.castling_rights &= ~rook_rights.get(to_square, 0)

        # Halfmove clock
        if piece_type == PieceType.PAWN or captured_piece_type is not None:
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        self.move_history.append(move)
        if color == Color.BLACK:
            self.fullmove += 1
        self.turn = color.opponent()
        self.zobrist_key = self._compute_zobrist()

    def unmake_move(self):
        if not self.move_history:
            return
        move = self.move_history.pop()
        color = self.turn.opponent()  # color that made the move
        self.turn = color

        to_square = move.to_square
        from_square = move.from_square

        # Restore piece (undoing promotion reverts to pawn)
        piece_on_dest = self.get_piece_at(to_square)
        assert piece_on_dest is not None
        placed_piece_type = piece_on_dest[1]
        original_piece_type = PieceType.PAWN if move.promotion is not None else placed_piece_type

        self._clear_piece(color, placed_piece_type, to_square)
        self._set_piece(color, original_piece_type, from_square)

        # Restore normal capture
        if move.captured_piece is not None and not move.is_en_passant:
            self._set_piece(move.captured_color, move.captured_piece, to_square)

        # Restore en passant pawn
        if move.is_en_passant:
            ep_square = to_square - 8 if color == Color.WHITE else to_square + 8
            self._set_piece(color.opponent(), PieceType.PAWN, ep_square)

        # Restore castling rook
        if move.is_castle:
            self._clear_piece(color, PieceType.ROOK, move.castle_rook_to)
            self._set_piece(color, PieceType.ROOK, move.castle_rook_from)

        # Restore saved state
        self.en_passant_square = move.prev_en_passant_square
        self.castling_rights = move.prev_castling_rights
        self.halfmove_clock = move.prev_halfmove_clock
        self.zobrist_key = move.prev_zobrist_key
        if color == Color.BLACK:
            self.fullmove -= 1

    # ── Legal moves ─────────────────────────────────────────────────────────

    def _castling_pseudo(self, color: Color) -> U64:
        """Returns destination squares for legal castling moves."""
        occ = self.occupied()
        attacked = self.get_attacks(color.opponent())
        result: U64 = 0

        if color == Color.WHITE:
            if attacked & square_to_bits(Square.E1):
                return 0  # Can't castle out of check
            if (self.castling_rights & CR_WK) and not (occ & 0x60) and not (attacked & 0x60):
                result |= square_to_bits(Square.G1)
            if (self.castling_rights & CR_WQ) and not (occ & 0x0E) and not (attacked & 0x0C):
                result |= square_to_bits(Square.C1)
        else:
            if attacked & square_to_bits(Square.E8):
                return 0
            if (
                (self.castling_rights & CR_BK)
                and not (occ & 0x6000000000000000)
                and not (attacked & 0x6000000000000000)
            ):
                result |= square_to_bits(Square.G8)
            if (
                (self.castling_rights & CR_BQ)
                and not (occ & 0x0E00000000000000)
                and not (attacked & 0x0C00000000000000)
            ):
                result |= square_to_bits(Square.C8)
        return result

    def get_legal_moves(self, square: int) -> U64:
        """Returns bits of legal destination squares for the piece on square."""
        info = self.get_piece_at(square)
        if info is None or info[0] != self.turn:
            return 0
        color, piece_type = info

        pseudo = self._get_pseudo_legal(square, color)
        if piece_type == PieceType.KING:
            pseudo |= self._castling_pseudo(color)

        legal: U64 = 0
        for dest in bits_to_squares(pseudo):
            self.make_move(square, dest)
            if not self.is_in_check(color):
                legal |= square_to_bits(dest)
            self.unmake_move()
        return legal

    def get_all_legal_moves(self) -> list[tuple[int, U64]]:
        """Returns [(square, legal_bits)] for all pieces of the current turn."""
        result = []
        for square in bits_to_squares(self.colors[self.turn]):
            legal = self.get_legal_moves(square)
            if legal:
                result.append((square, legal))
        return result

    # ── Game state ──────────────────────────────────────────────────────────

    def is_checkmate(self) -> bool:
        return self.is_in_check(self.turn) and not self.get_all_legal_moves()

    def is_stalemate(self) -> bool:
        return not self.is_in_check(self.turn) and not self.get_all_legal_moves()

    def needs_promotion(self, from_square: int, to_square: int) -> bool:
        """Returns True when a pawn move would reach the back rank."""
        info = self.get_piece_at(from_square)
        if info is None or info[1] != PieceType.PAWN:
            return False
        rank = self.get_rank_idx(to_square)
        return (info[0] == Color.WHITE and rank == 7) or (info[0] == Color.BLACK and rank == 0)
