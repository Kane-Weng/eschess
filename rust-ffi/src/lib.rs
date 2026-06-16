//! `eschess_native`: PyO3 bindings over the eschess Rust core, plus a native
//! AlphaZero-style self-play engine for the ML training loop.
//!
//! Exposes:
//!   - `PyBoard`         — the core CBoard (make/unmake, legal moves, FEN, zobrist)
//!   - `board_to_planes` — native (18,8,8) f32 encoding (mirrors nn/encoding.py)
//!   - `SelfPlayEngine`  — parallel, GIL-released MCTS self-play with batched NN
//!     inference supplied by a Python callback
//!
//! See python/nn/native.py for the Python-side adapter and fallback wiring.

use pyo3::prelude::*;

mod board;
mod encoding;
mod mcts;
mod moves;
mod selfplay;

use board::{board_to_planes, PyBoard};
use selfplay::SelfPlayEngine;

#[pymodule]
fn eschess_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyBoard>()?;
    m.add_class::<SelfPlayEngine>()?;
    m.add_function(wrap_pyfunction!(board_to_planes, m)?)?;
    m.add("INPUT_PLANES", encoding::INPUT_PLANES)?;
    m.add("POLICY_SIZE", 64 * 64)?;
    Ok(())
}
