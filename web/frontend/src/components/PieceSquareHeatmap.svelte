<script lang="ts">
  // Piece-square-table heatmap for the Bishop chapter.
  // These are the handcrafted evaluation tables from engine/evaluate.py: a small
  // centipawn bonus for putting each piece on each square, from White's view
  // (LERF indexing, a1 = 0, h8 = 63). It is the static, human-written precursor
  // to the value network, the same "where does this piece belong" judgement the
  // ResNet later learns for itself.

  const TABLES: Record<string, number[]> = {
    Pawn: [0, 0, 0, 0, 0, 0, 0, 0, 5, 10, 10, -20, -20, 10, 10, 5, 5, -5, -10, 0, 0, -10, -5, 5, 0, 0, 0, 20, 20, 0, 0, 0, 5, 5, 10, 25, 25, 10, 5, 5, 10, 10, 20, 30, 30, 20, 10, 10, 50, 50, 50, 50, 50, 50, 50, 50, 0, 0, 0, 0, 0, 0, 0, 0],
    Knight: [-50, -40, -30, -30, -30, -30, -40, -50, -40, -20, 0, 0, 0, 0, -20, -40, -30, 0, 10, 15, 15, 10, 0, -30, -30, 5, 15, 20, 20, 15, 5, -30, -30, 0, 15, 20, 20, 15, 0, -30, -30, 5, 10, 15, 15, 10, 5, -30, -40, -20, 0, 5, 5, 0, -20, -40, -50, -40, -30, -30, -30, -30, -40, -50],
    Bishop: [-20, -10, -10, -10, -10, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 10, 10, 5, 0, -10, -10, 5, 5, 10, 10, 5, 5, -10, -10, 0, 10, 10, 10, 10, 0, -10, -10, 10, 10, 10, 10, 10, 10, -10, -10, 5, 0, 0, 0, 0, 5, -10, -20, -10, -10, -10, -10, -10, -10, -20],
    Rook: [0, 0, 0, 5, 5, 0, 0, 0, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, -5, 0, 0, 0, 0, 0, 0, -5, 5, 10, 10, 10, 10, 10, 10, 5, 0, 0, 0, 0, 0, 0, 0, 0],
    Queen: [-20, -10, -10, -5, -5, -10, -10, -20, -10, 0, 0, 0, 0, 0, 0, -10, -10, 0, 5, 5, 5, 5, 0, -10, -5, 0, 5, 5, 5, 5, 0, -5, 0, 0, 5, 5, 5, 5, 0, -5, -10, 5, 5, 5, 5, 5, 0, -10, -10, 0, 5, 0, 0, 0, 0, -10, -20, -10, -10, -5, -5, -10, -10, -20],
    "King (midgame)": [20, 30, 10, 0, 0, 10, 30, 20, 20, 20, 0, 0, 0, 0, 20, 20, -10, -20, -20, -20, -20, -20, -20, -10, -20, -30, -30, -40, -40, -30, -30, -20, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30, -30, -40, -40, -50, -50, -40, -40, -30],
    "King (endgame)": [-50, -40, -30, -20, -20, -30, -40, -50, -30, -20, -10, 0, 0, -10, -20, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 30, 40, 40, 30, -10, -30, -30, -10, 20, 30, 30, 20, -10, -30, -30, -30, 0, 0, 0, 0, -30, -30, -50, -30, -30, -30, -30, -30, -30, -50],
  };

  const PIECES = Object.keys(TABLES);
  const files = ["a", "b", "c", "d", "e", "f", "g", "h"];
  const ranks = [7, 6, 5, 4, 3, 2, 1, 0]; // rank 8 at the top

  let piece = $state("Knight");
  const table = $derived(TABLES[piece]);
  const maxAbs = $derived(Math.max(...table.map((v) => Math.abs(v)), 1));

  const indexOf = (file: number, rank: number) => rank * 8 + file;

  function color(value: number): string {
    const t = Math.max(-1, Math.min(1, value / maxAbs));
    // neutral slate at 0, warm accent for bonuses, cool blue for penalties.
    const base = [30, 41, 59]; // slate-800
    const warm = [216, 163, 91]; // accent gold
    const cool = [56, 89, 138]; // muted blue
    const target = t >= 0 ? warm : cool;
    const k = Math.abs(t);
    const mix = base.map((b, i) => Math.round(b + (target[i] - b) * k));
    return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
  }
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="mb-4 flex flex-wrap gap-1.5">
    {#each PIECES as p}
      <button
        type="button"
        onclick={() => (piece = p)}
        class="rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
        style={piece === p
          ? "background: var(--color-accent); color: #0f172a;"
          : "background: rgba(255,255,255,0.05); color: #cbd5e1;"}
      >
        {p}
      </button>
    {/each}
  </div>

  <div class="flex flex-col gap-5 sm:flex-row sm:items-start">
    <div class="shrink-0">
      <div
        class="grid grid-cols-8 overflow-hidden rounded-md border border-white/10"
        style="width: min(22rem, 84vw);"
      >
        {#each ranks as rank}
          {#each files as _f, file}
            {@const i = indexOf(file, rank)}
            {@const v = table[i]}
            <div
              class="relative flex aspect-square items-center justify-center font-mono text-[0.6rem]"
              style={`background: ${color(v)}; color: ${Math.abs(v) > maxAbs * 0.55 ? "#0f172a" : "#e2e8f0"};`}
              title={`${files[file]}${rank + 1}: ${v >= 0 ? "+" : ""}${v}`}
            >
              {v}
            </div>
          {/each}
        {/each}
      </div>
    </div>

    <div class="min-w-0 flex-1 text-sm leading-relaxed text-slate-400">
      <p>
        Each square holds the <span class="text-slate-200">{piece}</span>'s positional
        bonus in centipawns, from White's perspective. Brighter gold means
        "this piece wants to be here"; blue means "keep it away".
      </p>
      <p class="mt-3">
        Read off the shape of the chess knowledge baked in by hand: knights crave the
        centre, rooks love the seventh rank, the midgame king hides in the corner while
        the endgame king marches out. The value network learns this same map of the
        board, except it is fit from millions of self-play games instead of written
        down.
      </p>
      <div class="mt-4 flex items-center gap-3 text-xs text-slate-500">
        <span class="inline-flex items-center gap-1.5">
          <span class="inline-block size-3 rounded-sm" style="background: rgb(56,89,138)"></span>
          penalty
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="inline-block size-3 rounded-sm" style="background: rgb(30,41,59)"></span>
          neutral
        </span>
        <span class="inline-flex items-center gap-1.5">
          <span class="inline-block size-3 rounded-sm" style="background: rgb(216,163,91)"></span>
          bonus
        </span>
      </div>
    </div>
  </div>
</div>
