// Evaluation functions — a TypeScript port of `python/engine/evaluate.py`.
//
//   simple  : material + doubled-pawn penalty + tiny positional bonuses
//   medium  : material + piece-square tables (PST)
//   complex : PST + pawn structure + bishop pair + mobility + king safety
//
// Scores are in pawn units from White's perspective (positive = White better),
// matching the reference engine. Squares use the LERF index (a1 = 0 ... h8 = 63).

import type { Color, PieceSymbol } from "./types";
import { fileOf, rankOf } from "./types";

export type EvalLevel = "simple" | "medium" | "complex";

export type Cell = { type: PieceSymbol; color: Color } | null;

// ── Piece values (pawn units) ────────────────────────────────────────────────
const PIECE_VALUES: Record<PieceSymbol, number> = {
  p: 1.0,
  n: 3.2,
  b: 3.3,
  r: 5.0,
  q: 9.0,
  k: 0.0,
};

// ── Piece-square tables (centipawns, White's perspective, LERF order) ────────
// prettier-ignore
const PAWN_PST = [
    0,  0,  0,  0,  0,  0,  0,  0,
    5, 10, 10,-20,-20, 10, 10,  5,
    5, -5,-10,  0,  0,-10, -5,  5,
    0,  0,  0, 20, 20,  0,  0,  0,
    5,  5, 10, 25, 25, 10,  5,  5,
   10, 10, 20, 30, 30, 20, 10, 10,
   50, 50, 50, 50, 50, 50, 50, 50,
    0,  0,  0,  0,  0,  0,  0,  0,
];

// prettier-ignore
const KNIGHT_PST = [
  -50,-40,-30,-30,-30,-30,-40,-50,
  -40,-20,  0,  0,  0,  0,-20,-40,
  -30,  0, 10, 15, 15, 10,  0,-30,
  -30,  5, 15, 20, 20, 15,  5,-30,
  -30,  0, 15, 20, 20, 15,  0,-30,
  -30,  5, 10, 15, 15, 10,  5,-30,
  -40,-20,  0,  5,  5,  0,-20,-40,
  -50,-40,-30,-30,-30,-30,-40,-50,
];

// prettier-ignore
const BISHOP_PST = [
  -20,-10,-10,-10,-10,-10,-10,-20,
  -10,  0,  0,  0,  0,  0,  0,-10,
  -10,  0,  5, 10, 10,  5,  0,-10,
  -10,  5,  5, 10, 10,  5,  5,-10,
  -10,  0, 10, 10, 10, 10,  0,-10,
  -10, 10, 10, 10, 10, 10, 10,-10,
  -10,  5,  0,  0,  0,  0,  5,-10,
  -20,-10,-10,-10,-10,-10,-10,-20,
];

// prettier-ignore
const ROOK_PST = [
    0,  0,  0,  5,  5,  0,  0,  0,
   -5,  0,  0,  0,  0,  0,  0, -5,
   -5,  0,  0,  0,  0,  0,  0, -5,
   -5,  0,  0,  0,  0,  0,  0, -5,
   -5,  0,  0,  0,  0,  0,  0, -5,
   -5,  0,  0,  0,  0,  0,  0, -5,
    5, 10, 10, 10, 10, 10, 10,  5,
    0,  0,  0,  0,  0,  0,  0,  0,
];

// prettier-ignore
const QUEEN_PST = [
  -20,-10,-10, -5, -5,-10,-10,-20,
  -10,  0,  0,  0,  0,  0,  0,-10,
  -10,  0,  5,  5,  5,  5,  0,-10,
   -5,  0,  5,  5,  5,  5,  0, -5,
    0,  0,  5,  5,  5,  5,  0, -5,
  -10,  5,  5,  5,  5,  5,  0,-10,
  -10,  0,  5,  0,  0,  0,  0,-10,
  -20,-10,-10, -5, -5,-10,-10,-20,
];

// prettier-ignore
const KING_MG_PST = [ // midgame: stay castled, avoid centre
   20, 30, 10,  0,  0, 10, 30, 20,
   20, 20,  0,  0,  0,  0, 20, 20,
  -10,-20,-20,-20,-20,-20,-20,-10,
  -20,-30,-30,-40,-40,-30,-30,-20,
  -30,-40,-40,-50,-50,-40,-40,-30,
  -30,-40,-40,-50,-50,-40,-40,-30,
  -30,-40,-40,-50,-50,-40,-40,-30,
  -30,-40,-40,-50,-50,-40,-40,-30,
];

