// Alpha-beta minimax with iterative deepening, transposition table,
// quiescence, MVV-LVA / killer / history move ordering. Port of
// python/engine/search.py. Scores are in pawn units from White's perspective.
#pragma once

#include <chrono>
#include <functional>
#include <memory>
#include <tuple>
#include <vector>

#include "board.hpp"
#include "evaluate.hpp"
#include "tt.hpp"

constexpr int MAX_PLY = 64;
constexpr int MAX_HISTORY = 16384;
constexpr int QS_DEPTH = 8;

// One root move's full-window analysis (for the GUI's MultiPV / density overlays).
struct RootAnalysis {
    Move move;
    double score;       // White's-POV pawns
    long node_count;    // nodes spent in this move's subtree
    std::vector<Move> pv;
};

class Search {
public:
    // info_callback(depth, score, nodes, elapsed_s, pv)
    using InfoCallback =
        std::function<void(int, double, long, double, const std::vector<Move> &)>;

    explicit Search(std::unique_ptr<BaseEvaluate> evaluator = nullptr, int tt_size_mb = 32);

    void new_game();

    // Iterative deepening; returns the best (from, to, promo) for the side to move.
    Move get_best_move(CBoard &board, int depth = 3);

    // Iterative deepening with optional time budget. Returns (best_move, score).
    std::pair<Move, double> search_position(CBoard &board, int max_depth = MAX_PLY,
                                            double time_limit_ms = -1.0,
                                            InfoCallback info_callback = nullptr);

    std::vector<RootAnalysis> analyze(CBoard &board, int depth);

private:
    std::unique_ptr<BaseEvaluate> evaluate_;
    TranspositionTable tt_;
    Move killers_[MAX_PLY][2];
    int history_[2][64][64];
    long nodes_;
    std::chrono::steady_clock::time_point deadline_;
    bool has_deadline_;
    bool stop_;

    void update_history(int color, int from_square, int to_square, int depth);
    void age_history();
    int order_key(CBoard &board, const Move &move, int ply, const Move &tt_move);

    double quiescence(CBoard &board, double alpha, double beta, int qdepth = 0);
    std::pair<double, Move> minimax(CBoard &board, int depth, double alpha = -99999.0,
                                    double beta = 99999.0, int ply = 0);

    Move first_legal_move(CBoard &board);
    std::vector<Move> extract_pv(CBoard &board, int max_len);
    bool time_up();

    // Per-root-move (move, score, subtree_nodes) from the last completed depth.
    std::vector<std::tuple<Move, double, long>> root_info_;
};
