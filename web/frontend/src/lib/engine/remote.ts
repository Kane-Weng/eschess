// WebSocket client for the Python / C++ / Rust engines.
//
// The JS engine runs in-browser (see search.ts); the other three ports run
// server-side and are reached over the FastAPI socket in web/backend. The wire
// format mirrors EngineInfo so the two paths are interchangeable. Unlike the
// in-browser engine the server returns a single final frame per request (no
// streamed search animation).

import type { EngineInfo, EngineMove, PieceSymbol, RootLine } from "./types";
import { EMPTY_INFO } from "./types";

export type RemoteLang = "py" | "cpp" | "rust";

export interface RemoteResult {
  bestMove: EngineMove | null;
  info: EngineInfo;
}

interface AnalyzeRequest {
  lang: RemoteLang;
  fen: string;
  depth: number;
  eval: string;
  multipv: number;
}

// Backend default (uvicorn on :8123). Override with PUBLIC_ENGINE_WS at build time.
function defaultUrl(): string {
  const env = import.meta.env.PUBLIC_ENGINE_WS as string | undefined;
  if (env) return env;
  const host = typeof location !== "undefined" ? location.hostname : "localhost";
  return `ws://${host}:8123/ws/engine`;
}

const PROMO = new Set(["q", "r", "b", "n"]);

// "e2e4" / "e7e8q" -> EngineMove. null for a null/empty bestmove.
function uciToMove(uci: string | null): EngineMove | null {
  if (!uci || uci.length < 4) return null;
  const move: EngineMove = { from: uci.slice(0, 2), to: uci.slice(2, 4) };
  const promo = uci[4];
  if (promo && PROMO.has(promo)) move.promotion = promo as PieceSymbol;
  return move;
}

// The server already projects onto the EngineInfo shape; fill any gaps so the
// overlays (which read nodes / multipv / effort) never see undefined.
function normalizeInfo(raw: Record<string, unknown> | undefined): EngineInfo {
  if (!raw) return { ...EMPTY_INFO };
  const multipv = Array.isArray(raw.multipv)
    ? (raw.multipv as Record<string, unknown>[]).map(
        (e): RootLine => ({
          move: (e.move as EngineMove) ?? { from: "", to: "" },
          score: (e.score as number) ?? 0,
          nodes: (e.nodes as number) ?? 0,
          pv: (e.pv as EngineMove[]) ?? [],
        }),
      )
    : [];
  return {
    nodes: (raw.nodes as number) ?? 0,
    nps: (raw.nps as number) ?? 0,
    score: (raw.score as number | null) ?? null,
    depth: (raw.depth as number) ?? 0,
    timeMs: (raw.timeMs as number) ?? 0,
    pv: (raw.pv as EngineMove[]) ?? [],
    multipv,
    effort: (raw.effort as Record<string, number>) ?? {},
    stmWhite: (raw.stmWhite as boolean) ?? true,
  };
}

/**
 * One persistent socket to the engine backend, reused across moves. The sandbox
 * only ever has one search in flight (its turn), so requests are serialized: a
 * single in-flight promise is resolved by the next server frame.
 */
export class RemoteEngine {
  private url: string;
  private ws: WebSocket | null = null;
  private connecting: Promise<WebSocket> | null = null;
  private pending: { resolve: (r: RemoteResult) => void; reject: (e: Error) => void } | null = null;

  constructor(url?: string) {
    this.url = url ?? defaultUrl();
  }

  private connect(): Promise<WebSocket> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return Promise.resolve(this.ws);
    if (this.connecting) return this.connecting;

    this.connecting = new Promise<WebSocket>((resolve, reject) => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(this.url);
      } catch (e) {
        this.connecting = null;
        reject(e instanceof Error ? e : new Error(String(e)));
        return;
      }
      ws.onopen = () => {
        this.ws = ws;
        this.connecting = null;
        resolve(ws);
      };
      ws.onerror = () => {
        this.connecting = null;
        if (ws.readyState !== WebSocket.OPEN) reject(new Error(`cannot reach engine at ${this.url}`));
      };
      ws.onclose = () => {
        this.ws = null;
        this.failPending(new Error("engine connection closed"));
      };
      ws.onmessage = (ev) => this.onMessage(ev);
    });
    return this.connecting;
  }

  private onMessage(ev: MessageEvent): void {
    const p = this.pending;
    if (!p) return;
    this.pending = null;
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(ev.data as string);
    } catch {
      p.reject(new Error("malformed engine response"));
      return;
    }
    if (typeof msg.error === "string") {
      p.reject(new Error(msg.error));
      return;
    }
    p.resolve({
      bestMove: uciToMove((msg.bestmove as string | null) ?? null),
      info: normalizeInfo(msg.info as Record<string, unknown> | undefined),
    });
  }

  private failPending(err: Error): void {
    const p = this.pending;
    if (p) {
      this.pending = null;
      p.reject(err);
    }
  }

  async analyze(req: AnalyzeRequest): Promise<RemoteResult> {
    const ws = await this.connect();
    if (this.pending) this.failPending(new Error("superseded by a newer request"));
    return new Promise<RemoteResult>((resolve, reject) => {
      this.pending = { resolve, reject };
      try {
        ws.send(JSON.stringify(req));
      } catch (e) {
        this.pending = null;
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    });
  }

  close(): void {
    this.failPending(new Error("engine closed"));
    this.ws?.close();
    this.ws = null;
  }
}
