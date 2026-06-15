#include "board.hpp"

#include <cassert>
#include <cctype>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

#include "zobrist.hpp"

const char *STARTPOS_FEN =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

static const char PIECE_TO_FEN[6] = {'p', 'n', 'b', 'r', 'q', 'k'};

static int fen_to_piece(char c) {
    switch (std::tolower(c)) {
        case 'p': return PAWN;
        case 'n': return KNIGHT;
        case 'b': return BISHOP;
        case 'r': return ROOK;
        case 'q': return QUEEN;
        case 'k': return KING;
    }
    return NO_PIECE;
}

static std::string square_name(int square) {
    std::string s;
    s += static_cast<char>('a' + file_of(square));
    s += static_cast<char>('1' + rank_of(square));
    return s;
}

static int name_to_square(const std::string &name) {
    int file_idx = name[0] - 'a';
    int rank_idx = name[1] - '1';
    return 8 * rank_idx + file_idx;
}

CBoard::CBoard() {
    zobrist::init();
    colors[WHITE] = colors[BLACK] = 0;
    for (int i = 0; i < 6; ++i) pieces[i] = 0;
    set_pieces();
    turn = WHITE;
    en_passant_square = -1;
    castling_rights = 0b1111;
    halfmove_clock = 0;
    fullmove = 1;
    game_over = false;
    winner = -1;
    zobrist_key = compute_zobrist();
}

void CBoard::set_pieces() {
    colors[WHITE] = 0x000000000000FFFFULL;
    colors[BLACK] = 0xFFFF000000000000ULL;
    pieces[PAWN]   = 0x00FF00000000FF00ULL;
    pieces[KNIGHT] = 0x4200000000000042ULL;
    pieces[BISHOP] = 0x2400000000000024ULL;
    pieces[ROOK]   = 0x8100000000000081ULL;
    pieces[QUEEN]  = 0x0800000000000008ULL;
    pieces[KING]   = 0x1000000000000010ULL;
}

CBoard CBoard::from_fen(const std::string &fen) {
    CBoard board;
    board.set_fen(fen);
    return board;
}

void CBoard::set_fen(const std::string &fen) {
    std::istringstream iss(fen);
    std::string placement, side, castling, ep;
    iss >> placement >> side >> castling >> ep;
    if (placement.empty() || side.empty() || castling.empty() || ep.empty())
        throw std::runtime_error("Invalid FEN (need >=4 fields): " + fen);

    colors[WHITE] = colors[BLACK] = 0;
    for (int i = 0; i < 6; ++i) pieces[i] = 0;

    int rank_idx = 7, file_idx = 0;
    for (char ch : placement) {
        if (ch == '/') {
            rank_idx -= 1;
            file_idx = 0;
        } else if (std::isdigit(static_cast<unsigned char>(ch))) {
            file_idx += ch - '0';
        } else {
            int color = std::isupper(static_cast<unsigned char>(ch)) ? WHITE : BLACK;
            set_piece(color, fen_to_piece(ch), 8 * rank_idx + file_idx);
            file_idx += 1;
        }
    }

    turn = (side == "w") ? WHITE : BLACK;
    int cr = 0;
    if (castling.find('K') != std::string::npos) cr |= CR_WK;
    if (castling.find('Q') != std::string::npos) cr |= CR_WQ;
    if (castling.find('k') != std::string::npos) cr |= CR_BK;
    if (castling.find('q') != std::string::npos) cr |= CR_BQ;
    castling_rights = cr;
    en_passant_square = (ep == "-") ? -1 : name_to_square(ep);

    int hmc = 0, fm = 1;
    if (iss >> hmc) { /* halfmove */ }
    if (iss >> fm) { /* fullmove */ }
    halfmove_clock = hmc;
    fullmove = fm;

    move_history.clear();
    game_over = false;
    winner = -1;
    zobrist_key = compute_zobrist();
}

std::string CBoard::to_fen() const {
    std::string rows;
    for (int rank_idx = 7; rank_idx >= 0; --rank_idx) {
        std::string row;
        int empty = 0;
        for (int file_idx = 0; file_idx < 8; ++file_idx) {
            Piece info = get_piece_at(8 * rank_idx + file_idx);
            if (info.empty()) {
                empty += 1;
                continue;
            }
            if (empty) {
                row += std::to_string(empty);
                empty = 0;
            }
            char ch = PIECE_TO_FEN[info.type];
            row += (info.color == WHITE) ? static_cast<char>(std::toupper(ch)) : ch;
        }
        if (empty) row += std::to_string(empty);
        if (rank_idx != 7) rows += '/';
        rows += row;
    }

    std::string side = (turn == WHITE) ? "w" : "b";
    std::string cr;
    if (castling_rights & CR_WK) cr += 'K';
    if (castling_rights & CR_WQ) cr += 'Q';
    if (castling_rights & CR_BK) cr += 'k';
    if (castling_rights & CR_BQ) cr += 'q';
    if (cr.empty()) cr = "-";
    std::string ep = (en_passant_square < 0) ? "-" : square_name(en_passant_square);

    return rows + " " + side + " " + cr + " " + ep + " " +
           std::to_string(halfmove_clock) + " " + std::to_string(fullmove);
}

