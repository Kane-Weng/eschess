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
neural nets in `python/nn`), leaving room for other-language implementations
beside it. Shared tooling (`assets/`, `harness/`) stays at the repo root.

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
**Stockfish**, **Ordo**, and **cutechess-cli** — so the whole pipeline is
reproducible with no host setup.

```bash
docker build -t eschess .

# Run the engine as a UCI process
docker run --rm -i eschess python python/uci.py

# Benchmark vs a strength-limited Stockfish:  GAMES  MOVETIME_MS  STOCKFISH_ELO
docker run --rm eschess harness/benchmark.sh 100 100 1320
```

The benchmark writes its PGN to `results.pgn` *inside* the container, so with
`--rm` it disappears when the run ends. To keep it, mount a host directory and
copy it out:

```bash
docker run --rm -v "$PWD:/out" eschess \
    bash -c "harness/benchmark.sh 100 100 1320 && cp results.pgn /out/"
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
    --games 100 --movetime 100 --openings harness/openings.epd --pgn results.pgn
```

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

**Standard tooling.** `harness/run_cutechess.sh` drives the same benchmark
through `cutechess-cli` and rates it with Ordo, and `harness/benchmark.sh`
wraps the one-shot match-then-rate flow used inside Docker.

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
- **Phase 3 — Cross-language benchmarking:** the same alpha-beta search and
  evaluation in Python, C++, and Rust, with telemetry for nodes-per-second,
  memory, and move quality (average centipawn loss vs Stockfish).
- **Phase 4 — Web deployment & visualization:** an interactive sandbox with a
  *learning* mode (watch engine-vs-engine games with the search tree and
  evaluations overlaid) and a *competition* mode (play a configurable engine),
  a live self-play training dashboard, and an LLM "chess coach" that narrates
  the engine's top variations.
