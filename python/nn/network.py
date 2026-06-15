"""
Date created: Jun 14
Author: Kane Weng

Policy and value networks, kept as two separate models so each can be slotted
into the engine on its own (value net as an evaluation, policy net as a move
prior). Both share the same building blocks and trunk shape.

  ConvBlock      : 3x3 conv + batchnorm + relu
  ResidualBlock  : two ConvBlocks with a skip connection (the "light ResNet")
  PolicyNet      : trunk -> from-to move logits, shape (batch, POLICY_SIZE)
  ValueNet       : trunk -> scalar in [-1, 1], shape (batch,)

Set num_res_blocks=0 for a plain CNN trunk; a small positive value gives the
light ResNet. Channels and depth are constructor knobs so the same code covers
both requested architectures.
"""

import torch
from torch import nn

from .encoding import INPUT_PLANES, POLICY_SIZE

_DEFAULT_CHANNELS = 64
_DEFAULT_RES_BLOCKS = 4
_BOARD_SQUARES = 8 * 8


# -- Building blocks ---------------------------------------------------------


class ConvBlock(nn.Module):
    """3x3 convolution that preserves the 8x8 shape, then batchnorm and relu."""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False)
        self.norm = nn.BatchNorm2d(out_channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.relu(self.norm(self.conv(x)))


class ResidualBlock(nn.Module):
    """Two convolutions whose output is added back to the block input."""

    def __init__(self, channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.norm1 = nn.BatchNorm2d(channels)
        self.conv2 = nn.Conv2d(channels, channels, kernel_size=3, padding=1, bias=False)
        self.norm2 = nn.BatchNorm2d(channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = torch.relu(self.norm1(self.conv1(x)))
        out = self.norm2(self.conv2(out))
        return torch.relu(out + x)


class _Trunk(nn.Module):
    """Shared body: an input ConvBlock followed by num_res_blocks residuals."""

    def __init__(self, channels: int, num_res_blocks: int):
        super().__init__()
        self.stem = ConvBlock(INPUT_PLANES, channels)
        self.blocks = nn.Sequential(*[ResidualBlock(channels) for _ in range(num_res_blocks)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.blocks(self.stem(x))


# -- Networks ----------------------------------------------------------------


class PolicyNet(nn.Module):
    """Maps a board tensor to from-to move logits."""

    def __init__(
        self,
        channels: int = _DEFAULT_CHANNELS,
        num_res_blocks: int = _DEFAULT_RES_BLOCKS,
        head_channels: int = 32,
    ):
        super().__init__()
        self.trunk = _Trunk(channels, num_res_blocks)
        self.head = ConvBlock(channels, head_channels)
        self.fc = nn.Linear(head_channels * _BOARD_SQUARES, POLICY_SIZE)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.head(self.trunk(x))
        return self.fc(out.flatten(start_dim=1))


class ValueNet(nn.Module):
    """Maps a board tensor to a single scalar in [-1, 1]."""

    def __init__(
        self,
        channels: int = _DEFAULT_CHANNELS,
        num_res_blocks: int = _DEFAULT_RES_BLOCKS,
        head_channels: int = 1,
        hidden: int = 64,
    ):
        super().__init__()
        self.trunk = _Trunk(channels, num_res_blocks)
        self.head = ConvBlock(channels, head_channels)
        self.fc1 = nn.Linear(head_channels * _BOARD_SQUARES, hidden)
        self.fc2 = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.head(self.trunk(x))
        out = torch.relu(self.fc1(out.flatten(start_dim=1)))
        return torch.tanh(self.fc2(out)).squeeze(-1)
