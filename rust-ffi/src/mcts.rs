//! Native PUCT MCTS and per-game self-play state machine.
//!
//! This is a faithful port of python/nn/mcts.py + python/nn/selfplay.py, with
//! one structural change for batching: a game never blocks on a neural-net call.
//! Instead each game descends to a leaf, hands back the encoded planes as a
//! *request*, and is resumed via `apply` once the batched NN result is known.
//! The driver in selfplay.rs runs many games in lockstep so every NN call sees a
//! full batch (see `SelfPlayEngine::generate`).
//!
//! Sign convention matches mcts.py: every node value is from the perspective of
//! the side to move at that node; a parent reads a child's mean value negated.
//!
//! The MCTS tree only adjudicates the no-legal-move terminals (checkmate /
//! stalemate), exactly like `_terminal_value`; the 50-move / threefold /
//! insufficient-material draws are layered on by the per-game loop, exactly like
//! `game_outcome`.

use std::collections::HashMap;

use rand::rngs::StdRng;
use rand::Rng;
use rand_distr::{Dirichlet, Distribution};

use eschess::board::CBoard;
use eschess::types::*;

use crate::encoding::encode;
use crate::moves::legal_movekeys;

/// (from, to) move identity within the tree (queen-only promotions, like the
/// policy head).
pub type MoveKey = (u8, u8);

/// Static search / self-play configuration shared by every game in a batch.
#[derive(Clone)]
pub struct Cfg {
    pub sims: u32,
    pub c_puct: f32,
    pub dirichlet_alpha: f64,
    pub noise_frac: f32,
    pub temperature: f64,
    pub temp_moves: u32,
    pub max_moves: u32,
}

/// One node in the arena-allocated search tree.
struct Node {
    prior: f32,
    visit: u32,
    value_sum: f32,
    children: Vec<(MoveKey, usize)>,
    expanded: bool,
}

impl Node {
    fn new(prior: f32) -> Node {
        Node {
            prior,
            visit: 0,
            value_sum: 0.0,
            children: Vec::new(),
            expanded: false,
        }
    }
    fn mean_value(&self) -> f32 {
        if self.visit > 0 {
            self.value_sum / self.visit as f32
        } else {
            0.0
        }
    }
}

/// A leaf awaiting NN evaluation: enough state to expand + back up once the
/// policy logits / value for this position are known.
pub struct LeafRequest {
    path: Vec<usize>,
    leaf: usize,
    legal: Vec<MoveKey>,
    leaf_turn: usize,
    is_root: bool,
    /// Encoded planes for the leaf position (length ENCODED_LEN).
    pub planes: Vec<f32>,
}

/// One self-play game's full state: board, repetition table, search tree for the
/// current ply, recorded training rows, and the outstanding NN request (if any).
pub struct GameState {
    board: CBoard,
    rep: HashMap<u64, u16>,
    /// (planes, sparse policy target) per played ply; value filled in at the end.
    #[allow(clippy::type_complexity)]
    pub records: Vec<(Vec<f32>, Vec<(u32, f32)>)>,
    pub finished: bool,
    pub result_white: f32,

    nodes: Vec<Node>,
    root: usize,
    root_planes: Vec<f32>,
    root_expanded: bool,
    sims_done: u32,
    move_num: u32,
    ply_started: bool,
    pending: Option<LeafRequest>,
    rng: StdRng,
    /// PUCT exploration constant, cached here for the hot `select_child` path.
    cfg_c_puct: f32,
}

impl GameState {
    pub fn new(rng: StdRng, c_puct: f32) -> GameState {
        let board = CBoard::new();
        let mut rep = HashMap::new();
        rep.insert(board.zobrist_key, 1);
        GameState {
            board,
            rep,
            records: Vec::new(),
            finished: false,
            result_white: 0.0,
            nodes: Vec::new(),
            root: 0,
            root_planes: Vec::new(),
            root_expanded: false,
            sims_done: 0,
            move_num: 0,
            ply_started: false,
            pending: None,
            rng,
            cfg_c_puct: c_puct,
        }
    }

    pub fn has_pending(&self) -> bool {
        self.pending.is_some()
    }

    /// Borrow the pending request's planes for batching (caller copies them out).
    pub fn pending_planes(&self) -> Option<&[f32]> {
        self.pending.as_ref().map(|p| p.planes.as_slice())
    }

    // -- Driver-facing steps -------------------------------------------------

    /// Advance the game (no NN needed for terminal-only sims) until either a
    /// leaf needs evaluation (sets `pending`) or the game finishes.
    pub fn prepare(&mut self, cfg: &Cfg) {
        loop {
            if self.finished {
                return;
            }
            if !self.ply_started {
                self.start_ply(cfg);
                if self.finished {
                    return;
                }
            }
            if !self.root_expanded {
                // The root is never terminal here (game_outcome was just checked).
                let legal = legal_movekeys(&mut self.board);
                self.pending = Some(LeafRequest {
                    path: vec![self.root],
                    leaf: self.root,
                    legal,
                    leaf_turn: self.board.turn,
                    is_root: true,
                    planes: self.root_planes.clone(),
                });
                return;
            }
            if self.sims_done >= cfg.sims {
                self.finish_ply(cfg);
                continue; // start the next ply (or finish the game)
            }
            match self.one_sim() {
                Step::Terminal => {
                    self.sims_done += 1;
                    continue;
                }
                Step::Pending(req) => {
                    self.pending = Some(req);
                    return;
                }
            }
        }
    }

