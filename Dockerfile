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
RUN uv sync --frozen

# Default to the UCI engine on stdin/stdout; override to run the benchmark, e.g.
#   docker run --rm eschess harness/benchmark.sh 100 100 1320
CMD ["python", "python/uci.py"]
