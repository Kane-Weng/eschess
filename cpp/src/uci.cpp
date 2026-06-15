// UCI protocol wrapper for the C++ Eschess engine. Port of python/uci.py.
// Supported: uci, isready, ucinewgame, setoption name Hash, position
// [startpos|fen] moves ..., go [depth|movetime|wtime/btime/winc/binc/movestogo|
// infinite], stop, quit.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#include <memory>

#include "board.hpp"
#include "evaluate.hpp"
#include "search.hpp"

namespace {

const char *ENGINE_NAME = "Eschess-cpp";
const char *ENGINE_AUTHOR = "Kane Weng";

constexpr double MATE_THRESHOLD = 8000.0;
constexpr double TIME_SAFETY = 0.85;
constexpr double MOVE_OVERHEAD_MS = 20.0;

double apply_margin(double budget_ms) {
    return std::max(10.0, budget_ms * TIME_SAFETY - MOVE_OVERHEAD_MS);
}

std::string square_name(int square) {
    std::string s;
    s += static_cast<char>('a' + file_of(square));
    s += static_cast<char>('1' + rank_of(square));
    return s;
}

int name_to_square(const std::string &name) {
    int file_idx = name[0] - 'a';
    int rank_idx = name[1] - '1';
    return 8 * rank_idx + file_idx;
}

char promo_to_char(int promotion) {
    switch (promotion) {
        case KNIGHT: return 'n';
        case BISHOP: return 'b';
        case ROOK: return 'r';
        case QUEEN: return 'q';
    }
    return '?';
}

int char_to_promo(char c) {
    switch (c) {
        case 'n': return KNIGHT;
        case 'b': return BISHOP;
        case 'r': return ROOK;
        case 'q': return QUEEN;
    }
    return NO_PIECE;
}

std::string move_to_uci(const Move &move) {
    std::string text = square_name(move.from) + square_name(move.to);
    if (move.promotion != NO_PIECE) text += promo_to_char(move.promotion);
    return text;
}

Move uci_to_move(const std::string &text) {
    int from_square = name_to_square(text.substr(0, 2));
    int to_square = name_to_square(text.substr(2, 2));
    int promotion = (text.size() > 4) ? char_to_promo(text[4]) : NO_PIECE;
    return {from_square, to_square, promotion};
}

std::string score_to_uci(double score, bool white_to_move, int pv_len) {
    double stm = white_to_move ? score : -score;
    if (std::abs(stm) >= MATE_THRESHOLD) {
        int moves = pv_len ? (pv_len + 1) / 2 : 1;
        return "mate " + std::to_string(stm > 0 ? moves : -moves);
    }
    return "cp " + std::to_string(static_cast<long>(std::lround(stm * 100)));
}

class UCIEngine {
public:
    UCIEngine() : board_(CBoard::from_fen(STARTPOS_FEN)), hash_mb_(32) {}

    void run() {
        std::string line;
        while (std::getline(std::cin, line)) {
            // trim trailing whitespace/CR
            while (!line.empty() && (line.back() == '\r' || line.back() == ' ')) line.pop_back();
            if (line.empty()) continue;
            std::istringstream iss(line);
            std::string cmd;
            iss >> cmd;
            std::string rest;
            std::getline(iss, rest);
            if (!rest.empty() && rest[0] == ' ') rest.erase(0, 1);

            if (cmd == "uci") {
                cmd_uci();
            } else if (cmd == "isready") {
                std::cout << "readyok" << std::endl;
            } else if (cmd == "ucinewgame") {
                search_.new_game();
                board_ = CBoard::from_fen(STARTPOS_FEN);
            } else if (cmd == "setoption") {
                cmd_setoption(rest);
            } else if (cmd == "position") {
                cmd_position(rest);
            } else if (cmd == "go") {
                cmd_go(rest);
            } else if (cmd == "stop" || cmd == "ponderhit") {
                // synchronous search: nothing in flight
            } else if (cmd == "quit") {
                break;
            }
        }
    }

private:
    CBoard board_;
    Search search_;
    int hash_mb_;
    std::string eval_level_ = "medium";
    int multipv_ = 1;

    // Build the evaluator named by eval_level_ (matches python/engine/evaluate.py).
    std::unique_ptr<BaseEvaluate> make_eval() const {
        if (eval_level_ == "simple") return std::make_unique<SimpleEvaluate>();
        if (eval_level_ == "complex") return std::make_unique<ComplexEvaluate>();
        return std::make_unique<MediumEvaluate>();
    }

    void cmd_uci() {
        std::cout << "id name " << ENGINE_NAME << "\n";
        std::cout << "id author " << ENGINE_AUTHOR << "\n";
        std::cout << "option name Hash type spin default 32 min 1 max 1024\n";
        std::cout << "option name Eval type combo default medium var simple var medium var complex\n";
        std::cout << "option name MultiPV type spin default 1 min 1 max 5\n";
        std::cout << "uciok" << std::endl;
    }

    void cmd_setoption(const std::string &rest) {
        std::istringstream iss(rest);
        std::vector<std::string> tokens;
        std::string t;
        while (iss >> t) tokens.push_back(t);
        if (tokens.size() >= 4 && tokens[0] == "name" && tokens[tokens.size() - 2] == "value") {
            std::string name = tokens[1];
            std::string value = tokens.back();
            std::transform(name.begin(), name.end(), name.begin(), ::tolower);
            std::transform(value.begin(), value.end(), value.begin(), ::tolower);
            if (name == "hash") {
                hash_mb_ = std::max(1, std::stoi(value));
                search_ = Search(make_eval(), hash_mb_);
            } else if (name == "eval") {
                eval_level_ = value;
                search_ = Search(make_eval(), hash_mb_);
            } else if (name == "multipv") {
                multipv_ = std::max(1, std::stoi(value));
            }
        }
    }

