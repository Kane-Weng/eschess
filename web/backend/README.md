# Eschess Web Backend

FastAPI + WebSocket server for the Python / ML engine behind the Engine Sandbox.

The Engine Sandbox already runs a TypeScript port of the alpha-beta engine
**client-side** (see `web/frontend/src/lib/engine/`), so the static site works
with no server. This backend is the path for the heavier engine that cannot run
in the browser: the value and policy neural networks. It reuses the existing
engine in [`python/`](../../python) directly rather than reimplementing it.

## Run

```bash
cd web/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

`GET /health` returns a readiness probe. The engine lives at the WebSocket
endpoint `/ws/engine`.

## Wire format

The contract mirrors the frontend's `EngineInfo` type
(`web/frontend/src/lib/engine/types.ts`) so the in-browser engine and this
server are interchangeable:

```jsonc
// client -> server
{ "fen": "rnbqkbnr/...", "depth": 3, "eval": "medium", "multipv": 1 }

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
and need the trained weights under `python/nn/weights/` plus the engine's Python
dependencies (numpy, torch).

## Status

Stub: alpha-beta over the three handcrafted eval tiers works end to end. The
frontend does not yet connect to it (it uses the client-side engine); switching
the sandbox's "Python" language tab to this socket is the follow-up.
