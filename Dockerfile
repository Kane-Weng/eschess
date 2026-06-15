# Eschess: reproducible engine + benchmarking environment.
#
# A multi-stage build. The first stage compiles the external benchmarking tools
# (Ordo for rating, cutechess-cli for match play); the final stage is the uv
# Python image plus Stockfish, with only the built binaries + Qt runtime copied
# in, so the toolchain and Qt dev headers never bloat the shipped image.

# ── Stage 1: build Ordo and cutechess-cli from source ────────────────────────
FROM debian:bookworm-slim AS tools

# cutechess's top-level CMake requires all of Core/Gui/Widgets/Concurrent/Svg/
# PrintSupport/Core5Compat to configure, even though only the CLI target is built.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates cmake ninja-build build-essential \
        qt6-base-dev qt6-svg-dev qt6-5compat-dev \
    && rm -rf /var/lib/apt/lists/*

# Ordo: BayesElo-style rating tool
RUN git clone --depth 1 https://github.com/michiguel/Ordo /tmp/ordo \
    && make -C /tmp/ordo \
    && install -D -m 0755 /tmp/ordo/ordo /out/ordo

# cutechess-cli: standard engine-vs-engine match runner (Qt6, CLI target only)
RUN git clone --depth 1 https://github.com/cutechess/cutechess.git /tmp/cc \
    && cmake -S /tmp/cc -B /tmp/cc/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/cc/build --target cutechess-cli \
    && install -D -m 0755 /tmp/cc/build/cutechess-cli /out/cutechess-cli \
    && echo "=== cutechess-cli Qt runtime deps ===" && ldd /out/cutechess-cli | grep -i qt6

# ── Stage 1b: build the C++ and Rust engines ─────────────────────────────────
# The rust image already has cargo + a C++ toolchain; only cmake is missing.
FROM rust:bookworm AS engines

RUN apt-get update && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY cpp/ cpp/
RUN cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release && cmake --build cpp/build -j

COPY rust/ rust/
RUN cargo build --release --manifest-path rust/Cargo.toml

# Sanity-check move generation matches the reference perft counts at build time.
RUN cpp/build/perft >/dev/null && rust/target/release/perft >/dev/null

# Build the native PyO3 extension (eschess_native) into an abi3 wheel, and gate
# the build on a perft parity smoke so a broken binding fails the image build.
COPY rust-ffi/ rust-ffi/
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages maturin \
    && maturin build --release -m rust-ffi/Cargo.toml --out /wheels \
    && pip3 install --break-system-packages /wheels/*.whl \
    && python3 -c "import eschess_native as e; assert e.PyBoard().perft(3) == 8902; print('eschess_native perft OK')"

# ── Stage 2: the runtime image ───────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# /app/.venv/bin → project venv; /usr/games → where Debian puts the stockfish binary
ENV PATH="/app/.venv/bin:/usr/games:${PATH}" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Stockfish (sparring partner) + the Qt6 runtime libraries cutechess-cli needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
        stockfish \
        libqt6core6 libqt6concurrent6 libqt6network6 libqt6core5compat6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=tools /out/ordo           /usr/local/bin/ordo
COPY --from=tools /out/cutechess-cli  /usr/local/bin/cutechess-cli
# Fail the build early if a runtime library is missing.
RUN cutechess-cli --version && ordo --help >/dev/null

WORKDIR /app

# Resolve Python dependencies first so the layer caches across source edits.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
# `bench` adds matplotlib for harness/telemetry.py plots.
RUN uv sync --frozen --extra bench

# Install the prebuilt native extension into the project venv so the RL loop can
# use the fast self-play backend (`python -m nn.rl --backend native`). Pulls in
# numpy; torch (the actual NN inference) still comes from the `nn` extra.
COPY --from=engines /wheels /tmp/wheels
RUN uv pip install --python /app/.venv/bin/python /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Drop the compiled C++/Rust engines at the paths the harness + GUI expect
# (cpp/build/uci, rust/target/release/uci). Placed after `COPY . .` so the
# source copy never shadows them.
COPY --from=engines /src/cpp/build/uci            /app/cpp/build/uci
COPY --from=engines /src/cpp/build/perft          /app/cpp/build/perft
COPY --from=engines /src/rust/target/release/uci   /app/rust/target/release/uci
COPY --from=engines /src/rust/target/release/perft /app/rust/target/release/perft

# Default to the UCI engine on stdin/stdout; override to run a benchmark, e.g.
#   docker run --rm eschess python harness/benchmark.py --a-eval medium --stockfish 1320 --games 100
#   docker run --rm eschess python harness/telemetry.py --depth 7
#   docker run --rm eschess python harness/acl.py <pgn> --ref stockfish --ref-depth 14
CMD ["python", "python/uci.py"]