    void cmd_position(const std::string &rest) {
        std::istringstream iss(rest);
        std::vector<std::string> tokens;
        std::string t;
        while (iss >> t) tokens.push_back(t);
        if (tokens.empty()) return;

        size_t idx;
        if (tokens[0] == "startpos") {
            board_ = CBoard::from_fen(STARTPOS_FEN);
            idx = 1;
        } else if (tokens[0] == "fen") {
            std::string fen;
            for (size_t i = 1; i < 7 && i < tokens.size(); ++i) {
                if (i > 1) fen += " ";
                fen += tokens[i];
            }
            board_ = CBoard::from_fen(fen);
            idx = 7;
        } else {
            return;
        }

        if (idx < tokens.size() && tokens[idx] == "moves") {
            for (size_t i = idx + 1; i < tokens.size(); ++i) {
                Move m = uci_to_move(tokens[i]);
                board_.make_move(m.from, m.to, m.promotion);
            }
        }
    }

    std::unordered_map<std::string, long> parse_go(const std::string &rest, bool &infinite) {
        std::istringstream iss(rest);
        std::vector<std::string> tokens;
        std::string t;
        while (iss >> t) tokens.push_back(t);
        std::unordered_map<std::string, long> params;
        infinite = false;
        size_t i = 0;
        while (i < tokens.size()) {
            const std::string &key = tokens[i];
            if (key == "depth" || key == "movetime" || key == "wtime" || key == "btime" ||
                key == "winc" || key == "binc" || key == "movestogo" || key == "nodes") {
                if (i + 1 < tokens.size()) params[key] = std::stol(tokens[i + 1]);
                i += 2;
            } else if (key == "infinite") {
                infinite = true;
                i += 1;
            } else {
                i += 1;
            }
        }
        return params;
    }

    std::pair<int, double> plan_time(const std::unordered_map<std::string, long> &params,
                                     bool infinite) {
        int max_depth = params.count("depth") ? static_cast<int>(params.at("depth")) : 64;

        if (params.count("movetime"))
            return {max_depth, apply_margin(static_cast<double>(params.at("movetime")))};

        if (params.count("wtime") || params.count("btime")) {
            bool white = board_.turn == WHITE;
            long remaining = params.count(white ? "wtime" : "btime")
                                 ? params.at(white ? "wtime" : "btime")
                                 : 1000;
            long increment =
                params.count(white ? "winc" : "binc") ? params.at(white ? "winc" : "binc") : 0;
            long movestogo = params.count("movestogo") ? params.at("movestogo") : 30;
            double budget = static_cast<double>(remaining) / std::max(1L, movestogo) +
                            increment * 0.8;
            return {max_depth, apply_margin(std::min(budget, remaining * 0.9))};
        }

        if (params.count("depth")) return {max_depth, -1.0};  // pure depth search

        if (infinite) return {max_depth, 10000.0};

        return {max_depth, apply_margin(1000.0)};  // bare "go"
    }

    void cmd_go(const std::string &rest) {
        bool infinite = false;
        auto params = parse_go(rest, infinite);
        auto plan = plan_time(params, infinite);
        int max_depth = plan.first;
        double time_limit_ms = plan.second;

        bool white = board_.turn == WHITE;

        if (multipv_ > 1) {
            go_multipv(max_depth < MAX_PLY ? max_depth : 4, white);
            return;
        }

        auto emit_info = [white](int depth, double score, long nodes, double elapsed,
                                 const std::vector<Move> &pv) {
            long nps = elapsed > 0 ? static_cast<long>(nodes / elapsed) : 0;
            std::string pv_text;
            for (size_t i = 0; i < pv.size(); ++i) {
                if (i) pv_text += " ";
                pv_text += move_to_uci(pv[i]);
            }
            std::cout << "info depth " << depth << " score "
                      << score_to_uci(score, white, static_cast<int>(pv.size())) << " nodes "
                      << nodes << " nps " << nps << " time "
                      << static_cast<long>(elapsed * 1000) << " pv " << pv_text << std::endl;
        };

        auto result = search_.search_position(board_, max_depth, time_limit_ms, emit_info);
        Move best_move = result.first;
        std::cout << "bestmove " << (best_move != NULL_MOVE ? move_to_uci(best_move) : "0000")
                  << std::endl;
    }

    void go_multipv(int depth, bool white) {
        auto results = search_.analyze(board_, depth);
        if (results.empty()) {
            std::cout << "bestmove 0000" << std::endl;
            return;
        }
        long total_nodes = 0;
        for (const auto &r : results) total_nodes += r.node_count;

        int k = std::min<int>(multipv_, static_cast<int>(results.size()));
        for (int i = 0; i < k; ++i) {
            const auto &r = results[i];
            std::string pv_text;
            for (size_t j = 0; j < r.pv.size(); ++j) {
                if (j) pv_text += " ";
                pv_text += move_to_uci(r.pv[j]);
            }
            std::cout << "info multipv " << (i + 1) << " depth " << depth << " score "
                      << score_to_uci(r.score, white, static_cast<int>(r.pv.size()))
                      << " nodes " << total_nodes << " pv " << pv_text << std::endl;
        }
        std::string effort = "info string effort";
        for (const auto &r : results)
            effort += " " + move_to_uci(r.move) + ":" + std::to_string(r.node_count);
        std::cout << effort << std::endl;
        std::cout << "bestmove " << move_to_uci(results[0].move) << std::endl;
    }
};

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    UCIEngine().run();
    return 0;
}
