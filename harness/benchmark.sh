#!/usr/bin/env bash
#
# Date created: Jun 14
# Author: Kane Weng
#
# One-shot Elo benchmark: play Eschess against a strength-limited Stockfish with
# the bundled match runner, then rate the PGN with Ordo (or harness/elo.py).
# Designed to run inside the Docker image, where stockfish and ordo are present.
#
# Usage:  harness/benchmark.sh [GAMES] [MOVETIME_MS] [STOCKFISH_ELO]
#         harness/benchmark.sh 100 100 1320

set -euo pipefail

GAMES="${1:-100}"
MOVETIME="${2:-100}"
SF_ELO="${3:-1320}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGN="${REPO_DIR}/results.pgn"

if ! command -v stockfish >/dev/null 2>&1; then
    echo "error: 'stockfish' not found. Run inside the Docker image, or install it." >&2
    exit 1
fi

echo "Eschess vs Stockfish(Elo ${SF_ELO}) — ${GAMES} games @ ${MOVETIME}ms/move"
python "${REPO_DIR}/harness/match.py" \
    --engine1 "python ${REPO_DIR}/python/uci.py" --name1 Eschess \
    --engine2 "stockfish"                 --name2 "SF-${SF_ELO}" \
    --opt2 UCI_LimitStrength=true --opt2 "UCI_Elo=${SF_ELO}" \
    --games "${GAMES}" --movetime "${MOVETIME}" \
    --openings "${REPO_DIR}/harness/openings.epd" --pgn "${PGN}"

echo
echo "=== Rating ==="
# elo.py is robust to one-sided results (Ordo refuses to rate a "not well
# connected" database, e.g. when one engine wins every game). Ordo is also
# installed in the image for well-connected multi-engine round-robins:
#   ordo -Q -a 1320 -A SF-1320 -W -s 100 -p results.pgn
python "${REPO_DIR}/harness/elo.py" "${PGN}" --anchor "SF-${SF_ELO}" --anchor-elo "${SF_ELO}"
