"""
Date created: Jun 14
Author: Kane Weng

Transposition Table, database that stores results of previously performed
searches, using Zobrist Hashing.
"""

from enum import IntEnum


class TTFlag(IntEnum):
    EXACT = 0  # score is exact
    LOWER = 1  # beta cutoff: score is a lower bound
    UPPER = 2  # failed low: score is an upper bound


class TTEntry:
    __slots__ = ("key", "depth", "flag", "score", "best_move")

    def __init__(self, key: int, depth: int, flag: TTFlag, score: float, best_move):
        self.key = key
        self.depth = depth
        self.flag = flag
        self.score = score
        self.best_move = best_move


class TranspositionTable:
    def __init__(self, size_mb: int = 32):
        # Rough ceiling: ~200 bytes per Python dict entry
        self._max = (size_mb * 1024 * 1024) // 200
        self._table: dict[int, TTEntry] = {}

    def probe(self, key: int) -> TTEntry | None:
        entry = self._table.get(key)
        return entry if (entry is not None and entry.key == key) else None

    def store(self, key: int, depth: int, flag: TTFlag, score: float, best_move) -> None:
        existing = self._table.get(key)
        # Depth-preferred replacement: only overwrite with a deeper or equal search
        if existing is None or depth >= existing.depth:
            if len(self._table) >= self._max:
                # Flush oldest quarter when the table fills up
                evict = self._max // 4
                keys = list(self._table)[:evict]
                for k in keys:
                    del self._table[k]
            self._table[key] = TTEntry(key, depth, flag, score, best_move)

    def clear(self) -> None:
        self._table.clear()
