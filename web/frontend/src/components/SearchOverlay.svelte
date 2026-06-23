<script lang="ts">
  // Static-position demo of the engine's search overlays for the Queen chapter.
  // The board + telemetry are frozen (a Giuoco Piano position, White to move);
  // the overlay math is the same port of main.py's draw_search_arrows /
  // draw_top3_arrows / draw_density_cloud used by the live sandbox Chessboard.

  type Mode = "off" | "pv" | "top3" | "density";
  let mode = $state<Mode>("pv");

  // ── Frozen position ───────────────────────────────────────────────────────────
  // r1bqkbnr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w
  const FEN = "r1bqkbnr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R";
  const GLYPH: Record<string, string> = {
    p: "♟︎", n: "♞︎", b: "♝︎", r: "♜︎", q: "♛︎", k: "♚︎",
  };

  interface Cell { type: string; white: boolean }
  // Parse the placement field into 8 ranks (rank 8 first) of 8 cells.
  const rows: (Cell | null)[][] = FEN.split("/").map((row) => {
    const out: (Cell | null)[] = [];
    for (const ch of row) {
      if (ch >= "1" && ch <= "8") {
        for (let i = 0; i < +ch; i++) out.push(null);
      } else {
        out.push({ type: ch.toLowerCase(), white: ch === ch.toUpperCase() });
      }
    }
    return out;
  });

  // ── Frozen telemetry (the engine's last_info for this position) ───────────────
  const STM_WHITE = true;
  type Move = { from: string; to: string };
  const m = (uci: string): Move => ({ from: uci.slice(0, 2), to: uci.slice(2, 4) });

  // Principal variation: the single line the engine believes is best.
  const PV: Move[] = ["c2c3", "g8f6", "d2d4", "e5d4", "c3d4", "c5b4"].map(m);

  // Top-3 root moves, each with its own reply chain and a score (pawns, White POV).
  const MULTIPV: { pv: Move[]; score: number }[] = [
    { pv: ["c2c3", "g8f6", "d2d4"].map(m), score: 0.4 },
    { pv: ["e1g1", "g8f6", "d2d3"].map(m), score: 0.3 },
    { pv: ["b2b4", "c5b4", "c2c3"].map(m), score: 0.1 },
  ];

  // Per-move search effort (nodes spent in each candidate's subtree).
  const EFFORT: Record<string, number> = {
    c3: 4200, g1: 2600, b4: 1800, d3: 900, c4: 700, g5: 480,
  };

  const TOP_SCORE = 0.4; // drives the eval bar

  // ── Geometry (board units, a8 at top-left) ────────────────────────────────────
  type Pt = { x: number; y: number };
  function center(sq: string): Pt {
    const file = sq.charCodeAt(0) - 97;
    const rankNum = +sq[1];
    return { x: file + 0.5, y: 8 - rankNum + 0.5 };
  }

  // Knight moves bend in an L: the long (2-square) leg is travelled first.
  function knightElbow(from: string, to: string, a: Pt, b: Pt): Pt | null {
    const df = Math.abs(to.charCodeAt(0) - from.charCodeAt(0));
    const dr = Math.abs(+to[1] - +from[1]);
    if (!((df === 1 && dr === 2) || (df === 2 && dr === 1))) return null;
    return df === 2 ? { x: b.x, y: a.y } : { x: a.x, y: b.y };
  }

  interface Arrow { shaft: string; head: string; color: string; width: number }
  function arrow(from: string, to: string, color: string, width: number): Arrow {
    const a = center(from);
    const b = center(to);
    const elbow = knightElbow(from, to, a, b);
    const pts: Pt[] = elbow ? [a, elbow, b] : [a, b];
    const tail = pts[pts.length - 2];
    const tip = pts[pts.length - 1];
    const dx = tip.x - tail.x;
    const dy = tip.y - tail.y;
    const dist = Math.hypot(dx, dy) || 1;
    const ux = dx / dist;
    const uy = dy / dist;
    const headLen = 0.32;
    const headW = 0.16 + width;
    const base = { x: tip.x - ux * headLen, y: tip.y - uy * headLen };
    const shaft = [...pts.slice(0, -1), base].map((p) => `${p.x},${p.y}`).join(" ");
    const px = -uy;
    const py = ux;
    const head = `${tip.x},${tip.y} ${base.x + px * headW},${base.y + py * headW} ${base.x - px * headW},${base.y - py * headW}`;
    return { shaft, head, color, width };
  }

  // ── Overlay layers ────────────────────────────────────────────────────────────
  const ARROW_BOT = "235,150,40"; // side to move (orange)
  const ARROW_OPP = "60,180,210"; // reply side (cyan)
  const RANK_COLORS = ["70,200,90", "225,185,60", "215,70,70"]; // best / alt / worst
  const DENSITY = "255,120,40";

  const pvArrows = $derived.by<Arrow[]>(() => {
    if (mode !== "pv") return [];
    return PV.map((mv, i) => {
      const base = i % 2 === 0 ? ARROW_BOT : ARROW_OPP;
      const alpha = Math.max(0.18, 0.9 - i * 0.13);
      return arrow(mv.from, mv.to, `rgba(${base},${alpha})`, i < 2 ? 0.16 : 0.1);
    });
  });

  function cpLabel(scorePawns: number): string {
    const stm = STM_WHITE ? scorePawns : -scorePawns;
    return (stm >= 0 ? "+" : "") + Math.round(stm * 100);
  }
  interface Top3 { chain: Arrow[]; root: Arrow; label: { x: number; y: number; text: string; color: string } }
  const top3 = $derived.by<Top3[]>(() => {
    if (mode !== "top3") return [];
    return MULTIPV.map((entry, rank) => {
      const color = RANK_COLORS[rank];
      const chain = entry.pv
        .slice(1, 4)
        .map((mv, j) => arrow(mv.from, mv.to, `rgba(${color},${Math.max(0.14, 0.45 - j * 0.12)})`, 0.07));
      const r = entry.pv[0];
      const root = arrow(r.from, r.to, `rgba(${color},0.92)`, 0.16);
      const c = center(r.to);
      return { chain, root, label: { x: c.x, y: c.y - 0.34, text: cpLabel(entry.score), color } };
    });
  });

  interface Ring { x: number; y: number; radius: number; alpha: number }
  const density = $derived.by<Ring[]>(() => {
    if (mode !== "density") return [];
    const peak = Math.max(1, ...Object.values(EFFORT));
    return Object.entries(EFFORT).map(([sq, nodes]) => {
      const norm = Math.min(1, nodes / peak);
      const c = center(sq);
      return { x: c.x, y: c.y, radius: 0.16 + norm * 0.3, alpha: 0.16 + norm * 0.6 };
    });
  });

  // Eval bar: White's share of the bar, tanh-squashed like eval_probe.py.
  const whiteFrac = $derived(0.5 + 0.5 * Math.tanh(TOP_SCORE / 4));

  const MODES: { id: Mode; label: string }[] = [
    { id: "off", label: "Off" },
    { id: "pv", label: "PV line" },
    { id: "top3", label: "Top 3" },
    { id: "density", label: "Density" },
  ];

  const CAPTIONS: Record<Mode, string> = {
    off: "Just the position. Everything below is a rendering of the engine's telemetry, not the board itself.",
    pv: "The principal variation: the single line the engine expects. Orange is the side to move, cyan the replies, fading with depth.",
    top3: "The three best root moves, ranked green → gold → red, each tagged with its score in centipawns and trailing a faint reply chain.",
    density: "Search effort. Each ring grows with the number of nodes the engine spent on that square — where it found the position sharp.",
  };
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="mb-4 flex flex-wrap gap-2">
    {#each MODES as m2}
      <button
        type="button"
        onclick={() => (mode = m2.id)}
        aria-pressed={mode === m2.id}
        class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
        class:active={mode === m2.id}
        class:idle={mode !== m2.id}
      >
        {m2.label}
      </button>
    {/each}
  </div>

  <div class="flex gap-3">
    <!-- Eval bar (left), mirroring the pygame GUI -->
    <div class="relative w-3 shrink-0 overflow-hidden rounded-sm bg-[#1c1c20]">
      <div
        class="absolute inset-x-0 bottom-0 bg-[#ebebeb]"
        style:height={`${whiteFrac * 100}%`}
      ></div>
      <div class="absolute inset-x-0 top-1/2 h-px bg-[#78788230]"></div>
    </div>

    <!-- Board + overlay -->
    <div class="relative aspect-square min-w-0 flex-1" style="container-type:size; max-width:26rem">
      <div class="grid h-full w-full grid-cols-8 grid-rows-8 overflow-hidden rounded-md">
        {#each rows as row, r}
          {#each row as cell, f}
            {@const light = (f + r) % 2 === 0}
            <div
              class="relative flex items-center justify-center"
              style:background-color={light ? "var(--color-board-light)" : "var(--color-board-dark)"}
            >
              {#if cell}
                <span
                  class="piece leading-none"
                  class:white-piece={cell.white}
                  class:black-piece={!cell.white}>{GLYPH[cell.type]}</span
                >
              {/if}
            </div>
          {/each}
        {/each}
      </div>

      <svg class="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 8 8" aria-hidden="true">
        {#each density as ring}
          <circle cx={ring.x} cy={ring.y} r={ring.radius} fill={`rgba(${DENSITY},${ring.alpha})`} />
          <circle
            cx={ring.x}
            cy={ring.y}
            r={ring.radius}
            fill="none"
            stroke={`rgba(${DENSITY},${Math.min(1, ring.alpha + 0.25)})`}
            stroke-width="0.04"
          />
        {/each}

        {#each pvArrows as a}
          <polyline points={a.shaft} fill="none" stroke={a.color} stroke-width={a.width} stroke-linecap="round" stroke-linejoin="round" />
          <polygon points={a.head} fill={a.color} />
        {/each}

        {#each top3 as t}
          {#each t.chain as a}
            <polyline points={a.shaft} fill="none" stroke={a.color} stroke-width={a.width} stroke-linecap="round" stroke-linejoin="round" />
            <polygon points={a.head} fill={a.color} />
          {/each}
          <polyline points={t.root.shaft} fill="none" stroke={t.root.color} stroke-width={t.root.width} stroke-linecap="round" stroke-linejoin="round" />
          <polygon points={t.root.head} fill={t.root.color} />
        {/each}
        {#each top3 as t}
          <rect x={t.label.x - 0.36} y={t.label.y - 0.2} width="0.72" height="0.4" rx="0.08" fill={`rgb(${t.label.color})`} />
          <text x={t.label.x} y={t.label.y + 0.13} text-anchor="middle" font-size="0.3" font-weight="700" fill="#15150f">
            {t.label.text}
          </text>
        {/each}
      </svg>
    </div>
  </div>

  <p class="mt-4 min-h-[2.5rem] text-xs leading-relaxed text-slate-400">{CAPTIONS[mode]}</p>
</div>

<style>
  button.active {
    background: color-mix(in srgb, var(--color-accent) 22%, transparent);
    color: var(--color-accent);
  }
  button.idle {
    background: rgba(255, 255, 255, 0.05);
    color: #cbd5e1;
  }
  button.idle:hover {
    background: rgba(255, 255, 255, 0.1);
  }
  .piece {
    font-size: 9cqw;
  }
  .white-piece {
    color: #f6f5f2;
    -webkit-text-stroke: 0.12em rgba(40, 30, 18, 0.85);
    paint-order: stroke fill;
  }
  .black-piece {
    color: #232327;
    -webkit-text-stroke: 0.05em rgba(225, 225, 230, 0.35);
    paint-order: stroke fill;
  }
</style>
