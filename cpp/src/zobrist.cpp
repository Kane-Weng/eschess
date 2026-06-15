#include "zobrist.hpp"

#include <random>

namespace zobrist {

U64 PIECE[2][6][64];
U64 TURN;
U64 CASTLE[16];
U64 EP[8];

void init() {
    static bool done = false;
    if (done) return;
    done = true;

    std::mt19937_64 rng(0xCAFEBABEULL);  // fixed seed → reproducible keys
    for (int c = 0; c < 2; ++c)
        for (int p = 0; p < 6; ++p)
            for (int s = 0; s < 64; ++s) PIECE[c][p][s] = rng();
    TURN = rng();
    for (int i = 0; i < 16; ++i) CASTLE[i] = rng();
    for (int i = 0; i < 8; ++i) EP[i] = rng();
}

}  // namespace zobrist
