#include "tt.hpp"

#include <algorithm>
#include <cstddef>

TranspositionTable::TranspositionTable(int size_mb) {
    std::size_t bytes = static_cast<std::size_t>(size_mb) * 1024 * 1024;
    std::size_t want = bytes / sizeof(TTEntry);
    if (want < 1) want = 1;
    // Round down to a power of two so we can index with a bitmask.
    std::size_t pow2 = 1;
    while (pow2 * 2 <= want) pow2 *= 2;
    table_.assign(pow2, TTEntry{});
    mask_ = pow2 - 1;
}

const TTEntry *TranspositionTable::probe(U64 key) const {
    const TTEntry &e = table_[key & mask_];
    return (e.valid && e.key == key) ? &e : nullptr;
}

void TranspositionTable::store(U64 key, int depth, TTFlag flag, double score, Move best_move) {
    TTEntry &e = table_[key & mask_];
    // Depth-preferred replacement: overwrite empty slots, the same position, or
    // a shallower stored search.
    if (!e.valid || e.key == key || depth >= e.depth) {
        e.key = key;
        e.depth = depth;
        e.flag = flag;
        e.score = score;
        e.best_move = best_move;
        e.valid = true;
    }
}

void TranspositionTable::clear() {
    std::fill(table_.begin(), table_.end(), TTEntry{});
}