U64 CBoard::compute_zobrist() const {
    U64 key = 0;
    for (int color = 0; color < 2; ++color)
        for (int pt = 0; pt < 6; ++pt) {
            U64 b = get_specific_pieces(color, pt);
            while (b) key ^= zobrist::PIECE[color][pt][pop_lsb(b)];
        }
    if (turn == BLACK) key ^= zobrist::TURN;
    key ^= zobrist::CASTLE[castling_rights & 0xF];
    if (en_passant_square >= 0) key ^= zobrist::EP[en_passant_square & 7];
    return key;
}

Piece CBoard::get_piece_at(int square) const {
    U64 bits = square_to_bits(square);
    for (int color = 0; color < 2; ++color) {
        if (colors[color] & bits) {
            for (int pt = 0; pt < 6; ++pt)
                if (pieces[pt] & bits) return {color, pt};
        }
    }
    return {-1, NO_PIECE};
}

int CBoard::king_square(int color) const {
    return lsb_index(get_specific_pieces(color, KING));
}

// ── Sliding rays ────────────────────────────────────────────────────────────

U64 CBoard::ray(int square, int delta, U64 edge_mask, U64 occ, U64 friendly) const {
    U64 result = 0;
    int cur = square;
    while (true) {
        if (square_to_bits(cur) & edge_mask) break;
        cur += delta;
        if (cur < 0 || cur > 63) break;
        U64 bits = square_to_bits(cur);
        if (bits & friendly) break;
        result |= bits;
        if (bits & occ) break;
    }
    return result;
}

U64 CBoard::bishop_attacks(int square, U64 occ, U64 friendly) const {
    U64 result = ray(square, 9, FILE_H | RANK_8, occ, friendly);
    result |= ray(square, 7, FILE_A | RANK_8, occ, friendly);
    result |= ray(square, -7, FILE_H | RANK_1, occ, friendly);
    result |= ray(square, -9, FILE_A | RANK_1, occ, friendly);
    return result;
}

U64 CBoard::rook_attacks(int square, U64 occ, U64 friendly) const {
    U64 result = ray(square, 8, RANK_8, occ, friendly);
    result |= ray(square, -8, RANK_1, occ, friendly);
    result |= ray(square, 1, FILE_H, occ, friendly);
    result |= ray(square, -1, FILE_A, occ, friendly);
    return result;
}

// ── Pseudo-legal generators ─────────────────────────────────────────────────

U64 CBoard::pawn_pseudo(int square, int color) const {
    U64 occ = occupied();
    U64 enemy = colors[opponent(static_cast<Color>(color))];
    U64 bits = square_to_bits(square);
    U64 result = 0;

    if (color == WHITE) {
        U64 push1 = shift_n(bits) & ~occ;
        result |= push1;
        if (bits & RANK_2) result |= shift_n(push1) & ~occ;
        result |= shift_nw(bits) & enemy;
        result |= shift_ne(bits) & enemy;
        if (en_passant_square >= 0) {
            U64 ep_bits = square_to_bits(en_passant_square);
            result |= (shift_nw(bits) | shift_ne(bits)) & ep_bits;
        }
    } else {
        U64 push1 = shift_s(bits) & ~occ;
        result |= push1;
        if (bits & RANK_7) result |= shift_s(push1) & ~occ;
        result |= shift_sw(bits) & enemy;
        result |= shift_se(bits) & enemy;
        if (en_passant_square >= 0) {
            U64 ep_bits = square_to_bits(en_passant_square);
            result |= (shift_sw(bits) | shift_se(bits)) & ep_bits;
        }
    }
    return result;
}

U64 CBoard::knight_pseudo(int square, int color) const {
    return knight_attacks(square_to_bits(square)) & ~colors[color];
}

U64 CBoard::bishop_pseudo(int square, int color) const {
    return bishop_attacks(square, occupied(), colors[color]);
}

U64 CBoard::rook_pseudo(int square, int color) const {
    return rook_attacks(square, occupied(), colors[color]);
}

U64 CBoard::queen_pseudo(int square, int color) const {
    U64 occ = occupied();
    U64 friendly = colors[color];
    return bishop_attacks(square, occ, friendly) | rook_attacks(square, occ, friendly);
}

U64 CBoard::king_pseudo(int square, int color) const {
    U64 bits = square_to_bits(square);
    U64 attacks = shift_n(bits) | shift_s(bits) | shift_e(bits) | shift_w(bits) |
                  shift_ne(bits) | shift_nw(bits) | shift_se(bits) | shift_sw(bits);
    return attacks & ~colors[color];
}

