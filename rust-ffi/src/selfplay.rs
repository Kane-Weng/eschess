//! `SelfPlayEngine`: drives many self-play games in parallel, batching their
//! leaf evaluations into a single Python/PyTorch callback per step.
//!
//! The CPU-heavy work (MCTS selection, make/unmake, board->planes encoding,
//! expansion, backup) runs across a rayon thread pool with the GIL released via
//! `Python::allow_threads` — true multi-core throughput, bypassing the GIL. The
//! only time the GIL is re-acquired is the batched `eval_fn(states)` call, which
//! returns `(policy_logits (N, 4096), values (N,))` for every pending leaf.
//!
//! Output is returned as packed arrays (CSR-sparse policy targets) that the
//! Python adapter turns into the existing `SelfPlaySample` records:
//!   states        : (M, 18, 8, 8) f32   board planes per played ply
//!   values        : (M,) f32            game result, White's perspective
//!   policy_index   : (nnz,) i64          flat from*64+to indices
//!   policy_prob    : (nnz,) f32          normalized MCTS visit probabilities
//!   offsets        : (M+1,) i64          CSR row offsets into policy_index/prob

use numpy::ndarray::{Array1, Array4};
use numpy::{IntoPyArray, PyReadonlyArray1, PyReadonlyArray2};
use pyo3::prelude::*;
use rand::rngs::StdRng;
use rand::SeedableRng;
use rayon::prelude::*;

use crate::encoding::ENCODED_LEN;
use crate::mcts::{Cfg, GameState};

const POLICY_SIZE: usize = 4096;

/// Configurable native self-play engine. Defaults mirror python/nn/mcts.py.
#[pyclass(module = "eschess_native")]
pub struct SelfPlayEngine {
    cfg: Cfg,
}

#[pymethods]
impl SelfPlayEngine {
    #[new]
    #[pyo3(signature = (
        sims = 100,
        c_puct = 1.5,
        dirichlet_alpha = 0.3,
        noise_frac = 0.25,
        temperature = 1.0,
        temp_moves = 30,
        max_moves = 200,
    ))]
    fn new(
        sims: u32,
        c_puct: f32,
        dirichlet_alpha: f64,
        noise_frac: f32,
        temperature: f64,
        temp_moves: u32,
        max_moves: u32,
    ) -> SelfPlayEngine {
        SelfPlayEngine {
            cfg: Cfg {
                sims,
                c_puct,
                dirichlet_alpha,
                noise_frac,
                temperature,
                temp_moves,
                max_moves,
            },
        }
    }

    /// Play `num_games` self-play games, calling `eval_fn` for batched NN
    /// inference. `seed` makes a run reproducible (game `i` is seeded `seed + i`).
    ///
    /// `eval_fn(states: np.ndarray[(N,18,8,8) f32]) -> (logits (N,4096) f32,
    /// values (N,) f32)` — values are from White's perspective, in [-1, 1].
    #[pyo3(signature = (num_games, eval_fn, seed = 0))]
    fn generate(
        &self,
        py: Python<'_>,
        num_games: usize,
        eval_fn: PyObject,
        seed: u64,
    ) -> PyResult<PyObject> {
        let cfg = self.cfg.clone();
        let mut games: Vec<GameState> = (0..num_games)
            .map(|i| GameState::new(StdRng::seed_from_u64(seed.wrapping_add(i as u64)), cfg.c_puct))
            .collect();

        loop {
            // Phase 1 — advance every game to its next NN request (GIL released).
            py.allow_threads(|| {
                games.par_iter_mut().for_each(|g| {
                    if !g.finished && !g.has_pending() {
                        g.prepare(&cfg);
                    }
                });
            });

            // Gather the pending leaves into one contiguous batch.
            let mut row_of: Vec<Option<usize>> = vec![None; num_games];
            let mut flat: Vec<f32> = Vec::new();
            let mut n = 0usize;
            for (i, g) in games.iter().enumerate() {
                if let Some(planes) = g.pending_planes() {
                    row_of[i] = Some(n);
                    flat.extend_from_slice(planes);
                    n += 1;
                }
            }
            if n == 0 {
                break; // every game finished
            }

            // Phase 2 — one batched NN call (holds the GIL).
            let (logits, values) = self.evaluate_batch(py, &eval_fn, flat, n)?;

            // Phase 3 — expand + back up each game with its result (GIL released).
            py.allow_threads(|| {
                games.par_iter_mut().enumerate().for_each(|(i, g)| {
                    if let Some(row) = row_of[i] {
                        let row_logits = &logits[row * POLICY_SIZE..(row + 1) * POLICY_SIZE];
                        g.apply(row_logits, values[row], &cfg);
                    }
                });
            });
        }

        Ok(pack_output(py, &games))
    }
}

impl SelfPlayEngine {
    /// Call the Python `eval_fn` with the batch and copy back the two arrays.
    fn evaluate_batch(
        &self,
        py: Python<'_>,
        eval_fn: &PyObject,
        flat: Vec<f32>,
        n: usize,
    ) -> PyResult<(Vec<f32>, Vec<f32>)> {
        let states = Array4::from_shape_vec((n, 18, 8, 8), flat)
            .expect("batch length matches (n,18,8,8)")
            .into_pyarray_bound(py);
        let result = eval_fn.call1(py, (states,))?;
        let (logits_obj, values_obj): (PyObject, PyObject) = result.extract(py)?;

        let logits: PyReadonlyArray2<f32> = logits_obj.extract(py)?;
        let values: PyReadonlyArray1<f32> = values_obj.extract(py)?;
        let logits_vec = logits.as_slice()?.to_vec();
        let values_vec = values.as_slice()?.to_vec();
        if logits_vec.len() != n * POLICY_SIZE || values_vec.len() != n {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "eval_fn returned shapes {}x?/{} but expected {}x{}/{}",
                logits_vec.len(),
                values_vec.len(),
                n,
                POLICY_SIZE,
                n
            )));
        }
        Ok((logits_vec, values_vec))
    }
}

/// Concatenate every game's recorded plies into the packed return arrays.
fn pack_output(py: Python<'_>, games: &[GameState]) -> PyObject {
    let total: usize = games.iter().map(|g| g.records.len()).sum();

    let mut states = Vec::with_capacity(total * ENCODED_LEN);
    let mut values = Vec::with_capacity(total);
    let mut policy_index: Vec<i64> = Vec::new();
    let mut policy_prob: Vec<f32> = Vec::new();
    let mut offsets: Vec<i64> = Vec::with_capacity(total + 1);
    offsets.push(0);

    for g in games {
        for (planes, target) in &g.records {
            states.extend_from_slice(planes);
            values.push(g.result_white);
            for &(idx, prob) in target {
                policy_index.push(idx as i64);
                policy_prob.push(prob);
            }
            offsets.push(policy_index.len() as i64);
        }
    }

    let states = Array4::from_shape_vec((total, 18, 8, 8), states)
        .expect("states length matches (total,18,8,8)")
        .into_pyarray_bound(py);
    let values = Array1::from_vec(values).into_pyarray_bound(py);
    let policy_index = Array1::from_vec(policy_index).into_pyarray_bound(py);
    let policy_prob = Array1::from_vec(policy_prob).into_pyarray_bound(py);
    let offsets = Array1::from_vec(offsets).into_pyarray_bound(py);

    (states, values, policy_index, policy_prob, offsets).into_py(py)
}
