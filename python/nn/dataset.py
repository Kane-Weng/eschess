"""
Date created: Jun 14
Author: Kane Weng

Supervised dataset built from the angeluriot/chess_games dataset on Hugging Face
(14M high level games). Each game is replayed move by move; every position along
the way becomes one training sample:

  policy target : the move actually played from that position (from-to index)
  value target  : the final game result from White's perspective in [-1, 1]
                  (1.0 White win, 0.0 draw, -1.0 Black win)
"""

import os
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import Dataset

from engine.board import CBoard, PieceType, name_to_square
from .encoding import board_to_planes, move_to_index

HF_DATASET_NAME = "angeluriot/chess_games"
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Final result from White's perspective; null winner means a draw.
_WINNER_VALUE = {"white": 1.0, "black": -1.0, None: 0.0}

# Promotion suffix in a UCI move (e.g. the 'q' in 'c7c8q').
_PROMO_CHARS = {
    "n": PieceType.KNIGHT, "b": PieceType.BISHOP,
    "r": PieceType.ROOK,   "q": PieceType.QUEEN,
}


@dataclass
class Sample:
    fen: str
    from_square: int
    to_square: int
    value: float


def _parse_uci(move: str) -> tuple[int, int, PieceType | None]:
    """UCI long algebraic to (from_square, to_square, promotion)."""
    from_square = name_to_square(move[0:2])
    to_square   = name_to_square(move[2:4])
    promotion   = _PROMO_CHARS.get(move[4]) if len(move) > 4 else None
    return from_square, to_square, promotion


def game_to_samples(moves_uci: list[str], winner: str | None) -> list[Sample]:
    """Replay one game, emitting a sample for each position before a move."""
    value = _WINNER_VALUE.get(winner, 0.0)
    board = CBoard()
    samples: list[Sample] = []
    for move in moves_uci:
        from_square, to_square, promotion = _parse_uci(move)
        samples.append(Sample(board.to_fen(), from_square, to_square, value))
        board.make_move(from_square, to_square, promotion)
    return samples


def _game_min_elo(game: dict) -> int | None:
    """Lower of the two player ELOs, or None if either is missing."""
    elos: list[int] = []
    for key in ("white_elo", "black_elo"):
        value = game.get(key)
        if value is None:
            return None
        elos.append(int(value))
    return min(elos)


def _load_dotenv(path: Path = _ENV_PATH) -> None:
    """Populate os.environ from a simple KEY=VALUE .env file, if one exists."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_hf_samples(max_games: int = 1000, split: str = "train",
                    min_elo: int | None = None, streaming: bool = True) -> list[Sample]:
    """Stream games from the Hugging Face dataset and replay them into samples."""
    from datasets import load_dataset   # optional dep, imported on demand

    _load_dotenv()
    token = os.environ.get("HF_TOKEN") or None   # None falls back to anonymous access
    dataset = load_dataset(HF_DATASET_NAME, split=split, streaming=streaming, token=token)
    samples: list[Sample] = []
    games = 0
    for game in dataset:
        if games >= max_games:
            break
        if min_elo is not None:
            game_elo = _game_min_elo(game)
            if game_elo is None or game_elo < min_elo:
                continue
        try:
            samples.extend(game_to_samples(game["moves_uci"], game["winner"]))
        except Exception:
            continue   # skip a malformed game rather than abort the whole run
        games += 1
    return samples


class ChessDataset(Dataset):
    """Yields (planes, policy_index, value) tensors for supervised training."""

    def __init__(self, samples: list[Sample]):
        self._samples = samples

    def __len__(self) -> int:
        return len(self._samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        sample = self._samples[idx]
        planes = board_to_planes(CBoard.from_fen(sample.fen))
        policy_index = move_to_index(sample.from_square, sample.to_square)
        return (
            torch.from_numpy(planes),
            torch.tensor(policy_index, dtype=torch.long),
            torch.tensor(sample.value, dtype=torch.float32),
        )
