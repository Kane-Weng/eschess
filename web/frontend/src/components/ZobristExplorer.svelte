<script lang="ts">
  // ZobristExplorer — Zobrist transposition demo.
  // Two move sequences reach the same position. Each move XORs out the source
  // square, XORs in the destination, and flips the turn flag. Because XOR is
  // commutative and associative, both orderings produce the same 64-bit key.

  const MASK64 = (1n << 64n) - 1n;
  const FILES  = ['a','b','c','d','e','f','g','h'];
  const RANKS  = [7,6,5,4,3,2,1,0]; // render rank 8 first

  type PColor = 0 | 1;
  type PKind  = 0 | 1 | 2 | 3 | 4 | 5;
  type Cell   = { color: PColor; kind: PKind } | null;

  const KIND_NAME  = ['Pawn','Knight','Bishop','Rook','Queen','King'] as const;
  const COLOR_NAME = ['White','Black'] as const;
  const GLYPH      = ['♟︎','♞︎','♝︎','♜︎','♛︎','♚︎'] as const;

  // ── SplitMix64 seeded PRNG ────────────────────────────────────────────────
  function splitmix64(seed: bigint) {
    let s = seed & MASK64;
    return (): bigint => {
      s = (s + 0x9e3779b97f4a7c15n) & MASK64;
      let z = s;
      z = ((z ^ (z >> 30n)) * 0xbf58476d1ce4e5b9n) & MASK64;
      z = ((z ^ (z >> 27n)) * 0x94d049bb133111ebn) & MASK64;
      return (z ^ (z >> 31n)) & MASK64;
    };
  }

  function buildTables(seed: bigint) {
    const rng = splitmix64(seed);
    return {
      piece: Array.from({length: 2}, () =>
        Array.from({length: 6}, () =>
          Array.from({length: 64}, () => rng())
        )
      ),
      turn: rng(), // ZOB_TURN: XOR'd in whenever it is Black to move
    };
  }

  // LERF starting position
  function startPos(): Cell[] {
    const pos: Cell[] = new Array(64).fill(null);
    const BACK: PKind[] = [3,1,2,4,5,2,1,3]; // R N B Q K B N R
    for (let f = 0; f < 8; f++) {
      pos[f]    = { color: 0, kind: BACK[f] };
      pos[8+f]  = { color: 0, kind: 0 };        // white pawns
      pos[48+f] = { color: 1, kind: 0 };        // black pawns
      pos[56+f] = { color: 1, kind: BACK[f] };
    }
    return pos;
  }

  function sqName(sq: number): string {
    return FILES[sq % 8] + (Math.floor(sq / 8) + 1);
  }

  function h64(n: bigint): string {
    return '0x' + n.toString(16).padStart(16, '0').toUpperCase();
  }

  const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

  // ── Move sequences ────────────────────────────────────────────────────────
  // LERF squares: e2=12 e4=28  e7=52 e5=36  g1=6 f3=21  g8=62 f6=45
  interface Move { fromSq: number; toSq: number; color: PColor; kind: PKind; notation: string }

  const SEQ_A: Move[] = [
    { fromSq: 12, toSq: 28, color: 0, kind: 0, notation: 'e4'  },
    { fromSq: 52, toSq: 36, color: 1, kind: 0, notation: 'e5'  },
    { fromSq:  6, toSq: 21, color: 0, kind: 1, notation: 'Nf3' },
    { fromSq: 62, toSq: 45, color: 1, kind: 1, notation: 'Nf6' },
  ];
  const SEQ_B: Move[] = [
    { fromSq:  6, toSq: 21, color: 0, kind: 1, notation: 'Nf3' },
    { fromSq: 62, toSq: 45, color: 1, kind: 1, notation: 'Nf6' },
    { fromSq: 12, toSq: 28, color: 0, kind: 0, notation: 'e4'  },
    { fromSq: 52, toSq: 36, color: 1, kind: 0, notation: 'e5'  },
  ];

  const HELP =
    'Both sequences reach the same position — White pawn on e4, Black pawn on e5, ' +
    'White knight on f3, Black knight on f6 — via different move orders. Each move ' +
    'XORs out the piece from its source square, XORs it into the destination, then ' +
    'toggles ZOB_TURN to flip the side to move. Because XOR is commutative and ' +
    'associative, the four updates combine to the same 64-bit key regardless of order. ' +
    'Change the seed to regenerate all random values; the equality still holds.';

  // ── Reactive state ────────────────────────────────────────────────────────
  let seedStr       = $state('0xCAFEBABE');
  let position      = $state<Cell[]>(startPos());
  let blackToMove   = $state(false); // white starts; ZOB_TURN XOR'd in when black
  let lastMove      = $state<Move | null>(null);
  let playing       = $state(false);
  let helpOpen      = $state(false);

  const seedBig = $derived.by((): bigint => {
    const raw = seedStr.trim();
    try {
      return (raw.startsWith('0x') || raw.startsWith('0X'))
        ? BigInt(raw) & MASK64
        : BigInt(Math.trunc(Number(raw))) & MASK64;
    } catch { return 0xCAFEBABEn; }
  });

  const tables = $derived(buildTables(seedBig));

  // Full recomputation — same result as applying incremental XOR steps.
  const zobKey = $derived.by((): bigint => {
    let key = 0n;
    for (let sq = 0; sq < 64; sq++) {
      const c = position[sq];
      if (c) key ^= tables.piece[c.color][c.kind][sq];
    }
    if (blackToMove) key ^= tables.turn;
    return key & MASK64;
  });

  const hexKey = $derived(h64(zobKey));

  const contributions = $derived.by(() => {
    const out: { label: string; val: bigint; changed: boolean }[] = [];
    const changedSqs = new Set([lastMove?.fromSq, lastMove?.toSq]);
    for (let sq = 0; sq < 64; sq++) {
      const c = position[sq];
      if (c) out.push({
        label:   `${COLOR_NAME[c.color][0]}${KIND_NAME[c.kind][0]} ${sqName(sq)}`,
        val:     tables.piece[c.color][c.kind][sq],
        changed: changedSqs.has(sq),
      });
    }
    if (blackToMove) out.push({ label: 'turn', val: tables.turn, changed: true });
    return out;
  });

  // ── Interaction ───────────────────────────────────────────────────────────
  async function playSeq(moves: Move[]) {
    if (playing) return;
    playing = true;
    position     = startPos();
    blackToMove  = false;
    lastMove     = null;
    await sleep(200);
    for (const move of moves) {
      position[move.fromSq] = null;
      position[move.toSq]   = { color: move.color, kind: move.kind };
      blackToMove            = !blackToMove;
      lastMove               = move;
      await sleep(700);
    }
    playing = false;
  }
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="flex flex-col gap-6 lg:flex-row lg:items-start">

    <!-- ── Board ────────────────────────────────────────────────────────── -->
    <div class="shrink-0">
      <div
        class="grid grid-cols-8 overflow-hidden rounded-md border border-white/10"
        style="width: min(20rem, 80vw);"
      >
        {#each RANKS as rank}
          {#each [0,1,2,3,4,5,6,7] as file}
            {@const sq      = rank * 8 + file}
            {@const dark    = (file + rank) % 2 === 0}
            {@const cell    = position[sq]}
            {@const fromSq  = lastMove?.fromSq === sq}
            {@const toSq    = lastMove?.toSq   === sq}
            <div
              class="relative flex aspect-square items-center justify-center"
              class:bg-board-dark={dark}
              class:bg-board-light={!dark}
            >
              {#if fromSq || toSq}
                <span class="absolute inset-0"
                  style="background: rgba(120,190,120,{toSq ? '0.45' : '0.25'})"></span>
              {/if}
              {#if cell}
                <span
                  class="piece relative z-10 select-none leading-none"
                  class:white-piece={cell.color === 0}
                  class:black-piece={cell.color === 1}
                >{GLYPH[cell.kind]}</span>
              {/if}
              <span class="pointer-events-none absolute bottom-0 left-0.5 select-none text-[0.45rem] text-black/20">
                {sqName(sq)}
              </span>
            </div>
          {/each}
        {/each}
      </div>
    </div>

    <!-- ── Controls + readout ───────────────────────────────────────────── -->
    <div class="relative min-w-0 flex-1 space-y-4">

      <!-- Header -->
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold text-slate-300">Transposition demo</span>
        <button
          type="button"
          class="help-btn"
          aria-label="About this demo"
          aria-expanded={helpOpen}
          onclick={() => (helpOpen = !helpOpen)}
        >?</button>
      </div>
      {#if helpOpen}
        <div class="help-pop" role="note">{HELP}</div>
      {/if}

      <!-- Seed -->
      <div>
        <label class="mb-1 block text-xs font-medium text-slate-400">seed</label>
        <input
          type="text"
          bind:value={seedStr}
          spellcheck="false"
          class="w-full rounded-md border border-white/10 bg-slate-800 px-3 py-1.5 font-mono text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
          placeholder="0xCAFEBABE or decimal"
        />
      </div>

      <!-- Sequence buttons -->
      <div class="space-y-2">
        <p class="text-xs font-medium text-slate-400">play sequence</p>
        <button type="button" disabled={playing} onclick={() => playSeq(SEQ_A)} class="seq-btn">
          <span class="seq-label">A</span>
          <span class="font-mono text-sm">e4 &nbsp;e5 &nbsp;Nf3 &nbsp;Nf6</span>
        </button>
        <button type="button" disabled={playing} onclick={() => playSeq(SEQ_B)} class="seq-btn">
          <span class="seq-label">B</span>
          <span class="font-mono text-sm">Nf3 &nbsp;Nf6 &nbsp;e4 &nbsp;e5</span>
        </button>
      </div>

      <!-- Key -->
      <div class="flex gap-2 font-mono text-xs">
        <span class="w-14 shrink-0 text-slate-500">key</span>
        <span class="break-all font-semibold text-[var(--color-accent)]">{hexKey}</span>
      </div>

      <!-- Last move: 3 XOR steps -->
      {#if lastMove}
        {@const outVal = tables.piece[lastMove.color][lastMove.kind][lastMove.fromSq]}
        {@const inVal  = tables.piece[lastMove.color][lastMove.kind][lastMove.toSq]}
        <div class="rounded-md border border-white/5 bg-slate-950/50 px-3 py-2.5 font-mono text-[0.68rem] leading-[1.65]">
          <span class="font-semibold text-slate-200">{lastMove.notation}</span>
          <span class="text-slate-500"> — {COLOR_NAME[lastMove.color]} {KIND_NAME[lastMove.kind]}, {sqName(lastMove.fromSq)} → {sqName(lastMove.toSq)}</span>
          <div class="mt-1.5 space-y-0.5">
            <div class="flex gap-2">
              <span class="w-16 shrink-0 text-slate-600">XOR out</span>
              <span class="w-8 shrink-0 text-slate-500">{sqName(lastMove.fromSq)}</span>
              <span class="text-slate-500">{h64(outVal)}</span>
            </div>
            <div class="flex gap-2">
              <span class="w-16 shrink-0 text-slate-600">XOR in</span>
              <span class="w-8 shrink-0 text-slate-500">{sqName(lastMove.toSq)}</span>
              <span class="text-slate-500">{h64(inVal)}</span>
            </div>
            <div class="flex gap-2">
              <span class="w-16 shrink-0 text-slate-600">XOR turn</span>
              <span class="w-8 shrink-0 text-slate-500">flag</span>
              <span class="text-slate-500">{h64(tables.turn)}</span>
            </div>
          </div>
        </div>
      {/if}

      <!-- XOR decomposition -->
      <div>
        <p class="mb-1 text-xs text-slate-500">
          XOR decomposition
          <span class="ml-1 text-slate-700">({contributions.length} terms)</span>
        </p>
        <div class="max-h-44 overflow-y-auto rounded-md border border-white/5 bg-slate-950/40 p-2 font-mono text-[0.65rem]">
          {#each contributions as c, i}
            <div class="flex gap-2 leading-[1.7]" class:text-[var(--color-accent)]={c.changed}>
              <span class="w-3 shrink-0 text-right" class:text-slate-700={!c.changed} class:text-[var(--color-accent)]={c.changed}>{i === 0 ? '' : '⊕'}</span>
              <span class="w-16 shrink-0" class:text-slate-400={!c.changed}>{c.label}</span>
              <span class:text-slate-600={!c.changed}>{h64(c.val)}</span>
            </div>
          {/each}
          <div class="mt-1 flex gap-2 border-t border-white/5 pt-1 leading-[1.7]">
            <span class="w-3 shrink-0 text-right text-slate-600">=</span>
            <span class="w-16 shrink-0 font-semibold text-[var(--color-accent)]">key</span>
            <span class="font-semibold text-[var(--color-accent)]">{hexKey}</span>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

<style>
  .piece {
    font-size: min(1.5rem, 6.5vw);
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

  /* ── Help button + popover ───────────────────────────────────────────────── */
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
    cursor: pointer;
  }
  .help-btn:hover {
    background: rgba(255, 255, 255, 0.16);
    color: #dde1e8;
  }
  .help-pop {
    position: absolute;
    right: 0;
    top: 2.1rem;
    z-index: 30;
    width: min(16rem, 80vw);
    border-radius: 0.5rem;
    border: 1px solid rgba(255, 255, 255, 0.15);
    background: #1b2130;
    padding: 0.7rem 0.8rem;
    font-size: 0.72rem;
    line-height: 1.5;
    color: #c2c7d0;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  }

  /* ── Sequence buttons ────────────────────────────────────────────────────── */
  .seq-btn {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    border-radius: 0.5rem;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 0.55rem 0.85rem;
    color: #cdcdd2;
    text-align: left;
    transition: background 0.12s;
    cursor: pointer;
  }
  .seq-btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
  }
  .seq-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .seq-label {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.35rem;
    height: 1.35rem;
    border-radius: 0.25rem;
    background: rgba(216, 163, 91, 0.18);
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--color-accent);
    flex-shrink: 0;
  }
</style>
