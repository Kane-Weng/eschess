<script lang="ts">
  // Live bitboard manipulator for the Pawn chapter.
  // A chess board is 64 squares, so it fits in a single 64-bit integer: one bit
  // per square, 1 = occupied. We use Little-Endian Rank-File (LERF) mapping —
  // square index = rank * 8 + file, so a1 = bit 0 and h8 = bit 63. Toggle squares
  // and watch the integer update; "push" left-shifts every bit north by 8.
  const MASK64 = (1n << 64n) - 1n; // keep results inside 64 bits

  let board = $state<bigint>(0x000000000000ff00n); // default: the white pawns (rank 2)

  const files = ["a", "b", "c", "d", "e", "f", "g", "h"];
  // Render rank 8 (index 7) at the top down to rank 1 (index 0).
  const ranks = [7, 6, 5, 4, 3, 2, 1, 0];

  const indexOf = (file: number, rank: number) => rank * 8 + file;
  const isSet = (i: number) => (board & (1n << BigInt(i))) !== 0n;

  function toggle(i: number) {
    board ^= 1n << BigInt(i);
  }

  const popcount = $derived.by(() => {
    let n = board;
    let c = 0;
    while (n) {
      n &= n - 1n;
      c++;
    }
    return c;
  });

  const hex = $derived("0x" + board.toString(16).padStart(16, "0").toUpperCase());
  const decimal = $derived(board.toString(10));

  function pushNorth() {
    board = (board << 8n) & MASK64;
  }
  function pushSouth() {
    board = board >> 8n;
  }
  function clear() {
    board = 0n;
  }
  function whitePawns() {
    board = 0x000000000000ff00n;
  }
  function blackPawns() {
    board = 0x00ff000000000000n;
  }
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="flex flex-col gap-5 sm:flex-row sm:items-start">
    <!-- Board -->
    <div class="shrink-0">
      <div
        class="grid grid-cols-8 overflow-hidden rounded-md border border-white/10"
        style="width: min(20rem, 80vw);"
      >
        {#each ranks as rank}
          {#each files as _f, file}
            {@const i = indexOf(file, rank)}
            {@const dark = (file + rank) % 2 === 0}
            <button
              type="button"
              onclick={() => toggle(i)}
              aria-label={`${files[file]}${rank + 1}`}
              aria-pressed={isSet(i)}
              class="relative flex aspect-square items-center justify-center text-[0.6rem] transition-colors"
              class:bg-board-dark={dark}
              class:bg-board-light={!dark}
            >
              {#if isSet(i)}
                <span
                  class="h-3/5 w-3/5 rounded-full bg-[var(--color-accent)] shadow-[0_0_8px_rgba(216,163,91,0.6)]"
                ></span>
              {/if}
              <span class="absolute bottom-0.5 left-1 text-[0.5rem] text-black/30">
                {files[file]}{rank + 1}
              </span>
            </button>
          {/each}
        {/each}
      </div>
    </div>

    <!-- Readout + controls -->
    <div class="min-w-0 flex-1">
      <dl class="space-y-1.5 font-mono text-xs">
        <div class="flex gap-2">
          <dt class="w-16 shrink-0 text-slate-500">hex</dt>
          <dd class="break-all text-[var(--color-accent)]">{hex}</dd>
        </div>
        <div class="flex gap-2">
          <dt class="w-16 shrink-0 text-slate-500">uint64</dt>
          <dd class="break-all text-slate-300">{decimal}</dd>
        </div>
        <div class="flex gap-2">
          <dt class="w-16 shrink-0 text-slate-500">popcount</dt>
          <dd class="text-slate-300">{popcount}</dd>
        </div>
      </dl>

      <div class="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onclick={pushNorth}
          class="rounded-md bg-[var(--color-accent)]/15 px-3 py-1.5 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent)]/25"
        >
          push north (&lt;&lt; 8)
        </button>
        <button
          type="button"
          onclick={pushSouth}
          class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10"
        >
          push south (&gt;&gt; 8)
        </button>
        <button
          type="button"
          onclick={whitePawns}
          class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10"
        >
          white pawns
        </button>
        <button
          type="button"
          onclick={blackPawns}
          class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10"
        >
          black pawns
        </button>
        <button
          type="button"
          onclick={clear}
          class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10"
        >
          clear
        </button>
      </div>

      <p class="mt-4 text-xs leading-relaxed text-slate-500">
        Click any square to flip its bit. Each square is one bit of a 64-bit integer
        (LERF: a1 = bit 0, h8 = bit 63). "Push north" left-shifts the whole board by 8 —
        every piece advances one rank in a single instruction.
      </p>
    </div>
  </div>
</div>
