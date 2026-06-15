"""
Date created: Jun 14
Author: Kane Weng

Cross-language performance telemetry for the equivalent eschess engines
(Python, C++, Rust). Drives each engine over UCI on a shared set of positions
and reports, per engine:

  - Nodes Per Second (NPS): search throughput (move-gen + evaluation loops).
    All three engines visit the same node count at a fixed depth (they are
    logically equivalent), so NPS is a clean speed comparison.
  - Peak memory (MB): high-water RSS of the engine process during the run
    (read from /proc/<pid>/status VmHWM). It shows the spatial cost of the search
    and its transposition table.
  - Cache misses: L1/LL cache-miss rate via 'perf stat', when the host permits
    hardware counters (needs perf_event_paranoid <= 2); otherwise reported N/A.

Writes a timestamped CSV under harness/results/ and, when matplotlib is
installed (the 'bench' extra), bar-chart PNGs beside it.

Examples:
    uv run python harness/telemetry.py --depth 6
    uv run --extra bench python harness/telemetry.py --depth 7 --plot
    uv run python harness/telemetry.py --engines py,cpp,rust --hash 64
"""

import argparse
import csv
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RESULTS_DIR = _REPO_ROOT / "harness" / "results"

ENGINE_COMMANDS = {
    "py":   f"{sys.executable} {_REPO_ROOT / 'python' / 'uci.py'}",
    "cpp":  str(_REPO_ROOT / "cpp" / "build" / "uci"),
    "rust": str(_REPO_ROOT / "rust" / "target" / "release" / "uci"),
}


def _binary_available(tag: str, command: str) -> bool:
    """Python is always runnable; the compiled engines need a built binary."""
    if tag == "py":
        return True
    return Path(shlex.split(command)[0]).exists()


def _load_positions(epd_path: Path, limit: int | None) -> list[str]:
    """FENs from an EPD file (first 4 fields + default clocks), startpos first."""
    fens = ["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"]
    if epd_path.exists():
        for line in epd_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split()
            # A valid placement+side+castling+ep prefix: side must be w/b.
            if len(fields) >= 4 and fields[1] in ("w", "b"):
                fens.append(" ".join(fields[:4]) + " 0 1")
    return fens[:limit] if limit else fens


