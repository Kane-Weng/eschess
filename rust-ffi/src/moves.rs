//! Shared legal-move enumeration helpers over the core `CBoard`.
//!
//! `CBoard::get_all_legal_moves` returns (from_square, legal_destination_bits);
//! the helpers here expand those bitboards into concrete moves. The policy head
//! keys moves by (from, to) only, so the MCTS path uses `legal_movekeys`; perft
//! / general callers want every promotion piece, so they use `legal_move_list`.

use eschess::board::CBoard;
use eschess::types::*;

const PROMO_PIECES: [i32; 4] = [QUEEN as i32, ROOK as i32, BISHOP as i32, KNIGHT as i32];

/// (from, to) pairs for every legal move, ascending by `from*64 + to`.
/// Promotions collapse to a single (from, to) — matching the queen-only policy
/// head in python/nn/encoding.py.
pub fn legal_movekeys(board: &mut CBoard) -> Vec<(u8, u8)> {
    let mut out = Vec::new();
    for (from, legal_bits) in board.get_all_legal_moves() {
        let mut bits = legal_bits;
        while bits != 0 {
            let to = pop_lsb(&mut bits);
            out.push((from as u8, to as u8));
        }
    }
    out
}

/// (from, to, promotion) for every legal move, expanding the four promotion
/// pieces on back-rank pawn moves. Mirrors rust/src/bin/perft.rs.
pub fn legal_move_list(board: &mut CBoard) -> Vec<(i32, i32, i32)> {
    let mut out = Vec::new();
    for (from, legal_bits) in board.get_all_legal_moves() {
        let mut bits = legal_bits;
        while bits != 0 {
            let to = pop_lsb(&mut bits);
            if board.needs_promotion(from, to) {
                for &promo in &PROMO_PIECES {
                    out.push((from, to, promo));
                }
            } else {
                out.push((from, to, NO_PIECE));
            }
        }
    }
    out
}
