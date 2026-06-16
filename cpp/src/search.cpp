#include "search.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <unordered_set>

namespace {

// Centipawn values for MVV-LVA ordering (matches _CP in search.py).
const int CP[6] = {100, 320, 330, 500, 900, 0};

const int PROMO_PIECES[4] = {QUEEN, ROOK, BISHOP, KNIGHT};

// Expand legal moves into (from, to, promo). With captures_only, keep only
// captures and (queen) promotions. Mirrors _flat_moves in search.py.
std::vector<Move> flat_moves(CBoard &board, bool captures_only = false) {
    U64 occ = board.occupied();
    std::vector<Move> moves;
    for (auto &entry : board.get_all_legal_moves()) {
        int from_square = entry.first;
        U64 bits = entry.second;
        while (bits) {
            int to_square = pop_lsb(bits);
            bool is_capture = (occ & (1ULL << to_square)) != 0;
            bool is_promo = board.needs_promotion(from_square, to_square);
            if (captures_only && !is_capture && !is_promo) continue;
            if (is_promo) {
                if (captures_only) {
                    moves.push_back({from_square, to_square, QUEEN});
                } else {
                    for (int promo : PROMO_PIECES) moves.push_back({from_square, to_square, promo});
                }
            } else {
                moves.push_back({from_square, to_square, NO_PIECE});
            }
        }
    }
    return moves;
}

// Floor division (Python //) for the history gravity term; denominator > 0.
inline int floordiv(long a, int b) {
    long q = a / b;
    if (a % b != 0 && a < 0) q -= 1;
    return static_cast<int>(q);
}

}  // namespace

Search::Search(std::unique_ptr<BaseEvaluate> evaluator, int tt_size_mb)
    : evaluate_(evaluator ? std::move(evaluator)
                          : std::unique_ptr<BaseEvaluate>(new MediumEvaluate())),
      tt_(tt_size_mb),
      nodes_(0),
      has_deadline_(false),
      stop_(false) {
    new_game();
}

void Search::new_game() {
    for (int p = 0; p < MAX_PLY; ++p) killers_[p][0] = killers_[p][1] = NULL_MOVE;
    for (int c = 0; c < 2; ++c)
        for (int f = 0; f < 64; ++f)
            for (int t = 0; t < 64; ++t) history_[c][f][t] = 0;
}

void Search::update_history(int color, int from_square, int to_square, int depth) {
    int bonus = std::min(depth * depth, MAX_HISTORY);
    int clamped = std::max(-MAX_HISTORY, std::min(MAX_HISTORY, bonus));
    int cur = history_[color][from_square][to_square];
    history_[color][from_square][to_square] +=
        clamped - floordiv(static_cast<long>(cur) * std::abs(clamped), MAX_HISTORY);
}

void Search::age_history() {
    for (int c = 0; c < 2; ++c)
        for (int f = 0; f < 64; ++f)
            for (int t = 0; t < 64; ++t) history_[c][f][t] >>= 1;
}

int Search::order_key(CBoard &board, const Move &move, int ply, const Move &tt_move) {
    if (move == tt_move) return 20000;

    if (move.promotion == QUEEN) return 10000;
    if (move.promotion != NO_PIECE) return 9000;

    Piece captured = board.get_piece_at(move.to);
    if (!captured.empty()) {
        Piece aggressor = board.get_piece_at(move.from);
        int agg_val = aggressor.empty() ? 0 : CP[aggressor.type];
        return 5000 + CP[captured.type] * 10 - agg_val;
    }

    if (killers_[ply][0] == move) return 4000;
    if (killers_[ply][1] == move) return 3000;
    return history_[board.turn][move.from][move.to];
}

bool Search::time_up() { return has_deadline_ && std::chrono::steady_clock::now() >= deadline_; }

