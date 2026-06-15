"""
Date created: Jun 14
Author: Kane Weng

Supervised training loops for the policy and value networks. Samples come from
the angeluriot/chess_games Hugging Face dataset (see dataset.py). Policy training
is cross-entropy on the from-to move logits; value training is mean-squared error
against the tanh target.

Run as a module from the python/ directory so package imports resolve:

  python -m nn.train --mode policy --max-games 2000 --epochs 5
  python -m nn.train --mode value  --max-games 2000 --min-elo 2200 --epochs 5
"""

import argparse
from datetime import datetime
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader

from .dataset import ChessDataset, load_hf_samples
from .network import PolicyNet, ValueNet


def train_policy(
    net: PolicyNet,
    dataset: ChessDataset,
    epochs: int = 5,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str = "cpu",
) -> None:
    net = net.to(device).train()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    # CrossEntropy: Choosing a chess move is a multi-class classification problem
    # It penalizes the model if it assigns low probability to high-level player's move
    loss_fn = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        total = 0.0
        for planes, policy_index, _value in loader:
            planes, policy_index = planes.to(device), policy_index.to(device)
            logits = net(planes)
            loss = loss_fn(logits, policy_index)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * planes.size(0)
        print(f"[policy] epoch {epoch + 1}/{epochs}  loss {total / len(dataset):.4f}", flush=True)


def train_value(
    net: ValueNet,
    dataset: ChessDataset,
    epochs: int = 5,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str = "cpu",
) -> None:
    net = net.to(device).train()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    # MSELoss: Evaluating a board state is a regression task
    # It penalizes incorrect evaluations through Mean Squared Error
    loss_fn = nn.MSELoss()

    for epoch in range(epochs):
        total = 0.0
        for planes, _policy_index, value in loader:
            planes, value = planes.to(device), value.to(device)
            prediction = net(planes)
            loss = loss_fn(prediction, value)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * planes.size(0)
        print(f"[value] epoch {epoch + 1}/{epochs}  loss {total / len(dataset):.4f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Supervised training for the eschess networks.")
    parser.add_argument("--mode", choices=("policy", "value"), required=True)
    parser.add_argument("--max-games", type=int, default=1000, help="number of games to stream")
    parser.add_argument("--min-elo", type=int, default=None, help="skip games below this ELO")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--res-blocks", type=int, default=4, help="0 for a plain CNN trunk")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", default=None, help="optional path to save the trained weights")
    args = parser.parse_args()

    if args.out is None:
        nn_dir = Path(__file__).resolve().parent
        weights_dir = nn_dir / "weights"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.out = str(weights_dir / f"{timestamp}_{args.mode}.pt")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    samples = load_hf_samples(max_games=args.max_games, min_elo=args.min_elo)
    print(f"loaded {len(samples)} samples from {args.max_games} games", flush=True)
    dataset = ChessDataset(samples)

    if args.mode == "policy":
        net = PolicyNet(num_res_blocks=args.res_blocks)
        train_policy(net, dataset, args.epochs, args.batch_size, args.lr, args.device)
    else:
        net = ValueNet(num_res_blocks=args.res_blocks)
        train_value(net, dataset, args.epochs, args.batch_size, args.lr, args.device)

    torch.save(net.state_dict(), args.out)
    print(f"saved weights to {args.out}", flush=True)


if __name__ == "__main__":
    main()
