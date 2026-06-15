//! Zobrist hash tables. Layout mirrors _ZOB_* in python/engine/board.py and
//! cpp/src/zobrist. The random values differ per language (own PRNG); only
//! internal consistency + TT correctness matter, not cross-language equality.

use crate::types::U64;
use std::sync::OnceLock;

pub struct Tables {
    pub piece: [[[U64; 64]; 6]; 2],
    pub turn: U64,
    pub castle: [U64; 16],
    pub ep: [U64; 8],
}

// splitmix64: a tiny dependency-free PRNG to fill the tables deterministically.
struct SplitMix64 {
    state: u64,
}
impl SplitMix64 {
    fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

static TABLES: OnceLock<Tables> = OnceLock::new();

pub fn tables() -> &'static Tables {
    TABLES.get_or_init(|| {
        let mut rng = SplitMix64 {
            state: 0xCAFE_BABE,
        };
        let mut piece = [[[0u64; 64]; 6]; 2];
        for c in 0..2 {
            for p in 0..6 {
                for s in 0..64 {
                    piece[c][p][s] = rng.next();
                }
            }
        }
        let turn = rng.next();
        let mut castle = [0u64; 16];
        for v in castle.iter_mut() {
            *v = rng.next();
        }
        let mut ep = [0u64; 8];
        for v in ep.iter_mut() {
            *v = rng.next();
        }
        Tables {
            piece,
            turn,
            castle,
            ep,
        }
    })
}