double Search::quiescence(CBoard &board, double alpha, double beta, int qdepth) {
    nodes_ += 1;
    if (has_deadline_ && (nodes_ & 255) == 0 && time_up()) stop_ = true;
    double stand_pat = evaluate_->evaluate(board);
    if (stop_) return stand_pat;
    bool maximizing = board.turn == WHITE;

    if (maximizing) {
        if (stand_pat >= beta) return stand_pat;
        if (stand_pat > alpha) alpha = stand_pat;
    } else {
        if (stand_pat <= alpha) return stand_pat;
        if (stand_pat < beta) beta = stand_pat;
    }

    if (qdepth >= QS_DEPTH) return stand_pat;

    std::vector<Move> captures = flat_moves(board, true);
    // MVV ordering by captured-piece value (stable, matches Python list.sort).
    std::vector<std::pair<int, Move>> keyed;
    keyed.reserve(captures.size());
    for (const Move &m : captures) {
        Piece cap = board.get_piece_at(m.to);
        keyed.push_back({cap.empty() ? 0 : CP[cap.type], m});
    }
    std::stable_sort(keyed.begin(), keyed.end(),
                     [](const std::pair<int, Move> &a, const std::pair<int, Move> &b) {
                         return a.first > b.first;
                     });

    for (auto &kv : keyed) {
        const Move &move = kv.second;
        board.make_move(move.from, move.to, move.promotion);
        double score = quiescence(board, alpha, beta, qdepth + 1);
        board.unmake_move();

        if (maximizing) {
            if (score > alpha) alpha = score;
            if (alpha >= beta) return alpha;
        } else {
            if (score < beta) beta = score;
            if (beta <= alpha) return beta;
        }
    }
    return maximizing ? alpha : beta;
}

std::pair<double, Move> Search::minimax(CBoard &board, int depth, double alpha, double beta,
                                        int ply) {
    if (stop_) return {0.0, NULL_MOVE};

    nodes_ += 1;
    if (has_deadline_ && (nodes_ & 255) == 0 && time_up()) {
        stop_ = true;
        return {0.0, NULL_MOVE};
    }

    double orig_alpha = alpha;

    U64 key = board.zobrist_key;
    const TTEntry *tt_entry = tt_.probe(key);
    Move tt_move = NULL_MOVE;
    if (tt_entry) {
        tt_move = tt_entry->best_move;
        if (tt_entry->depth >= depth) {
            if (tt_entry->flag == TTFlag::EXACT)
                return {tt_entry->score, tt_entry->best_move};
            else if (tt_entry->flag == TTFlag::LOWER)
                alpha = std::max(alpha, tt_entry->score);
            else if (tt_entry->flag == TTFlag::UPPER)
                beta = std::min(beta, tt_entry->score);
            if (alpha >= beta) return {tt_entry->score, tt_entry->best_move};
        }
    }

    std::vector<Move> legal_moves = flat_moves(board);

    if (legal_moves.empty()) {
        if (board.is_in_check(board.turn))
            return {(board.turn == WHITE) ? (-9000.0 - depth) : (9000.0 + depth), NULL_MOVE};
        return {0.0, NULL_MOVE};  // stalemate
    }

    if (depth == 0) return {quiescence(board, alpha, beta), NULL_MOVE};

    std::vector<std::pair<int, Move>> keyed;
    keyed.reserve(legal_moves.size());
    for (const Move &m : legal_moves) keyed.push_back({order_key(board, m, ply, tt_move), m});
    std::stable_sort(keyed.begin(), keyed.end(),
                     [](const std::pair<int, Move> &a, const std::pair<int, Move> &b) {
                         return a.first > b.first;
                     });

    bool maximizing = board.turn == WHITE;
    bool have_best = false;
    double best_eval = 0.0;
    Move best_move = NULL_MOVE;

    // At the root, record each move's score and the (un-pruned) nodes spent in
    // its subtree for feeding the GUI's MultiPV / density overlays.
    bool record_root = ply == 0;
    std::vector<std::tuple<Move, double, long>> root_info;

    for (auto &kv : keyed) {
        const Move &move = kv.second;
        bool is_quiet = move.promotion == NO_PIECE && board.get_piece_at(move.to).empty();

        long nodes_before = nodes_;
        board.make_move(move.from, move.to, move.promotion);
        auto child = minimax(board, depth - 1, alpha, beta, ply + 1);
        double eval_score = child.first;
        board.unmake_move();

        if (stop_) return {have_best ? best_eval : 0.0, best_move};

        if (record_root) root_info.emplace_back(move, eval_score, nodes_ - nodes_before);

        if (maximizing) {
            if (!have_best || eval_score > best_eval) {
                best_eval = eval_score;
                best_move = move;
                have_best = true;
            }
            alpha = std::max(alpha, best_eval);
        } else {
            if (!have_best || eval_score < best_eval) {
                best_eval = eval_score;
                best_move = move;
                have_best = true;
            }
            beta = std::min(beta, best_eval);
        }

        if (beta <= alpha) {
            if (is_quiet && ply < MAX_PLY) {
                if (!(killers_[ply][0] == move)) {
                    killers_[ply][1] = killers_[ply][0];
                    killers_[ply][0] = move;
                }
                update_history(board.turn, move.from, move.to, depth);
            }
            break;
        }
    }

    if (record_root) root_info_ = std::move(root_info);

    TTFlag flag = TTFlag::EXACT;
    if (best_eval <= orig_alpha)
        flag = TTFlag::UPPER;
    else if (best_eval >= beta)
        flag = TTFlag::LOWER;
    tt_.store(key, depth, flag, best_eval, best_move);

    return {best_eval, best_move};
}

