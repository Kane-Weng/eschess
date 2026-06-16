<script lang="ts">
  // The board: square grid + Unicode pieces, with an SVG overlay (viewBox 0..8)
  // for legal-move dots and the search-visualization layers. The overlays are a
  // direct port of main.py's draw_search_arrows / draw_top3_arrows /
  // draw_density_cloud / draw_move_dots.
  import type { Cell } from "../../lib/engine/evaluate";
  import type { EngineInfo, EngineMove, PieceSymbol } from "../../lib/engine/types";

  interface Props {
    board2d: Cell[][];
    selected: string | null;
    legalTargets: string[];
    lastMove: { from: string; to: string } | null;
    showLastMove: boolean;
    vizMode: "off" | "pv" | "top3" | "density";
    info: EngineInfo;
    promotion: { from: string; to: string; color: "w" | "b" } | null;
    interactive: boolean;
    onSquareClick: (sq: string) => void;
    onPromote: (piece: PieceSymbol) => void;
  }
  const {
    board2d,
    selected,
    legalTargets,
    lastMove,
    showLastMove,
    vizMode,
    info,
    promotion,
    interactive,
    onSquareClick,
    onPromote,
  }: Props = $props();

  // Trailing U+FE0E forces text (not emoji) presentation, so the glyph honours
  // CSS `color` / stroke on first paint instead of rendering as a grey emoji.
  const GLYPH: Record<PieceSymbol, string> = {
    p: "♟︎",
    n: "♞︎",
    b: "♝︎",
    r: "♜︎",
    q: "♛︎",
    k: "♚︎",
  };
  const PROMO_PIECES: PieceSymbol[] = ["q", "r", "b", "n"];

  // ── Geometry (board units, a8 at top-left) ───────────────────────────────────
  function center(sq: string): { x: number; y: number } {
    const file = sq.charCodeAt(0) - 97;
    const rankNum = +sq[1];
    return { x: file + 0.5, y: 8 - rankNum + 0.5 };
  }
  const occupiedAt = (sq: string): boolean => {
    const file = sq.charCodeAt(0) - 97;
    const r = 8 - +sq[1];
    return board2d[r][file] !== null;
  };
  const targetSet = $derived(new Set(legalTargets));

  // Squares, rank 8 → rank 1.
  interface Sq {
    name: string;
    light: boolean;
    cell: Cell;
  }
  const squares = $derived.by<Sq[]>(() => {
    const out: Sq[] = [];
    for (let r = 0; r < 8; r++) {
      for (let f = 0; f < 8; f++) {
        out.push({
          name: String.fromCharCode(97 + f) + (8 - r),
          light: (f + r) % 2 === 0,
          cell: board2d[r][f],
        });
      }
    }
    return out;
  });

  // ── Arrow helper ─────────────────────────────────────────────────────────────
  interface Arrow {
    shaft: string; // polyline points "x1,y1 x2,y2 ..." up to the head base
    head: string; // head polygon points
    color: string;
    width: number;
  }
  type Pt = { x: number; y: number };

  // Knight moves bend in an L: the long (2-square) leg is travelled first, as in
  // main.py's _knight_elbow. Returns the elbow point, or null for non-knight moves.
  function knightElbow(from: string, to: string, a: Pt, b: Pt): Pt | null {
    const df = Math.abs(to.charCodeAt(0) - from.charCodeAt(0));
    const dr = Math.abs(+to[1] - +from[1]);
    if (!((df === 1 && dr === 2) || (df === 2 && dr === 1))) return null;
    return df === 2 ? { x: b.x, y: a.y } : { x: a.x, y: b.y };
  }

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

  // ── PV overlay ───────────────────────────────────────────────────────────────
  // Ply 0 is the side that searched (the engine); colour it like main.py's
  // ARROW_BOT_SIDE, with the player's replies in the contrasting hue.
  const ARROW_BOT = "235,150,40"; // engine / side to move (orange)
  const ARROW_OPP = "60,180,210"; // reply side (cyan)
  const RANK_COLORS = ["70,200,90", "225,185,60", "215,70,70"]; // best / alt / worst
  const DENSITY = "255,120,40";

  const pvArrows = $derived.by<Arrow[]>(() => {
    if (vizMode !== "pv") return [];
    return info.pv.slice(0, 8).map((m, i) => {
      const base = i % 2 === 0 ? ARROW_BOT : ARROW_OPP;
      const alpha = Math.max(0.18, 0.9 - i * 0.1);
      return arrow(m.from, m.to, `rgba(${base},${alpha})`, i < 2 ? 0.16 : 0.1);
    });
  });

  // ── Top-3 overlay ────────────────────────────────────────────────────────────
  function cpLabel(scorePawns: number, stmWhite: boolean): string {
    const stm = stmWhite ? scorePawns : -scorePawns;
    if (Math.abs(stm) >= 999) return stm > 0 ? "M+" : "M-";
    return (stm >= 0 ? "+" : "") + Math.round(stm * 100);
  }
  interface Top3 {
    chain: Arrow[];
    root: Arrow;
    label?: { x: number; y: number; text: string; color: string };
  }
  const top3 = $derived.by<Top3[]>(() => {
    if (vizMode !== "top3") return [];
    return info.multipv.slice(0, 3).map((entry, rank) => {
      const color = RANK_COLORS[rank];
      const pv = entry.pv.length ? entry.pv : [entry.move];
      const chain = pv
        .slice(1, 4)
        .map((m, j) => arrow(m.from, m.to, `rgba(${color},${Math.max(0.14, 0.45 - j * 0.1)})`, 0.07));
      const r = pv[0];
      const root = arrow(r.from, r.to, `rgba(${color},0.92)`, 0.16);
      const c = center(r.to);
      return {
        chain,
        root,
        label: { x: c.x, y: c.y - 0.34, text: cpLabel(entry.score, info.stmWhite), color },
      };
    });
  });

  // ── Density overlay ──────────────────────────────────────────────────────────
  interface Ring {
    x: number;
    y: number;
    radius: number;
    alpha: number;
  }
  const density = $derived.by<Ring[]>(() => {
    if (vizMode !== "density") return [];
    const bySquare: Record<string, number> = {};
    for (const [key, nodes] of Object.entries(info.effort)) {
      const to = key.slice(2, 4); // moveKey = from(2)+to(2)+promo
      bySquare[to] = (bySquare[to] ?? 0) + nodes;
    }
    const peak = Math.max(1, ...Object.values(bySquare));
    return Object.entries(bySquare).map(([sq, nodes]) => {
      const norm = Math.min(1, nodes / peak);
      const c = center(sq);
      return { x: c.x, y: c.y, radius: 0.16 + norm * 0.3, alpha: 0.16 + norm * 0.6 };
    });
  });

  // Legal-move dots.
  interface Dot {
    x: number;
    y: number;
    capture: boolean;
  }
  const dots = $derived.by<Dot[]>(() =>
    legalTargets.map((sq) => {
      const c = center(sq);
      return { x: c.x, y: c.y, capture: occupiedAt(sq) };
    }),
  );
