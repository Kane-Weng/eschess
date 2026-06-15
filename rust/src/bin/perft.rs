//! Perft (performance test): counts leaf nodes of the legal move tree to a
//! given depth, to validate move generation against the Python/C++ engines.
//! Run: cargo run --release --bin perft   (or: ./perft "<fen>" <depth>)

use eschess::board::CBoard;
use eschess::types::*;

const PROMO_PIECES: [i32; 4] = [QUEEN as i32, ROOK as i32, BISHOP as i32, KNIGHT as i32];

fn legal_move_list(board: &mut CBoard) -> Vec<Move> {
    let mut moves = Vec::new();
    for (from, legal_bits) in board.get_all_legal_moves() {
        let mut bits = legal_bits;
        while bits != 0 {
            let to = pop_lsb(&mut bits);
            if board.needs_promotion(from, to) {
                for &promo in &PROMO_PIECES {
                    moves.push(Move { from, to, promotion: promo });
                }
            } else {
                moves.push(Move { from, to, promotion: NO_PIECE });
            }
        }
    }
    moves
}

fn perft(board: &mut CBoard, depth: i32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let mut nodes = 0;
    for m in legal_move_list(board) {
        board.make_move(m.from, m.to, m.promotion);
        nodes += perft(board, depth - 1);
        board.unmake_move();
    }
    nodes
}

/// Run perft for depths 1..=N, comparing against known reference node counts
/// (Chess Programming Wiki). `expected[i]` is the reference for depth `i + 1`.
fn run(name: &str, fen: &str, expected: &[u64]) {
    println!("{}  ({})", name, fen);
    for (i, &reference) in expected.iter().enumerate() {
        let d = i as i32 + 1;
        let mut b = CBoard::from_fen(fen);
        let got = perft(&mut b, d);
        let status = if got == reference { "OK" } else { "MISMATCH" };
        println!("  perft({}) = {}  (expected {}) {}", d, got, reference, status);
    }
    println!();
}

/// Variant for a custom position with no known reference numbers.
fn run_custom(name: &str, fen: &str, max_depth: i32) {
    println!("{}  ({})", name, fen);
    for d in 1..=max_depth {
        let mut b = CBoard::from_fen(fen);
        println!("  perft({}) = {}  (no reference)", d, perft(&mut b, d));
    }
    println!();
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() >= 3 {
        let depth: i32 = args[2].parse().unwrap();
        run_custom("custom", &args[1], depth);
        return;
    }
    run(
        "startpos",
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        &[20, 400, 8902, 197281, 4865609],
    );
    run(
        "kiwipete",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        &[48, 2039, 97862, 4085603],
    );
    run(
        "position3",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        &[14, 191, 2812, 43238, 674624],
    );
    run(
        "position4",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        &[6, 264, 9467, 422333],
    );
}