Move Search::first_legal_move(CBoard &board) {
    for (auto &entry : board.get_all_legal_moves()) {
        int from_square = entry.first;
        U64 bits = entry.second;
        if (bits) {
            int to_square = lsb_index(bits);
            int promo = board.needs_promotion(from_square, to_square) ? QUEEN : NO_PIECE;
            return {from_square, to_square, promo};
        }
    }
    return NULL_MOVE;
}

std::vector<Move> Search::extract_pv(CBoard &board, int max_len) {
    std::vector<Move> pv;
    std::unordered_set<U64> seen;
    int applied = 0;
    for (int i = 0; i < max_len; ++i) {
        if (seen.count(board.zobrist_key)) break;  // repetition guard
        seen.insert(board.zobrist_key);
        const TTEntry *entry = tt_.probe(board.zobrist_key);
        if (!entry || entry->best_move == NULL_MOVE) break;
        Move m = entry->best_move;
        if (!(board.get_legal_moves(m.from) & (1ULL << m.to))) break;  // stale TT move
        pv.push_back(m);
        board.make_move(m.from, m.to, m.promotion);
        applied += 1;
    }
    for (int i = 0; i < applied; ++i) board.unmake_move();
    return pv;
}

Move Search::get_best_move(CBoard &board, int depth) { return search_position(board, depth).first; }

std::pair<Move, double> Search::search_position(CBoard &board, int max_depth, double time_limit_ms,
                                                InfoCallback info_callback) {
    for (int p = 0; p < MAX_PLY; ++p) killers_[p][0] = killers_[p][1] = NULL_MOVE;
    age_history();
    nodes_ = 0;
    stop_ = false;

    auto start = std::chrono::steady_clock::now();
    bool has_budget = time_limit_ms > 0.0;
    double budget_s = has_budget ? time_limit_ms / 1000.0 : 0.0;
    has_deadline_ = has_budget;
    if (has_budget)
        deadline_ = start + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                                std::chrono::duration<double>(budget_s));

    Move best_move = first_legal_move(board);
    double best_score = 0.0;
    bool completed_any = false;

    for (int d = 1; d <= std::max(1, max_depth); ++d) {
        auto res = minimax(board, d);
        double score = res.first;
        Move move = res.second;
        if (stop_) {
            if (!completed_any && move != NULL_MOVE) best_move = move;
            break;
        }
        if (move != NULL_MOVE) {
            best_move = move;
            best_score = score;
            completed_any = true;
        }
        if (info_callback) {
            double elapsed =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            info_callback(d, best_score, nodes_, elapsed, extract_pv(board, d));
        }
        if (std::abs(best_score) > 8000.0) break;
        if (has_budget) {
            double elapsed =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            if (elapsed >= budget_s * 0.5) break;
        }
    }

    return {best_move, best_score};
}

std::vector<RootAnalysis> Search::analyze(CBoard &board, int depth) {
    // Run the normal (alpha-beta pruned) search; report per root move. Node count
    // reflects how much of each move's subtree survived pruning (density signal).
    search_position(board, depth);

    bool maximizing = board.turn == WHITE;
    auto ranked = root_info_;
    std::stable_sort(ranked.begin(), ranked.end(), [maximizing](const auto &a, const auto &b) {
        return maximizing ? std::get<1>(a) > std::get<1>(b) : std::get<1>(a) < std::get<1>(b);
    });

    std::vector<RootAnalysis> results;
    for (const auto &r : ranked) {
        Move move = std::get<0>(r);
        board.make_move(move.from, move.to, move.promotion);
        std::vector<Move> pv = extract_pv(board, depth);  // response chain from TT
        board.unmake_move();
        pv.insert(pv.begin(), move);
        results.push_back({move, std::get<1>(r), std::get<2>(r), pv});
    }
    return results;
}
