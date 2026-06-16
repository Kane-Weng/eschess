// Shared types, enums and bit helpers. Mirrors the enums/constants in
// python/engine/board.py (LERF mapping, Color/PieceType ordering, castle bits).
#pragma once

#include <cstdint>

using U64 = uint64_t;

// Color & PieceType
enum Color { WHITE = 0, BLACK = 1 };
inline Color opponent(Color c) { return static_cast<Color>(1 - c); }
enum PieceType { PAWN = 0, KNIGHT = 1, BISHOP = 2, ROOK = 3, QUEEN = 4, KING = 5, NO_PIECE = -1 };

// Castling-rights bitmask
constexpr int CR_WK = 0b1000;
constexpr int CR_WQ = 0b0100;
constexpr int CR_BK = 0b0010;
constexpr int CR_BQ = 0b0001;

// Bitboard constants
constexpr U64 FULL_BOARD = 0xFFFFFFFFFFFFFFFFULL;

constexpr U64 FILE_A = 0x0101010101010101ULL;
constexpr U64 FILE_H = 0x8080808080808080ULL;
constexpr U64 FILE_AB = FILE_A | (FILE_A << 1);
constexpr U64 FILE_GH = FILE_H | (FILE_H >> 1);

constexpr U64 NOT_FILE_A = FULL_BOARD ^ FILE_A;
constexpr U64 NOT_FILE_H = FULL_BOARD ^ FILE_H;
constexpr U64 NOT_FILE_AB = FULL_BOARD ^ FILE_AB;
constexpr U64 NOT_FILE_GH = FULL_BOARD ^ FILE_GH;

constexpr U64 RANK_1 = 0x00000000000000FFULL;
constexpr U64 RANK_2 = 0x000000000000FF00ULL;
constexpr U64 RANK_7 = 0x00FF000000000000ULL;
constexpr U64 RANK_8 = 0xFF00000000000000ULL;

// LERF square index helpers
inline U64 square_to_bits(int square) { return 1ULL << square; }

inline int file_of(int square) { return square & 7; }   // square % 8
inline int rank_of(int square) { return square >> 3; }  // square // 8

// Counts the number of set bits (1s)
inline int popcount(U64 b) { return __builtin_popcountll(b); }

// Index of the least-significant set bit (square 0..63). Undefined for 0.
inline int lsb_index(U64 b) { return __builtin_ctzll(b); }

// Pop the LSB, returning its square index.
inline int pop_lsb(U64 &b) {
    int idx = lsb_index(b);
    b &= b - 1;
    return idx;
}

// ── Wrap-safe directional shifts (compass rose from board.py) ───────────────
inline U64 shift_n(U64 b) { return (b << 8) & FULL_BOARD; }
inline U64 shift_s(U64 b) { return b >> 8; }
inline U64 shift_e(U64 b) { return (b & NOT_FILE_H) << 1; }
inline U64 shift_w(U64 b) { return (b & NOT_FILE_A) >> 1; }
inline U64 shift_ne(U64 b) { return ((b & NOT_FILE_H) << 9) & FULL_BOARD; }
inline U64 shift_nw(U64 b) { return ((b & NOT_FILE_A) << 7) & FULL_BOARD; }
inline U64 shift_se(U64 b) { return (b & NOT_FILE_H) >> 7; }
inline U64 shift_sw(U64 b) { return (b & NOT_FILE_A) >> 9; }

inline U64 knight_attacks(U64 b) {
    U64 l1 = (b >> 1) & NOT_FILE_H;
    U64 l2 = (b >> 2) & NOT_FILE_GH;
    U64 r1 = (b << 1) & NOT_FILE_A;
    U64 r2 = (b << 2) & NOT_FILE_AB;
    U64 h1 = l1 | r1;
    U64 h2 = l2 | r2;
    return ((h1 << 16) | (h1 >> 16) | (h2 << 8) | (h2 >> 8)) & FULL_BOARD;
}

// A search move: (from, to, promotion). promotion == NO_PIECE for none.
// Mirrors the 'Move = tuple[int,int,PieceType|None]' alias in search.py.
struct Move {
    int from;
    int to;
    int promotion;  // PieceType or NO_PIECE

    bool operator==(const Move &o) const {
        return from == o.from && to == o.to && promotion == o.promotion;
    }
    bool operator!=(const Move &o) const { return !(*this == o); }
};

constexpr Move NULL_MOVE{-1, -1, NO_PIECE};
