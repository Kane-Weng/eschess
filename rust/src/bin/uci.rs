//! UCI protocol wrapper for the Rust Eschess engine. Port of python/uci.py and
//! cpp/src/uci.cpp. Supported: uci, isready, ucinewgame, setoption name Hash,
//! position [startpos|fen] moves ..., go [depth|movetime|wtime/btime/winc/binc/
//! movestogo|infinite], stop, quit.

use std::collections::HashMap;
use std::io::{self, BufRead, Write};

use eschess::board::{CBoard, STARTPOS_FEN};
use eschess::evaluate::make_evaluator;
use eschess::search::{Search, MAX_PLY};
use eschess::types::*;

const ENGINE_NAME: &str = "Eschess-rust";
const ENGINE_AUTHOR: &str = "Kane Weng";

const MATE_THRESHOLD: f64 = 8000.0;
const TIME_SAFETY: f64 = 0.85;
const MOVE_OVERHEAD_MS: f64 = 20.0;

fn apply_margin(budget_ms: f64) -> f64 {
    (budget_ms * TIME_SAFETY - MOVE_OVERHEAD_MS).max(10.0)
}

fn square_name(square: i32) -> String {
    let mut s = String::new();
    s.push((b'a' + file_of(square) as u8) as char);
    s.push((b'1' + rank_of(square) as u8) as char);
    s
}

fn name_to_square(name: &[u8]) -> i32 {
    let file_idx = (name[0] - b'a') as i32;
    let rank_idx = (name[1] - b'1') as i32;
    8 * rank_idx + file_idx
}

fn promo_to_char(promotion: i32) -> char {
    match promotion as usize {
        KNIGHT => 'n',
        BISHOP => 'b',
        ROOK => 'r',
        QUEEN => 'q',
        _ => '?',
    }
}

fn char_to_promo(c: u8) -> i32 {
    match c {
        b'n' => KNIGHT as i32,
        b'b' => BISHOP as i32,
        b'r' => ROOK as i32,
        b'q' => QUEEN as i32,
        _ => NO_PIECE,
    }
}

fn move_to_uci(m: &Move) -> String {
    let mut s = square_name(m.from) + &square_name(m.to);
    if m.promotion != NO_PIECE {
        s.push(promo_to_char(m.promotion));
    }
    s
}

fn uci_to_move(text: &str) -> Move {
    let b = text.as_bytes();
    Move {
        from: name_to_square(&b[0..2]),
        to: name_to_square(&b[2..4]),
        promotion: if b.len() > 4 { char_to_promo(b[4]) } else { NO_PIECE },
    }
}

fn score_to_uci(score: f64, white_to_move: bool, pv_len: usize) -> String {
    let stm = if white_to_move { score } else { -score };
    if stm.abs() >= MATE_THRESHOLD {
        let moves = if pv_len > 0 { (pv_len + 1) / 2 } else { 1 } as i64;
        format!("mate {}", if stm > 0.0 { moves } else { -moves })
    } else {
        format!("cp {}", (stm * 100.0).round() as i64)
    }
}

struct UCIEngine {
    board: CBoard,
    search: Search,
    hash_mb: usize,
    eval_level: String,
    multipv: usize,
}

impl UCIEngine {
    fn new() -> UCIEngine {
        UCIEngine {
            board: CBoard::from_fen(STARTPOS_FEN),
            search: Search::new(None, 32),
            hash_mb: 32,
            eval_level: "medium".to_string(),
            multipv: 1,
        }
    }

    fn run(&mut self) {
        let stdin = io::stdin();
        for raw in stdin.lock().lines() {
            let line = match raw {
                Ok(l) => l,
                Err(_) => break,
            };
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let mut it = line.splitn(2, ' ');
            let cmd = it.next().unwrap_or("");
            let rest = it.next().unwrap_or("");

            match cmd {
                "uci" => self.cmd_uci(),
                "isready" => println!("readyok"),
                "ucinewgame" => {
                    self.search.new_game();
                    self.board = CBoard::from_fen(STARTPOS_FEN);
                }
                "setoption" => self.cmd_setoption(rest),
                "position" => self.cmd_position(rest),
                "go" => self.cmd_go(rest),
                "stop" | "ponderhit" => {}
                "quit" => break,
                _ => {}
            }
            io::stdout().flush().ok();
        }
    }

    fn cmd_uci(&self) {
        println!("id name {}", ENGINE_NAME);
        println!("id author {}", ENGINE_AUTHOR);
        println!("option name Hash type spin default 32 min 1 max 1024");
        println!("option name Eval type combo default medium var simple var medium var complex");
        println!("option name MultiPV type spin default 1 min 1 max 5");
        println!("uciok");
    }

    fn cmd_setoption(&mut self, rest: &str) {
        let tokens: Vec<&str> = rest.split_whitespace().collect();
        if tokens.len() >= 4 && tokens[0] == "name" && tokens[tokens.len() - 2] == "value" {
            let name = tokens[1].to_lowercase();
            let value = tokens[tokens.len() - 1].to_lowercase();
            if name == "hash" {
                if let Ok(v) = value.parse::<usize>() {
                    self.hash_mb = v.max(1);
                    self.search = Search::new(Some(make_evaluator(&self.eval_level)), self.hash_mb);
                }
            } else if name == "eval" {
                self.eval_level = value;
                self.search = Search::new(Some(make_evaluator(&self.eval_level)), self.hash_mb);
            } else if name == "multipv" {
                if let Ok(v) = value.parse::<usize>() {
                    self.multipv = v.max(1);
                }
            }
        }
    }

