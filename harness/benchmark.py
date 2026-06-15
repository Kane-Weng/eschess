"""
Date created: Jun 14
Author: Kane Weng

Benchmark one eschess configuration against another (or against Stockfish) and
rate the result. A portable replacement for benchmark.sh: it builds the engine
commands, runs harness/match.py to play the games, then harness/elo.py to rate
the PGN.

Engine A and engine B are eschess configs by default (alpha-beta with an
evaluation level, or the policy net). Point B at Stockfish with --stockfish ELO.

Examples:
    # value network vs the medium handcrafted eval
    uv run --extra nn python harness/benchmark.py --a-eval nn --b-eval medium --games 100

    # policy network vs a 1320 Stockfish, 4 games at a time
    uv run --extra nn python harness/benchmark.py --a-search policy --stockfish 1320 \
        --games 100 --concurrency 4

ML configs (eval nn / search policy) need the torch deps, so run under the nn
extra: that way this interpreter (sys.executable) can import torch, and the
engine subprocesses inherit it.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UCI   = _REPO_ROOT / "python" / "uci.py"
_MATCH = _REPO_ROOT / "harness" / "match.py"
_ELO   = _REPO_ROOT / "harness" / "elo.py"
_RESULTS_DIR = _REPO_ROOT / "harness" / "results"


def _eschess_cmd(search: str, evaluator: str, device: str) -> str:
    """Shell command that launches an eschess UCI engine with the given config."""
    return f"{sys.executable} {_UCI} --search {search} --eval {evaluator} --device {device}"


def _eschess_name(search: str, evaluator: str) -> str:
    return f"eschess-{'policy' if search == 'policy' else evaluator}"


def _run_logged(cmd: list[str], log) -> None:
    """Run a subprocess, streaming its output to both the console and a log file."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log.write(line)
        log.flush()
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark an eschess config and rate it.")
    ap.add_argument("--a-search", choices=("alphabeta", "policy"), default="alphabeta")
    ap.add_argument("--a-eval", choices=("simple", "medium", "complex", "nn"), default="nn")
    ap.add_argument("--b-search", choices=("alphabeta", "policy"), default="alphabeta")
    ap.add_argument("--b-eval", choices=("simple", "medium", "complex", "nn"), default="medium")
    ap.add_argument("--stockfish", type=int, default=None,
                    help="benchmark engine A against Stockfish at this Elo (overrides engine B)")
    ap.add_argument("--device", default="cpu", help="torch device for ML configs")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--movetime", type=int, default=100, help="ms per move")
    ap.add_argument("--concurrency", type=int, default=1, help="games to play in parallel")
    ap.add_argument("--openings", default=str(_REPO_ROOT / "harness" / "openings.epd"))
    ap.add_argument("--out-dir", default=str(_RESULTS_DIR),
                    help="parent dir for timestamped run folders (holds the pgn + log)")
    ap.add_argument("--pgn", default=None, help="explicit PGN path (default: inside the run dir)")
    args = ap.parse_args()

    a_cmd  = _eschess_cmd(args.a_search, args.a_eval, args.device)
    a_name = _eschess_name(args.a_search, args.a_eval)

    if args.stockfish is not None:
        b_cmd  = "stockfish"
        b_opts = ["UCI_LimitStrength=true", f"UCI_Elo={args.stockfish}"]
        b_name = f"SF-{args.stockfish}"
    else:
        b_cmd  = _eschess_cmd(args.b_search, args.b_eval, args.device)
        b_opts = []
        b_name = _eschess_name(args.b_search, args.b_eval)

    # elo.py needs two distinct names; disambiguate identical configs.
    if a_name == b_name:
        a_name, b_name = f"{a_name}-A", f"{b_name}-B"

    # One timestamped run folder holds the PGN and a full log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.out_dir) / f"{timestamp}_{a_name}_vs_{b_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pgn_path = args.pgn or str(run_dir / "games.pgn")
    log_path = run_dir / "benchmark.log"

    match_cmd = [
        sys.executable, str(_MATCH),
        "--engine1", a_cmd, "--name1", a_name,
        "--engine2", b_cmd, "--name2", b_name,
        "--games", str(args.games), "--movetime", str(args.movetime),
        "--concurrency", str(args.concurrency),
        "--openings", args.openings, "--pgn", pgn_path,
    ]
    for opt in b_opts:
        match_cmd += ["--opt2", opt]

    header = (f"Benchmark: {a_name} vs {b_name}  ({args.games} games @ {args.movetime}ms, "
              f"concurrency {args.concurrency})")

    with open(log_path, "w") as log:
        log.write(f"{header}\nstarted: {timestamp}\n")
        log.write(f"engine1: {a_cmd}\n")
        log.write(f"engine2: {b_cmd}" + (f"  opts={b_opts}" if b_opts else "") + "\n\n")
        log.flush()

        print(header, flush=True)
        _run_logged(match_cmd, log)

        log.write("\n=== Rating ===\n")
        print("\n=== Rating ===", flush=True)
        elo_cmd = [sys.executable, str(_ELO), pgn_path]
        if args.stockfish is not None:
            elo_cmd += ["--anchor", b_name, "--anchor-elo", str(args.stockfish)]
        _run_logged(elo_cmd, log)

    print(f"\nResults saved to {run_dir}", flush=True)


if __name__ == "__main__":
    main()
