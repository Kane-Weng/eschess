//! Chess board: representation, move generation, legality, make/unmake, game
//! state. 1:1 port of CBoard in python/engine/board.py and cpp/src/board.cpp.

// Import modules; crate is 'abs path starting at the root module'
use crate::types::*;
use crate::zobrist;

// pub is akin to constexpr (compiled time constants)
pub const STARTPOS_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// Array syntax specifies [Type; Size]; b'p' (byte literals) directly evaluates char ASCII as a u8
const PIECE_TO_FEN: [u8; 6] = [b'p', b'n', b'b', b'r', b'q', b'k'];

fn fen_to_piece(c: char) -> usize {
    match c.to_ascii_lowercase() {
        // control flow: switch-statement variant
        'p' => PAWN,
        'n' => KNIGHT,
        'b' => BISHOP,
        'r' => ROOK,
        'q' => QUEEN,
        'k' => KING,
        _ => unreachable!(), // default in cpp
    }
}

fn square_name(square: i32) -> String {
    let mut s = String::new();
    s.push((b'a' + file_of(square) as u8) as char);
    s.push((b'1' + rank_of(square) as u8) as char);
    s // Implicit Returns
}

fn name_to_square(name: &str) -> i32 {
    let b = name.as_bytes();
    let file_idx = (b[0] - b'a') as i32;
    let rank_idx = (b[1] - b'1') as i32;
    8 * rank_idx + file_idx
}

/// Result of get_piece_at: type == NO_PIECE means the square is empty.
#[derive(Clone, Copy)]
pub struct Piece {
    pub color: i32,
    pub ptype: i32,
}
impl Piece {
    #[inline]
    pub fn is_empty(&self) -> bool {
        self.ptype == NO_PIECE
    }
}

// Undo record stored per move (mirrors the Python Move dataclass fields).
#[derive(Clone, Copy)]
struct Undo {
    from: i32,
    to: i32,
    captured_piece: i32,
    captured_color: i32,
    promotion: i32,
    is_en_passant: bool,
    is_castle: bool,
    castle_rook_from: i32,
    castle_rook_to: i32,
    prev_en_passant_square: i32,
    prev_castling_rights: i32,
    prev_halfmove_clock: i32,
    prev_zobrist_key: U64,
}

pub struct CBoard {
    pub colors: [U64; 2],
    pub pieces: [U64; 6],
    pub turn: usize,
    pub en_passant_square: i32, // -1 == none
    pub castling_rights: i32,
    pub halfmove_clock: i32,
    pub fullmove: i32,
    pub game_over: bool,
    pub winner: i32, // Color, or -1 for stalemate / none
    pub zobrist_key: U64,
    move_history: Vec<Undo>,
}

impl CBoard {
    pub fn new() -> CBoard {
        let mut b = CBoard {
            colors: [0, 0],
            pieces: [0; 6],
            turn: WHITE,
            en_passant_square: -1,
            castling_rights: 0b1111,
            halfmove_clock: 0,
            fullmove: 1,
            game_over: false,
            winner: -1,
            zobrist_key: 0,
            move_history: Vec::with_capacity(64), // similar to vec.reserve(64) in cpp
        };
        b.set_pieces();
        b.zobrist_key = b.compute_zobrist();
        b
    }

    pub fn from_fen(fen: &str) -> CBoard {
        let mut b = CBoard::new();
        b.set_fen(fen);
        b
    }

    fn set_pieces(&mut self) {
        self.colors[WHITE] = 0x0000_0000_0000_FFFF;
        self.colors[BLACK] = 0xFFFF_0000_0000_0000;
        self.pieces[PAWN] = 0x00FF_0000_0000_FF00;
        self.pieces[KNIGHT] = 0x4200_0000_0000_0042;
        self.pieces[BISHOP] = 0x2400_0000_0000_0024;
        self.pieces[ROOK] = 0x8100_0000_0000_0081;
        self.pieces[QUEEN] = 0x0800_0000_0000_0008;
        self.pieces[KING] = 0x1000_0000_0000_0010;
    }

