//! Eschess chess engine (Rust port). Equivalent logic to python/engine and
//! cpp/src: bitboard board, handcrafted evaluation, alpha-beta search with a
//! transposition table, exposed through a UCI binary.

pub mod board;
pub mod evaluate;
pub mod search;
pub mod tt;
pub mod types;
pub mod zobrist;
