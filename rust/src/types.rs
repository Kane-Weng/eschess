//! Shared types, constants and bit helpers. Mirrors cpp/src/types.hpp and the
//! enums/constants in python/engine/board.py (LERF mapping, Color/PieceType
//! ordering, castle bits).

pub type U64 = u64;

pub const WHITE: usize = 0;
pub const BLACK: usize = 1;

#[inline]
pub fn opponent(c: usize) -> usize {
    1 - c
}

// Piece types: PAWN..KING == 0..5. NO_PIECE uses a sentinel index.
pub const PAWN: usize = 0;
pub const KNIGHT: usize = 1;
pub const BISHOP: usize = 2;
pub const ROOK: usize = 3;
pub const QUEEN: usize = 4;
pub const KING: usize = 5;
pub const NO_PIECE: i32 = -1;

// Castling-rights bitmask (matches CR_* in board.py).
pub const CR_WK: i32 = 0b1000;
pub const CR_WQ: i32 = 0b0100;
pub const CR_BK: i32 = 0b0010;
pub const CR_BQ: i32 = 0b0001;

pub const FULL_BOARD: U64 = 0xFFFF_FFFF_FFFF_FFFF;

pub const FILE_A: U64 = 0x0101_0101_0101_0101;
pub const FILE_H: U64 = 0x8080_8080_8080_8080;
pub const FILE_AB: U64 = FILE_A | (FILE_A << 1);
pub const FILE_GH: U64 = FILE_H | (FILE_H >> 1);

pub const NOT_FILE_A: U64 = FULL_BOARD ^ FILE_A;
pub const NOT_FILE_H: U64 = FULL_BOARD ^ FILE_H;
pub const NOT_FILE_AB: U64 = FULL_BOARD ^ FILE_AB;
pub const NOT_FILE_GH: U64 = FULL_BOARD ^ FILE_GH;

pub const RANK_1: U64 = 0x0000_0000_0000_00FF;
pub const RANK_2: U64 = 0x0000_0000_0000_FF00;
pub const RANK_7: U64 = 0x00FF_0000_0000_0000;
pub const RANK_8: U64 = 0xFF00_0000_0000_0000;

#[inline]
pub fn square_to_bits(square: i32) -> U64 {
    1u64 << square
}
#[inline]
pub fn file_of(square: i32) -> i32 {
    square & 7
}
#[inline]
pub fn rank_of(square: i32) -> i32 {
    square >> 3
}
#[inline]
pub fn popcount(b: U64) -> i32 {
    b.count_ones() as i32
}
#[inline]
pub fn lsb_index(b: U64) -> i32 {
    b.trailing_zeros() as i32
}
/// Pop the least-significant bit, returning its square index.
#[inline]
pub fn pop_lsb(b: &mut U64) -> i32 {
    let idx = lsb_index(*b);
    *b &= *b - 1;
    idx
}

// ── Wrap-safe directional shifts (compass rose from board.py) ───────────────
#[inline]
pub fn shift_n(b: U64) -> U64 {
    (b << 8) & FULL_BOARD
}
#[inline]
pub fn shift_s(b: U64) -> U64 {
    b >> 8
}
#[inline]
pub fn shift_e(b: U64) -> U64 {
    (b & NOT_FILE_H) << 1
}
#[inline]
pub fn shift_w(b: U64) -> U64 {
    (b & NOT_FILE_A) >> 1
}
#[inline]
pub fn shift_ne(b: U64) -> U64 {
    ((b & NOT_FILE_H) << 9) & FULL_BOARD
}
#[inline]
pub fn shift_nw(b: U64) -> U64 {
    ((b & NOT_FILE_A) << 7) & FULL_BOARD
}
#[inline]
pub fn shift_se(b: U64) -> U64 {
    (b & NOT_FILE_H) >> 7
}
#[inline]
pub fn shift_sw(b: U64) -> U64 {
    (b & NOT_FILE_A) >> 9
}

#[inline]
pub fn knight_attacks(b: U64) -> U64 {
    let l1 = (b >> 1) & NOT_FILE_H;
    let l2 = (b >> 2) & NOT_FILE_GH;
    let r1 = (b << 1) & NOT_FILE_A;
    let r2 = (b << 2) & NOT_FILE_AB;
    let h1 = l1 | r1;
    let h2 = l2 | r2;
    ((h1 << 16) | (h1 >> 16) | (h2 << 8) | (h2 >> 8)) & FULL_BOARD
}

/// A search move: (from, to, promotion). promotion == NO_PIECE for none.
/// Mirrors the `Move = tuple[int,int,PieceType|None]` alias in search.py.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Move {
    pub from: i32,
    pub to: i32,
    pub promotion: i32,
}

pub const NULL_MOVE: Move = Move {
    from: -1,
    to: -1,
    promotion: NO_PIECE,
};
