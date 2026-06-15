//! Alpha-beta minimax with iterative deepening, transposition table,
//! quiescence, MVV-LVA / killer / history move ordering. Port of
//! python/engine/search.py and cpp/src/search.cpp. Scores are in pawn units
//! from White's perspective.

use std::collections::HashSet;
use std::time::{Duration, Instant};

use crate::board::CBoard;
use crate::evaluate::{BaseEvaluate, MediumEvaluate};
use crate::tt::{TTFlag, TranspositionTable};
use crate::types::*;

pub const MAX_PLY: usize = 64;
pub const MAX_HISTORY: i32 = 16384;
pub const QS_DEPTH: i32 = 8;

// Centipawn values for MVV-LVA ordering (matches _CP in search.py).
const CP: [i32; 6] = [100, 320, 330, 500, 900, 0];
const PROMO_PIECES: [i32; 4] = [QUEEN as i32, ROOK as i32, BISHOP as i32, KNIGHT as i32];

/// Expand legal moves into (from, to, promo). With captures_only, keep only
/// captures and (queen) promotions. Mirrors _flat_moves in search.py.
fn flat_moves(board: &mut CBoard, captures_only: bool) -> Vec<Move> {
    let occ = board.occupied();
    let mut moves = Vec::new();
    for (from_square, legal_bits) in board.get_all_legal_moves() {
        let mut bits = legal_bits;
        while bits != 0 {
            let to_square = pop_lsb(&mut bits);
            let is_capture = occ & (1u64 << to_square) != 0;
            let is_promo = board.needs_promotion(from_square, to_square);
            if captures_only && !is_capture && !is_promo {
                continue;
            }
            if is_promo {
                if captures_only {
                    moves.push(Move {
                        from: from_square,
                        to: to_square,
                        promotion: QUEEN as i32,
                    });
                } else {
                    for &promo in &PROMO_PIECES {
                        moves.push(Move {
                            from: from_square,
                            to: to_square,
                            promotion: promo,
                        });
                    }
                }
            } else {
                moves.push(Move {
                    from: from_square,
                    to: to_square,
                    promotion: NO_PIECE,
                });
            }
        }
    }
    moves
}

/// Floor division (Python //) for the history gravity term; denominator > 0.
#[inline]
fn floordiv(a: i64, b: i32) -> i32 {
    let b = b as i64;
    let mut q = a / b;
    if a % b != 0 && a < 0 {
        q -= 1;
    }
    q as i32
}

pub struct Search {
    evaluate: Box<dyn BaseEvaluate>,
    tt: TranspositionTable,
    killers: [[Move; 2]; MAX_PLY],
    history: Vec<i32>, // [2][64][64] flattened
    nodes: i64,
    deadline: Option<Instant>,
    stop: bool,
}

#[inline]
fn hist_idx(color: usize, from: i32, to: i32) -> usize {
    (color * 64 * 64) + (from as usize * 64) + to as usize
}

pub type InfoCallback<'a> = dyn FnMut(i32, f64, i64, f64, &[Move]) + 'a;

impl Search {
    pub fn new(evaluator: Option<Box<dyn BaseEvaluate>>, tt_size_mb: usize) -> Search {
        let mut s = Search {
            evaluate: evaluator.unwrap_or_else(|| Box::new(MediumEvaluate)),
            tt: TranspositionTable::new(tt_size_mb),
            killers: [[NULL_MOVE; 2]; MAX_PLY],
            history: vec![0; 2 * 64 * 64],
            nodes: 0,
            deadline: None,
            stop: false,
        };
        s.new_game();
        s
    }

    pub fn new_game(&mut self) {
        self.killers = [[NULL_MOVE; 2]; MAX_PLY];
        for v in self.history.iter_mut() {
            *v = 0;
        }
    }

    fn update_history(&mut self, color: usize, from_square: i32, to_square: i32, depth: i32) {
        let bonus = (depth * depth).min(MAX_HISTORY);
        let clamped = bonus.clamp(-MAX_HISTORY, MAX_HISTORY);
        let idx = hist_idx(color, from_square, to_square);
        let cur = self.history[idx];
        self.history[idx] += clamped - floordiv(cur as i64 * clamped.abs() as i64, MAX_HISTORY);
    }

    fn age_history(&mut self) {
        for v in self.history.iter_mut() {
            *v >>= 1;
        }
    }

