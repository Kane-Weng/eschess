"""
Date created: Jun 15
Author: Kane Weng

Left-hand vertical evaluation bar for the pygame GUI.

The score comes from Stockfish when a stockfish binary is on PATH (an
objective oracle, independent of which engine is playing); otherwise the GUI
falls back to the playing engine's own search score.
"""

import math
import shlex
import shutil
import subprocess
import threading

import pygame

WHITE_FILL = (235, 235, 235)
BLACK_FILL = (28, 28, 32)
MID_LINE = (120, 120, 130)
RIM_COLOR = (100, 100, 110)

_EVAL_FONT = None


def score_to_white_fraction(score_pawns: float) -> float:
    """Pawn advantage (White POV) -> White's fraction of the bar, 0.5 at even."""
    return 0.5 + 0.5 * math.tanh(score_pawns / 4.0)


def draw_eval_bar(screen, rect, score_pawns) -> None:
    """Vertical bar in `rect`; score_pawns None -> neutral grey (no score)."""
    global _EVAL_FONT

    pygame.draw.rect(screen, BLACK_FILL, rect)
    if score_pawns is None:
        pygame.draw.rect(screen, (60, 60, 66), rect)
        pygame.draw.line(screen, MID_LINE, (rect.x, rect.centery), (rect.right, rect.centery), 1)
    else:
        frac = score_to_white_fraction(score_pawns)
        white_h = int(rect.height * frac)
        pygame.draw.rect(screen, WHITE_FILL, (rect.x, rect.bottom - white_h, rect.width, white_h))
        # faint midline marks the 50/50 point
        pygame.draw.line(screen, MID_LINE, (rect.x, rect.centery), (rect.right, rect.centery), 1)

        if _EVAL_FONT is None:
            pygame.font.init()
            _EVAL_FONT = pygame.font.SysFont("arial", 8, bold=True)

        if score_pawns >= 999:
            score_str = "+M"
        elif score_pawns <= -999:
            score_str = "-M"
        else:
            score_str = f"{score_pawns:+.1f}"

        text_color = BLACK_FILL if white_h > 25 else WHITE_FILL
        text_surf = _EVAL_FONT.render(score_str, True, text_color)
        text_rect = text_surf.get_rect(centerx=rect.centerx, bottom=rect.bottom - 4)
        screen.blit(text_surf, text_rect)

    pygame.draw.rect(screen, RIM_COLOR, rect, width=4)


class StockfishProbe:
    """Background Stockfish evaluator. No-op (.available False) without a binary."""

    def __init__(self, depth: int = 12):
        self._depth = depth
        self._score: float | None = None
        self._pending: str | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._closing = False
        self._proc = None

        path = shutil.which("stockfish")
        self.available = path is not None
        if not self.available:
            return
        self._proc = subprocess.Popen(
            shlex.split(path),
            text=True,
            bufsize=1,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._send("uci")
        self._wait_for("uciok")
        threading.Thread(target=self._worker, daemon=True).start()

    @property
    def score(self) -> float | None:
        """Latest evaluation in pawns, White POV (None until first result)."""
        return self._score

    def request(self, fen: str) -> None:
        """Queue a position to evaluate (only the most recent one is kept)."""
        if not self.available:
            return
        with self._lock:
            self._pending = fen
        self._wake.set()

    def _send(self, line: str) -> None:
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _wait_for(self, token: str) -> None:
        for raw in self._proc.stdout:
            if raw.strip() == token:
                return

    def _worker(self) -> None:
        while not self._closing:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                fen = self._pending
                self._pending = None
            if fen is None:
                continue
            white_to_move = fen.split()[1] == "w" if len(fen.split()) > 1 else True
            self._send(f"position fen {fen}")
            self._send(f"go depth {self._depth}")
            stm_pawns: float | None = None
            for raw in self._proc.stdout:
                line = raw.strip()
                if line.startswith("info") and " score " in line:
                    toks = line.split()
                    i = toks.index("score")
                    kind, val = toks[i + 1], int(toks[i + 2])
                    stm_pawns = (val / 100.0) if kind == "cp" else (1000.0 if val > 0 else -1000.0)
                elif line.startswith("bestmove"):
                    break
            if stm_pawns is not None:
                self._score = stm_pawns if white_to_move else -stm_pawns

    def close(self) -> None:
        self._closing = True
        self._wake.set()
        if self._proc is not None:
            try:
                self._send("quit")
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
