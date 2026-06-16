// Shared engine types for the in-browser chess engine.
//
// The engine is a TypeScript port of the Python reference in
// `python/engine/` (evaluate.py + search.py), driven on top of chess.js for
// move generation, legality, FEN and game-over detection. Scores are always in
// pawn units from White's perspective, matching the reference.

export type Color = "w" | "b";
export type PieceSymbol = "p" | "n" | "b" | "r" | "q" | "k";

/** A move in the engine's internal form (algebraic squares + optional promotion). */
export interface EngineMove {
  from: string; // "e2"
  to: string; // "e4"
  promotion?: PieceSymbol; // "q" | "r" | "b" | "n"
}

/** One root candidate from a MultiPV analysis. */
export interface RootLine {
  move: EngineMove;
  score: number; // pawns, White POV
  nodes: number; // un-pruned nodes spent in this move's subtree (density signal)
  pv: EngineMove[]; // the move followed by the engine's expected reply chain
}

/** Telemetry from the most recent search, consumed by the sidebar + overlays. */
export interface EngineInfo {
  nodes: number;
  nps: number;
  score: number | null; // pawns, White POV
  depth: number;
  timeMs: number;
  pv: EngineMove[];
  multipv: RootLine[];
  effort: Record<string, number>; // "e2e4" -> nodes
  stmWhite: boolean; // side to move at the searched root
}

export const EMPTY_INFO: EngineInfo = {
  nodes: 0,
  nps: 0,
  score: null,
  depth: 0,
  timeMs: 0,
  pv: [],
  multipv: [],
  effort: {},
  stmWhite: true,
};

// ── Square helpers (LERF index: a1 = 0, b1 = 1, ... h8 = 63) ─────────────────
// This matches the Python board's indexing so the piece-square tables port
// across unchanged.

/** "e2" -> 12 (rank * 8 + file). */
export function squareToIndex(square: string): number {
  const file = square.charCodeAt(0) - 97; // 'a' -> 0
  const rank = square.charCodeAt(1) - 49; // '1' -> 0
  return rank * 8 + file;
}

export const fileOf = (idx: number): number => idx & 7;
export const rankOf = (idx: number): number => idx >> 3;

/** A move key used for the density / effort map, e.g. "e2e4" or "g7g8q". */
export function moveKey(m: EngineMove): string {
  return m.from + m.to + (m.promotion ?? "");
}
