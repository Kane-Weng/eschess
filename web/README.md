# Eschess Web

The public web showcase for the Eschess chess engine — built to **show how it thinks**.

It has two halves:

- **A Detailed Record** — an interactive engineering blog that tells the engine's story
  through the six chess pieces (Pawn → King), from bitboards and alpha-beta search up to
  neural networks and high-level orchestration, with live widgets embedded in the text.
- **Four interactive modules**, reached from the landing page:
  1. **Engine Sandbox** — play or watch the engines (C++/Rust in WebAssembly, Python/ML over a socket).
  2. **Detailed Record** — the six-piece blog above.
  3. **Live Training & Dashboard** — a real-time stream of self-play training metrics.
  4. **LLM Chess Coach** — a chat that explains, in plain English, why moves are good or bad.

## Layout

```
web/
├── frontend/   # Astro site (Svelte islands + Tailwind) — the static UI
└── backend/    # FastAPI + WebSocket server for the Python/ML engine (planned)
```

## Stack

- **Astro** — static-first site with component islands
- **Svelte** — the interactive widgets (bitboard explorer, pruning-tree visualizer, coach chat)
- **Tailwind CSS** — styling
- Heavy compute splits two ways: **WebAssembly** for the client-side C++/Rust search, and a
  **FastAPI + WebSocket** backend for the Python / neural-net engine.

## Run the frontend

```bash
cd web/frontend
npm install
npm run dev        # http://localhost:4321
npm run build      # static output in dist/
```

## Status

The landing page is live. Everything else is tracked in [TODO.md](./TODO.md).

This work is based on "Chess pieces" (https://sketchfab.com/3d-models/chess-pieces-6c30b70322ff4ebfb5874cf51a4e2bba) by nikolokko (https://sketchfab.com/nikolokko) licensed under CC-BY-4.0 (http://creativecommons.org/licenses/by/4.0/)