    /// Resume a game with the NN result for its pending leaf: expand the leaf
    /// with the policy priors and back up the value.
    pub fn apply(&mut self, logits: &[f32], value_white: f32, cfg: &Cfg) {
        let req = match self.pending.take() {
            Some(r) => r,
            None => return,
        };

        let mut priors = softmax_over_legal(logits, &req.legal);
        if req.is_root {
            self.apply_noise(&mut priors, cfg);
        }

        let mut children = Vec::with_capacity(priors.len());
        for (mk, prob) in priors {
            let idx = self.nodes.len();
            self.nodes.push(Node::new(prob));
            children.push((mk, idx));
        }
        let leaf = req.leaf;
        self.nodes[leaf].children = children;
        self.nodes[leaf].expanded = true;

        let stm_value = if req.leaf_turn == WHITE {
            value_white
        } else {
            -value_white
        };
        backup(&mut self.nodes, &req.path, stm_value);

        if req.is_root {
            self.root_expanded = true;
        } else {
            self.sims_done += 1;
        }
    }

    // -- Internals -----------------------------------------------------------

    fn start_ply(&mut self, cfg: &Cfg) {
        if let Some(result) = self.outcome(cfg) {
            self.finalize(result);
            return;
        }
        if self.move_num >= cfg.max_moves {
            self.finalize(0.0); // over-long game adjudicated as a draw
            return;
        }
        self.nodes.clear();
        self.nodes.push(Node::new(1.0));
        self.root = 0;
        self.root_planes = encode(&self.board);
        self.root_expanded = false;
        self.sims_done = 0;
        self.ply_started = true;
    }

    /// Run one simulation from the (already expanded) root. Returns whether the
    /// leaf was terminal (handled inline) or needs NN evaluation.
    fn one_sim(&mut self) -> Step {
        let mut path = vec![self.root];
        let mut node = self.root;

        // Selection: descend, making moves, until an unexpanded/childless node.
        loop {
            if !self.nodes[node].expanded || self.nodes[node].children.is_empty() {
                break;
            }
            let (mk, child) = self.select_child(node);
            let promo = if self.board.needs_promotion(mk.0 as i32, mk.1 as i32) {
                QUEEN as i32
            } else {
                NO_PIECE
            };
            self.board.make_move(mk.0 as i32, mk.1 as i32, promo);
            path.push(child);
            node = child;
        }

        let leaf = node;
        let leaf_turn = self.board.turn;
        let legal = legal_movekeys(&mut self.board);

        if legal.is_empty() {
            // Terminal (mate/stalemate) from the leaf's perspective.
            let value = if self.board.is_in_check(leaf_turn) {
                -1.0
            } else {
                0.0
            };
            self.unwind(path.len() - 1);
            backup(&mut self.nodes, &path, value);
            return Step::Terminal;
        }

        let planes = encode(&self.board);
        self.unwind(path.len() - 1);
        Step::Pending(LeafRequest {
            path,
            leaf,
            legal,
            leaf_turn,
            is_root: false,
            planes,
        })
    }

    fn select_child(&self, node: usize) -> (MoveKey, usize) {
        let parent = &self.nodes[node];
        let sqrt_total = (parent.visit as f32).sqrt();
        let mut best_score = f32::NEG_INFINITY;
        let mut best = parent.children[0];
        for &(mk, child) in &parent.children {
            let c = &self.nodes[child];
            let q = -c.mean_value(); // child is the opponent's turn
            let u = self.c_puct() * c.prior * sqrt_total / (1.0 + c.visit as f32);
            let score = q + u;
            if score > best_score {
                best_score = score;
                best = (mk, child);
            }
        }
        best
    }

    fn finish_ply(&mut self, cfg: &Cfg) {
        // Visit counts of the root's children become the training policy target.
        let mut total: u32 = 0;
        let mut counts: Vec<(MoveKey, u32)> =
            Vec::with_capacity(self.nodes[self.root].children.len());
        for &(mk, child) in &self.nodes[self.root].children {
            let v = self.nodes[child].visit;
            total += v;
            counts.push((mk, v));
        }
        let mut target = Vec::new();
        if total > 0 {
            for &(mk, v) in &counts {
                if v > 0 {
                    let index = mk.0 as u32 * 64 + mk.1 as u32;
                    target.push((index, v as f32 / total as f32));
                }
            }
        }
        self.records
            .push((std::mem::take(&mut self.root_planes), target));

        let temp = if self.move_num < cfg.temp_moves {
            cfg.temperature
        } else {
            0.0
        };
        let (from, to) = self.select_move(&counts, temp);
        let promo = if self.board.needs_promotion(from as i32, to as i32) {
            QUEEN as i32
        } else {
            NO_PIECE
        };
        self.board.make_move(from as i32, to as i32, promo);
        *self.rep.entry(self.board.zobrist_key).or_insert(0) += 1;
        self.move_num += 1;
        self.ply_started = false;
    }