// prettier-ignore
const KING_EG_PST = [ // endgame: centralise the king
  -50,-40,-30,-20,-20,-30,-40,-50,
  -30,-20,-10,  0,  0,-10,-20,-30,
  -30,-10, 20, 30, 30, 20,-10,-30,
  -30,-10, 30, 40, 40, 30,-10,-30,
  -30,-10, 30, 40, 40, 30,-10,-30,
  -30,-10, 20, 30, 30, 20,-10,-30,
  -30,-30,  0,  0,  0,  0,-30,-30,
  -50,-30,-30,-30,-30,-30,-30,-50,
];

const PST_MAP: Record<PieceSymbol, number[]> = {
  p: PAWN_PST,
  n: KNIGHT_PST,
  b: BISHOP_PST,
  r: ROOK_PST,
  q: QUEEN_PST,
  k: KING_MG_PST,
};

// Passed-pawn rank bonus (centipawns); 0/7 are back ranks (never used).
const PASSED_BONUS = [0, 0, 10, 20, 35, 60, 100, 0];

/** Vertical flip for Black PST lookup (maps idx to the equivalent White index). */
function mirror(idx: number): number {
  return (7 - (idx >> 3)) * 8 + (idx & 7);
}

function pstVal(pst: number[], idx: number, color: Color): number {
  const raw = pst[color === "w" ? idx : mirror(idx)];
  return (color === "w" ? raw : -raw) / 100.0;
}

/** Convert a chess.js `board()` (rank 8 → rank 1) into a LERF-indexed array. */
export function boardToArray(board2d: Cell[][]): Cell[] {
  const arr: Cell[] = new Array(64).fill(null);
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const cell = board2d[r][f];
      if (cell) arr[(7 - r) * 8 + f] = { type: cell.type, color: cell.color };
    }
  }
  return arr;
}

/**
 * Convert chess.js's internal 0x88 board (`_board`, length 128, rank 8 first)
 * into a LERF-indexed array. This is the hot path used inside the search; it
 * avoids the allocation-heavy public `board()` call.
 */
export function internalToArray(board0x88: (Cell | undefined)[]): Cell[] {
  const arr: Cell[] = new Array(64).fill(null);
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const cell = board0x88[r * 16 + f]; // 0x88: square = rank*16 + file, rank 0 = rank 8
      if (cell) arr[(7 - r) * 8 + f] = { type: cell.type, color: cell.color };
    }
  }
  return arr;
}

// ── Level 1: Simple ──────────────────────────────────────────────────────────

function simpleEval(arr: Cell[]): number {
  let score = 0;
  for (let idx = 0; idx < 64; idx++) {
    const cell = arr[idx];
    if (!cell) continue;
    const sign = cell.color === "w" ? 1 : -1;
    const rank = rankOf(idx);
    const file = fileOf(idx);
    score += PIECE_VALUES[cell.type] * sign;

    if (cell.type === "p") {
      const behind = cell.color === "w" ? idx - 8 : idx + 8;
      if (behind >= 0 && behind <= 63) {
        const b = arr[behind];
        if (b && b.type === "p" && b.color === cell.color) score -= 0.5 * sign;
      }
    } else if (cell.type === "n") {
      if ((rank === 3 || rank === 4) && (file === 3 || file === 4)) score += 0.5 * sign;
      else if ((rank === 2 || rank === 5) && (file === 2 || file === 5)) score += 0.25 * sign;
      else if (rank === 0 || rank === 7 || file === 0 || file === 7) score -= 0.5 * sign;
    } else if (cell.type === "k") {
      if (cell.color === "w" && rank === 0 && (file === 2 || file === 6)) score += 0.75;
      else if (cell.color === "b" && rank === 7 && (file === 2 || file === 6)) score -= 0.75;
    }
  }
  return score;
}

// ── Level 2: Medium ──────────────────────────────────────────────────────────

function mediumEval(arr: Cell[]): number {
  let score = 0;
  for (let idx = 0; idx < 64; idx++) {
    const cell = arr[idx];
    if (!cell) continue;
    const sign = cell.color === "w" ? 1 : -1;
    score += PIECE_VALUES[cell.type] * sign;
    score += pstVal(PST_MAP[cell.type], idx, cell.color);
  }
  return score;
}

// ── Level 3: Complex ─────────────────────────────────────────────────────────

const KNIGHT_OFFS = [
  [1, 2],
  [2, 1],
  [2, -1],
  [1, -2],
  [-1, -2],
  [-2, -1],
  [-2, 1],
  [-1, 2],
];
const KING_OFFS = [
  [1, 0],
  [1, 1],
  [0, 1],
  [-1, 1],
  [-1, 0],
  [-1, -1],
  [0, -1],
  [1, -1],
];
const BISHOP_DIRS = [
  [1, 1],
  [1, -1],
  [-1, 1],
  [-1, -1],
];
const ROOK_DIRS = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];

