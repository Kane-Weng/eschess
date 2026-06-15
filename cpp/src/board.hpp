// Chess board: representation, move generation, legality, make/unmake, game
// state. 1:1 port of CBoard in python/engine/board.py.
#pragma once

#include <string>
#include <utility>
#include <vector>

#include "types.hpp"

extern const char *STARTPOS_FEN;

struct Piece {
    int color;
    int type;   
    bool empty() const { return type == NO_PIECE; }
};

class CBoard {
public:
    U64 colors[2];
    U64 pieces[6];
    Color turn;
    int en_passant_square;   // -1 == none
    int castling_rights;
    int halfmove_clock;
    int fullmove;
    bool game_over;
    int winner;              // Color, or -1 for stalemate / none
    U64 zobrist_key;

    CBoard();

    static CBoard from_fen(const std::string &fen);
    void set_fen(const std::string &fen);
    std::string to_fen() const;

    // ── Queries ──────────────────────────────────────────────────────────────
    U64 occupied() const { return colors[WHITE] | colors[BLACK]; }
    U64 get_specific_pieces(int color, int piece_type) const {
        return colors[color] & pieces[piece_type];
    }
    Piece get_piece_at(int square) const;

    // ── Attacks / check ──────────────────────────────────────────────────────
    U64 get_attacks(int color) const;
    bool is_in_check(int color) const;

    // ── Make / unmake ────────────────────────────────────────────────────────
    void make_move(int from_square, int to_square, int promotion = NO_PIECE);
    void unmake_move();

    // ── Legal moves ──────────────────────────────────────────────────────────
    U64 get_legal_moves(int square);
    std::vector<std::pair<int, U64>> get_all_legal_moves();

    // ── Game state ───────────────────────────────────────────────────────────
    bool is_checkmate();
    bool is_stalemate();
    bool needs_promotion(int from_square, int to_square) const;

private:
    // Undo record stored per move
    struct Undo {
        int from, to;
        int captured_piece;   // NO_PIECE == none
        int captured_color;   // -1 == none
        int promotion;
        bool is_en_passant;
        bool is_castle;
        int castle_rook_from, castle_rook_to;
        int prev_en_passant_square;
        int prev_castling_rights;
        int prev_halfmove_clock;
        U64 prev_zobrist_key;
    };
    std::vector<Undo> move_history;

    void set_pieces();
    U64 compute_zobrist() const;
    int king_square(int color) const;

    void set_piece(int color, int piece_type, int square) {
        U64 bits = square_to_bits(square);
        colors[color] |= bits;
        pieces[piece_type] |= bits;
    }
    void clear_piece(int color, int piece_type, int square) {
        U64 bits = ~square_to_bits(square);
        colors[color] &= bits;
        pieces[piece_type] &= bits;
    }

    U64 ray(int square, int delta, U64 edge_mask, U64 occ, U64 friendly) const;
    U64 bishop_attacks(int square, U64 occ, U64 friendly) const;
    U64 rook_attacks(int square, U64 occ, U64 friendly) const;

    U64 pawn_pseudo(int square, int color) const;
    U64 knight_pseudo(int square, int color) const;
    U64 bishop_pseudo(int square, int color) const;
    U64 rook_pseudo(int square, int color) const;
    U64 queen_pseudo(int square, int color) const;
    U64 king_pseudo(int square, int color) const;
    U64 get_pseudo_legal(int square, int color) const;
    U64 castling_pseudo(int color) const;
};
