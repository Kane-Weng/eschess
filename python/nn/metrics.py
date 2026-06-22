"""
Date created: Jun 22
Author: Kane Weng

JSONL metrics sink for the training loops. One flushed line per event so a
reader (the web dashboard) can tail the file live. Generic by design: the RL
loop emits 'epoch' and 'gen' events today; supervised training can reuse the
same writer for its own 'epoch' events later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MetricsWriter:
    """Append-only JSONL writer. Each event is one flushed line."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w", buffering=1)  # line-buffered

    def emit(self, event: dict[str, Any]) -> None:
        self._fh.write(json.dumps(event) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> MetricsWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
