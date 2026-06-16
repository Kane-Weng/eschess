//! `PyBoard`: a thin PyO3 wrapper around the core `CBoard`, exposing the
//! move-generation / make-unmake / FEN / zobrist surface the Python training and
//! parity tests need, plus a native `board_to_planes`.

use numpy::ndarray::Array3;
use numpy::{IntoPyArray, PyArray3};
use pyo3::prelude::*;

use eschess::board::{CBoard, STARTPOS_FEN};
use eschess::types::NO_PIECE;

use crate::encoding::{encode_into, ENCODED_LEN, INPUT_PLANES};
use crate::moves::{legal_move_list, legal_movekeys};

/// A chess position, wrapping `eschess::board::CBoard`.
#[pyclass(module = "eschess_native")]
pub struct PyBoard {
    pub(crate) inner: CBoard,
}

#[pymethods]
impl PyBoard {
    /// Create a board. With no argument (or `None`) this is the start position;
    /// otherwise the FEN is parsed.
    #[new]
    #[pyo3(signature = (fen=None))]
    fn new(fen: Option<&str>) -> PyBoard {
        let inner = match fen {
            Some(f) => CBoard::from_fen(f),
            None => CBoard::from_fen(STARTPOS_FEN),
        };
        PyBoard { inner }
    }

    /// Replace the position from a FEN string.
    fn set_fen(&mut self, fen: &str) {
        self.inner.set_fen(fen);
    }

    /// Serialize the current position to FEN.
    fn to_fen(&self) -> String {
        self.inner.to_fen()
    }

    /// Apply a move. `promotion` defaults to NO_PIECE (-1); pass a piece-type
    /// index (QUEEN=4, etc.) for a promotion.
    #[pyo3(signature = (from_square, to_square, promotion=NO_PIECE))]
    fn make_move(&mut self, from_square: i32, to_square: i32, promotion: i32) {
        self.inner.make_move(from_square, to_square, promotion);
    }

    /// Undo the most recent move (no-op if the history is empty).
    fn unmake_move(&mut self) {
        self.inner.unmake_move();
    }

    /// All legal moves as (from, to, promotion) triples (promotions expanded).
    fn legal_moves(&mut self) -> Vec<(i32, i32, i32)> {
        legal_move_list(&mut self.inner)
    }

    /// All legal (from, to) pairs (promotions collapsed to one entry).
    fn legal_move_keys(&mut self) -> Vec<(i32, i32)> {
        legal_movekeys(&mut self.inner)
            .into_iter()
            .map(|(f, t)| (f as i32, t as i32))
            .collect()
    }

    fn is_checkmate(&mut self) -> bool {
        self.inner.is_checkmate()
    }

    fn is_stalemate(&mut self) -> bool {
        self.inner.is_stalemate()
    }

    fn is_in_check(&self, color: usize) -> bool {
        self.inner.is_in_check(color)
    }

    fn needs_promotion(&self, from_square: i32, to_square: i32) -> bool {
        self.inner.needs_promotion(from_square, to_square)
    }

    /// Bitboard of a (color, piece_type) set, as a Python int.
    fn get_specific_pieces(&self, color: usize, piece_type: usize) -> u64 {
        self.inner.get_specific_pieces(color, piece_type)
    }

    /// Encode the position as an (18, 8, 8) float32 numpy array.
    fn board_to_planes<'py>(&self, py: Python<'py>) -> Bound<'py, PyArray3<f32>> {
        let mut flat = vec![0.0f32; ENCODED_LEN];
        encode_into(&self.inner, &mut flat);
        Array3::from_shape_vec((INPUT_PLANES, 8, 8), flat)
            .expect("encoded length matches (18,8,8)")
            .into_pyarray_bound(py)
    }

    /// Perft node count to `depth` from the current position (validation aid).
    fn perft(&mut self, depth: i32) -> u64 {
        perft(&mut self.inner, depth)
    }

    #[getter]
    fn turn(&self) -> usize {
        self.inner.turn
    }

    #[getter]
    fn zobrist_key(&self) -> u64 {
        self.inner.zobrist_key
    }

    #[getter]
    fn halfmove_clock(&self) -> i32 {
        self.inner.halfmove_clock
    }

    #[getter]
    fn en_passant_square(&self) -> i32 {
        self.inner.en_passant_square
    }

    #[getter]
    fn castling_rights(&self) -> i32 {
        self.inner.castling_rights
    }

    #[getter]
    fn game_over(&self) -> bool {
        self.inner.game_over
    }

    fn __repr__(&self) -> String {
        format!("PyBoard(\"{}\")", self.inner.to_fen())
    }
}

/// Standalone perft over a core board (used by `PyBoard::perft`).
pub fn perft(board: &mut CBoard, depth: i32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let mut nodes = 0u64;
    for (from, to, promo) in legal_move_list(board) {
        board.make_move(from, to, promo);
        nodes += perft(board, depth - 1);
        board.unmake_move();
    }
    nodes
}

/// Free function `eschess_native.board_to_planes(board)` for the supervised /
/// dataset path (the same encoding as the method, kept callable standalone).
#[pyfunction]
pub fn board_to_planes<'py>(py: Python<'py>, board: &PyBoard) -> Bound<'py, PyArray3<f32>> {
    board.board_to_planes(py)
}
