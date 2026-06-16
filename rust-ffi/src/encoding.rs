//! Native board -> planes encoding. Byte-for-byte mirror of
//! python/nn/encoding.py `board_to_planes`: an (INPUT_PLANES, 8, 8) f32 stack,
//! flattened C-contiguous so element (plane, rank, file) lives at
//! `plane*64 + rank*8 + file`.
//!
//! Plane layout (must match encoding.py exactly):
//!   0..=5   white pieces  (PAWN..KING)
//!   6..=11  black pieces  (PAWN..KING)
//!   12      side-to-move  (all ones when White to move)
//!   13..=16 castling      (WK, WQ, BK, BQ)
//!   17      en passant    (single one-hot target square)

use eschess::board::CBoard;
use eschess::types::*;

pub const INPUT_PLANES: usize = 18;
pub const PLANE_SIZE: usize = 64;
pub const ENCODED_LEN: usize = INPUT_PLANES * PLANE_SIZE; // 1152

const PLANE_STM: usize = 12;
const PLANE_CASTLE: usize = 13;
const PLANE_EP: usize = 17;
const CASTLE_BITS: [i32; 4] = [CR_WK, CR_WQ, CR_BK, CR_BQ];

/// Write the plane stack for `board` into `out` (length == ENCODED_LEN).
/// `out` is assumed to be all zeros on entry (the caller allocates it that way).
pub fn encode_into(board: &CBoard, out: &mut [f32]) {
    debug_assert_eq!(out.len(), ENCODED_LEN);

    for color in 0..2 {
        for pt in 0..6 {
            let row = color * 6 + pt; // matches _piece_plane_index: color*6 + type
            let mut bb = board.get_specific_pieces(color, pt);
            while bb != 0 {
                let sq = pop_lsb(&mut bb);
                let r = (sq >> 3) as usize;
                let f = (sq & 7) as usize;
                out[row * PLANE_SIZE + r * 8 + f] = 1.0;
            }
        }
    }

    if board.turn == WHITE {
        let base = PLANE_STM * PLANE_SIZE;
        out[base..base + PLANE_SIZE].fill(1.0);
    }

    for (offset, &bit) in CASTLE_BITS.iter().enumerate() {
        if board.castling_rights & bit != 0 {
            let base = (PLANE_CASTLE + offset) * PLANE_SIZE;
            out[base..base + PLANE_SIZE].fill(1.0);
        }
    }

    if board.en_passant_square >= 0 {
        let sq = board.en_passant_square;
        let r = (sq >> 3) as usize;
        let f = (sq & 7) as usize;
        out[PLANE_EP * PLANE_SIZE + r * 8 + f] = 1.0;
    }
}

/// Allocate and return a fresh encoded plane stack for `board`.
pub fn encode(board: &CBoard) -> Vec<f32> {
    let mut out = vec![0.0f32; ENCODED_LEN];
    encode_into(board, &mut out);
    out
}