    /// Pick a move from visit counts: greedy at temperature 0, else sampled
    /// proportionally to count^(1/temperature). Mirrors `select_move`.
    fn select_move(&mut self, counts: &[(MoveKey, u32)], temperature: f64) -> MoveKey {
        if temperature <= 1e-6 {
            let mut best = counts[0];
            for &c in counts {
                if c.1 > best.1 {
                    best = c;
                }
            }
            return best.0;
        }
        let inv = 1.0 / temperature;
        let weights: Vec<f64> = counts.iter().map(|&(_, n)| (n as f64).powf(inv)).collect();
        let sum: f64 = weights.iter().sum();
        let mut r = self.rng.gen::<f64>() * sum;
        for (i, &w) in weights.iter().enumerate() {
            r -= w;
            if r <= 0.0 {
                return counts[i].0;
            }
        }
        counts[counts.len() - 1].0
    }

    fn apply_noise(&mut self, priors: &mut [(MoveKey, f32)], cfg: &Cfg) {
        let k = priors.len();
        if k < 2 {
            return; // Dirichlet undefined for <2 moves; mixing leaves prior at 1.0
        }
        let dir = match Dirichlet::new(&vec![cfg.dirichlet_alpha; k]) {
            Ok(d) => d,
            Err(_) => return,
        };
        let noise = dir.sample(&mut self.rng);
        let frac = cfg.noise_frac;
        for (i, entry) in priors.iter_mut().enumerate() {
            entry.1 = (1.0 - frac) * entry.1 + frac * noise[i] as f32;
        }
    }

    /// White-perspective terminal result, or None while the game is live.
    /// Mirrors selfplay.py `game_outcome`.
    fn outcome(&mut self, _cfg: &Cfg) -> Option<f32> {
        if legal_movekeys(&mut self.board).is_empty() {
            if self.board.is_in_check(self.board.turn) {
                return Some(if self.board.turn == WHITE { -1.0 } else { 1.0 });
            }
            return Some(0.0); // stalemate
        }
        if self.board.halfmove_clock >= 100 {
            return Some(0.0); // fifty-move rule
        }
        if self.rep.get(&self.board.zobrist_key).copied().unwrap_or(0) >= 3 {
            return Some(0.0); // threefold repetition
        }
        if insufficient_material(&self.board) {
            return Some(0.0);
        }
        None
    }

    fn finalize(&mut self, result_white: f32) {
        self.result_white = result_white;
        self.finished = true;
    }

    fn unwind(&mut self, n: usize) {
        for _ in 0..n {
            self.board.unmake_move();
        }
    }

    #[inline]
    fn c_puct(&self) -> f32 {
        self.cfg_c_puct
    }
}

enum Step {
    Terminal,
    Pending(LeafRequest),
}

fn backup(nodes: &mut [Node], path: &[usize], mut value: f32) {
    for &idx in path.iter().rev() {
        let n = &mut nodes[idx];
        n.visit += 1;
        n.value_sum += value;
        value = -value;
    }
}

/// Softmax of the policy logits restricted to the legal (from, to) moves.
/// Mirrors `policy_priors` (subtract max, exp, normalize).
fn softmax_over_legal(logits: &[f32], legal: &[MoveKey]) -> Vec<(MoveKey, f32)> {
    let mut out: Vec<(MoveKey, f32)> = Vec::with_capacity(legal.len());
    let mut max = f32::NEG_INFINITY;
    for &(f, t) in legal {
        let v = logits[f as usize * 64 + t as usize];
        if v > max {
            max = v;
        }
    }
    let mut sum = 0.0f32;
    for &(f, t) in legal {
        let w = (logits[f as usize * 64 + t as usize] - max).exp();
        sum += w;
        out.push(((f, t), w));
    }
    if sum > 0.0 {
        for entry in &mut out {
            entry.1 /= sum;
        }
    }
    out
}

/// Trivial-draw material check. Mirrors selfplay.py `_insufficient_material`.
fn insufficient_material(board: &CBoard) -> bool {
    for pt in [PAWN, ROOK, QUEEN] {
        if board.get_specific_pieces(WHITE, pt) != 0 || board.get_specific_pieces(BLACK, pt) != 0 {
            return false;
        }
    }
    let mut minors = 0i32;
    for pt in [KNIGHT, BISHOP] {
        minors += board.get_specific_pieces(WHITE, pt).count_ones() as i32;
        minors += board.get_specific_pieces(BLACK, pt).count_ones() as i32;
    }
    minors <= 1
}
