"""
Date created: Jun 15
Author: Kane Weng

Adopt the best self-play RL networks for the engine and GUI. Training (nn.rl)
writes its accepted nets to nn/weights/rl/ so the supervised baseline keeps
serving the GUI; this script copies the chosen RL checkpoints up into
nn/weights/ as freshly timestamped *_policy.pt / *_value.pt, which is where
engine_backend._latest_weights looks.

  python -m nn.promote                 # promote nn/weights/rl/best_{policy,value}.pt
  python -m nn.promote --policy <path> --value <path>
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from engine_backend import _WEIGHTS_DIR

_RL_DIR = _WEIGHTS_DIR / "rl"


def _default_source(kind: str) -> Path:
    """Prefer the gate-accepted best; fall back to the latest candidate."""
    best = _RL_DIR / f"best_{kind}.pt"
    if best.exists():
        return best
    return _RL_DIR / f"latest_{kind}.pt"   # may be absent; _promote reports it


def _promote(kind: str, source: Path, stamp: str) -> Path:
    if not source.exists():
        raise FileNotFoundError(
            f"no '{kind}' RL weights at {source}. Train some first: python -m nn.rl")
    target = _WEIGHTS_DIR / f"{stamp}_{kind}.pt"
    shutil.copyfile(source, target)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote RL networks for the engine/GUI to load.")
    parser.add_argument("--policy", default=None, help="RL policy weights (default: rl/best_policy.pt)")
    parser.add_argument("--value", default=None, help="RL value weights (default: rl/best_value.pt)")
    args = parser.parse_args()

    policy_src = Path(args.policy) if args.policy else _default_source("policy")
    value_src  = Path(args.value)  if args.value  else _default_source("value")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    policy_out = _promote("policy", policy_src, stamp)
    value_out  = _promote("value", value_src, stamp)
    print(f"promoted policy -> {policy_out}", flush=True)
    print(f"promoted value  -> {value_out}", flush=True)
    print("the engine/GUI will now load these as the latest weights.", flush=True)


if __name__ == "__main__":
    main()
