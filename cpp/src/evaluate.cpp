#include "evaluate.hpp"

namespace {

// Piece values in pawn units (matches PIECE_VALUES in evaluate.py).
const double PIECE_VALUES[6] = {1.0, 3.2, 3.3, 5.0, 9.0, 0.0};

// Piece-square tables (centipawns, White's perspective, LERF order).
const int PAWN_PST[64] = {
    0,  0,  0,  0,  0,  0,  0,  0,  5,  10, 10, -20, -20, 10, 10, 5,  5, -5, -10, 0,  0,  -10,
    -5, 5,  0,  0,  0,  20, 20, 0,  0,  0,  5,  5,   10,  25, 25, 10, 5, 5,  10,  10, 20, 30,
    30, 20, 10, 10, 50, 50, 50, 50, 50, 50, 50, 50,  0,   0,  0,  0,  0, 0,  0,   0,
};
const int KNIGHT_PST[64] = {
    -50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0,   0,   0,   0,   -20, -40,
    -30, 0,   10,  15,  15,  10,  0,   -30, -30, 5,   15,  20,  20,  15,  5,   -30,
    -30, 0,   15,  20,  20,  15,  0,   -30, -30, 5,   10,  15,  15,  10,  5,   -30,
    -40, -20, 0,   5,   5,   0,   -20, -40, -50, -40, -30, -30, -30, -30, -40, -50,
};
const int BISHOP_PST[64] = {
    -20, -10, -10, -10, -10, -10, -10, -20, -10, 0,   0,   0,   0,   0,   0,   -10,
    -10, 0,   5,   10,  10,  5,   0,   -10, -10, 5,   5,   10,  10,  5,   5,   -10,
    -10, 0,   10,  10,  10,  10,  0,   -10, -10, 10,  10,  10,  10,  10,  10,  -10,
    -10, 5,   0,   0,   0,   0,   5,   -10, -20, -10, -10, -10, -10, -10, -10, -20,
};
const int ROOK_PST[64] = {
    0, 0,  0,  5,  5, 0,  0,  0,  -5, 0,  0,  0, 0, 0, 0, -5, -5, 0,  0,  0, 0, 0,
    0, -5, -5, 0,  0, 0,  0,  0,  0,  -5, -5, 0, 0, 0, 0, 0,  0,  -5, -5, 0, 0, 0,
    0, 0,  0,  -5, 5, 10, 10, 10, 10, 10, 10, 5, 0, 0, 0, 0,  0,  0,  0,  0,
};
const int QUEEN_PST[64] = {
    -20, -10, -10, -5, -5, -10, -10, -20, -10, 0,   0,   0,  0,  0,   0,   -10,
    -10, 0,   5,   5,  5,  5,   0,   -10, -5,  0,   5,   5,  5,  5,   0,   -5,
    0,   0,   5,   5,  5,  5,   0,   -5,  -10, 5,   5,   5,  5,  5,   0,   -10,
    -10, 0,   5,   0,  0,  0,   0,   -10, -20, -10, -10, -5, -5, -10, -10, -20,
};
const int KING_MG_PST[64] = {
    20,  30,  10,  0,   0,   10,  30,  20,  20,  20,  0,   0,   0,   0,   20,  20,
    -10, -20, -20, -20, -20, -20, -20, -10, -20, -30, -30, -40, -40, -30, -30, -20,
    -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30,
};
const int KING_EG_PST[64] = {
    -50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0,   0,   -10, -20, -30,
    -30, -10, 20,  30,  30,  20,  -10, -30, -30, -10, 30,  40,  40,  30,  -10, -30,
    -30, -10, 30,  40,  40,  30,  -10, -30, -30, -10, 20,  30,  30,  20,  -10, -30,
    -30, -30, 0,   0,   0,   0,   -30, -30, -50, -30, -30, -30, -30, -30, -30, -50,
};

const int *PST_MAP[6] = {PAWN_PST, KNIGHT_PST, BISHOP_PST, ROOK_PST, QUEEN_PST, KING_MG_PST};

inline U64 file_mask(int f) { return FILE_A << f; }

// Passed-pawn rank bonus (centipawns), indexed by advancement 0..7.
const int PASSED_BONUS[8] = {0, 0, 10, 20, 35, 60, 100, 0};

inline int mirror(int sq) { return (7 - sq / 8) * 8 + sq % 8; }

inline double pst_val(const int *pst, int sq, int color) {
    int idx = (color == WHITE) ? sq : mirror(sq);
    int raw = pst[idx];
    return (color == WHITE ? raw : -raw) / 100.0;
}

bool is_passed(int sq, int color, U64 white_pawns, U64 black_pawns) {
    int file_idx = sq % 8;
    int rank_idx = sq / 8;
    U64 fm = file_mask(file_idx);
    if (file_idx > 0) fm |= file_mask(file_idx - 1);
    if (file_idx < 7) fm |= file_mask(file_idx + 1);
    if (color == WHITE) {
        int sh = (rank_idx + 1) * 8;
        U64 ahead = (sh >= 64) ? 0 : (fm & (FULL_BOARD << sh));
        return (black_pawns & ahead) == 0;
    } else {
        int sh = rank_idx * 8;
        U64 below = (sh >= 64) ? FULL_BOARD : ((1ULL << sh) - 1);
        U64 ahead = fm & below;
        return (white_pawns & ahead) == 0;
    }
}

}  // namespace