U64 CBoard::get_pseudo_legal(int square, int color) const {
    Piece info = get_piece_at(square);
    if (info.empty() || info.color != color) return 0;
    switch (info.type) {
        case PAWN:   return pawn_pseudo(square, color);
        case KNIGHT: return knight_pseudo(square, color);
        case BISHOP: return bishop_pseudo(square, color);
        case ROOK:   return rook_pseudo(square, color);
        case QUEEN:  return queen_pseudo(square, color);
        case KING:   return king_pseudo(square, color);
    }
    return 0;
}

// ── Attack map / check ──────────────────────────────────────────────────────

U64 CBoard::get_attacks(int color) const {
    U64 occ = occupied();
    U64 result = 0;

    U64 p = get_specific_pieces(color, PAWN);
    while (p) {
        U64 bits = square_to_bits(pop_lsb(p));
        if (color == WHITE) result |= shift_nw(bits) | shift_ne(bits);
        else                result |= shift_sw(bits) | shift_se(bits);
    }
    U64 n = get_specific_pieces(color, KNIGHT);
    while (n) result |= knight_attacks(square_to_bits(pop_lsb(n)));

    U64 b = get_specific_pieces(color, BISHOP);
    while (b) result |= bishop_attacks(pop_lsb(b), occ, 0);

    U64 r = get_specific_pieces(color, ROOK);
    while (r) result |= rook_attacks(pop_lsb(r), occ, 0);

    U64 q = get_specific_pieces(color, QUEEN);
    while (q) {
        int sq = pop_lsb(q);
        result |= bishop_attacks(sq, occ, 0) | rook_attacks(sq, occ, 0);
    }
    U64 k = get_specific_pieces(color, KING);
    while (k) {
        U64 bits = square_to_bits(pop_lsb(k));
        result |= shift_n(bits) | shift_s(bits) | shift_e(bits) | shift_w(bits) |
                  shift_ne(bits) | shift_nw(bits) | shift_se(bits) | shift_sw(bits);
    }
    return result;
}

bool CBoard::is_in_check(int color) const {
    int ks = king_square(color);
    return (get_attacks(opponent(static_cast<Color>(color))) & square_to_bits(ks)) != 0;
}

// ── Make / unmake ───────────────────────────────────────────────────────────

void CBoard::make_move(int from_square, int to_square, int promotion) {
    Piece piece_info = get_piece_at(from_square);
    assert(!piece_info.empty());
    int color = piece_info.color;
    int piece_type = piece_info.type;

    Piece captured_info = get_piece_at(to_square);
    int captured_piece_type = captured_info.empty() ? NO_PIECE : captured_info.type;
    int captured_piece_color = captured_info.empty() ? -1 : captured_info.color;

    Undo move;
    move.from = from_square;
    move.to = to_square;
    move.captured_piece = captured_piece_type;
    move.captured_color = captured_piece_color;
    move.promotion = promotion;
    move.is_en_passant = false;
    move.is_castle = false;
    move.castle_rook_from = -1;
    move.castle_rook_to = -1;
    move.prev_en_passant_square = en_passant_square;
    move.prev_castling_rights = castling_rights;
    move.prev_halfmove_clock = halfmove_clock;
    move.prev_zobrist_key = zobrist_key;

    if (captured_piece_type != NO_PIECE)
        clear_piece(captured_piece_color, captured_piece_type, to_square);

    if (piece_type == PAWN && en_passant_square == to_square) {
        int ep_square = (color == WHITE) ? to_square - 8 : to_square + 8;
        clear_piece(opponent(static_cast<Color>(color)), PAWN, ep_square);
        move.is_en_passant = true;
    }

    clear_piece(color, piece_type, from_square);
    int placed_piece_type = (promotion != NO_PIECE) ? promotion : piece_type;
    set_piece(color, placed_piece_type, to_square);

    if (piece_type == KING) {
        int diff = to_square - from_square;
        int rook_from = -1, rook_to = -1;
        if (diff == 2) {
            rook_from = from_square + 3;
            rook_to = from_square + 1;
        } else if (diff == -2) {
            rook_from = from_square - 4;
            rook_to = from_square - 1;
        }
        if (rook_from >= 0) {
            clear_piece(color, ROOK, rook_from);
            set_piece(color, ROOK, rook_to);
            move.is_castle = true;
            move.castle_rook_from = rook_from;
            move.castle_rook_to = rook_to;
        }
    }

    if (piece_type == PAWN && std::abs(to_square - from_square) == 16)
        en_passant_square = (from_square + to_square) / 2;
    else
        en_passant_square = -1;

    if (piece_type == KING)
        castling_rights &= (color == WHITE) ? ~(CR_WK | CR_WQ) : ~(CR_BK | CR_BQ);
    auto rook_right = [](int sq) -> int {
        switch (sq) {
            case 0: return CR_WQ;
            case 7: return CR_WK;
            case 56: return CR_BQ;
            case 63: return CR_BK;
        }
        return 0;
    };
    if (piece_type == ROOK) castling_rights &= ~rook_right(from_square);
    if (captured_piece_type == ROOK) castling_rights &= ~rook_right(to_square);

    if (piece_type == PAWN || captured_piece_type != NO_PIECE) halfmove_clock = 0;
    else halfmove_clock += 1;

    move_history.push_back(move);
    if (color == BLACK) fullmove += 1;
    turn = opponent(static_cast<Color>(color));
    zobrist_key = compute_zobrist();
}

