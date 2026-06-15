// Transposition table keyed by Zobrist hash. Port of
// python/engine/transposition.py, but backed by a fixed-size power-of-two
// array (index = key & mask) instead of a Python dict, with depth-preferred
// replacement.
#pragma once

#include <cstddef>
#include <vector>

#include "types.hpp"

enum class TTFlag { EXACT = 0, LOWER = 1, UPPER = 2 };

struct TTEntry {
    U64 key = 0;
    int depth = 0;
    TTFlag flag = TTFlag::EXACT;
    double score = 0.0;
    Move best_move = NULL_MOVE;
    bool valid = false;
};

class TranspositionTable {
public:
    explicit TranspositionTable(int size_mb = 32);
    const TTEntry *probe(U64 key) const;
    void store(U64 key, int depth, TTFlag flag, double score, Move best_move);
    void clear();

private:
    std::vector<TTEntry> table_;
    std::size_t mask_;
};