double SimpleEvaluate::evaluate(const CBoard &board) const {
    double score = 0.0;
    for (int color = 0; color < 2; ++color) {
        int sign = (color == WHITE) ? 1 : -1;
        for (int pt = 0; pt < 6; ++pt) {
            U64 b = board.get_specific_pieces(color, pt);
            while (b) {
                int sq = pop_lsb(b);
                score += PIECE_VALUES[pt] * sign;
                int rank = sq / 8, file = sq % 8;

                if (pt == PAWN) {
                    int behind = (color == WHITE) ? sq - 8 : sq + 8;
                    if (behind >= 0 && behind <= 63 &&
                        (board.get_specific_pieces(color, PAWN) & (1ULL << behind)))
                        score -= 0.5 * sign;
                } else if (pt == KNIGHT) {
                    if ((rank == 3 || rank == 4) && (file == 3 || file == 4))
                        score += 0.50 * sign;
                    else if ((rank == 2 || rank == 5) && (file == 2 || file == 5))
                        score += 0.25 * sign;
                    else if (rank == 0 || rank == 7 || file == 0 || file == 7)
                        score -= 0.50 * sign;
                } else if (pt == KING) {
                    if (color == WHITE && rank == 0 && (file == 2 || file == 6))
                        score += 0.75;
                    else if (color == BLACK && rank == 7 && (file == 2 || file == 6))
                        score -= 0.75;
                }
            }
        }
    }
    return score;
}

double MediumEvaluate::evaluate(const CBoard &board) const {
    double score = 0.0;
    for (int color = 0; color < 2; ++color) {
        for (int pt = 0; pt < 6; ++pt) {
            const int *pst = PST_MAP[pt];
            U64 b = board.get_specific_pieces(color, pt);
            while (b) {
                int sq = pop_lsb(b);
                score += PIECE_VALUES[pt] * (color == WHITE ? 1 : -1);
                score += pst_val(pst, sq, color);
            }
        }
    }
    return score;
}

double ComplexEvaluate::evaluate(const CBoard &board) const {
    double score = 0.0;
    U64 white_pawns = board.get_specific_pieces(WHITE, PAWN);
    U64 black_pawns = board.get_specific_pieces(BLACK, PAWN);

    double minor_major = 0.0;
    for (int c = 0; c < 2; ++c)
        for (int pt : {KNIGHT, BISHOP, ROOK, QUEEN})
            minor_major += popcount(board.get_specific_pieces(c, pt)) * PIECE_VALUES[pt];
    const int *king_pst = (minor_major < 14.0) ? KING_EG_PST : KING_MG_PST;

    for (int color = 0; color < 2; ++color) {
        int sign = (color == WHITE) ? 1 : -1;

        for (int pt = 0; pt < 6; ++pt) {
            const int *pst = (pt == KING) ? king_pst : PST_MAP[pt];
            U64 b = board.get_specific_pieces(color, pt);
            while (b) {
                int sq = pop_lsb(b);
                score += PIECE_VALUES[pt] * sign;
                score += pst_val(pst, sq, color);

                if (pt == PAWN) {
                    int file_idx = sq % 8;
                    int rank_idx = sq / 8;
                    U64 fmask = file_mask(file_idx);
                    U64 friendly = board.get_specific_pieces(color, PAWN);

                    if (popcount(friendly & fmask) > 1) score -= 0.20 * sign;  // doubled

                    U64 neighbor = 0;
                    if (file_idx > 0) neighbor |= file_mask(file_idx - 1);
                    if (file_idx < 7) neighbor |= file_mask(file_idx + 1);
                    if (!(friendly & neighbor)) score -= 0.25 * sign;  // isolated

                    if (is_passed(sq, color, white_pawns, black_pawns)) {
                        int adv = (color == WHITE) ? rank_idx : 7 - rank_idx;
                        score += PASSED_BONUS[adv] / 100.0 * sign;
                    }
                }
            }
        }

        if (popcount(board.get_specific_pieces(color, BISHOP)) >= 2) score += 0.50 * sign;

        score += popcount(board.get_attacks(color)) * 0.005 * sign;  // rough mobility
    }
    return score;
}
