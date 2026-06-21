#include "evaluate.hpp"

namespace {

// Constant tables (PIECE_VALUES, PSTs, PASSED_BONUS) come from the shared
// schema via generated.hpp (included through board.hpp -> types.hpp).
inline U64 file_mask(int f) { return FILE_A << f; }

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
