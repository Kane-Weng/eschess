// Zobrist hash tables. Layout mirrors _ZOB_* in python/engine/board.py:
// one key per (color, piece_type, square), one for black-to-move, 16 for
// castling-rights states, 8 for the en-passant file. The actual random values
// differ from Python (own RNG); only internal consistency + TT correctness
// matter, not cross-language key equality.
#pragma once

#include "types.hpp"

namespace zobrist {

extern U64 PIECE[2][6][64];
extern U64 TURN;
extern U64 CASTLE[16];
extern U64 EP[8];

// Fills the tables. Safe to call repeatedly; runs once on first use.
void init();

}  // namespace zobrist