void CBoard::unmake_move() {
    if (move_history.empty()) return;
    Undo move = move_history.back();
    move_history.pop_back();
    int color = opponent(turn);  // color that made the move
    turn = static_cast<Color>(color);

    int to_square = move.to;
    int from_square = move.from;

    Piece piece_on_dest = get_piece_at(to_square);
    int placed_piece_type = piece_on_dest.type;
    int original_piece_type = (move.promotion != NO_PIECE) ? PAWN : placed_piece_type;

    clear_piece(color, placed_piece_type, to_square);
    set_piece(color, original_piece_type, from_square);

    if (move.captured_piece != NO_PIECE && !move.is_en_passant)
        set_piece(move.captured_color, move.captured_piece, to_square);

    if (move.is_en_passant) {
        int ep_square = (color == WHITE) ? to_square - 8 : to_square + 8;
        set_piece(opponent(static_cast<Color>(color)), PAWN, ep_square);
    }

    if (move.is_castle) {
        clear_piece(color, ROOK, move.castle_rook_to);
        set_piece(color, ROOK, move.castle_rook_from);
    }

    en_passant_square = move.prev_en_passant_square;
    castling_rights = move.prev_castling_rights;
    halfmove_clock = move.prev_halfmove_clock;
    zobrist_key = move.prev_zobrist_key;
    if (color == BLACK) fullmove -= 1;
}

// ── Legal moves ─────────────────────────────────────────────────────────────

U64 CBoard::castling_pseudo(int color) const {
    U64 occ = occupied();
    U64 attacked = get_attacks(opponent(static_cast<Color>(color)));
    U64 result = 0;

    if (color == WHITE) {
        if (attacked & square_to_bits(4)) return 0;  // E1, can't castle out of check
        if ((castling_rights & CR_WK) && !(occ & 0x60ULL) && !(attacked & 0x60ULL))
            result |= square_to_bits(6);   // G1
        if ((castling_rights & CR_WQ) && !(occ & 0x0EULL) && !(attacked & 0x0CULL))
            result |= square_to_bits(2);   // C1
    } else {
        if (attacked & square_to_bits(60)) return 0;  // E8
        if ((castling_rights & CR_BK) && !(occ & 0x6000000000000000ULL) &&
            !(attacked & 0x6000000000000000ULL))
            result |= square_to_bits(62);  // G8
        if ((castling_rights & CR_BQ) && !(occ & 0x0E00000000000000ULL) &&
            !(attacked & 0x0C00000000000000ULL))
            result |= square_to_bits(58);  // C8
    }
    return result;
}

U64 CBoard::get_legal_moves(int square) {
    Piece info = get_piece_at(square);
    if (info.empty() || info.color != turn) return 0;
    int color = info.color;
    int piece_type = info.type;

    U64 pseudo = get_pseudo_legal(square, color);
    if (piece_type == KING) pseudo |= castling_pseudo(color);

    U64 legal = 0;
    U64 bb = pseudo;
    while (bb) {
        int dest = pop_lsb(bb);
        make_move(square, dest);
        if (!is_in_check(color)) legal |= square_to_bits(dest);
        unmake_move();
    }
    return legal;
}

std::vector<std::pair<int, U64>> CBoard::get_all_legal_moves() {
    std::vector<std::pair<int, U64>> result;
    U64 bb = colors[turn];
    while (bb) {
        int square = pop_lsb(bb);
        U64 legal = get_legal_moves(square);
        if (legal) result.emplace_back(square, legal);
    }
    return result;
}

bool CBoard::is_checkmate() {
    return is_in_check(turn) && get_all_legal_moves().empty();
}

bool CBoard::is_stalemate() {
    return !is_in_check(turn) && get_all_legal_moves().empty();
}

bool CBoard::needs_promotion(int from_square, int to_square) const {
    Piece info = get_piece_at(from_square);
    if (info.empty() || info.type != PAWN) return false;
    int rank = rank_of(to_square);
    return (info.color == WHITE && rank == 7) || (info.color == BLACK && rank == 0);
}
