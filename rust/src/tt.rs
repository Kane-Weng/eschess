//! Transposition table keyed by Zobrist hash. Port of
//! python/engine/transposition.py and cpp/src/tt: a fixed-size power-of-two
//! array (index = key & mask) with depth-preferred replacement.

use crate::types::{Move, NULL_MOVE, U64};

// TTFlag comes from the shared schema; re-export so `eschess::tt::TTFlag` holds.
pub use crate::generated::TTFlag;

#[derive(Clone, Copy)]
pub struct TTEntry {
    pub key: U64,
    pub depth: i32,
    pub flag: TTFlag,
    pub score: f64,
    pub best_move: Move,
    pub valid: bool,
}

impl TTEntry {
    const EMPTY: TTEntry = TTEntry {
        key: 0,
        depth: 0,
        flag: TTFlag::Exact,
        score: 0.0,
        best_move: NULL_MOVE,
        valid: false,
    };
}

pub struct TranspositionTable {
    table: Vec<TTEntry>,
    mask: usize,
}

impl TranspositionTable {
    pub fn new(size_mb: usize) -> TranspositionTable {
        let bytes = size_mb * 1024 * 1024;
        let want = (bytes / std::mem::size_of::<TTEntry>()).max(1);
        let mut pow2 = 1usize;
        while pow2 * 2 <= want {
            pow2 *= 2;
        }
        TranspositionTable {
            table: vec![TTEntry::EMPTY; pow2],
            mask: pow2 - 1,
        }
    }

    #[inline]
    pub fn probe(&self, key: U64) -> Option<&TTEntry> {
        let e = &self.table[(key as usize) & self.mask];
        if e.valid && e.key == key {
            Some(e)
        } else {
            None
        }
    }

    pub fn store(&mut self, key: U64, depth: i32, flag: TTFlag, score: f64, best_move: Move) {
        let e = &mut self.table[(key as usize) & self.mask];
        // Depth-preferred: overwrite empty slots, the same position, or shallower.
        if !e.valid || e.key == key || depth >= e.depth {
            *e = TTEntry {
                key,
                depth,
                flag,
                score,
                best_move,
                valid: true,
            };
        }
    }
}
