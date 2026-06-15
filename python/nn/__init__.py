"""
Date created: Jun 14
Author: Kane Weng

Supervised policy and value networks for eschess, plus the encoding and hybrid
hooks that connect them to the engine. Requires the optional torch/numpy deps
(install with: uv sync --extra nn).
"""

from .encoding import (
    INPUT_PLANES, POLICY_SIZE,
    board_to_planes, move_to_index, index_to_move, legal_policy_mask,
)
from .network import ConvBlock, ResidualBlock, PolicyNet, ValueNet
from .inference import NNEvaluate, policy_priors

__all__ = [
    "INPUT_PLANES", "POLICY_SIZE",
    "board_to_planes", "move_to_index", "index_to_move", "legal_policy_mask",
    "ConvBlock", "ResidualBlock", "PolicyNet", "ValueNet",
    "NNEvaluate", "policy_priors",
]
