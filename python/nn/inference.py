"""
Date created: Jun 14
Author: Kane Weng

Hybrid hooks that let the trained networks plug into the existing engine.

  NNEvaluate    : wraps a ValueNet as a BaseEvaluate, so the alpha-beta search
                  can use it in place of (or alongside) the handcrafted eval.
  policy_priors : turns a PolicyNet into per-move probabilities, usable for
                  move ordering on top of the handcrafted search.

The value net is trained with targets from White's perspective in [-1, 1]; the
engine works in pawn units from White's perspective, so the evaluation scales
the tanh output by a constant pawn factor.
"""

import numpy as np
import torch

from engine.board import CBoard
from engine.evaluate import BaseEvaluate
from .encoding import board_to_planes, index_to_move, legal_policy_mask
from .network import PolicyNet, ValueNet

# A decisive but non-mating value (+-1) maps to roughly this many pawns.
_VALUE_PAWN_SCALE = 10.0


def _planes_tensor(board: CBoard, device: str) -> torch.Tensor:
    """Encode a board and add the batch dimension the networks expect."""
    planes = board_to_planes(board)
    return torch.from_numpy(planes).unsqueeze(0).to(device)


class NNEvaluate(BaseEvaluate):
    """Use a trained ValueNet as the search's evaluation function."""

    def __init__(self, net: ValueNet, device: str = "cpu", pawn_scale: float = _VALUE_PAWN_SCALE):
        self._net    = net.to(device).eval()
        self._device = device
        self._scale  = pawn_scale

    def evaluate(self, board: CBoard) -> float:
        with torch.no_grad():
            value = self._net(_planes_tensor(board, self._device)).item()
        return value * self._scale   # White's perspective, pawn units


def value_estimate(net: ValueNet, board: CBoard, device: str = "cpu") -> float:
    """Raw tanh value in [-1, 1] from White's perspective."""
    with torch.no_grad():
        return float(net(_planes_tensor(board, device)).item())


def policy_priors(net: PolicyNet, board: CBoard, device: str = "cpu") -> dict[tuple[int, int], float]:
    """Return {(from_square, to_square): probability} over the legal moves."""
    with torch.no_grad():
        logits = net(_planes_tensor(board, device)).squeeze(0).cpu().numpy()

    mask = legal_policy_mask(board)
    legal_indices = np.flatnonzero(mask)
    if legal_indices.size == 0:
        return {}

    legal_logits = logits[legal_indices]
    legal_logits -= legal_logits.max()          # stabilise before exp
    weights = np.exp(legal_logits)
    weights /= weights.sum()

    return {index_to_move(int(idx)): float(p) for idx, p in zip(legal_indices, weights)}
