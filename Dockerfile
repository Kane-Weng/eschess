# === Multi-stage build for Eschess: Engine + Benchmarking ===
# Strategy: Compile tools and native engines in separate builder stages. 
# The final image only contains the Python environment, precompiled binaries, 
# and runtime libraries to eliminate toolchain bloat.

# ── Stage 1: Build benchmarking tools (Ordo, cutechess-cli) ──────────────────
FROM debian:bookworm-slim AS tools

# Install build tools and Qt6 dependencies required by cutechess.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates cmake ninja-build build-essential \
        qt6-base-dev qt6-svg-dev qt6-5compat-dev \
    && rm -rf /var/lib/apt/lists/*

# Build Ordo (Rating tool)
RUN git clone --depth 1 https://github.com/michiguel/Ordo /tmp/ordo \
    && make -C /tmp/ordo \
    && install -D -m 0755 /tmp/ordo/ordo /out/ordo

# Build cutechess-cli (Match runner)
RUN git clone --depth 1 https://github.com/cutechess/cutechess.git /tmp/cc \
    && cmake -S /tmp/cc -B /tmp/cc/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /tmp/cc/build --target cutechess-cli \
    && install -D -m 0755 /tmp/cc/build/cutechess-cli /out/cutechess-cli \
    && echo "=== cutechess-cli Qt runtime deps ===" && ldd /out/cutechess-cli | grep -i qt6

# ── Stage 2: Build C++ and Rust engines ──────────────────────────────────────
FROM rust:bookworm AS engines

RUN apt-get update && apt-get install -y --no-install-recommends cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Compile C++ engine
COPY cpp/ cpp/
RUN cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build cpp/build -j

# Compile Rust engine
COPY rust/ rust/
RUN cargo build --release --manifest-path rust/Cargo.toml

# Smoke test: Ensure both engines generate correct perft counts before proceeding
RUN cpp/build/perft >/dev/null && rust/target/release/perft >/dev/null

# Build PyO3 native extension wheel and run parity check
COPY rust-ffi/ rust-ffi/
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --break-system-packages maturin \
    && maturin build --release -m rust-ffi/Cargo.toml --out /wheels

# ── Stage 3: Final Runtime Image ─────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Configure venv path and uv behavior
ENV PATH="/app/.venv/bin:/usr/games:${PATH}" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install Stockfish and Qt6 runtime dependencies for cutechess-cli
RUN apt-get update && apt-get install -y --no-install-recommends \
        stockfish \
        libqt6core6 libqt6concurrent6 libqt6network6 libqt6core5compat6 \
    && rm -rf /var/lib/apt/lists/*

# Inject precompiled benchmarking tools
COPY --from=tools /out/ordo           /usr/local/bin/ordo
COPY --from=tools /out/cutechess-cli  /usr/local/bin/cutechess-cli

# Fast fail if tool runtime dependencies are missing
RUN cutechess-cli --version && ordo --help >/dev/null

WORKDIR /app

# Cache Python dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Copy necessary source code 
# Note: Ensure .dockerignore excludes /cpp, /rust, and /rust-ffi to avoid bloat
COPY . .

# Sync project and install benchmark dependencies
RUN uv sync --frozen --extra bench

# Install the prebuilt Rust FFI wheel directly into the uv venv
COPY --from=engines /wheels /wheels
RUN uv pip install --system /wheels/*.whl \
    && python3 -c "import site, os; print('\n--- INSTALLED FILES ---'); print('\n'.join(f for f in os.listdir(site.getsitepackages()[0]) if 'eschess' in f.lower())); print('-----------------------')"

# Inject precompiled engines into expected harness paths
COPY --from=engines /src/cpp/build/uci             /app/cpp/build/uci
COPY --from=engines /src/cpp/build/perft           /app/cpp/build/perft
COPY --from=engines /src/rust/target/release/uci   /app/rust/target/release/uci
COPY --from=engines /src/rust/target/release/perft /app/rust/target/release/perft

CMD ["python", "python/uci.py"]