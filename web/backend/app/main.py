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

Run:
    cd web/backend
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000

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

from engine.board import CBoard, Color, PieceType, square_name  # noqa: E402
from engine_backend import make_engine  # noqa: E402

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
    """One alpha-beta engine per connection; rebuilt when the eval tier changes."""

    def __init__(self) -> None:
        self._engine = None
        self._eval = None

    def _ensure(self, evaluator: str):
        if self._engine is None or evaluator != self._eval:
            self._engine = make_engine(lang="py", search="alphabeta", evaluator=evaluator)
            self._eval = evaluator
        return self._engine

    def analyze(self, fen: str, depth: int, evaluator: str, multipv: int) -> dict:
        engine = self._ensure(evaluator)
        engine.set_multipv(max(1, multipv))
        board = CBoard.from_fen(fen)
        stm_white = board.turn == Color.WHITE
        start = time.time()
        best = engine.get_best_move(board, depth)
        info = dict(engine.last_info)
        info.setdefault("time_s", time.time() - start)
        return {"bestmove": _move_to_uci(best), "info": _serialize_info(info, stm_white)}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": "python alpha-beta"}


@app.websocket("/ws/engine")
async def ws_engine(ws: WebSocket) -> None:
    await ws.accept()
    session = EngineSession()
    try:
        while True:
            req = await ws.receive_json()
            fen = req.get("fen", CBoard().to_fen())
            depth = int(req.get("depth", 3))
            evaluator = req.get("eval", "medium")
            multipv = int(req.get("multipv", 1))
            try:
                result = session.analyze(fen, depth, evaluator, multipv)
            except Exception as exc:  # malformed FEN, etc.
                await ws.send_json({"error": str(exc)})
                continue
            await ws.send_json(result)
    except WebSocketDisconnect:
        return
