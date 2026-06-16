<script lang="ts">
  // Engine Sandbox — Competition mode. A web port of the pygame reference
  // (python/main.py): play White against the in-browser engine, with a live
  // eval bar, an engine settings + performance panel, search-visualization
  // overlays (PV / Top-3 / Density), a captured-piece tray, and an undo/redo
  // move list. The engine itself lives in src/lib/engine (a port of the Python
  // alpha-beta search + evaluators).
  import { tick } from "svelte";
  import { Chess } from "chess.js";
  import { Engine } from "../../lib/engine/search";
  import type { EvalLevel } from "../../lib/engine/evaluate";
  import type { EngineInfo, EngineMove, PieceSymbol } from "../../lib/engine/types";
  import { EMPTY_INFO } from "../../lib/engine/types";
  import Chessboard from "./Chessboard.svelte";
  import EvalBar from "./EvalBar.svelte";

  type Viz = "off" | "pv" | "top3" | "density";
  const PLAYER: "w" = "w";

  // ── Game state ───────────────────────────────────────────────────────────────
  let game = new Chess();
  let board2d = $state(game.board());
  let turn = $state<"w" | "b">(game.turn());
  let selected = $state<string | null>(null);
  let legalTargets = $state<string[]>([]);
  let lastMove = $state<{ from: string; to: string } | null>(null);
  let promotion = $state<{ from: string; to: string; color: "w" | "b" } | null>(null);
  let moveLog = $state<EngineMove[]>([]); // full history incl. redo tail
  let cursor = $state(0); // plies currently applied to `game`
  let gameOver = $state(false);
  let result = $state("");

  // ── Engine + telemetry ───────────────────────────────────────────────────────
  const engine = new Engine();
  let info = $state<EngineInfo>(EMPTY_INFO);
  let botThinking = $state(false);
  let engineToken = 0;

  // ── Settings ─────────────────────────────────────────────────────────────────
  let evalLevel = $state<EvalLevel>("medium");
  let depth = $state(3);
  let vizMode = $state<Viz>("pv");
  let showEvalBar = $state(true);
  let showLastMove = $state(true);

  // Which section's help popover is open (one at a time, null = none).
  let helpKey = $state<string | null>(null);
  const HELP: Record<string, string> = {
    settings:
      "The engine runs entirely in your browser, a TypeScript port of the Python alpha-beta search. The C++/Rust (WASM) and Python (WebSocket) backends are planned, so those tabs are disabled. A higher depth and the complex evaluation play stronger but think a little longer.",
    viz: "While the engine (Black) searches for its move, the overlay replays its thinking: candidate lines appear and re-rank, and the best line switches as deeper refutations surface. PV shows the single expected line; Top 3 ranks the best root moves (green, gold, red) with centipawn labels; Density rings each square by how many search nodes were spent there.",
    perf: "Nodes is positions searched. NPS is nodes per second. Depth is the plies the search reached. Think time is how long the last search ran.",
  };
  const toggleHelp = (key: string) => (helpKey = helpKey === key ? null : key);

  function sync() {
    board2d = game.board();
    turn = game.turn();
  }

  function checkGameOver() {
    if (game.isCheckmate()) {
      gameOver = true;
      result = (game.turn() === "w" ? "Black" : "White") + " wins by checkmate";
    } else if (game.isStalemate()) {
      gameOver = true;
      result = "Draw by stalemate";
    } else if (game.isGameOver()) {
      gameOver = true;
      result = "Draw";
    }
  }

  function pushMove(m: EngineMove) {
    if (cursor < moveLog.length) moveLog = moveLog.slice(0, cursor); // drop redo tail
    game.move({ from: m.from, to: m.to, promotion: m.promotion });
    moveLog = [...moveLog, m];
    cursor = moveLog.length;
    lastMove = { from: m.from, to: m.to };
    sync();
    checkGameOver();
  }

  const raf = () =>
    new Promise((r) =>
      typeof requestAnimationFrame !== "undefined"
        ? requestAnimationFrame(() => r(null))
        : setTimeout(() => r(null), 16),
    );
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // The engine's turn (Black). When a visualization is on, the overlays replay the
  // engine's own search as it thinks: candidate lines appear, re-rank, and the
  // principal variation switches as deeper refutations surface, then it plays the
  // chosen move. With visualization off it just plays as fast as the budget allows.
  async function engineMove() {
    const my = ++engineToken;
    botThinking = true;
    engine.level = evalLevel;
    // Clear the previous overlay but keep the score so the eval bar does not flash.
    info = { ...EMPTY_INFO, score: info.score, stmWhite: false };
    const fen = game.fen();
    await tick();
    await raf();
    if (my !== engineToken) return;

    if (vizMode === "off") {
      const { bestMove, info: ni } = engine.search(fen, depth, 1500);
      if (my !== engineToken) return;
      info = ni;
      botThinking = false;
      if (bestMove) {
        pushMove(bestMove);
        afterPosition();
      }
      return;
    }

    const { bestMove, frames } = engine.searchFrames(fen, depth, 1200);
    if (my !== engineToken) return;
    // Pace the recorded frames into a ~1.3s animation.
    const delay = frames.length ? Math.max(45, Math.min(140, Math.round(1300 / frames.length))) : 0;
    for (const f of frames) {
      if (my !== engineToken) return;
      info = f;
      await wait(delay);
    }
    if (my !== engineToken) return;
    await wait(320); // hold the chosen line a beat before moving
    if (my !== engineToken) return;
    botThinking = false;
    if (bestMove) {
      pushMove(bestMove);
      afterPosition();
    }
  }

  function afterPosition() {
    selected = null;
    legalTargets = [];
    if (gameOver || turn === PLAYER) return; // the player's turn: no overlays
    engineMove();
  }

  // ── Player interaction ───────────────────────────────────────────────────────
  function targetsFor(sq: string): string[] {
    return [...new Set(game.moves({ square: sq, verbose: true }).map((m) => m.to))];
  }

  function onSquareClick(sq: string) {
    if (botThinking || gameOver || turn !== PLAYER || promotion) return;
    const piece = game.get(sq);

    if (selected === null) {
      if (piece && piece.color === PLAYER) {
        selected = sq;
        legalTargets = targetsFor(sq);
      }
      return;
    }
    if (sq === selected) {
      selected = null;
      legalTargets = [];
      return;
    }
    const moves = game.moves({ square: selected, verbose: true }).filter((m) => m.to === sq);
    if (moves.length) {
      if (moves.some((m) => m.promotion)) {
        promotion = { from: selected, to: sq, color: PLAYER };
        return;
      }
      pushMove({ from: selected, to: sq });
      afterPosition();
      return;
    }
    if (piece && piece.color === PLAYER) {
      selected = sq;
      legalTargets = targetsFor(sq);
    } else {
      selected = null;
      legalTargets = [];
    }
  }

  function onPromote(pt: PieceSymbol) {
    if (!promotion) return;
    pushMove({ from: promotion.from, to: promotion.to, promotion: pt });
    promotion = null;
    afterPosition();
  }

  // ── Undo / redo / reset (step to the player's turn, as in main.py) ───────────
  function refreshLastMove() {
    lastMove = cursor > 0 ? { from: moveLog[cursor - 1].from, to: moveLog[cursor - 1].to } : null;
  }
  function undo() {
    if (botThinking || cursor === 0) return;
    engineToken++;
    do {
      game.undo();
      cursor--;
    } while (cursor > 0 && game.turn() !== PLAYER);
    gameOver = false;
    result = "";
    selected = null;
    legalTargets = [];
    refreshLastMove();
    sync();
  }
  function redo() {
    if (botThinking || cursor >= moveLog.length) return;
    engineToken++;
    do {
      const m = moveLog[cursor];
      game.move({ from: m.from, to: m.to, promotion: m.promotion });
      cursor++;
    } while (cursor < moveLog.length && game.turn() !== PLAYER);
    selected = null;
    legalTargets = [];
    refreshLastMove();
    sync();
    checkGameOver();
    if (!gameOver) afterPosition();
  }
  function reset() {
    engineToken++;
    game = new Chess();
    moveLog = [];
    cursor = 0;
    selected = null;
    legalTargets = [];
    promotion = null;
    lastMove = null;
    gameOver = false;
    result = "";
    info = EMPTY_INFO;
    botThinking = false;
    sync();
  }

  // ── Setting handlers ─────────────────────────────────────────────────────────
  // Settings take effect on the engine's next move. While it is mid-animation the
  // overlay reads vizMode live, so switching visualization re-renders the current
  // frame immediately (each frame carries pv + multipv + effort).
  function setEval(level: EvalLevel) {
    evalLevel = level;
  }
  function setDepth(d: number) {
    depth = d;
  }
  function setViz(mode: Viz) {
    vizMode = mode;
  }

  // ── Derived: captured tray + move list ───────────────────────────────────────
  // Trailing U+FE0E forces text (not emoji) glyph presentation so CSS colour applies.
  const GLYPH: Record<PieceSymbol, string> = {
    p: "♟︎",
    n: "♞︎",
    b: "♝︎",
    r: "♜︎",
    q: "♛︎",
    k: "♚︎",
  };
  const START_COUNTS: Record<PieceSymbol, number> = { p: 8, n: 2, b: 2, r: 2, q: 1, k: 1 };
  const VALUE: Record<PieceSymbol, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };

  const captured = $derived.by(() => {
    const counts: Record<"w" | "b", Record<PieceSymbol, number>> = {
      w: { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 },
      b: { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 },
    };
    for (const row of board2d)
      for (const cell of row) if (cell) counts[cell.color][cell.type]++;
    const take = (by: "w" | "b") => {
      const enemy = by === "w" ? "b" : "w";
      const list: PieceSymbol[] = [];
      let mat = 0;
      (["q", "r", "b", "n", "p"] as PieceSymbol[]).forEach((pt) => {
        const missing = START_COUNTS[pt] - counts[enemy][pt];
        for (let i = 0; i < missing; i++) list.push(pt);
        mat += VALUE[pt] * counts[by][pt];
      });
      return { list, mat };
    };
    const w = take("w");
    const b = take("b");
    return { white: w.list, black: b.list, adv: w.mat - b.mat };
  });

  interface Row {
    n: number;
    w: string;
    b: string;
    wGrey: boolean;
    bGrey: boolean;
  }
  const uci = (m: EngineMove) => m.from + m.to + (m.promotion ?? "");
  const moveRows = $derived.by<Row[]>(() => {
    const rows: Row[] = [];
    for (let i = 0; i < moveLog.length; i += 2) {
      rows.push({
        n: i / 2 + 1,
        w: uci(moveLog[i]),
        b: i + 1 < moveLog.length ? uci(moveLog[i + 1]) : "",
        wGrey: i >= cursor,
        bGrey: i + 1 >= cursor,
      });
    }
    return rows;
  });

  const evalScore = $derived(info.score);
  // Overlays only show while the engine is actually searching (its turn).
  const effectiveViz = $derived<Viz>(botThinking ? vizMode : "off");
  const statusText = $derived(
    gameOver
      ? result
      : botThinking
        ? "Engine is thinking…"
        : turn === PLAYER
          ? "Your move (White)"
          : "Engine to move (Black)",
  );

  // Segmented-control helpers.
  const EVALS: { id: EvalLevel; label: string }[] = [
    { id: "simple", label: "simple" },
    { id: "medium", label: "medium" },
    { id: "complex", label: "complex" },
  ];
  const VIZ: { id: Viz; label: string }[] = [
    { id: "off", label: "Off" },
    { id: "pv", label: "PV" },
    { id: "top3", label: "Top 3" },
    { id: "density", label: "Density" },
  ];
  const LANGS = [
    { id: "js", label: "JS", on: true },
    { id: "cpp", label: "C++", on: false },
    { id: "rust", label: "Rust", on: false },
    { id: "py", label: "Python", on: false },
  ];
  const fmt = (n: number) => n.toLocaleString("en-US");
