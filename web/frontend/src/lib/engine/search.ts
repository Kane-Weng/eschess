// Alpha-beta search — a TypeScript port of `python/engine/search.py`.
//
// Move generation and make/unmake run on chess.js's *internal* 0x88 API
// (`_moves` / `_makeMove` / `_undoMove`) rather than the public `moves({verbose})`,
// which is ~40x slower because it builds a SAN string and before/after FENs for
// every move. Only the chosen moves are converted to algebraic at the boundary.
//
// Carried over from the reference: iterative deepening, a captures-only
// quiescence with delta pruning, MVV-LVA + promotion ordering, and the same
// telemetry shape (nodes / NPS / depth / PV / MultiPV / per-move effort). A wall
// clock budget bounds the move latency, with iterative deepening returning the
// last fully completed depth. Scores are pawn units, White POV.

import { Chess } from "chess.js";
import { evaluate, internalToArray, type Cell, type EvalLevel } from "./evaluate";
import type { EngineInfo, EngineMove, PieceSymbol, RootLine } from "./types";
import { moveKey } from "./types";

const MATE = 100_000; // mate score base; the eval bar treats |score| >= 999 as mate
const QS_LIMIT = 6; // quiescence safety depth
const BITS_CAPTURE = 2 | 8; // chess.js BITS.CAPTURE | BITS.EP_CAPTURE
const CP: Record<PieceSymbol, number> = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
const DELTA_MARGIN = 2.0; // pawns; quiescence delta-pruning safety margin

// chess.js internal move + the private surface we lean on (pinned to chess.js 1.x).
interface IMove {
  color: "w" | "b";
  from: number;
  to: number;
  piece: PieceSymbol;
  captured?: PieceSymbol;
  promotion?: PieceSymbol;
  flags: number;
}
interface ChessInternal {
  _moves(opts?: { legal?: boolean }): IMove[];
  _makeMove(m: IMove): void;
  _undoMove(): IMove | null;
  _board: (Cell | undefined)[];
}

const FILES = "abcdefgh";
const alg = (sq: number): string => FILES[sq & 7] + (8 - (sq >> 4)); // 0x88 -> "e4"

function toEngineMove(m: IMove): EngineMove {
  return { from: alg(m.from), to: alg(m.to), promotion: m.promotion };
}

function orderKey(m: IMove): number {
  if (m.promotion === "q") return 10_000;
  if (m.promotion) return 9_000;
  if (m.captured) return 5_000 + CP[m.captured] * 10 - CP[m.piece];
  return 0;
}

export class Engine {
  level: EvalLevel = "medium";
  multipv = 1;
  lastInfo: EngineInfo = blankInfo();

  private nodes = 0;
  private deadline = Infinity;
  private stopped = false;

  setMultipv(k: number): void {
    this.multipv = Math.max(1, k);
  }

  private timeUp(): boolean {
    if (this.stopped) return true;
    if ((this.nodes & 2047) === 0 && performance.now() >= this.deadline) this.stopped = true;
    return this.stopped;
  }

  private evalNow(ci: ChessInternal): number {
    return evaluate(internalToArray(ci._board), this.level);
  }

  // ── Quiescence (captures + queen promotions, with delta pruning) ────────────
  private quiescence(ci: ChessInternal, alpha: number, beta: number, qdepth: number): number {
    this.nodes++;
    const standPat = this.evalNow(ci);
    const maximizing = (ci as unknown as Chess).turn() === "w";

    if (maximizing) {
      if (standPat >= beta) return standPat;
      if (standPat > alpha) alpha = standPat;
    } else {
      if (standPat <= alpha) return standPat;
      if (standPat < beta) beta = standPat;
    }
    if (qdepth >= QS_LIMIT || this.timeUp()) return standPat;

    const caps = ci
      ._moves({ legal: true })
      .filter((m) => m.flags & BITS_CAPTURE || m.promotion === "q")
      .sort((a, b) => (b.captured ? CP[b.captured] : 0) - (a.captured ? CP[a.captured] : 0));

    for (const m of caps) {
      // Delta pruning: if even winning this material cannot reach the window, skip.
      const gain = m.captured ? CP[m.captured] / 100 : 0;
      if (maximizing && standPat + gain + DELTA_MARGIN < alpha) continue;
      if (!maximizing && standPat - gain - DELTA_MARGIN > beta) continue;

      ci._makeMove(m);
      const score = this.quiescence(ci, alpha, beta, qdepth + 1);
      ci._undoMove();
      if (maximizing) {
        if (score > alpha) alpha = score;
        if (alpha >= beta) return alpha;
      } else {
        if (score < beta) beta = score;
        if (beta <= alpha) return beta;
      }
      if (this.stopped) break;
    }
    return maximizing ? alpha : beta;
  }

