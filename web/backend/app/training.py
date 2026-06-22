"""
Eschess training-room backend: the live/replay metrics stream.

The RL loop (`python -m nn.rl`) writes a JSONL metrics stream to
`harness/results/<stamp>_rl_training.jsonl` (and the legacy CSV beside it). This
module serves those runs to the web dashboard two ways:

  GET /training/runs        list available recorded runs (jsonl + legacy csv)
  WS  /ws/train             stream a run's events, either replayed (paced) or
                            attached live (tail the file as the trainer appends)

Wire format (JSON over /ws/train):
    client -> {"mode": "replay" | "attach", "run": "<name>", "speed": 8}
    server -> {"event": <metrics event>}                 one per metrics row
    server -> {"status": "eof" | "error", "detail": ...}  terminal frames

Metrics events mirror nn/metrics.py: 'run', 'epoch', 'gen', 'done'. Legacy CSV
runs are projected onto 'gen' events (no per-epoch or W/D/L granularity).
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESULTS_DIR = _REPO_ROOT / "harness" / "results"

router = APIRouter()


def _runs_dir() -> Path:
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return _RESULTS_DIR


def list_runs() -> list[dict[str, Any]]:
    """Recorded RL runs, newest first. JSONL preferred; CSV-only runs included."""
    runs: dict[str, dict[str, Any]] = {}
    for path in _runs_dir().glob("*_rl_training.jsonl"):
        stamp = path.name.removesuffix("_rl_training.jsonl")
        runs[stamp] = {"name": path.name, "stamp": stamp, "format": "jsonl"}
    for path in _runs_dir().glob("*_rl_training.csv"):
        stamp = path.name.removesuffix("_rl_training.csv")
        runs.setdefault(stamp, {"name": path.name, "stamp": stamp, "format": "csv"})
    return sorted(runs.values(), key=lambda r: r["stamp"], reverse=True)


def _resolve(name: str) -> Path:
    """Resolve a run name to a file inside the results dir (no path escape)."""
    candidate = (_runs_dir() / name).resolve()
    if candidate.parent != _runs_dir().resolve() or not candidate.is_file():
        raise FileNotFoundError(name)
    return candidate


def _csv_events(path: Path) -> list[dict[str, Any]]:
    """Project a legacy CSV run onto the JSONL 'gen' event shape."""
    events: list[dict[str, Any]] = []
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    events.append({"type": "run", "stamp": path.name, "generations": len(rows)})
    for row in rows:
        gate = row.get("gate_score")
        events.append(
            {
                "type": "gen",
                "gen": int(row["generation"]),
                "samples": int(row["samples"]),
                "policy_loss": float(row["policy_loss"]),
                "value_loss": float(row["value_loss"]),
                "gate_score": None if not gate or math.isnan(float(gate)) else float(gate),
                "accepted": bool(int(row["accepted"])),
            }
        )
    events.append({"type": "done", "generations": len(rows)})
    return events


def _read_all_events(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".csv":
        return _csv_events(path)
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


async def _tail_jsonl(path: Path, poll_s: float = 0.5) -> AsyncIterator[dict[str, Any]]:
    """Yield events from a JSONL file as it grows. Stops after a 'done' event."""
    pos = 0
    buffer = ""
    while True:
        text = path.read_text()
        if len(text) > pos:
            buffer += text[pos:]
            pos = len(text)
            *lines, buffer = buffer.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                yield event
                if event.get("type") == "done":
                    return
        await asyncio.sleep(poll_s)


@router.get("/training/runs")
def get_runs() -> dict[str, Any]:
    return {"runs": list_runs()}


@router.websocket("/ws/train")
async def ws_train(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            req = await ws.receive_json()
            mode = req.get("mode", "replay")
            name = req.get("run")
            try:
                path = _resolve(name) if name else _resolve(list_runs()[0]["name"])
            except (FileNotFoundError, IndexError):
                await ws.send_json({"status": "error", "detail": f"run not found: {name!r}"})
                continue

            if mode == "attach" and path.suffix == ".jsonl":
                async for event in _tail_jsonl(path):
                    await ws.send_json({"event": event})
                await ws.send_json({"status": "eof"})
            else:
                # Replay: stream the whole run paced by 1/speed seconds per event.
                speed = max(1.0, float(req.get("speed", 8)))
                for event in _read_all_events(path):
                    await ws.send_json({"event": event})
                    if event.get("type") == "gen":
                        await asyncio.sleep(1.0 / speed)
                await ws.send_json({"status": "eof"})
    except WebSocketDisconnect:
        return