</script>

<div class="flex flex-col gap-5 lg:flex-row">
  <!-- Left column: eval bar + board, move list below -->
  <div class="min-w-0 flex-1">
    <div class="flex items-stretch gap-2">
      {#if showEvalBar}
        <EvalBar score={evalScore} />
      {/if}
      <div class="min-w-0 flex-1">
        <Chessboard
          {board2d}
          {selected}
          {legalTargets}
          {lastMove}
          {showLastMove}
          vizMode={effectiveViz}
          {info}
          {promotion}
          interactive={!botThinking && !gameOver && turn === PLAYER}
          {onSquareClick}
          {onPromote}
        />
      </div>
    </div>

    <!-- Status bar -->
    <div
      class="mt-2 rounded-md px-3 py-2 text-sm font-medium"
      class:bg-emerald-800={turn === PLAYER && !gameOver && !botThinking}
      class:bg-slate-800={!(turn === PLAYER && !gameOver && !botThinking)}
    >
      {statusText}
    </div>

    <!-- Move list -->
    <div class="mt-3 rounded-md border border-white/10 bg-slate-900/70">
      <div class="flex items-center justify-between border-b border-white/10 px-3 py-2">
        <span class="font-[var(--font-display)] text-sm font-semibold">Moves</span>
        <div class="flex gap-1.5">
          <button type="button" class="ctl" onclick={undo} disabled={cursor === 0 || botThinking}
            >‹ undo</button
          >
          <button
            type="button"
            class="ctl"
            onclick={redo}
            disabled={cursor >= moveLog.length || botThinking}>redo ›</button
          >
          <button type="button" class="ctl" onclick={reset} disabled={botThinking}>reset</button>
        </div>
      </div>
      <div class="max-h-40 overflow-y-auto px-3 py-2 font-mono text-sm">
        {#if moveRows.length === 0}
          <p class="text-slate-500">No moves yet. Click a white piece to begin.</p>
        {:else}
          {#each moveRows as row}
            <div class="flex gap-3 py-0.5">
              <span class="w-8 text-right text-slate-500">{row.n}.</span>
              <span class="w-16" class:text-slate-500={row.wGrey} class:text-slate-200={!row.wGrey}
                >{row.w}</span
              >
              <span class="w-16" class:text-slate-500={row.bGrey} class:text-slate-200={!row.bGrey}
                >{row.b}</span
              >
            </div>
          {/each}
        {/if}
      </div>
    </div>
  </div>

  <!-- Right sidebar -->
  <aside class="w-full shrink-0 space-y-5 lg:w-[300px]">
    {#snippet sectionHead(title: string, key: string)}
      <div class="mb-3 flex items-center gap-2">
        <h2 class="font-[var(--font-display)] text-base font-semibold">{title}</h2>
        <button
          type="button"
          class="help-btn"
          aria-label={`About ${title}`}
          aria-expanded={helpKey === key}
          onclick={() => toggleHelp(key)}>?</button
        >
      </div>
      {#if helpKey === key}
        <div class="help-pop" role="note">{HELP[key]}</div>
      {/if}
    {/snippet}

    <!-- Engine settings -->
    <section class="relative rounded-lg border border-white/10 bg-slate-900/70 p-4">
      {@render sectionHead("Engine settings", "settings")}

      <p class="panel-label">Language</p>
      <div class="seg">
        {#each LANGS as l}
          <button
            type="button"
            class="seg-btn"
            class:seg-on={l.id === "js"}
            disabled={!l.on}
            title={l.on ? "In-browser TypeScript engine" : "Planned (WASM / WebSocket backend)"}
            >{l.label}</button
          >
        {/each}
      </div>
      <p class="panel-label mt-3">Move source</p>
      <div class="seg">
        <button type="button" class="seg-btn seg-on">alpha-beta</button>
        <button type="button" class="seg-btn" disabled title="Policy network (backend only)"
          >policy</button
        >
      </div>

      <p class="panel-label mt-3">Evaluation</p>
      <div class="seg">
        {#each EVALS as e}
          <button
            type="button"
            class="seg-btn"
            class:seg-on={evalLevel === e.id}
            onclick={() => setEval(e.id)}>{e.label}</button
          >
        {/each}
        <button type="button" class="seg-btn" disabled title="Value network (backend only)">nn</button
        >
      </div>

      <div class="mt-3 flex items-center justify-between">
        <span class="panel-label !mb-0">Depth</span>
        <span class="font-mono text-sm text-slate-300">{depth}</span>
      </div>
      <input
        type="range"
        min="2"
        max="4"
        step="1"
        value={depth}
        class="mt-1 w-full accent-[var(--color-accent)]"
        oninput={(e) => setDepth(+e.currentTarget.value)}
      />
    </section>

    <!-- Visualization -->
    <section class="relative rounded-lg border border-white/10 bg-slate-900/70 p-4">
      {@render sectionHead("Visualization", "viz")}
      <div class="seg">
        {#each VIZ as v}
          <button
            type="button"
            class="seg-btn"
            class:seg-on={vizMode === v.id}
            onclick={() => setViz(v.id)}>{v.label}</button
          >
        {/each}
      </div>
    </section>

    <!-- Performance -->
    <section class="relative rounded-lg border border-white/10 bg-slate-900/70 p-4">
      {@render sectionHead("Engine performance", "perf")}
      <dl class="grid grid-cols-2 gap-y-1 font-mono text-sm">
        <dt class="text-slate-500">Nodes</dt>
        <dd class="text-right text-slate-200">{fmt(info.nodes)}</dd>
        <dt class="text-slate-500">NPS</dt>
        <dd class="text-right text-slate-200">{fmt(info.nps)}</dd>
        <dt class="text-slate-500">Depth</dt>
        <dd class="text-right text-slate-200">{info.depth}</dd>
        <dt class="text-slate-500">Think time</dt>
        <dd class="text-right text-slate-200">{(info.timeMs / 1000).toFixed(2)}s</dd>
      </dl>
    </section>

    <!-- Captured tray -->
    <section class="rounded-lg border border-white/10 bg-slate-900/70 p-4">
      <h2 class="mb-3 font-[var(--font-display)] text-base font-semibold">Captured</h2>
      {#each [{ label: "White", taken: captured.white, color: "b" }, { label: "Black", taken: captured.black, color: "w" }] as side}
        <div class="flex min-h-7 items-center gap-2">
          <span class="w-12 text-xs text-slate-500">{side.label}</span>
          <span class="text-xl leading-none" class:cap-white={side.color === "w"} class:cap-black={side.color === "b"}>
            {#each side.taken as pt}{GLYPH[pt]}{/each}
          </span>
        </div>
      {/each}
      {#if captured.adv !== 0}
        <p class="mt-1 text-sm text-slate-300">
          {captured.adv > 0 ? "White" : "Black"} +{Math.abs(captured.adv)}
        </p>
      {/if}
    </section>

    <!-- Extras -->
    <section class="rounded-lg border border-white/10 bg-slate-900/70 p-4">
      <h2 class="mb-3 font-[var(--font-display)] text-base font-semibold">Display</h2>
      <label class="flex cursor-pointer items-center gap-2 py-1 text-sm text-slate-300">
        <input type="checkbox" bind:checked={showEvalBar} class="accent-[var(--color-accent)]" />
        Evaluation bar
      </label>
      <label class="flex cursor-pointer items-center gap-2 py-1 text-sm text-slate-300">
        <input type="checkbox" bind:checked={showLastMove} class="accent-[var(--color-accent)]" />
        Last-move highlight
      </label>
    </section>
  </aside>
</div>

<style>
  .panel-label {
    margin-bottom: 0.35rem;
    font-size: 0.75rem;
    color: #8b8b94;
  }
  .help-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.15rem;
    height: 1.15rem;
    border-radius: 9999px;
    background: rgba(255, 255, 255, 0.08);
    font-size: 0.72rem;
    font-weight: 700;
    line-height: 1;
    color: #9aa0aa;
  }
  .help-btn:hover {
    background: rgba(255, 255, 255, 0.16);
    color: #dde1e8;
  }
  .help-pop {
    position: absolute;
    right: 0.85rem;
    top: 2.9rem;
    z-index: 30;
    width: 15rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(255, 255, 255, 0.15);
    background: #1b2130;
    padding: 0.7rem 0.8rem;
    font-size: 0.72rem;
    line-height: 1.5;
    color: #c2c7d0;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  }
  .seg {
    display: flex;
    gap: 0.35rem;
  }
  .seg-btn {
    flex: 1;
    border-radius: 0.35rem;
    background: #34343c;
    padding: 0.35rem 0.25rem;
    font-size: 0.78rem;
    color: #cdcdd2;
    transition: background 0.15s;
  }
  .seg-btn:hover:not(:disabled):not(.seg-on) {
    background: #41414b;
  }
  .seg-on {
    background: #4278c8;
    color: #fff;
    box-shadow: inset 0 0 0 2px rgba(210, 225, 255, 0.6);
  }
  .seg-btn:disabled {
    background: #26262c;
    color: #5c5c64;
    cursor: not-allowed;
  }
  .ctl {
    border-radius: 0.35rem;
    background: rgba(255, 255, 255, 0.06);
    padding: 0.25rem 0.6rem;
    font-size: 0.75rem;
    color: #cdcdd2;
  }
  .ctl:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.12);
  }
  .ctl:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }
  .cap-white {
    color: #f6f5f2;
    -webkit-text-stroke: 0.04em rgba(40, 30, 18, 0.8);
  }
  .cap-black {
    color: #2a2a2e;
    -webkit-text-stroke: 0.03em rgba(225, 225, 230, 0.3);
  }
</style>