    fn order_key(&self, board: &CBoard, mv: &Move, ply: usize, tt_move: &Move) -> i32 {
        if mv == tt_move {
            return 20000;
        }
        if mv.promotion == QUEEN as i32 {
            return 10000;
        }
        if mv.promotion != NO_PIECE {
            return 9000;
        }
        let captured = board.get_piece_at(mv.to);
        if !captured.is_empty() {
            let aggressor = board.get_piece_at(mv.from);
            let agg_val = if aggressor.is_empty() {
                0
            } else {
                CP[aggressor.ptype as usize]
            };
            return 5000 + CP[captured.ptype as usize] * 10 - agg_val;
        }
        if self.killers[ply][0] == *mv {
            return 4000;
        }
        if self.killers[ply][1] == *mv {
            return 3000;
        }
        self.history[hist_idx(board.turn, mv.from, mv.to)]
    }

    #[inline]
    fn time_up(&self) -> bool {
        matches!(self.deadline, Some(d) if Instant::now() >= d)
    }

    fn quiescence(&mut self, board: &mut CBoard, mut alpha: f64, mut beta: f64, qdepth: i32) -> f64 {
        self.nodes += 1;
        if self.deadline.is_some() && (self.nodes & 255) == 0 && self.time_up() {
            self.stop = true;
        }
        let stand_pat = self.evaluate.evaluate(board);
        if self.stop {
            return stand_pat;
        }
        let maximizing = board.turn == WHITE;

        if maximizing {
            if stand_pat >= beta {
                return stand_pat;
            }
            if stand_pat > alpha {
                alpha = stand_pat;
            }
        } else {
            if stand_pat <= alpha {
                return stand_pat;
            }
            if stand_pat < beta {
                beta = stand_pat;
            }
        }

        if qdepth >= QS_DEPTH {
            return stand_pat;
        }

        let captures = flat_moves(board, true);
        // MVV ordering by captured-piece value (stable, matches Python list.sort).
        let mut keyed: Vec<(i32, Move)> = captures
            .into_iter()
            .map(|m| {
                let cap = board.get_piece_at(m.to);
                let v = if cap.is_empty() {
                    0
                } else {
                    CP[cap.ptype as usize]
                };
                (v, m)
            })
            .collect();
        keyed.sort_by(|a, b| b.0.cmp(&a.0));

        for (_, mv) in keyed {
            board.make_move(mv.from, mv.to, mv.promotion);
            let score = self.quiescence(board, alpha, beta, qdepth + 1);
            board.unmake_move();
            if maximizing {
                if score > alpha {
                    alpha = score;
                }
                if alpha >= beta {
                    return alpha;
                }
            } else {
                if score < beta {
                    beta = score;
                }
                if beta <= alpha {
                    return beta;
                }
            }
        }
        if maximizing {
            alpha
        } else {
            beta
        }
    }

    fn minimax(
        &mut self,
        board: &mut CBoard,
        depth: i32,
        mut alpha: f64,
        mut beta: f64,
        ply: usize,
    ) -> (f64, Move) {
        if self.stop {
            return (0.0, NULL_MOVE);
        }
        self.nodes += 1;
        if self.deadline.is_some() && (self.nodes & 255) == 0 && self.time_up() {
            self.stop = true;
            return (0.0, NULL_MOVE);
        }

        let orig_alpha = alpha;

        let key = board.zobrist_key;
        let mut tt_move = NULL_MOVE;
        if let Some(entry) = self.tt.probe(key) {
            tt_move = entry.best_move;
            if entry.depth >= depth {
                match entry.flag {
                    TTFlag::Exact => return (entry.score, entry.best_move),
                    TTFlag::Lower => alpha = alpha.max(entry.score),
                    TTFlag::Upper => beta = beta.min(entry.score),
                }
                if alpha >= beta {
                    return (entry.score, entry.best_move);
                }
            }
        }

        let legal_moves = flat_moves(board, false);
        if legal_moves.is_empty() {
            if board.is_in_check(board.turn) {
                return (
                    if board.turn == WHITE {
                        -9000.0 - depth as f64
                    } else {
                        9000.0 + depth as f64
                    },
                    NULL_MOVE,
                );
            }
            return (0.0, NULL_MOVE); // stalemate
        }

        if depth == 0 {
            return (self.quiescence(board, alpha, beta, 0), NULL_MOVE);
        }

        let mut keyed: Vec<(i32, Move)> = legal_moves
            .into_iter()
            .map(|m| (self.order_key(board, &m, ply, &tt_move), m))
            .collect();
        keyed.sort_by(|a, b| b.0.cmp(&a.0));

        let maximizing = board.turn == WHITE;
        let mut have_best = false;
        let mut best_eval = 0.0;
        let mut best_move = NULL_MOVE;

        for (_, mv) in keyed {
            let is_quiet = mv.promotion == NO_PIECE && board.get_piece_at(mv.to).is_empty();

            board.make_move(mv.from, mv.to, mv.promotion);
            let (eval_score, _) = self.minimax(board, depth - 1, alpha, beta, ply + 1);
            board.unmake_move();

            if self.stop {
                return (if have_best { best_eval } else { 0.0 }, best_move);
            }

            if maximizing {
                if !have_best || eval_score > best_eval {
                    best_eval = eval_score;
                    best_move = mv;
                    have_best = true;
                }
                alpha = alpha.max(best_eval);
            } else {
                if !have_best || eval_score < best_eval {
                    best_eval = eval_score;
                    best_move = mv;
                    have_best = true;
                }
                beta = beta.min(best_eval);
            }

            if beta <= alpha {
                if is_quiet && ply < MAX_PLY {
                    if self.killers[ply][0] != mv {
                        self.killers[ply][1] = self.killers[ply][0];
                        self.killers[ply][0] = mv;
                    }
                    self.update_history(board.turn, mv.from, mv.to, depth);
                }
                break;
            }
        }

        let flag = if best_eval <= orig_alpha {
            TTFlag::Upper
        } else if best_eval >= beta {
            TTFlag::Lower
        } else {
            TTFlag::Exact
        };
        self.tt.store(key, depth, flag, best_eval, best_move);

        (best_eval, best_move)
    }

