<script lang="ts">
  // Nodes-per-second comparison for the Knight chapter.
  // The three engines run the identical fixed-depth search; only the language
  // differs. Drag the think-time slider and watch how many nodes each backend
  // gets through. NPS figures are the order-of-magnitude numbers measured on the
  // project's dev host (pure-Python reference vs the native C++/Rust ports).

  interface Engine {
    name: string;
    nps: number;
    accent: boolean;
  }

  const ENGINES: Engine[] = [
    { name: "Python", nps: 1_824, accent: false },
    { name: "C++", nps: 518_057, accent: false },
    { name: "Rust", nps: 589_782, accent: true },
  ];

  let secs = $state(1);

  const targets = $derived(ENGINES.map((e) => Math.round(e.nps * secs)));
  const maxTarget = $derived(Math.max(...targets));
  const baseline = ENGINES[0].nps; // Python, the reference

  function fmt(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + "k";
    return `${n}`;
  }
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <p class="text-sm text-slate-300">
      Nodes searched in
      <span class="font-mono text-[var(--color-accent)]">{secs.toFixed(1)}s</span>
      of equal thinking time (Depth=5)
    </p>
    <label class="flex items-center gap-2 text-xs text-slate-500">
      think time
      <input
        type="range"
        min="0.5"
        max="5"
        step="0.5"
        bind:value={secs}
        class="accent-[var(--color-accent)]"
      />
    </label>
  </div>

  <div class="space-y-3">
    {#each ENGINES as engine, i}
      {@const nodes = targets[i]}
      {@const speedup = engine.nps / baseline}
      <div>
        <div class="mb-1 flex items-baseline justify-between text-xs">
          <span class="font-medium text-slate-200">{engine.name}</span>
          <span class="font-mono text-slate-400">
            {fmt(nodes)} nodes
            <span class="ml-2 text-slate-600">
              {speedup === 1 ? "baseline" : `${speedup.toFixed(0)}× faster`}
            </span>
          </span>
        </div>
        <div class="h-3 w-full overflow-hidden rounded-full bg-white/5">
          <div
            class="h-full rounded-full transition-[width] duration-500 ease-out"
            style={`width: ${Math.max((nodes / maxTarget) * 100, 0.5)}%; background: ${
              engine.accent ? "var(--color-accent)" : "#64748b"
            };`}
          ></div>
        </div>
      </div>
    {/each}
  </div>

  <p class="mt-4 text-xs leading-relaxed text-slate-500">
    Same search, same position, same move ordering. The pure-Python reference manages
    about {fmt(baseline)} nodes per second; the native C++ and Rust ports of that exact
    logic clear hundreds of times more, which is the whole reason for the leap across the
    language boundary. Python's bar is there, it is just too short to see.
  </p>
</div>
