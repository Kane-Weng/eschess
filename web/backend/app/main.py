"""
Eschess web backend — FastAPI + WebSocket engine server (stub).

This is the server half of the Engine Sandbox. The frontend already ships a
self-contained TypeScript port of the alpha-beta engine that runs in the
browser; this backend is the path for the heavier Python / ML engine (the value
and policy networks), which cannot run client-side.

It reuses the existing engine in `python/` directly: a WebSocket client sends a
position (FEN) plus engine settings, and the server streams back the chosen move
and the same telemetry the in-browser engine produces (nodes / NPS / score /
depth / PV / MultiPV / per-move effort), so the two backends are interchangeable
behind one wire format.

Run (from the repo root; uv reads the root pyproject.toml / uv.lock):
    uv sync --extra web
    uv run --extra web uvicorn app.main:app --reload --port 8123 --app-dir web/backend

Wire format (JSON over the /ws/engine socket):
    client -> {"fen": "...", "depth": 3, "eval": "medium", "multipv": 1}
    server -> {"bestmove": "e2e4" | null, "info": EngineInfo}
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# Make the existing engine in python/ importable (engine.*, engine_backend, ...).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PYTHON_DIR = _REPO_ROOT / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from app.training import router as training_router  # noqa: E402
from engine.board import CBoard, Color, PieceType, square_name  # noqa: E402
from engine_backend import cpp_available, make_engine, rust_available  # noqa: E402

_LANGS = {"py", "cpp", "rust"}

_PROMO_CHAR = {
    PieceType.KNIGHT: "n",
    PieceType.BISHOP: "b",
    PieceType.ROOK: "r",
    PieceType.QUEEN: "q",
}

app = FastAPI(title="Eschess Engine Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev: the static frontend is served from a different origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# Training-room dashboard stream (GET /training/runs, WS /ws/train).
app.include_router(training_router)


def _move_to_uci(move) -> str | None:
    """(from_idx, to_idx, promo|None) -> 'e2e4' / 'e7e8q'."""
    if move is None:
        return None
    from_sq, to_sq, promo = move
    return square_name(from_sq) + square_name(to_sq) + (_PROMO_CHAR.get(promo, "") if promo else "")


def _move_to_obj(move) -> dict | None:
    if move is None:
        return None
    from_sq, to_sq, promo = move
    return {
        "from": square_name(from_sq),
        "to": square_name(to_sq),
        "promotion": _PROMO_CHAR.get(promo) if promo else None,
    }


def _serialize_info(info: dict, stm_white: bool) -> dict:
    """Project the Python engine's last_info onto the frontend EngineInfo shape."""
    return {
        "nodes": info.get("nodes", 0),
        "nps": info.get("nps", 0),
        "score": info.get("score"),
        "depth": info.get("depth", 0),
        "timeMs": int(info.get("time_s", 0.0) * 1000),
        "pv": [_move_to_obj(m) for m in info.get("pv", [])],
        "multipv": [
            {
                "move": _move_to_obj(entry.get("move")),
                "score": entry.get("score"),
                "pv": [_move_to_obj(m) for m in entry.get("pv", [])],
            }
            for entry in info.get("multipv", [])
        ],
        "effort": {_move_to_uci(m): n for m, n in info.get("effort", {}).items()},
        "stmWhite": stm_white,
    }


class EngineSession:
    """One engine per connection; rebuilt when the language or eval tier changes.

    'py' is the in-process Python search; 'cpp'/'rust' drive the compiled UCI
    binaries over a subprocess (see engine_backend.make_engine).
    """

    def __init__(self) -> None:
        self._engine = None
        self._lang = None
        self._eval = None

    def _ensure(self, lang: str, evaluator: str):
        if self._engine is None or lang != self._lang or evaluator != self._eval:
            # Build the new engine before closing the old one: a failed build
            # (e.g. missing cpp/rust binary) must not strand the session.
            engine = make_engine(lang=lang, search="alphabeta", evaluator=evaluator)
            self.close()
            self._engine, self._lang, self._eval = engine, lang, evaluator
        return self._engine

    def analyze(self, lang: str, fen: str, depth: int, evaluator: str, multipv: int) -> dict:
        if lang not in _LANGS:
            raise ValueError(f"unknown language {lang!r} (expected one of {sorted(_LANGS)})")
        engine = self._ensure(lang, evaluator)
        engine.set_multipv(max(1, multipv))
        board = CBoard.from_fen(fen)
        stm_white = board.turn == Color.WHITE
        start = time.time()
        best = engine.get_best_move(board, depth)
        info = dict(engine.last_info)
        info.setdefault("time_s", time.time() - start)
        return {"bestmove": _move_to_uci(best), "info": _serialize_info(info, stm_white)}

    def close(self) -> None:
        # UCI subprocesses (cpp/rust) hold an OS process; release it on switch/disconnect.
        if self._engine is not None and hasattr(self._engine, "close"):
            self._engine.close()


@app.get("/health")
def health() -> dict:
    # 'py' is always available; cpp/rust need their UCI binary compiled.
    return {
        "status": "ok",
        "langs": {"py": True, "cpp": cpp_available(), "rust": rust_available()},
    }


@app.websocket("/ws/engine")
async def ws_engine(ws: WebSocket) -> None:
    await ws.accept()
    session = EngineSession()
    try:
        while True:
            req = await ws.receive_json()
            lang = req.get("lang", "py")
            fen = req.get("fen", CBoard().to_fen())
            depth = int(req.get("depth", 3))
            evaluator = req.get("eval", "medium")
            multipv = int(req.get("multipv", 1))
            try:
                result = session.analyze(lang, fen, depth, evaluator, multipv)
            except Exception as exc:  # malformed FEN, missing binary, etc.
                await ws.send_json({"error": str(exc)})
                continue
            await ws.send_json(result)
    except WebSocketDisconnect:
        return
    finally:
        session.close()
