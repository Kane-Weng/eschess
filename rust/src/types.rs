//! Shared types, constants and bit helpers. Mirrors cpp/src/types.hpp and the
//! enums/constants in python/engine/board.py (LERF mapping, Color/PieceType
//! ordering, castle bits).

pub type U64 = u64;

// Enums, sentinels, castle bits and bitboard masks come from the shared schema
// (schema/engine.toml -> generated.rs); re-exported here so that the crate's
// pervasive `use crate::types::*` keeps resolving these names.
pub use crate::generated::{
    BISHOP, BLACK, CR_BK, CR_BQ, CR_WK, CR_WQ, FILE_A, FILE_AB, FILE_GH, FILE_H, FULL_BOARD, KING,
    KNIGHT, NOT_FILE_A, NOT_FILE_AB, NOT_FILE_GH, NOT_FILE_H, NO_PIECE, PAWN, QUEEN, RANK_1,
    RANK_2, RANK_7, RANK_8, ROOK, WHITE,
};

// `opponent` is behavior (not data), so it stays here.
#[inline]
pub fn opponent(c: usize) -> usize {
    1 - c
}

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