  // ── Core alpha-beta (White-POV minimax) ─────────────────────────────────────
  private minimax(
    ci: ChessInternal,
    depth: number,
    alpha: number,
    beta: number,
    ply: number,
  ): { score: number; line: EngineMove[] } {
    this.nodes++;
    if (this.timeUp()) return { score: this.evalNow(ci), line: [] };

    const moves = ci._moves({ legal: true });
    if (moves.length === 0) {
      if ((ci as unknown as Chess).isCheck()) {
        const score = (ci as unknown as Chess).turn() === "w" ? -(MATE - ply) : MATE - ply;
        return { score, line: [] };
      }
      return { score: 0, line: [] }; // stalemate
    }
    if (depth === 0) return { score: this.quiescence(ci, alpha, beta, 0), line: [] };

    moves.sort((a, b) => orderKey(b) - orderKey(a));
    const maximizing = (ci as unknown as Chess).turn() === "w";
    let best = maximizing ? -Infinity : Infinity;
    let bestLine: EngineMove[] = [];
    let bestMove: IMove | null = null;

    for (const m of moves) {
      ci._makeMove(m);
      const child = this.minimax(ci, depth - 1, alpha, beta, ply + 1);
      ci._undoMove();
      if (maximizing ? child.score > best : child.score < best) {
        best = child.score;
        bestMove = m;
        bestLine = child.line;
      }
      if (maximizing) alpha = Math.max(alpha, best);
      else beta = Math.min(beta, best);
      if (alpha >= beta || this.stopped) break;
    }
    return { score: best, line: bestMove ? [toEngineMove(bestMove), ...bestLine] : [] };
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  /**
   * Search `fen` to `depth` within `budgetMs`. Returns the chosen move plus
   * telemetry, also stored on `this.lastInfo`. When `multipv > 1` a full root
   * analysis runs so the Top-3 / Density overlays have per-move scores + effort.
   */
  search(fen: string, depth: number, budgetMs = 1200): { bestMove: EngineMove | null; info: EngineInfo } {
    const chess = new Chess(fen);
    const ci = chess as unknown as ChessInternal;
    const stmWhite = chess.turn() === "w";
    const start = performance.now();
    this.nodes = 0;
    this.stopped = false;
    this.deadline = start + budgetMs;

    if (this.multipv > 1) {
      const lines = this.analyzeRoot(ci, depth);
      const elapsed = performance.now() - start;
      const totalNodes = lines.reduce((s, l) => s + l.nodes, 0) || this.nodes;
      const effort: Record<string, number> = {};
      for (const l of lines) effort[moveKey(l.move)] = l.nodes;
      const best = lines[0] ?? null;
      this.lastInfo = {
        nodes: totalNodes,
        nps: elapsed > 0 ? Math.round((totalNodes / elapsed) * 1000) : 0,
        score: best ? best.score : null,
        depth,
        timeMs: elapsed,
        pv: best ? best.pv : [],
        multipv: lines.slice(0, this.multipv),
        effort,
        stmWhite,
      };
      return { bestMove: best ? best.move : null, info: this.lastInfo };
    }

    // Iterative deepening; keep the deepest fully completed result.
    let bestMove: EngineMove | null = null;
    let bestScore = 0;
    let pv: EngineMove[] = [];
    let reached = 0;
    for (let d = 1; d <= Math.max(1, depth); d++) {
      const { score, line } = this.minimax(ci, d, -Infinity, Infinity, 0);
      if (this.stopped && d > 1) break; // discard the aborted depth, keep the last
      bestScore = score;
      pv = line;
      bestMove = line[0] ?? bestMove;
      reached = d;
      if (Math.abs(score) > MATE - 1000) break; // mate found
      if (performance.now() >= this.deadline) break;
    }
    const elapsed = performance.now() - start;
    this.lastInfo = {
      nodes: this.nodes,
      nps: elapsed > 0 ? Math.round((this.nodes / elapsed) * 1000) : 0,
      score: bestScore,
      depth: reached,
      timeMs: elapsed,
      pv,
      multipv: [],
      effort: {},
      stmWhite,
    };
    return { bestMove, info: this.lastInfo };
  }

  /** Per-root-move analysis: {move, score, nodes, pv} ranked best-first. */
  private analyzeRoot(ci: ChessInternal, depth: number): RootLine[] {
    const maximizing = (ci as unknown as Chess).turn() === "w";
    const moves = ci._moves({ legal: true }).sort((a, b) => orderKey(b) - orderKey(a));
    const results: RootLine[] = [];
    for (const m of moves) {
      const before = this.nodes;
      ci._makeMove(m);
      const child = this.minimax(ci, depth - 1, -Infinity, Infinity, 1);
      ci._undoMove();
      results.push({
        move: toEngineMove(m),
        score: child.score,
        nodes: this.nodes - before,
        pv: [toEngineMove(m), ...child.line],
      });
      if (this.stopped) break; // time budget hit; rank what we have
    }
    results.sort((a, b) => (maximizing ? b.score - a.score : a.score - b.score));
    return results;
  }

  /**
   * Search that records a *sequence* of telemetry frames as it thinks, for the
   * animated "watch the engine search" overlay. Iterative deepening, and within
   * the deepest iteration a frame is captured after each root move is scored, so
   * the replay shows candidate lines appearing, re-ranking, and the principal
   * variation switching as deeper refutations surface. Returns the chosen move
   * (best of the last completed ranking) plus the frames.
   */
  searchFrames(
    fen: string,
    depth: number,
    budgetMs = 1200,
  ): { bestMove: EngineMove | null; frames: EngineInfo[] } {
    const chess = new Chess(fen);
    const ci = chess as unknown as ChessInternal;
    const stmWhite = chess.turn() === "w";
    const maximizing = stmWhite;
    const start = performance.now();
    this.nodes = 0;
    this.stopped = false;
    this.deadline = start + budgetMs;

    const rootMoves = ci._moves({ legal: true }).sort((a, b) => orderKey(b) - orderKey(a));
    const frames: EngineInfo[] = [];
    let finalRanked: RootLine[] = [];

    const rank = (lines: RootLine[]) =>
      [...lines].sort((a, b) => (maximizing ? b.score - a.score : a.score - b.score));
    const snapshot = (ranked: RootLine[], d: number): EngineInfo => {
      const effort: Record<string, number> = {};
      for (const l of ranked) effort[moveKey(l.move)] = l.nodes;
      const elapsed = performance.now() - start;
      return {
        nodes: this.nodes,
        nps: elapsed > 0 ? Math.round((this.nodes / elapsed) * 1000) : 0,
        score: ranked.length ? ranked[0].score : null,
        depth: d,
        timeMs: elapsed,
        pv: ranked.length ? ranked[0].pv : [],
        multipv: ranked.slice(0, 3),
        effort,
        stmWhite,
      };
    };

    for (let d = 1; d <= Math.max(1, depth); d++) {
      const perMove: RootLine[] = [];
      for (const m of rootMoves) {
        const before = this.nodes;
        ci._makeMove(m);
        const child = this.minimax(ci, d - 1, -Infinity, Infinity, 1);
        ci._undoMove();
        if (this.stopped) break; // interrupted search: discard the partial score
        perMove.push({
          move: toEngineMove(m),
          score: child.score,
          nodes: this.nodes - before,
          pv: [toEngineMove(m), ...child.line],
        });
        if (d === depth) frames.push(snapshot(rank(perMove), d)); // per-candidate frame
      }
      if (perMove.length) finalRanked = rank(perMove);
      if (d !== depth && finalRanked.length) frames.push(snapshot(finalRanked, d)); // depth frame
      if (this.stopped) break;
    }

    if (frames.length === 0 && finalRanked.length) frames.push(snapshot(finalRanked, depth));
    this.lastInfo = frames.length ? frames[frames.length - 1] : blankInfo();
    return { bestMove: finalRanked.length ? finalRanked[0].move : null, frames };
  }
}

function blankInfo(): EngineInfo {
  return {
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
}
