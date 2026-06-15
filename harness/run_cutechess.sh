#!/usr/bin/env bash
#
# Date created: Jun 14
# Author: Kane Weng
#
# Benchmark Eschess against a dialed-down Stockfish using cutechess-cli, then
# rate the result with Ordo (falling back to harness/elo.py).
#
# cutechess-cli, Stockfish, and Ordo are only bundled in the Docker image, so
# this is the "production" path: run it in the container. The PGN is written to
# harness/results/, so mount that dir to keep it on the host.
#
# Usage (in Docker):
#   docker run --rm -v "$PWD/harness/results:/app/harness/results" eschess \
#       harness/run_cutechess.sh [GAMES] [TIME_CONTROL] [STOCKFISH_ELO]
#   docker run --rm -v "$PWD/harness/results:/app/harness/results" eschess \
#       harness/run_cutechess.sh 100 20+0.2 1320
#
# (Locally it needs cutechess-cli + stockfish + ordo on PATH; otherwise prefer
#  the pure-Python harness/match.py path.)

set -euo pipefail

GAMES="${1:-100}"
TC="${2:-20+0.2}"        # cutechess clock control: base+increment, in seconds
SF_ELO="${3:-1320}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${REPO_DIR}/harness/results"
mkdir -p "${RESULTS_DIR}"
PGN="${RESULTS_DIR}/cutechess_$(date +%Y%m%d_%H%M%S).pgn"
ROUNDS=$(( (GAMES + 1) / 2 ))   # 2 games per round (-repeat swaps colours)

for tool in cutechess-cli stockfish; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "error: '$tool' not found on PATH." >&2
        echo "       Use the Docker image (it bundles this tool) or the pure-Python path:" >&2
        echo "       python harness/match.py --engine1 \"python3 python/uci.py\" \\" >&2
        echo "           --engine2 stockfish --opt2 UCI_LimitStrength=true --opt2 UCI_Elo=${SF_ELO} \\" >&2
        echo "           --games ${GAMES} --movetime 100 \\" >&2
        echo "           --openings harness/openings.epd --pgn results.pgn" >&2
        exit 1
    fi
done

echo "Eschess vs Stockfish(Elo ${SF_ELO}) — ${GAMES} games @ tc=${TC}"

cutechess-cli \
    -engine name=Eschess cmd=python3 arg="${REPO_DIR}/python/uci.py" dir="${REPO_DIR}" proto=uci \
    -engine name="SF-${SF_ELO}" cmd=stockfish proto=uci \
        option.UCI_LimitStrength=true option."UCI_Elo=${SF_ELO}" \
    -each tc="${TC}" \
    -openings file="${REPO_DIR}/harness/openings.epd" format=epd order=random \
    -games 2 -rounds "${ROUNDS}" -repeat \
    -draw movenumber=40 movecount=8 score=10 \
    -resign movecount=4 score=900 \
    -ratinginterval 10 \
    -pgnout "${PGN}"

echo
echo "=== Rating ==="
if command -v ordo >/dev/null 2>&1; then
    ordo -Q -D -a "${SF_ELO}" -A "SF-${SF_ELO}" -W -n8 -s100 -p "${PGN}"
else
    echo "(ordo not found — using bundled harness/elo.py)"
    python3 "${REPO_DIR}/harness/elo.py" "${PGN}" --anchor "SF-${SF_ELO}" --anchor-elo "${SF_ELO}"
fi