</script>

<div class="board-wrap relative aspect-square w-full select-none" style="container-type:size">
  <div class="grid h-full w-full grid-cols-8 grid-rows-8 overflow-hidden rounded-md">
    {#each squares as sq (sq.name)}
      <button
        type="button"
        class="relative flex items-center justify-center"
        style:background-color={sq.light ? "var(--color-board-light)" : "var(--color-board-dark)"}
        disabled={!interactive}
        aria-label={sq.name}
        onclick={() => onSquareClick(sq.name)}
      >
        {#if showLastMove && lastMove && (lastMove.from === sq.name || lastMove.to === sq.name)}
          <span class="absolute inset-0 bg-[rgb(120,190,120)]/45"></span>
        {/if}
        {#if selected === sq.name}
          <span class="absolute inset-0 bg-yellow-300/45"></span>
        {/if}
        {#if sq.cell}
          <span
            class="piece relative z-10 leading-none"
            class:white-piece={sq.cell.color === "w"}
            class:black-piece={sq.cell.color === "b"}>{GLYPH[sq.cell.type]}</span
          >
        {/if}
      </button>
    {/each}
  </div>

  <!-- Overlay: dots + search visualization -->
  <svg
    class="pointer-events-none absolute inset-0 h-full w-full"
    viewBox="0 0 8 8"
    aria-hidden="true"
  >
    <!-- density rings (under the arrows) -->
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

    <!-- legal-move dots -->
    {#each dots as dot}
      {#if dot.capture}
        <circle
          cx={dot.x}
          cy={dot.y}
          r="0.4"
          fill="none"
          stroke="rgba(180,0,0,0.5)"
          stroke-width="0.09"
        />
      {:else}
        <circle cx={dot.x} cy={dot.y} r="0.16" fill="rgba(0,0,0,0.32)" />
      {/if}
    {/each}

    <!-- PV arrows -->
    {#each pvArrows as a}
      <polyline
        points={a.shaft}
        fill="none"
        stroke={a.color}
        stroke-width={a.width}
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <polygon points={a.head} fill={a.color} />
    {/each}

    <!-- Top-3 arrows -->
    {#each top3 as t}
      {#each t.chain as a}
        <polyline
          points={a.shaft}
          fill="none"
          stroke={a.color}
          stroke-width={a.width}
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <polygon points={a.head} fill={a.color} />
      {/each}
      <polyline
        points={t.root.shaft}
        fill="none"
        stroke={t.root.color}
        stroke-width={t.root.width}
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <polygon points={t.root.head} fill={t.root.color} />
    {/each}
    {#each top3 as t}
      {#if t.label}
        <g>
          <rect
            x={t.label.x - 0.36}
            y={t.label.y - 0.2}
            width="0.72"
            height="0.4"
            rx="0.08"
            fill={`rgb(${t.label.color})`}
          />
          <text
            x={t.label.x}
            y={t.label.y + 0.13}
            text-anchor="middle"
            font-size="0.3"
            font-weight="700"
            fill="#15150f"
          >
            {t.label.text}
          </text>
        </g>
      {/if}
    {/each}
  </svg>

  <!-- Promotion picker -->
  {#if promotion}
    <div class="absolute inset-0 z-20 flex items-center justify-center bg-black/55">
      <div class="flex gap-2 rounded-lg bg-[#dcc896] p-2 shadow-xl">
        {#each PROMO_PIECES as pt}
          <button
            type="button"
            class="flex h-14 w-14 items-center justify-center rounded-md border-2 border-[#80603c] bg-[#e8d7af] text-4xl hover:bg-white"
            class:white-piece={promotion.color === "w"}
            class:black-piece={promotion.color === "b"}
            aria-label={`Promote to ${pt}`}
            onclick={() => onPromote(pt)}>{GLYPH[pt]}</button
          >
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .piece {
    font-size: 9.5cqw;
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