    pub fn set_fen(&mut self, fen: &str) {
        let parts: Vec<&str> = fen.split_whitespace().collect();
        if parts.len() < 4 {
            panic!("Invalid FEN (need >=4 fields): {}", fen);
        }
        self.colors = [0, 0];
        self.pieces = [0; 6];

        let mut rank_idx: i32 = 7;
        let mut file_idx: i32 = 0;
        for ch in parts[0].chars() {
            if ch == '/' {
                rank_idx -= 1;
                file_idx = 0;
            } else if ch.is_ascii_digit() {
                file_idx += ch as i32 - '0' as i32;
            } else {
                let color = if ch.is_ascii_uppercase() {
                    WHITE
                } else {
                    BLACK
                };
                self.set_piece(color, fen_to_piece(ch), 8 * rank_idx + file_idx);
                file_idx += 1;
            }
        }

        self.turn = if parts[1] == "w" { WHITE } else { BLACK };
        let mut cr = 0;
        if parts[2].contains('K') {
            cr |= CR_WK;
        }
        if parts[2].contains('Q') {
            cr |= CR_WQ;
        }
        if parts[2].contains('k') {
            cr |= CR_BK;
        }
        if parts[2].contains('q') {
            cr |= CR_BQ;
        }
        self.castling_rights = cr;
        self.en_passant_square = if parts[3] == "-" {
            -1
        } else {
            name_to_square(parts[3])
        };
        self.halfmove_clock = parts.get(4).and_then(|s| s.parse().ok()).unwrap_or(0);
        self.fullmove = parts.get(5).and_then(|s| s.parse().ok()).unwrap_or(1);

        self.move_history.clear();
        self.game_over = false;
        self.winner = -1;
        self.zobrist_key = self.compute_zobrist();
    }

    pub fn to_fen(&self) -> String {
        let mut rows = String::new();
        for rank_idx in (0..8).rev() {
            let mut row = String::new();
            let mut empty = 0;
            for file_idx in 0..8 {
                let info = self.get_piece_at(8 * rank_idx + file_idx);
                if info.is_empty() {
                    empty += 1;
                    continue;
                }
                if empty > 0 {
                    row.push_str(&empty.to_string());
                    empty = 0;
                }
                let ch = PIECE_TO_FEN[info.ptype as usize] as char;
                row.push(if info.color == WHITE as i32 {
                    ch.to_ascii_uppercase()
                } else {
                    ch
                });
            }
            if empty > 0 {
                row.push_str(&empty.to_string());
            }
            if rank_idx != 7 {
                rows.push('/');
            }
            rows.push_str(&row);
        }

        let side = if self.turn == WHITE { "w" } else { "b" };
        let mut cr = String::new();
        if self.castling_rights & CR_WK != 0 {
            cr.push('K');
        }
        if self.castling_rights & CR_WQ != 0 {
            cr.push('Q');
        }
        if self.castling_rights & CR_BK != 0 {
            cr.push('k');
        }
        if self.castling_rights & CR_BQ != 0 {
            cr.push('q');
        }
        if cr.is_empty() {
            cr.push('-');
        }
        let ep = if self.en_passant_square < 0 {
            "-".to_string()
        } else {
            square_name(self.en_passant_square)
        };
        format!(
            "{} {} {} {} {} {}",
            rows, side, cr, ep, self.halfmove_clock, self.fullmove
        )
    }

    fn compute_zobrist(&self) -> U64 {
        let z = zobrist::tables();
        let mut key: U64 = 0;
        for color in 0..2 {
            for pt in 0..6 {
                let mut b = self.get_specific_pieces(color, pt);
                while b != 0 {
                    key ^= z.piece[color][pt][pop_lsb(&mut b) as usize];
                }
            }
        }
        if self.turn == BLACK {
            key ^= z.turn;
        }
        key ^= z.castle[(self.castling_rights & 0xF) as usize];
        if self.en_passant_square >= 0 {
            key ^= z.ep[(self.en_passant_square & 7) as usize];
        }
        key
    }

