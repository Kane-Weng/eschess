// WebSocket + REST client for the training-room dashboard.
//
// The RL loop (python -m nn.rl) writes a JSONL metrics stream; the FastAPI
// backend (web/backend/app/training.py) serves it over /ws/train (replay or
// live-attach) and lists runs at /training/runs. The wire format mirrors
// nn/metrics.py event shapes. Generic enough that a future supervised view can
// reuse the same 'epoch' events.

export interface RunInfo {
  name: string;
  stamp: string;
  format: "jsonl" | "csv";
}

export interface RunEvent {
  type: "run";
  stamp?: string;
  generations?: number;
  games_per_gen?: number;
  sims?: number;
  backend?: string;
}

export interface EpochEvent {
  type: "epoch";
  phase: "policy" | "value";
  gen: number;
  epoch: number;
  loss: number;
}

export interface GenEvent {
  type: "gen";
  gen: number;
  samples: number;
  new_samples?: number;
  policy_loss: number;
  value_loss: number;
  gate_score: number | null;
  accepted: boolean;
  wins?: number;
  draws?: number;
  losses?: number;
}

export interface DoneEvent {
  type: "done";
  generations: number;
}

export type MetricEvent = RunEvent | EpochEvent | GenEvent | DoneEvent;

export type StreamMode = "replay" | "attach";

// Backend default (uvicorn on :8123). Override with PUBLIC_TRAIN_WS at build time.
function host(): string {
  return typeof location !== "undefined" ? location.hostname : "localhost";
}

function wsUrl(): string {
  const env = import.meta.env.PUBLIC_TRAIN_WS as string | undefined;
  return env ?? `ws://${host()}:8123/ws/train`;
}

function httpBase(): string {
  const env = import.meta.env.PUBLIC_TRAIN_HTTP as string | undefined;
  return env ?? `http://${host()}:8123`;
}

export async function fetchRuns(): Promise<RunInfo[]> {
  const res = await fetch(`${httpBase()}/training/runs`);
  if (!res.ok) throw new Error(`runs request failed: ${res.status}`);
  const data = (await res.json()) as { runs: RunInfo[] };
  return data.runs ?? [];
}

export interface StreamHandlers {
  onEvent: (event: MetricEvent) => void;
  onStatus?: (status: "eof" | "error", detail?: string) => void;
  onOpen?: () => void;
  onClose?: () => void;
}

export interface TrainStream {
  close: () => void;
}

// Open a stream for one run. Replay paces by `speed` events/sec server-side;
// attach tails a live JSONL file. Returns a handle to close the socket.
export function openStream(
  run: string,
  mode: StreamMode,
  speed: number,
  handlers: StreamHandlers,
): TrainStream {
  const ws = new WebSocket(wsUrl());
  ws.onopen = () => {
    ws.send(JSON.stringify({ mode, run, speed }));
    handlers.onOpen?.();
  };
  ws.onmessage = (msg) => {
    const frame = JSON.parse(msg.data) as
      | { event: MetricEvent }
      | { status: "eof" | "error"; detail?: string };
    if ("event" in frame) handlers.onEvent(frame.event);
    else handlers.onStatus?.(frame.status, frame.detail);
  };
  ws.onclose = () => handlers.onClose?.();
  ws.onerror = () => handlers.onStatus?.("error", "socket error");
  return { close: () => ws.close() };
}

// Simple trailing moving average over a numeric series.
export function movingAverage(values: number[], window: number): number[] {
  const out: number[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    out.push(sum / Math.min(i + 1, window));
  }
  return out;
}