    fn first_legal_move(&self, board: &mut CBoard) -> Move {
        for (from_square, legal_bits) in board.get_all_legal_moves() {
            if legal_bits != 0 {
                let to_square = lsb_index(legal_bits);
                let promo = if board.needs_promotion(from_square, to_square) {
                    QUEEN as i32
                } else {
                    NO_PIECE
                };
                return Move {
                    from: from_square,
                    to: to_square,
                    promotion: promo,
                };
            }
        }
        NULL_MOVE
    }

    fn extract_pv(&self, board: &mut CBoard, max_len: i32) -> Vec<Move> {
        let mut pv = Vec::new();
        let mut seen: HashSet<U64> = HashSet::new();
        let mut applied = 0;
        for _ in 0..max_len {
            if seen.contains(&board.zobrist_key) {
                break;
            }
            seen.insert(board.zobrist_key);
            let entry = match self.tt.probe(board.zobrist_key) {
                Some(e) if e.best_move != NULL_MOVE => *e,
                _ => break,
            };
            let m = entry.best_move;
            if board.get_legal_moves(m.from) & (1u64 << m.to) == 0 {
                break;
            }
            pv.push(m);
            board.make_move(m.from, m.to, m.promotion);
            applied += 1;
        }
        for _ in 0..applied {
            board.unmake_move();
        }
        pv
    }

    pub fn get_best_move(&mut self, board: &mut CBoard, depth: i32) -> Move {
        self.search_position(board, depth, None, None).0
    }

    pub fn search_position(
        &mut self,
        board: &mut CBoard,
        max_depth: i32,
        time_limit_ms: Option<f64>,
        mut info_callback: Option<&mut InfoCallback>,
    ) -> (Move, f64) {
        self.killers = [[NULL_MOVE; 2]; MAX_PLY];
        self.age_history();
        self.nodes = 0;
        self.stop = false;

        let start = Instant::now();
        let budget_s = time_limit_ms.filter(|&ms| ms > 0.0).map(|ms| ms / 1000.0);
        self.deadline = budget_s.map(|s| start + Duration::from_secs_f64(s));

        let mut best_move = self.first_legal_move(board);
        let mut best_score = 0.0;
        let mut completed_any = false;

        for d in 1..=max_depth.max(1) {
            let (score, mv) = self.minimax(board, d, -99999.0, 99999.0, 0);
            if self.stop {
                if !completed_any && mv != NULL_MOVE {
                    best_move = mv;
                }
                break;
            }
            if mv != NULL_MOVE {
                best_move = mv;
                best_score = score;
                completed_any = true;
            }
            if let Some(cb) = info_callback.as_deref_mut() {
                let elapsed = start.elapsed().as_secs_f64();
                let pv = self.extract_pv(board, d);
                cb(d, best_score, self.nodes, elapsed, &pv);
            }
            if best_score.abs() > 8000.0 {
                break;
            }
            if let Some(b) = budget_s {
                if start.elapsed().as_secs_f64() >= b * 0.5 {
                    break;
                }
            }
        }

        (best_move, best_score)
    }
}