class UCIClient:
    """Minimal UCI driver that also tracks the engine process for /proc stats."""

    def __init__(self, command: str):
        self.command = command
        # shell=False so self.proc.pid is the engine itself (needed for an
        # accurate VmHWM read in peak_rss_mb())
        self.proc = subprocess.Popen(
            shlex.split(command), text=True, bufsize=1, shell=False, 
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        self._send("uci")
        self._wait_for("uciok")

    def _send(self, line: str) -> None:
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _wait_for(self, token: str) -> None:
        for raw in self.proc.stdout:
            if raw.strip() == token:
                return
        raise RuntimeError(f"engine {self.command!r} closed before '{token}'")

    def set_hash(self, mb: int) -> None:
        self._send(f"setoption name Hash value {mb}")
        self._send("isready")
        self._wait_for("readyok")

    def search(self, fen: str, depth: int) -> tuple[int, float]:
        """Run a fixed-depth search; return (nodes, wall_seconds)."""
        self._send("ucinewgame")
        self._send(f"position fen {fen}")
        nodes = 0
        start = time.perf_counter()
        self._send(f"go depth {depth}")
        for raw in self.proc.stdout:
            line = raw.strip()
            if line.startswith("info"):
                toks = line.split()
                if "nodes" in toks:
                    nodes = int(toks[toks.index("nodes") + 1])
            elif line.startswith("bestmove"):
                break
        return nodes, time.perf_counter() - start

    def peak_rss_mb(self) -> float | None:
        """High-water RSS of the engine process, from /proc/<pid>/status."""
        try:
            for line in Path(f"/proc/{self.proc.pid}/status").read_text().splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0  # kB → MB
        except OSError:
            pass
        return None

    def close(self) -> None:
        try:
            self._send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def _measure_cache(command: str, fen: str, depth: int) -> tuple[float | None, str]:
    """Cache-miss rate via 'perf stat', or (None, reason) when unavailable."""
    if not Path("/usr/bin/perf").exists():
        return None, "perf not installed"
    uci_input = f"uci\nposition fen {fen}\ngo depth {depth}\nquit\n"
    perf_cmd = ["perf", "stat", "-x", ",", "-e", "cache-references,cache-misses",
                "bash", "-c", f"{command} >/dev/null"]
    try:
        proc = subprocess.run(perf_cmd, input=uci_input, capture_output=True,
                              text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, f"perf failed: {exc}"
    refs = misses = None
    for line in proc.stderr.splitlines():
        parts = line.split(",")
        if len(parts) >= 3:
            val, _unit, event = parts[0], parts[1], parts[2]
            if "not supported" in line or "not counted" in line or "<not" in val:
                return None, "counters blocked (perf_event_paranoid)"
            try:
                if event.startswith("cache-references"):
                    refs = float(val)
                elif event.startswith("cache-misses"):
                    misses = float(val)
            except ValueError:
                continue
    if refs and misses is not None:
        return 100.0 * misses / refs, "ok"
    return None, "counters blocked (perf_event_paranoid)"


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-language engine telemetry (NPS / memory / cache).")
    ap.add_argument("--engines", default="py,cpp,rust",
                    help="comma-separated engine tags to benchmark (py, cpp, rust)")
    ap.add_argument("--depth", type=int, default=5, help="fixed search depth per position")
    ap.add_argument("--hash", type=int, default=32, help="transposition-table size (MB)")
    ap.add_argument("--positions", type=int, default=8, help="number of positions to average over")
    ap.add_argument("--openings", default=str(_REPO_ROOT / "harness" / "openings.epd"))
    ap.add_argument("--cache", action="store_true", help="also measure cache misses via perf")
    ap.add_argument("--plot", action="store_true", help="render PNG charts (needs matplotlib)")
    ap.add_argument("--out-dir", default=str(_RESULTS_DIR))
    args = ap.parse_args()

    tags = [t.strip() for t in args.engines.split(",") if t.strip()]
    fens = _load_positions(Path(args.openings), args.positions)
    print(f"Telemetry: depth {args.depth}, {len(fens)} positions, Hash {args.hash} MB\n")

    rows = []
    for tag in tags:
        command = ENGINE_COMMANDS.get(tag)
        if command is None:
            print(f"  {tag}: unknown engine tag, skipping")
            continue
        if not _binary_available(tag, command):
            print(f"  {tag}: binary not built ({shlex.split(command)[0]}), skipping")
            continue

        client = UCIClient(command)
        client.set_hash(args.hash)
        total_nodes, total_time = 0, 0.0
        for fen in fens:
            nodes, secs = client.search(fen, args.depth)
            total_nodes += nodes
            total_time += secs
        nps = total_nodes / total_time if total_time > 0 else 0.0
        peak_mb = client.peak_rss_mb()
        client.close()

        cache_rate, cache_note = (None, "skipped")
        if args.cache:
            cache_rate, cache_note = _measure_cache(command, fens[0], args.depth)

        rows.append({
            "engine": tag, "depth": args.depth, "nodes": total_nodes,
            "time_s": round(total_time, 4), "nps": round(nps),
            "peak_rss_mb": round(peak_mb, 1) if peak_mb else None,
            "cache_miss_pct": round(cache_rate, 2) if cache_rate is not None else None,
            "cache_note": cache_note,
        })
        speed = f"{nps:>12,.0f} nps"
        mem = f"{peak_mb:6.1f} MB" if peak_mb else "    n/a"
        cache = f"{cache_rate:5.2f}%" if cache_rate is not None else f"n/a ({cache_note})"
        print(f"  {tag:>4}: {speed}   peak {mem}   cache-miss {cache}")

    if not rows:
        print("\nNo engines benchmarked. Build the C++/Rust binaries first.")
        return

    # Speedups relative to the slowest engine (usually Python).
    base = min(r["nps"] for r in rows if r["nps"])
    print("\nRelative speed:")
    for r in rows:
        if r["nps"]:
            print(f"  {r['engine']:>4}: {r['nps'] / base:6.1f}x")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"telemetry_{ts}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV written to {csv_path}")

    if args.plot:
        _plot(rows, out_dir / f"telemetry_{ts}.png", args.depth)


def _plot(rows: list[dict], path: Path, depth: int) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot (install the 'bench' extra).")
        return

    engines = [r["engine"] for r in rows]
    have_cache = any(r["cache_miss_pct"] is not None for r in rows)
    ncols = 3 if have_cache else 2
    fig, axes = plt.subplots(1, ncols, figsize=(5 * ncols, 4))

    axes[0].bar(engines, [r["nps"] for r in rows], color="#4C72B0")
    axes[0].set_title(f"Nodes per second (depth {depth})")
    axes[0].set_ylabel("NPS")

    axes[1].bar(engines, [r["peak_rss_mb"] or 0 for r in rows], color="#55A868")
    axes[1].set_title("Peak memory")
    axes[1].set_ylabel("MB")

    if have_cache:
        axes[2].bar(engines, [r["cache_miss_pct"] or 0 for r in rows], color="#C44E52")
        axes[2].set_title("Cache-miss rate")
        axes[2].set_ylabel("%")

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"Plot written to {path}")


if __name__ == "__main__":
    main()
