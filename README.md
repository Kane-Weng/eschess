# Eschess

A chess engine project built to **show how it thinks**, and to compare engine
techniques across methods
and languages.

## What's inside

**Board & move generation**
- Bitboard representation with Little-Endian Rank-File (LERF) mapping
- Wrap-safe directional shifts and ray-walking for sliding pieces
- Full legal move generation with make/unmake, castling, en passant, promotion
- Zobrist hashing for fast position keys
- FEN (de)serialization

**Search** (alpha-beta family)
- Minimax with alpha-beta pruning
- Iterative deepening with time management
- Transposition table keyed by Zobrist hash (depth-preferred replacement)
- Move ordering: TT move → promotions → MVV-LVA captures → killer moves →
  history heuristic (with a self-bounding "gravity" update)
- Quiescence search to tame the horizon effect

**Evaluation** (handcrafted, three interchangeable levels)
- Material + piece-square tables
- Pawn structure (doubled / isolated / passed), bishop pair, rough mobility,
  and a midgame/endgame king-safety table

**Neural networks** (supervised; optional `nn` extra)
- Separate policy and value networks, each with a CNN or light-ResNet trunk
  (one `num_res_blocks` knob switches between them)
- Board-to-planes encoding and a 4096 from-to policy head
- Hybrid hooks: the value net drops into the alpha-beta search as a
  `BaseEvaluate`, and the policy net supplies move priors
- Dataset and training-loop templates for supervised learning (no RL yet)

**Interfaces**
- UCI protocol over stdin/stdout — drives from any GUI or match runner
- A pygame GUI to play against the bot, with legal-move hints and a promotion picker

**Benchmarking harness**
- A dependency-free UCI match runner that referees games and emits PGN
- Elo analysis: head-to-head Elo difference with a 95% confidence interval and
  likelihood-of-superiority, plus a Bradley-Terry rating table for 3+ engines
- A `cutechess-cli` + Stockfish + Ordo pipeline for the standard workflow
- A 12-position opening suite for positional variety

## Tools

Python 3.12 · [uv](https://docs.astral.sh/uv/) · pygame · Stockfish (sparring
partner) · Ordo (rating) · cutechess-cli (match runner) · Docker

## Quick start (local)

```bash
uv sync                 # create the environment from the lockfile

uv run python python/main.py   # play against the bot (pygame GUI)
uv run python python/uci.py    # talk UCI:  uci, isready, position startpos, go movetime 1000
```

The Python implementation lives under `python/` (engine core in `python/engine`,
neural nets in `python/nn`), with equivalent-logic ports beside it in `cpp/`
(C++17) and `rust/` (Rust). Each port is a standalone UCI binary that the match
harness and the GUI drive identically. Shared tooling (`assets/`, `harness/`)
stays at the repo root.

### Cross-language engines (C++ / Rust)

The C++ and Rust engines are line-for-line ports of the Python core: the same
bitboard move generation, handcrafted evaluation, and alpha-beta search with a
transposition table. They are verified equivalent — identical perft counts and
byte-identical search output (scores, node counts, principal variation) at a
fixed depth — and run orders of magnitude faster.

```bash
# C++  → cpp/build/uci
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release && cmake --build cpp/build -j

# Rust → rust/target/release/uci
cargo build --release --manifest-path rust/Cargo.toml

# Validate move generation (should match the reference perft numbers)
cpp/build/perft
cargo run --release --manifest-path rust/Cargo.toml --bin perft
```

