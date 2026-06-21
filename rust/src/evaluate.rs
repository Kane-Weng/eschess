//! Position evaluation, three levels behind a common trait. 1:1 port of
//! python/engine/evaluate.py and cpp/src/evaluate.cpp. Uses f64 (pawn units)
//! to match the Python float scores exactly; positive == White winning.

use crate::board::CBoard;
use crate::generated::{KING_EG_PST, KING_MG_PST, PASSED_BONUS, PIECE_VALUES, PST_MAP};
use crate::types::*;

// PIECE_VALUES, the piece-square tables, PST_MAP and PASSED_BONUS come from
// the shared schema via crate::generated (see schema/engine.toml).

#[inline]
fn file_mask(f: i32) -> U64 {
    FILE_A << f
}
#[inline]
fn mirror(sq: i32) -> i32 {
    (7 - sq / 8) * 8 + sq % 8
}
#[inline]
fn pst_val(pst: &[i32; 64], sq: i32, color: usize) -> f64 {
    let idx = if color == WHITE { sq } else { mirror(sq) };
    let raw = pst[idx as usize];
    (if color == WHITE { raw } else { -raw }) as f64 / 100.0
}

fn is_passed(sq: i32, color: usize, white_pawns: U64, black_pawns: U64) -> bool {
    let file_idx = sq % 8;
    let rank_idx = sq / 8;
    let mut fm = file_mask(file_idx);
    if file_idx > 0 {
        fm |= file_mask(file_idx - 1);
    }
    if file_idx < 7 {
        fm |= file_mask(file_idx + 1);
    }
    if color == WHITE {
        let sh = (rank_idx + 1) * 8;
        let ahead = if sh >= 64 { 0 } else { fm & (FULL_BOARD << sh) };
        black_pawns & ahead == 0
    } else {
        let sh = rank_idx * 8;
        let below = if sh >= 64 {
            FULL_BOARD
        } else {
            (1u64 << sh) - 1
        };
        white_pawns & (fm & below) == 0
    }
}

pub trait BaseEvaluate {
    fn evaluate(&self, board: &CBoard) -> f64;
}

pub struct SimpleEvaluate;
pub struct MediumEvaluate;
pub struct ComplexEvaluate;

impl BaseEvaluate for SimpleEvaluate {
    fn evaluate(&self, board: &CBoard) -> f64 {
        let mut score = 0.0;
        for color in 0..2 {
            let sign = if color == WHITE { 1.0 } else { -1.0 };
            // Index-based loop mirrors the Python/C++ ports (pt is a piece-type id).
            #[allow(clippy::needless_range_loop)]
            for pt in 0..6 {
                let mut b = board.get_specific_pieces(color, pt);
                while b != 0 {
                    let sq = pop_lsb(&mut b);
                    score += PIECE_VALUES[pt] * sign;
                    let rank = sq / 8;
                    let file = sq % 8;

                    if pt == PAWN {
                        let behind = if color == WHITE { sq - 8 } else { sq + 8 };
                        if (0..=63).contains(&behind)
                            && board.get_specific_pieces(color, PAWN) & (1u64 << behind) != 0
                        {
                            score -= 0.5 * sign;
                        }
                    } else if pt == KNIGHT {
                        if (rank == 3 || rank == 4) && (file == 3 || file == 4) {
                            score += 0.50 * sign;
                        } else if (rank == 2 || rank == 5) && (file == 2 || file == 5) {
                            score += 0.25 * sign;
                        } else if rank == 0 || rank == 7 || file == 0 || file == 7 {
                            score -= 0.50 * sign;
                        }
                    } else if pt == KING {
                        if color == WHITE && rank == 0 && (file == 2 || file == 6) {
                            score += 0.75;
                        } else if color == BLACK && rank == 7 && (file == 2 || file == 6) {
                            score -= 0.75;
                        }
                    }
                }
            }
        }
        score
    }
}

impl BaseEvaluate for MediumEvaluate {
    fn evaluate(&self, board: &CBoard) -> f64 {
        let mut score = 0.0;
        for color in 0..2 {
            for pt in 0..6 {
                let pst = PST_MAP[pt];
                let mut b = board.get_specific_pieces(color, pt);
                while b != 0 {
                    let sq = pop_lsb(&mut b);
                    score += PIECE_VALUES[pt] * if color == WHITE { 1.0 } else { -1.0 };
                    score += pst_val(pst, sq, color);
                }
            }
        }
        score
    }
}

impl BaseEvaluate for ComplexEvaluate {
    fn evaluate(&self, board: &CBoard) -> f64 {
        let mut score = 0.0;
        let white_pawns = board.get_specific_pieces(WHITE, PAWN);
        let black_pawns = board.get_specific_pieces(BLACK, PAWN);

        let mut minor_major = 0.0;
        for c in 0..2 {
            for &pt in &[KNIGHT, BISHOP, ROOK, QUEEN] {
                minor_major += popcount(board.get_specific_pieces(c, pt)) as f64 * PIECE_VALUES[pt];
            }
        }
        let king_pst: &[i32; 64] = if minor_major < 14.0 {
            &KING_EG_PST
        } else {
            &KING_MG_PST
        };

        for color in 0..2 {
            let sign = if color == WHITE { 1.0 } else { -1.0 };

            for pt in 0..6 {
                let pst = if pt == KING { king_pst } else { PST_MAP[pt] };
                let mut b = board.get_specific_pieces(color, pt);
                while b != 0 {
                    let sq = pop_lsb(&mut b);
                    score += PIECE_VALUES[pt] * sign;
                    score += pst_val(pst, sq, color);

                    if pt == PAWN {
                        let file_idx = sq % 8;
                        let rank_idx = sq / 8;
                        let fmask = file_mask(file_idx);
                        let friendly = board.get_specific_pieces(color, PAWN);

                        if popcount(friendly & fmask) > 1 {
                            score -= 0.20 * sign; // doubled
                        }
                        let mut neighbor = 0;
                        if file_idx > 0 {
                            neighbor |= file_mask(file_idx - 1);
                        }
                        if file_idx < 7 {
                            neighbor |= file_mask(file_idx + 1);
                        }
                        if friendly & neighbor == 0 {
                            score -= 0.25 * sign; // isolated
                        }
                        if is_passed(sq, color, white_pawns, black_pawns) {
                            let adv = if color == WHITE {
                                rank_idx
                            } else {
                                7 - rank_idx
                            };
                            score += PASSED_BONUS[adv as usize] as f64 / 100.0 * sign;
                        }
                    }
                }
            }

            if popcount(board.get_specific_pieces(color, BISHOP)) >= 2 {
                score += 0.50 * sign; // bishop pair
            }
            score += popcount(board.get_attacks(color)) as f64 * 0.005 * sign; // mobility
        }
        score
    }
}

pub fn make_evaluator(name: &str) -> Box<dyn BaseEvaluate> {
    match name {
        "simple" => Box::new(SimpleEvaluate),
        "complex" => Box::new(ComplexEvaluate),
        _ => Box::new(MediumEvaluate),
    }
}
