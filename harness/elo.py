"""
Date created: Jun 14
Author: Kane Weng

Elo rating + confidence intervals from a PGN of match results.

A dependency-free stand-in for Ordo / BayesElo: parse the [White]/[Black]/[Result]
tags, then report ratings. For a two-engine match it prints the full head-to-head
breakdown (score, Elo difference ± 95% margin, likelihood-of-superiority, draw
rate). For three or more engines it solves a Bradley-Terry model by
minorization-maximization for a full rating table.

Anchor an absolute scale with a known opponent rating, e.g. Stockfish at 1320:

    python harness/elo.py results.pgn --anchor SF-1320 --anchor-elo 1320
"""

import argparse
import math
import re
from collections import defaultdict
from pathlib import Path

_TAG = re.compile(r'\[(\w+)\s+"([^"]*)"\]')


# ── PGN parsing ───────────────────────────────────────────────────────────────

def parse_games(pgn_path: str) -> list[tuple[str, str, str]]:
    """Return [(white, black, result)] for each game with a decisive/drawn result."""
    games: list[tuple[str, str, str]] = []
    white = black = result = None
    for line in Path(pgn_path).read_text().splitlines():
        match = _TAG.match(line.strip())
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key == "White":
            white = value
        elif key == "Black":
            black = value
        elif key == "Result":
            result = value
            if white is not None and black is not None and result in ("1-0", "0-1", "1/2-1/2"):
                games.append((white, black, result))
            white = black = result = None
    return games


# ── Elo helpers ───────────────────────────────────────────────────────────────

def score_to_elo(score: float) -> float:
    """Expected-score → Elo difference (the inverse of the logistic Elo curve)."""
    score = min(max(score, 1e-12), 1 - 1e-12)
    return -400.0 * math.log10(1.0 / score - 1.0)


def _erf(x: float) -> float:
    return math.erf(x)


# ── Head-to-head (two engines) ────────────────────────────────────────────────

def head_to_head(games, anchor: str | None, anchor_elo: float) -> None:
    players = sorted({p for g in games for p in g[:2]})
    a, b = players

    wins = draws = losses = 0          # from a's perspective
    for white, black, result in games:
        if result == "1/2-1/2":
            draws += 1
        elif (result == "1-0") == (white == a):
            wins += 1
        else:
            losses += 1

    n = wins + draws + losses
    if n == 0:
        print("No games found.")
        return

    p_w, p_d, p_l = wins / n, draws / n, losses / n
    mu = p_w + 0.5 * p_d
    # Per-game variance of the score, then standard error of the mean.
    var = p_w * (1 - mu) ** 2 + p_d * (0.5 - mu) ** 2 + p_l * (0 - mu) ** 2
    stderr = math.sqrt(var / n) if n else 0.0

    elo = score_to_elo(mu)
    elo_lo = score_to_elo(mu - 1.96 * stderr)
    elo_hi = score_to_elo(mu + 1.96 * stderr)
    margin = (elo_hi - elo_lo) / 2

    # Likelihood of superiority (probability a is genuinely stronger than b).
    decisive = wins + losses
    los = 0.5 * (1 + _erf((wins - losses) / math.sqrt(2 * decisive))) if decisive else 0.5

    print(f"Games:        {n}")
    print(f"{a} vs {b}:   +{wins} ={draws} -{losses}")
    print(f"Score:        {mu:.4f}  ({mu:.1%})   draw rate {p_d:.1%}")
    print(f"Elo diff:     {elo:+.1f}  ±{margin:.1f}   (95% CI [{elo_lo:+.1f}, {elo_hi:+.1f}])")
    print(f"LOS:          {los:.1%}   ({a} stronger than {b})")

    if anchor in (a, b):
        other = b if anchor == a else a
        diff = -elo if anchor == a else elo
        d_lo, d_hi = (-elo_hi, -elo_lo) if anchor == a else (elo_lo, elo_hi)
        print(f"\nAnchored to {anchor} = {anchor_elo:.0f} Elo:")
        print(f"  {other}: {anchor_elo + diff:.0f} Elo   "
              f"(95% CI [{anchor_elo + d_lo:.0f}, {anchor_elo + d_hi:.0f}])")
    elif anchor is not None:
        print(f"\n[warn] anchor {anchor!r} is not one of the two players: {a}, {b}")


# ── Bradley-Terry MM (three or more engines) ──────────────────────────────────

def bradley_terry(games, anchor: str | None, anchor_elo: float) -> None:
    players = sorted({p for g in games for p in g[:2]})
    idx = {p: i for i, p in enumerate(players)}
    n = len(players)

    points = [0.0] * n                       # wins + 0.5·draws
    pair_games = defaultdict(int)            # games between each unordered pair
    for white, black, result in games:
        i, j = idx[white], idx[black]
        pair_games[(min(i, j), max(i, j))] += 1
        if result == "1-0":
            points[i] += 1
        elif result == "0-1":
            points[j] += 1
        else:
            points[i] += 0.5
            points[j] += 0.5

    gamma = [1.0] * n
    for _ in range(1000):
        new = gamma[:]
        for i in range(n):
            if points[i] == 0:
                continue
            denom = 0.0
            for (a, b), cnt in pair_games.items():
                if i == a:
                    denom += cnt / (gamma[i] + gamma[b])
                elif i == b:
                    denom += cnt / (gamma[i] + gamma[a])
            if denom > 0:
                new[i] = points[i] / denom
        # Normalize to the geometric mean to keep the scale stable.
        logmean = sum(math.log(g) for g in new) / n
        scale = math.exp(logmean)
        new = [g / scale for g in new]
        if max(abs(a - b) for a, b in zip(new, gamma)) < 1e-9:
            gamma = new
            break
        gamma = new

    elos = {p: 400.0 * math.log10(gamma[idx[p]]) for p in players}

    # Shift so the anchor sits at its known rating, else center the field on 0.
    if anchor in elos:
        shift = anchor_elo - elos[anchor]
    else:
        if anchor is not None:
            print(f"[warn] anchor {anchor!r} not found; centering field on 0\n")
        shift = -sum(elos.values()) / n
    elos = {p: e + shift for p, e in elos.items()}

    games_played = [0] * n
    for (a, b), cnt in pair_games.items():
        games_played[a] += cnt
        games_played[b] += cnt

    print(f"{'Rank':<5}{'Engine':<24}{'Elo':>8}{'Points':>9}{'Games':>8}")
    print("-" * 54)
    for rank, p in enumerate(sorted(players, key=lambda q: -elos[q]), 1):
        print(f"{rank:<5}{p:<24}{elos[p]:>8.0f}{points[idx[p]]:>9.1f}{games_played[idx[p]]:>8}")


# ── Driver ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Rate engines from a PGN of results.")
    ap.add_argument("pgn", help="PGN file produced by the match harness / cutechess-cli")
    ap.add_argument("--anchor", default=None, help="engine name to fix on the absolute scale")
    ap.add_argument("--anchor-elo", type=float, default=0.0, help="known Elo of the anchor")
    args = ap.parse_args()

    games = parse_games(args.pgn)
    if not games:
        print(f"No rated games found in {args.pgn}")
        return

    players = {p for g in games for p in g[:2]}
    print(f"Parsed {len(games)} games among {len(players)} engine(s) from {args.pgn}\n")

    if len(players) == 2:
        head_to_head(games, args.anchor, args.anchor_elo)
    else:
        bradley_terry(games, args.anchor, args.anchor_elo)


if __name__ == "__main__":
    main()