    // ── Queries ──────────────────────────────────────────────────────────────
    #[inline]
    pub fn occupied(&self) -> U64 {
        self.colors[WHITE] | self.colors[BLACK]
    }
    #[inline]
    pub fn get_specific_pieces(&self, color: usize, piece_type: usize) -> U64 {
        self.colors[color] & self.pieces[piece_type]
    }

    pub fn get_piece_at(&self, square: i32) -> Piece {
        let bits = square_to_bits(square);
        for color in 0..2 {
            if self.colors[color] & bits != 0 {
                for pt in 0..6 {
                    if self.pieces[pt] & bits != 0 {
                        return Piece {
                            color: color as i32,
                            ptype: pt as i32,
                        };
                    }
                }
            }
        }
        Piece {
            color: -1,
            ptype: NO_PIECE,
        }
    }

    fn king_square(&self, color: usize) -> i32 {
        lsb_index(self.get_specific_pieces(color, KING))
    }

    #[inline]
    fn set_piece(&mut self, color: usize, piece_type: usize, square: i32) {
        let bits = square_to_bits(square);
        self.colors[color] |= bits;
        self.pieces[piece_type] |= bits;
    }
    #[inline]
    fn clear_piece(&mut self, color: usize, piece_type: usize, square: i32) {
        let bits = !square_to_bits(square);
        self.colors[color] &= bits;
        self.pieces[piece_type] &= bits;
    }

    // ── Sliding rays ───────────────────────────────────────────────────────────
    fn ray(&self, square: i32, delta: i32, edge_mask: U64, occ: U64, friendly: U64) -> U64 {
        let mut result: U64 = 0;
        let mut cur = square;
        loop {
            // infinite 'while true' loop block
            if square_to_bits(cur) & edge_mask != 0 {
                break;
            }
            cur += delta;
            if !(0..=63).contains(&cur) {
                break;
            }
            let bits = square_to_bits(cur);
            if bits & friendly != 0 {
                break;
            }
            result |= bits;
            if bits & occ != 0 {
                break;
            }
        }
        result
    }

    fn bishop_attacks(&self, square: i32, occ: U64, friendly: U64) -> U64 {
        let mut r = self.ray(square, 9, FILE_H | RANK_8, occ, friendly);
        r |= self.ray(square, 7, FILE_A | RANK_8, occ, friendly);
        r |= self.ray(square, -7, FILE_H | RANK_1, occ, friendly);
        r |= self.ray(square, -9, FILE_A | RANK_1, occ, friendly);
        r
    }

    fn rook_attacks(&self, square: i32, occ: U64, friendly: U64) -> U64 {
        let mut r = self.ray(square, 8, RANK_8, occ, friendly);
        r |= self.ray(square, -8, RANK_1, occ, friendly);
        r |= self.ray(square, 1, FILE_H, occ, friendly);
        r |= self.ray(square, -1, FILE_A, occ, friendly);
        r
    }

    // ── Pseudo-legal generators ─────────────────────────────────────────────────
    fn pawn_pseudo(&self, square: i32, color: usize) -> U64 {
        let occ = self.occupied();
        let enemy = self.colors[opponent(color)];
        let bits = square_to_bits(square);
        let mut result: U64 = 0;

        if color == WHITE {
            let push1 = shift_n(bits) & !occ;
            result |= push1;
            if bits & RANK_2 != 0 {
                result |= shift_n(push1) & !occ;
            }
            result |= shift_nw(bits) & enemy;
            result |= shift_ne(bits) & enemy;
            if self.en_passant_square >= 0 {
                let ep_bits = square_to_bits(self.en_passant_square);
                result |= (shift_nw(bits) | shift_ne(bits)) & ep_bits;
            }
        } else {
            let push1 = shift_s(bits) & !occ;
            result |= push1;
            if bits & RANK_7 != 0 {
                result |= shift_s(push1) & !occ;
            }
            result |= shift_sw(bits) & enemy;
            result |= shift_se(bits) & enemy;
            if self.en_passant_square >= 0 {
                let ep_bits = square_to_bits(self.en_passant_square);
                result |= (shift_sw(bits) | shift_se(bits)) & ep_bits;
            }
        }
        result
    }

