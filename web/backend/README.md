# Eschess Web Backend

FastAPI + WebSocket server for the Python / C++ / Rust engines behind the Engine
Sandbox.

The Engine Sandbox runs a TypeScript port of the alpha-beta engine
**client-side** (see `web/frontend/src/lib/engine/`), so the static site works
with no server (the "JS" language tab). This backend serves the other three
ports, which cannot run in the browser:

- `py` - the in-process Python reference engine ([`python/`](../../python)).
- `cpp` / `rust` - the compiled UCI binaries, driven as subprocesses via
  `engine_backend.make_engine` (no reimplementation).

It is also the path for the heavier value / policy neural networks (still TODO).

## Run

```bash
# from the repo root (uv reads the root pyproject.toml / uv.lock)
uv sync --extra web
uv run --extra web uvicorn app.main:app --reload --port 8123 --app-dir web/backend
```

Port 8123 matches the frontend's default WebSocket URL. To use a different port,
start uvicorn there and point the frontend at it with
`PUBLIC_ENGINE_WS=ws://localhost:<port>/ws/engine` at build time.

`GET /health` returns a readiness probe plus which language ports are available
(`cpp` / `rust` need their UCI binary compiled, see the repo `CLAUDE.md`):

```jsonc
{ "status": "ok", "langs": { "py": true, "cpp": true, "rust": false } }
```

The engine lives at the WebSocket endpoint `/ws/engine`. The training-room
dashboard adds `GET /training/runs` + the `/ws/train` socket (see below).

## Wire format

The contract mirrors the frontend's `EngineInfo` type
(`web/frontend/src/lib/engine/types.ts`) so the in-browser engine and this
server are interchangeable:

```jsonc
// client -> server
{ "lang": "py", "fen": "rnbqkbnr/...", "depth": 3, "eval": "medium", "multipv": 1 }
// lang: "py" | "cpp" | "rust" (default "py"). "js" runs client-side, never here.

// server -> client
{
  "bestmove": "e2e4",            // or null
  "info": {
    "nodes": 12345, "nps": 98000, "score": 0.3, "depth": 3, "timeMs": 120,
    "pv": [{ "from": "e2", "to": "e4" }, ...],
    "multipv": [{ "move": {...}, "score": 0.3, "pv": [...] }, ...],
    "effort": { "e2e4": 5400, ... },
    "stmWhite": true
  }
}
```

`eval` accepts `simple | medium | complex`. Wiring `nn` (value network) and a
`policy` search is the next step; both already exist in `engine_backend.make_engine`
and need the trained weights under `python/nn/weights/` plus the engine's NN deps
(`uv sync --extra web --extra nn` pulls numpy + torch).

## Training room (`/training/runs`, `/ws/train`)

Serves the RL self-play metrics to the frontend training dashboard
(`/training`). `python -m nn.rl` writes a JSONL metrics stream next to its CSV at
`harness/results/<stamp>_rl_training.jsonl` (events: `run`, per-epoch `epoch`,
per-generation `gen` with W/D/L, `done`). The dashboard streams a run two ways:

- **Replay**: page through any recorded run (JSONL, or a legacy CSV projected
  onto `gen` events), paced server-side by a `speed` (gen/s) the UI sets.
- **Attach**: tail a JSONL a local trainer is still writing, live.

```jsonc
// GET /training/runs -> { "runs": [{ "name", "stamp", "format": "jsonl"|"csv" }] }

// client -> /ws/train
{ "mode": "replay" | "attach", "run": "<name>", "speed": 8 }
// server -> client
{ "event": { "type": "gen", "gen": 1, "policy_loss": 2.43, "value_loss": 0.04,
             "gate_score": 0.5, "accepted": false, "wins": 3, "draws": 2, "losses": 1 } }
{ "status": "eof" | "error", "detail": "..." }
```

Produce a live run with, e.g.:

```bash
cd python && uv run --extra nn python -m nn.rl --generations 5 --games-per-gen 20
# then pick that run in the dashboard (Replay), or attach to it while it runs.
```

Override the dashboard's backend URL at build time with
`PUBLIC_TRAIN_WS` / `PUBLIC_TRAIN_HTTP` (default `:8123`).

## Status

Working: the sandbox's Python / C++ / Rust language tabs drive this socket
(alpha-beta over the three handcrafted eval tiers), with JS still running
in-browser. The server returns a single final frame per request, so the search
animation stays JS-only. Remaining: the `nn` value eval and `policy` move source
(both wired in `make_engine`, pending weights + torch).