/** Number of squares attacked by `color` (rough mobility signal). */
function attackedCount(arr: Cell[], color: Color): number {
  const attacked = new Set<number>();
  const add = (r: number, f: number) => {
    if (r >= 0 && r < 8 && f >= 0 && f < 8) attacked.add(r * 8 + f);
  };
  const ray = (r: number, f: number, dirs: number[][]) => {
    for (const [dr, df] of dirs) {
      let nr = r + dr;
      let nf = f + df;
      while (nr >= 0 && nr < 8 && nf >= 0 && nf < 8) {
        attacked.add(nr * 8 + nf);
        if (arr[nr * 8 + nf]) break; // blocked (the blocker square still counts)
        nr += dr;
        nf += df;
      }
    }
  };
  for (let idx = 0; idx < 64; idx++) {
    const cell = arr[idx];
    if (!cell || cell.color !== color) continue;
    const r = rankOf(idx);
    const f = fileOf(idx);
    switch (cell.type) {
      case "p": {
        const dir = color === "w" ? 1 : -1;
        add(r + dir, f - 1);
        add(r + dir, f + 1);
        break;
      }
      case "n":
        for (const [dr, df] of KNIGHT_OFFS) add(r + dr, f + df);
        break;
      case "k":
        for (const [dr, df] of KING_OFFS) add(r + dr, f + df);
        break;
      case "b":
        ray(r, f, BISHOP_DIRS);
        break;
      case "r":
        ray(r, f, ROOK_DIRS);
        break;
      case "q":
        ray(r, f, BISHOP_DIRS);
        ray(r, f, ROOK_DIRS);
        break;
    }
  }
  return attacked.size;
}

function complexEval(arr: Cell[]): number {
  let score = 0;

  // Pawn squares per colour, and per-file counts, for structure terms.
  const pawns: Record<Color, number[]> = { w: [], b: [] };
  let minorMajor = 0;
  for (let idx = 0; idx < 64; idx++) {
    const cell = arr[idx];
    if (!cell) continue;
    if (cell.type === "p") pawns[cell.color].push(idx);
    if (cell.type === "n" || cell.type === "b" || cell.type === "r" || cell.type === "q") {
      minorMajor += PIECE_VALUES[cell.type];
    }
  }
  const kingPst = minorMajor < 14.0 ? KING_EG_PST : KING_MG_PST;

  const fileHasPawn = (squares: number[], file: number) => squares.some((s) => fileOf(s) === file);
  const isPassed = (idx: number, color: Color): boolean => {
    const file = fileOf(idx);
    const rank = rankOf(idx);
    const enemy = pawns[color === "w" ? "b" : "w"];
    return !enemy.some((e) => {
      const ef = fileOf(e);
      if (Math.abs(ef - file) > 1) return false;
      return color === "w" ? rankOf(e) > rank : rankOf(e) < rank;
    });
  };

  let bishops: Record<Color, number> = { w: 0, b: 0 };

  for (let idx = 0; idx < 64; idx++) {
    const cell = arr[idx];
    if (!cell) continue;
    const color = cell.color;
    const sign = color === "w" ? 1 : -1;
    const pst = cell.type === "k" ? kingPst : PST_MAP[cell.type];
    score += PIECE_VALUES[cell.type] * sign;
    score += pstVal(pst, idx, color);
    if (cell.type === "b") bishops[color] += 1;

    if (cell.type === "p") {
      const file = fileOf(idx);
      const rank = rankOf(idx);
      const friendly = pawns[color];
      if (friendly.filter((s) => fileOf(s) === file).length > 1) score -= 0.2 * sign; // doubled
      const isolated = !fileHasPawn(friendly, file - 1) && !fileHasPawn(friendly, file + 1);
      if (isolated) score -= 0.25 * sign;
      if (isPassed(idx, color)) {
        const adv = color === "w" ? rank : 7 - rank;
        score += (PASSED_BONUS[adv] / 100.0) * sign;
      }
    }
  }

  for (const color of ["w", "b"] as Color[]) {
    const sign = color === "w" ? 1 : -1;
    if (bishops[color] >= 2) score += 0.5 * sign; // bishop pair
    score += attackedCount(arr, color) * 0.005 * sign; // rough mobility
  }

  return score;
}

const EVALUATORS: Record<EvalLevel, (arr: Cell[]) => number> = {
  simple: simpleEval,
  medium: mediumEval,
  complex: complexEval,
};

/** Evaluate a LERF-indexed board array at the given level (White POV, pawns). */
export function evaluate(arr: Cell[], level: EvalLevel): number {
  return EVALUATORS[level](arr);
}