    fn knight_pseudo(&self, square: i32, color: usize) -> U64 {
        knight_attacks(square_to_bits(square)) & !self.colors[color]
    }
    fn bishop_pseudo(&self, square: i32, color: usize) -> U64 {
        self.bishop_attacks(square, self.occupied(), self.colors[color])
    }
    fn rook_pseudo(&self, square: i32, color: usize) -> U64 {
        self.rook_attacks(square, self.occupied(), self.colors[color])
    }
    fn queen_pseudo(&self, square: i32, color: usize) -> U64 {
        let occ = self.occupied();
        let friendly = self.colors[color];
        self.bishop_attacks(square, occ, friendly) | self.rook_attacks(square, occ, friendly)
    }
    fn king_pseudo(&self, square: i32, color: usize) -> U64 {
        let bits = square_to_bits(square);
        let attacks = shift_n(bits)
            | shift_s(bits)
            | shift_e(bits)
            | shift_w(bits)
            | shift_ne(bits)
            | shift_nw(bits)
            | shift_se(bits)
            | shift_sw(bits);
        attacks & !self.colors[color]
    }

    fn get_pseudo_legal(&self, square: i32, color: usize) -> U64 {
        let info = self.get_piece_at(square);
        if info.is_empty() || info.color != color as i32 {
            return 0;
        }
        match info.ptype as usize {
            PAWN => self.pawn_pseudo(square, color),
            KNIGHT => self.knight_pseudo(square, color),
            BISHOP => self.bishop_pseudo(square, color),
            ROOK => self.rook_pseudo(square, color),
            QUEEN => self.queen_pseudo(square, color),
            KING => self.king_pseudo(square, color),
            _ => 0,
        }
    }

    // ── Attack map / check ──────────────────────────────────────────────────────
    pub fn get_attacks(&self, color: usize) -> U64 {
        let occ = self.occupied();
        let mut result: U64 = 0;

        let mut p = self.get_specific_pieces(color, PAWN);
        while p != 0 {
            let bits = square_to_bits(pop_lsb(&mut p));
            if color == WHITE {
                result |= shift_nw(bits) | shift_ne(bits);
            } else {
                result |= shift_sw(bits) | shift_se(bits);
            }
        }
        let mut n = self.get_specific_pieces(color, KNIGHT);
        while n != 0 {
            result |= knight_attacks(square_to_bits(pop_lsb(&mut n)));
        }
        let mut b = self.get_specific_pieces(color, BISHOP);
        while b != 0 {
            result |= self.bishop_attacks(pop_lsb(&mut b), occ, 0);
        }
        let mut r = self.get_specific_pieces(color, ROOK);
        while r != 0 {
            result |= self.rook_attacks(pop_lsb(&mut r), occ, 0);
        }
        let mut q = self.get_specific_pieces(color, QUEEN);
        while q != 0 {
            let sq = pop_lsb(&mut q);
            result |= self.bishop_attacks(sq, occ, 0) | self.rook_attacks(sq, occ, 0);
        }
        let mut k = self.get_specific_pieces(color, KING);
        while k != 0 {
            let bits = square_to_bits(pop_lsb(&mut k));
            result |= shift_n(bits)
                | shift_s(bits)
                | shift_e(bits)
                | shift_w(bits)
                | shift_ne(bits)
                | shift_nw(bits)
                | shift_se(bits)
                | shift_sw(bits);
        }
        result
    }

    pub fn is_in_check(&self, color: usize) -> bool {
        let ks = self.king_square(color);
        self.get_attacks(opponent(color)) & square_to_bits(ks) != 0
    }