    fn cmd_position(&mut self, rest: &str) {
        let tokens: Vec<&str> = rest.split_whitespace().collect();
        if tokens.is_empty() {
            return;
        }
        let idx;
        if tokens[0] == "startpos" {
            self.board = CBoard::from_fen(STARTPOS_FEN);
            idx = 1;
        } else if tokens[0] == "fen" {
            let fen = tokens[1..tokens.len().min(7)].join(" ");
            self.board = CBoard::from_fen(&fen);
            idx = 7;
        } else {
            return;
        }
        if idx < tokens.len() && tokens[idx] == "moves" {
            for t in &tokens[idx + 1..] {
                let m = uci_to_move(t);
                self.board.make_move(m.from, m.to, m.promotion);
            }
        }
    }

    fn parse_go(&self, rest: &str) -> (HashMap<String, i64>, bool) {
        let tokens: Vec<&str> = rest.split_whitespace().collect();
        let mut params = HashMap::new();
        let mut infinite = false;
        let mut i = 0;
        while i < tokens.len() {
            let key = tokens[i];
            if matches!(
                key,
                "depth" | "movetime" | "wtime" | "btime" | "winc" | "binc" | "movestogo" | "nodes"
            ) {
                if i + 1 < tokens.len() {
                    if let Ok(v) = tokens[i + 1].parse::<i64>() {
                        params.insert(key.to_string(), v);
                    }
                }
                i += 2;
            } else if key == "infinite" {
                infinite = true;
                i += 1;
            } else {
                i += 1;
            }
        }
        (params, infinite)
    }

    fn plan_time(&self, params: &HashMap<String, i64>, infinite: bool) -> (i32, Option<f64>) {
        let max_depth = params.get("depth").map(|&d| d as i32).unwrap_or(64);

        if let Some(&mt) = params.get("movetime") {
            return (max_depth, Some(apply_margin(mt as f64)));
        }
        if params.contains_key("wtime") || params.contains_key("btime") {
            let white = self.board.turn == WHITE;
            let remaining = *params.get(if white { "wtime" } else { "btime" }).unwrap_or(&1000);
            let increment = *params.get(if white { "winc" } else { "binc" }).unwrap_or(&0);
            let movestogo = *params.get("movestogo").unwrap_or(&30);
            let budget = remaining as f64 / movestogo.max(1) as f64 + increment as f64 * 0.8;
            return (max_depth, Some(apply_margin(budget.min(remaining as f64 * 0.9))));
        }
        if params.contains_key("depth") {
            return (max_depth, None);
        }
        if infinite {
            return (max_depth, Some(10000.0));
        }
        (max_depth, Some(apply_margin(1000.0)))
    }

    fn cmd_go(&mut self, rest: &str) {
        let (params, infinite) = self.parse_go(rest);
        let (max_depth, time_limit_ms) = self.plan_time(&params, infinite);
        let white = self.board.turn == WHITE;

        if self.multipv > 1 {
            let depth = if max_depth < MAX_PLY as i32 { max_depth } else { 4 };
            self.go_multipv(depth, white);
            return;
        }

        let mut emit = |depth: i32, score: f64, nodes: i64, elapsed: f64, pv: &[Move]| {
            let nps = if elapsed > 0.0 {
                (nodes as f64 / elapsed) as i64
            } else {
                0
            };
            let pv_text: Vec<String> = pv.iter().map(move_to_uci).collect();
            println!(
                "info depth {} score {} nodes {} nps {} time {} pv {}",
                depth,
                score_to_uci(score, white, pv.len()),
                nodes,
                nps,
                (elapsed * 1000.0) as i64,
                pv_text.join(" ")
            );
            io::stdout().flush().ok();
        };

        let (best_move, _) =
            self.search
                .search_position(&mut self.board, max_depth, time_limit_ms, Some(&mut emit));
        println!(
            "bestmove {}",
            if best_move != NULL_MOVE {
                move_to_uci(&best_move)
            } else {
                "0000".to_string()
            }
        );
    }

    fn go_multipv(&mut self, depth: i32, white: bool) {
        let results = self.search.analyze(&mut self.board, depth);
        if results.is_empty() {
            println!("bestmove 0000");
            return;
        }
        let total_nodes: i64 = results.iter().map(|r| r.node_count).sum();
        let k = self.multipv.min(results.len());
        for (i, r) in results.iter().take(k).enumerate() {
            let pv_text: Vec<String> = r.pv.iter().map(move_to_uci).collect();
            println!(
                "info multipv {} depth {} score {} nodes {} pv {}",
                i + 1,
                depth,
                score_to_uci(r.score, white, r.pv.len()),
                total_nodes,
                pv_text.join(" ")
            );
        }
        let effort: Vec<String> = results
            .iter()
            .map(|r| format!("{}:{}", move_to_uci(&r.mv), r.node_count))
            .collect();
        println!("info string effort {}", effort.join(" "));
        println!("bestmove {}", move_to_uci(&results[0].mv));
        io::stdout().flush().ok();
    }
}

fn main() {
    UCIEngine::new().run();
}
