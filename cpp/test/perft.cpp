// Perft (performance test): counts leaf nodes of the legal move tree to a given
// depth. Used to validate move generation against the Python engine's counts.
// Run: ./perft  (prints node counts for startpos + standard test positions).
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "board.hpp"

namespace {

const int PROMO_PIECES[4] = {QUEEN, ROOK, BISHOP, KNIGHT};

// Expand legal destinations into concrete moves (promotions become 4 moves).
std::vector<Move> legal_move_list(CBoard &board) {
    std::vector<Move> moves;
    for (auto &entry : board.get_all_legal_moves()) {
        int from = entry.first;
        U64 bits = entry.second;
        while (bits) {
            int to = pop_lsb(bits);
            if (board.needs_promotion(from, to)) {
                for (int promo : PROMO_PIECES) moves.push_back({from, to, promo});
            } else {
                moves.push_back({from, to, NO_PIECE});
            }
        }
    }
    return moves;
}

uint64_t perft(CBoard &board, int depth) {
    if (depth == 0) return 1;
    uint64_t nodes = 0;
    for (const Move &m : legal_move_list(board)) {
        board.make_move(m.from, m.to, m.promotion);
        nodes += perft(board, depth - 1);
        board.unmake_move();
    }
    return nodes;
}

// Run perft for depths 1..N. `expected` holds the known reference node counts
// (Chess Programming Wiki); pass an empty vector when no reference is known.
void run(const std::string &name, const std::string &fen, const std::vector<uint64_t> &expected) {
    std::cout << name << "  (" << fen << ")\n";
    for (size_t i = 0; i < expected.size(); ++i) {
        int d = static_cast<int>(i) + 1;
        CBoard b = CBoard::from_fen(fen);
        uint64_t got = perft(b, d);
        uint64_t ref = expected[i];
        std::cout << "  perft(" << d << ") = " << got << "  (expected " << ref << ") "
                  << (got == ref ? "OK" : "MISMATCH") << "\n";
    }
    std::cout << std::endl;
}

// Variant for a custom position with no known reference numbers.
void run(const std::string &name, const std::string &fen, int max_depth) {
    std::cout << name << "  (" << fen << ")\n";
    for (int d = 1; d <= max_depth; ++d) {
        CBoard b = CBoard::from_fen(fen);
        std::cout << "  perft(" << d << ") = " << perft(b, d) << "  (no reference)\n";
    }
    std::cout << std::endl;
}

}  // namespace

int main(int argc, char **argv) {
    // Optional: ./perft "<fen>" <depth>
    if (argc >= 3) {
        run("custom", argv[1], std::stoi(argv[2]));
        return 0;
    }

    // Standard reference positions (Chess Programming Wiki perft results).
    run("startpos", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        {20, 400, 8902, 197281, 4865609});
    run("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        {48, 2039, 97862, 4085603});
    run("position3", "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", {14, 191, 2812, 43238, 674624});
    run("position4", "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        {6, 264, 9467, 422333});
    return 0;
}