    // ── Make / unmake ───────────────────────────────────────────────────────────
    pub fn make_move(&mut self, from_square: i32, to_square: i32, promotion: i32) {
        let piece_info = self.get_piece_at(from_square);
        let color = piece_info.color as usize;
        let piece_type = piece_info.ptype as usize;

        let captured_info = self.get_piece_at(to_square);
        let captured_piece_type = captured_info.ptype;
        let captured_piece_color = captured_info.color;

        let mut mv = Undo {
            from: from_square,
            to: to_square,
            captured_piece: captured_piece_type,
            captured_color: captured_piece_color,
            promotion,
            is_en_passant: false,
            is_castle: false,
            castle_rook_from: -1,
            castle_rook_to: -1,
            prev_en_passant_square: self.en_passant_square,
            prev_castling_rights: self.castling_rights,
            prev_halfmove_clock: self.halfmove_clock,
            prev_zobrist_key: self.zobrist_key,
        };

        if captured_piece_type != NO_PIECE {
            self.clear_piece(
                captured_piece_color as usize,
                captured_piece_type as usize,
                to_square,
            );
        }

        if piece_type == PAWN && self.en_passant_square == to_square {
            let ep_square = if color == WHITE {
                to_square - 8
            } else {
                to_square + 8
            };
            self.clear_piece(opponent(color), PAWN, ep_square);
            mv.is_en_passant = true;
        }

        self.clear_piece(color, piece_type, from_square);
        let placed_piece_type = if promotion != NO_PIECE {
            promotion as usize
        } else {
            piece_type
        };
        self.set_piece(color, placed_piece_type, to_square);

        if piece_type == KING {
            let diff = to_square - from_square;
            let (mut rook_from, mut rook_to) = (-1, -1);
            if diff == 2 {
                rook_from = from_square + 3;
                rook_to = from_square + 1;
            } else if diff == -2 {
                rook_from = from_square - 4;
                rook_to = from_square - 1;
            }
            if rook_from >= 0 {
                self.clear_piece(color, ROOK, rook_from);
                self.set_piece(color, ROOK, rook_to);
                mv.is_castle = true;
                mv.castle_rook_from = rook_from;
                mv.castle_rook_to = rook_to;
            }
        }

        if piece_type == PAWN && (to_square - from_square).abs() == 16 {
            self.en_passant_square = (from_square + to_square) / 2;
        } else {
            self.en_passant_square = -1;
        }

        if piece_type == KING {
            self.castling_rights &= if color == WHITE {
                !(CR_WK | CR_WQ)
            } else {
                !(CR_BK | CR_BQ)
            };
        }
        let rook_right = |sq: i32| -> i32 {
            match sq {
                0 => CR_WQ,
                7 => CR_WK,
                56 => CR_BQ,
                63 => CR_BK,
                _ => 0,
            }
        };
        if piece_type == ROOK {
            self.castling_rights &= !rook_right(from_square);
        }
        if captured_piece_type == ROOK as i32 {
            self.castling_rights &= !rook_right(to_square);
        }

        if piece_type == PAWN || captured_piece_type != NO_PIECE {
            self.halfmove_clock = 0;
        } else {
            self.halfmove_clock += 1;
        }

        self.move_history.push(mv);
        if color == BLACK {
            self.fullmove += 1;
        }
        self.turn = opponent(color);
        self.zobrist_key = self.compute_zobrist();
    }

