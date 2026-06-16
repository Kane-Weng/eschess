<script lang="ts">
  // Elo / confidence-interval calculator for the Rook chapter.
  // It reproduces harness/elo.py's head-to-head math exactly: expected score to
  // Elo via the inverse logistic curve, a 95% interval from the standard error of
  // the score, and the likelihood-of-superiority from the decisive games. Adjust
  // the win/draw/loss tallies and watch how many games it takes before a result
  // is actually trustworthy.

  let wins = $state(54);
  let draws = $state(72);
  let losses = $state(34);

  const n = $derived(wins + draws + losses);

  // Expected score -> Elo difference (inverse of the logistic Elo curve).
  function scoreToElo(s: number): number {
    const c = Math.min(Math.max(s, 1e-12), 1 - 1e-12);
    return -400 * Math.log10(1 / c - 1);
  }

  // Abramowitz-Stegun erf approximation (math.erf in the Python source).
  function erf(x: number): number {
    const sign = Math.sign(x);
    x = Math.abs(x);
    const t = 1 / (1 + 0.3275911 * x);
    const y =
      1 -
      ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
        0.254829592) *
        t *
        Math.exp(-x * x);
    return sign * y;
  }

  const stats = $derived.by(() => {
    if (n === 0) return null;
    const pw = wins / n;
    const pd = draws / n;
    const pl = losses / n;
    const mu = pw + 0.5 * pd;
    const variance =
      pw * (1 - mu) ** 2 + pd * (0.5 - mu) ** 2 + pl * (0 - mu) ** 2;
    const stderr = Math.sqrt(variance / n);
    const elo = scoreToElo(mu);
    const eloLo = scoreToElo(mu - 1.96 * stderr);
    const eloHi = scoreToElo(mu + 1.96 * stderr);
    const margin = (eloHi - eloLo) / 2;
    const decisive = wins + losses;
    const los = decisive
      ? 0.5 * (1 + erf((wins - losses) / Math.sqrt(2 * decisive)))
      : 0.5;
    return { mu, pd, elo, eloLo, eloHi, margin, los };
  });

  function step(which: "w" | "d" | "l", delta: number) {
    if (which === "w") wins = Math.max(0, wins + delta);
    if (which === "d") draws = Math.max(0, draws + delta);
    if (which === "l") losses = Math.max(0, losses + delta);
  }

  const rows: { key: "w" | "d" | "l"; label: string; get: () => number }[] = [
    { key: "w", label: "Wins", get: () => wins },
    { key: "d", label: "Draws", get: () => draws },
    { key: "l", label: "Losses", get: () => losses },
  ];

  const fmt = (v: number, d = 1) => (v >= 0 ? "+" : "") + v.toFixed(d);
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <div class="flex flex-col gap-6 sm:flex-row sm:items-center">
    <!-- inputs -->
    <div class="shrink-0 space-y-2">
      {#each rows as row}
        <div class="flex items-center gap-3">
          <span class="w-14 text-xs text-slate-400">{row.label}</span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              onclick={() => step(row.key, -1)}
              class="size-6 rounded bg-white/5 text-slate-300 hover:bg-white/10">−</button
            >
            <span class="w-10 text-center font-mono text-sm text-slate-100">{row.get()}</span>
            <button
              type="button"
              onclick={() => step(row.key, 1)}
              class="size-6 rounded bg-white/5 text-slate-300 hover:bg-white/10">+</button
            >
            <button
              type="button"
              onclick={() => step(row.key, 10)}
              class="ml-1 rounded bg-white/5 px-1.5 text-[0.65rem] text-slate-400 hover:bg-white/10"
              >+10</button
            >
          </div>
        </div>
      {/each}
      <p class="pt-1 font-mono text-xs text-slate-500">{n} games total</p>
    </div>

    <!-- results -->
    <div class="min-w-0 flex-1 border-l border-white/10 pl-6">
      {#if stats}
        <div class="space-y-2.5">
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">Elo difference</p>
            <p class="font-mono text-2xl text-[var(--color-accent)]">
              {fmt(stats.elo)} <span class="text-base text-slate-400">± {stats.margin.toFixed(1)}</span>
            </p>
          </div>
          <dl class="space-y-1 font-mono text-xs">
            <div class="flex gap-2">
              <dt class="w-28 shrink-0 text-slate-500">score</dt>
              <dd class="text-slate-300">{(stats.mu * 100).toFixed(1)}% (draws {(stats.pd * 100).toFixed(0)}%)</dd>
            </div>
            <div class="flex gap-2">
              <dt class="w-28 shrink-0 text-slate-500">95% CI</dt>
              <dd class="text-slate-300">[{fmt(stats.eloLo)}, {fmt(stats.eloHi)}]</dd>
            </div>
            <div class="flex gap-2">
              <dt class="w-28 shrink-0 text-slate-500">superiority</dt>
              <dd class="text-slate-300">{(stats.los * 100).toFixed(1)}%</dd>
            </div>
          </dl>
        </div>
      {:else}
        <p class="text-sm text-slate-500">Add some games to see a rating.</p>
      {/if}
    </div>
  </div>

  <p class="mt-5 text-xs leading-relaxed text-slate-500">
    The same tally can mean very different things. A narrow lead over thousands of games is
    a real rating; the identical winning percentage over a handful of games has an interval
    wide enough to swallow zero. The likelihood of superiority is the probability the lead
    is genuine rather than noise. This is exactly why the harness reports the interval, not
    just the number.
  </p>
</div>