Play the GUI against any of the three brains (the board still renders in Python;
only the bot's move is computed by the chosen engine):

```bash
uv run python python/main.py --lang py                 # in-process Python (default)
uv run python python/main.py --lang cpp                # C++ UCI binary
uv run python python/main.py --lang rust               # Rust UCI binary
```

To train the supervised networks, install the optional dependencies first. Games
are streamed from the [angeluriot/chess_games](https://huggingface.co/datasets/angeluriot/chess_games)
dataset and replayed into (position, move, result) samples:

```bash
uv sync --extra nn             # adds torch + numpy + datasets

cd python
python -m nn.train --mode policy --max-games 2000 --epochs 5
python -m nn.train --mode value  --max-games 2000 --min-elo 2200 --epochs 5
```

## Docker

The image bundles the engine with every external tool the benchmark needs —
**Stockfish**, **Ordo**, and **cutechess-cli** — and builds the **C++ and Rust**
engines (`cpp/build/uci`, `rust/target/release/uci`), so the entire
cross-language pipeline (matches, telemetry, ACL vs Stockfish) is reproducible
with no host setup.

```bash
docker build -t eschess .

# Run the engine as a UCI process
docker run --rm -i eschess python python/uci.py

# Benchmark vs a strength-limited Stockfish
docker run --rm eschess python harness/benchmark.py --a-eval medium --stockfish 1320 --games 100

# Cross-language throughput, and move quality vs Stockfish
docker run --rm eschess python harness/telemetry.py --depth 7
docker run --rm eschess bash -c '\
    python harness/match.py --engine1 cpp/build/uci --name1 eschess-cpp \
        --engine2 stockfish --name2 SF-1350 --opt2 UCI_LimitStrength=true \
        --opt2 UCI_Elo=1350 --games 4 --movetime 100 --pgn /tmp/g.pgn && \
    python harness/acl.py /tmp/g.pgn --ref stockfish --ref-depth 12'
```

The benchmark writes its PGN to `results.pgn` *inside* the container, so with
`--rm` it disappears when the run ends. To keep it, mount a host directory and
copy it out:

```bash
docker run --rm -v "$PWD:/out" eschess \
    bash -c "python harness/benchmark.py --a-eval medium --stockfish 1320 --games 100 && cp results.pgn /out/"
```

(Running the harness locally instead writes `results.pgn` straight into your
working directory.)

## Benchmarking & Elo

**Play a match.** The runner launches two UCI engines, referees with Eschess's
own board logic (checkmate, stalemate, 50-move, threefold, insufficient
material), and writes a PGN:

```bash
uv run python harness/match.py \
    --engine1 "python3 python/uci.py" --name1 EschessA \
    --engine2 "python3 python/uci.py" --name2 EschessB \
    --games 100 --movetime 100 --concurrency 4 \
    --openings harness/openings.epd --pgn results.pgn
```

`--concurrency N` plays N games in parallel (each worker owns its own engine
pair). The engine config is chosen on the command line, so any matchup works,
e.g. `--engine1 "python3 python/uci.py --eval nn"` (value network) or
`--engine2 "python3 python/uci.py --search policy"` (policy network).

Point `--engine2` at Stockfish (capped to 1320 Elo) for a real benchmark:

```bash
uv run python harness/match.py \
    --engine1 "python3 python/uci.py" --name1 Eschess \
    --engine2 "stockfish"             --name2 SF-1320 \
    --opt2 UCI_LimitStrength=true --opt2 UCI_Elo=1320 \
    --games 100 --movetime 100 --openings harness/openings.epd --pgn results.pgn
```

**Rate the results.** For two engines this reports the score, Elo difference ±
95% margin, the confidence interval, likelihood-of-superiority, and draw rate;
for three or more it solves a Bradley-Terry model for a full rating table:

```bash
uv run python harness/elo.py results.pgn --anchor SF-1320 --anchor-elo 1320
```

**Benchmark the ML model (one shot).** `harness/benchmark.py` wraps the
match-then-rate flow and builds the engine commands for you. ML configs (`nn`
evaluation, `policy` search) need the torch deps, so run under the `nn` extra:

```bash
# value network vs the medium handcrafted eval
uv run --extra nn python harness/benchmark.py --a-eval nn --b-eval medium \
    --games 100 --movetime 100 --concurrency 4

# policy network vs a 1320 Stockfish
uv run --extra nn python harness/benchmark.py --a-search policy --stockfish 1320 \
    --games 100 --concurrency 4
```

**Standard tooling.** `harness/run_cutechess.sh` drives the same benchmark
through `cutechess-cli` and rates it with Ordo.

**Cross-language telemetry.** `harness/telemetry.py` drives the Python, C++, and
Rust engines over UCI on a shared set of positions and reports nodes-per-second,
peak memory, and (where `perf` hardware counters are permitted) cache-miss rate.
Because the three engines are logically equivalent they visit the same nodes at a
fixed depth, so NPS is a clean speed comparison. Results go to a timestamped CSV
under `harness/results/`; with the `bench` extra it also renders PNG charts:

```bash
uv run --extra bench python harness/telemetry.py --depth 6 --cache --plot
```

**Move quality (Average Centipawn Loss).** `harness/acl.py` scores the moves in a
played PGN against a strong reference engine (Stockfish), reporting ACL split by
game phase (opening / middlegame / endgame) and by player — how much worse each
played move was than the reference's best:

```bash
uv run python harness/acl.py harness/results/<run>/games.pgn --ref stockfish --ref-depth 14
```

**Notes**
- The engine is pure Python (~2–16k NPS), so use short fixed-time controls
  (50–200 ms/move) to keep 100-game matches to minutes rather than hours.
- PGN move text is UCI coordinate notation, not SAN — raters key off the
  `[Result]` tag, so this does not affect ratings.
- Ordo refuses to rate a "not well connected" database (e.g. when one engine
  wins every game); the bundled `elo.py` handles that case, so the scripts
  default to it for the headline number.

## Roadmap

- **Phase 1 — Core engine (done):** bitboard representation, alpha-beta minimax
  with iterative deepening and a Zobrist transposition table, MVV-LVA / killer /
  history move ordering, and a handcrafted piece-square + structural evaluation.
- **Phase 1.5 — UCI & benchmarking (done):** UCI protocol wrapper, an automated
  match harness against a dialed-down Stockfish, and Elo analysis with
  confidence intervals.
- **Phase 2 — Machine learning & hybrids:** supervised value/policy networks on
  master games, an AlphaZero-style self-play RL loop with MCTS, and a hybrid
  orchestrator (opening book early, search/ML in the middlegame, endgame
  tablebases when the board simplifies).
- **Phase 3 — Cross-language benchmarking (done):** the same alpha-beta search
  and evaluation in Python, C++ (`cpp/`), and Rust (`rust/`), verified equivalent
  by perft and byte-identical fixed-depth search; telemetry for nodes-per-second,
  memory, and cache misses (`harness/telemetry.py`); and move quality via average
  centipawn loss vs Stockfish (`harness/acl.py`).
- **Phase 4 — Web deployment & visualization:** an interactive sandbox with a
  *learning* mode (watch engine-vs-engine games with the search tree and
  evaluations overlaid) and a *competition* mode (play a configurable engine),
  a live self-play training dashboard, and an LLM "chess coach" that narrates
  the engine's top variations.
