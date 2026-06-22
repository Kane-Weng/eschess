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

The engine lives at the WebSocket endpoint `/ws/engine`.

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

## Status

Working: the sandbox's Python / C++ / Rust language tabs drive this socket
(alpha-beta over the three handcrafted eval tiers), with JS still running
in-browser. The server returns a single final frame per request, so the search
animation stays JS-only. Remaining: the `nn` value eval and `policy` move source
(both wired in `make_engine`, pending weights + torch).