    pub fn unmake_move(&mut self) {
        let mv = match self.move_history.pop() {
            Some(m) => m,
            None => return,
        };
        let color = opponent(self.turn);
        self.turn = color;

        let to_square = mv.to;
        let from_square = mv.from;

        let piece_on_dest = self.get_piece_at(to_square);
        let placed_piece_type = piece_on_dest.ptype as usize;
        let original_piece_type = if mv.promotion != NO_PIECE {
            PAWN
        } else {
            placed_piece_type
        };

        self.clear_piece(color, placed_piece_type, to_square);
        self.set_piece(color, original_piece_type, from_square);

        if mv.captured_piece != NO_PIECE && !mv.is_en_passant {
            self.set_piece(
                mv.captured_color as usize,
                mv.captured_piece as usize,
                to_square,
            );
        }

        if mv.is_en_passant {
            let ep_square = if color == WHITE {
                to_square - 8
            } else {
                to_square + 8
            };
            self.set_piece(opponent(color), PAWN, ep_square);
        }

        if mv.is_castle {
            self.clear_piece(color, ROOK, mv.castle_rook_to);
            self.set_piece(color, ROOK, mv.castle_rook_from);
        }

        self.en_passant_square = mv.prev_en_passant_square;
        self.castling_rights = mv.prev_castling_rights;
        self.halfmove_clock = mv.prev_halfmove_clock;
        self.zobrist_key = mv.prev_zobrist_key;
        if color == BLACK {
            self.fullmove -= 1;
        }
    }

    // ── Legal moves ─────────────────────────────────────────────────────────────
    fn castling_pseudo(&self, color: usize) -> U64 {
        let occ = self.occupied();
        let attacked = self.get_attacks(opponent(color));
        let mut result: U64 = 0;

        if color == WHITE {
            if attacked & square_to_bits(4) != 0 {
                return 0;
            }
            if (self.castling_rights & CR_WK != 0) && (occ & 0x60 == 0) && (attacked & 0x60 == 0) {
                result |= square_to_bits(6);
            }
            if (self.castling_rights & CR_WQ != 0) && (occ & 0x0E == 0) && (attacked & 0x0C == 0) {
                result |= square_to_bits(2);
            }
        } else {
            if attacked & square_to_bits(60) != 0 {
                return 0;
            }
            if (self.castling_rights & CR_BK != 0)
                && (occ & 0x6000_0000_0000_0000 == 0)
                && (attacked & 0x6000_0000_0000_0000 == 0)
            {
                result |= square_to_bits(62);
            }
            if (self.castling_rights & CR_BQ != 0)
                && (occ & 0x0E00_0000_0000_0000 == 0)
                && (attacked & 0x0C00_0000_0000_0000 == 0)
            {
                result |= square_to_bits(58);
            }
        }
        result
    }

    pub fn get_legal_moves(&mut self, square: i32) -> U64 {
        let info = self.get_piece_at(square);
        if info.is_empty() || info.color != self.turn as i32 {
            return 0;
        }
        let color = info.color as usize;
        let piece_type = info.ptype as usize;

        let mut pseudo = self.get_pseudo_legal(square, color);
        if piece_type == KING {
            pseudo |= self.castling_pseudo(color);
        }

        let mut legal: U64 = 0;
        let mut bb = pseudo;
        while bb != 0 {
            let dest = pop_lsb(&mut bb);
            self.make_move(square, dest, NO_PIECE);
            if !self.is_in_check(color) {
                legal |= square_to_bits(dest);
            }
            self.unmake_move();
        }
        legal
    }

    pub fn get_all_legal_moves(&mut self) -> Vec<(i32, U64)> {
        let mut result = Vec::new();
        let mut bb = self.colors[self.turn];
        while bb != 0 {
            let square = pop_lsb(&mut bb);
            let legal = self.get_legal_moves(square);
            if legal != 0 {
                result.push((square, legal));
            }
        }
        result
    }

    pub fn is_checkmate(&mut self) -> bool {
        self.is_in_check(self.turn) && self.get_all_legal_moves().is_empty()
    }
    pub fn is_stalemate(&mut self) -> bool {
        !self.is_in_check(self.turn) && self.get_all_legal_moves().is_empty()
    }

    pub fn needs_promotion(&self, from_square: i32, to_square: i32) -> bool {
        let info = self.get_piece_at(from_square);
        if info.is_empty() || info.ptype != PAWN as i32 {
            return false;
        }
        let rank = rank_of(to_square);
        (info.color == WHITE as i32 && rank == 7) || (info.color == BLACK as i32 && rank == 0)
    }
}

impl Default for CBoard {
    fn default() -> Self {
        CBoard::new()
    }
}
