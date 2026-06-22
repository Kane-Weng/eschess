<script lang="ts">
  // Generic multi-series SVG line chart for the training dashboard. No chart
  // dependency: one responsive viewBox, auto y-domain, optional dashed series
  // (used for moving-average overlays). x is the sample index.
  interface Series {
    label: string;
    color: string;
    values: number[];
    dashed?: boolean;
  }

  interface Props {
    series: Series[];
    title: string;
    yLabel?: string;
    height?: number;
  }

  let { series, title, yLabel = "", height = 200 }: Props = $props();

  const W = 560;
  const PAD = { top: 16, right: 16, bottom: 26, left: 46 };

  const count = $derived(Math.max(1, ...series.map((s) => s.values.length)));

  const yDomain = $derived.by(() => {
    const all = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v));
    if (all.length === 0) return [0, 1];
    let lo = Math.min(...all);
    let hi = Math.max(...all);
    if (lo === hi) {
      lo -= 1;
      hi += 1;
    }
    const pad = (hi - lo) * 0.08;
    return [lo - pad, hi + pad];
  });

  function x(i: number): number {
    const span = Math.max(1, count - 1);
    return PAD.left + (i / span) * (W - PAD.left - PAD.right);
  }

  function y(v: number): number {
    const [lo, hi] = yDomain;
    const t = (v - lo) / (hi - lo || 1);
    return height - PAD.bottom - t * (height - PAD.top - PAD.bottom);
  }

  function path(values: number[]): string {
    return values
      .map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
      .join(" ");
  }

  const ticks = $derived.by(() => {
    const [lo, hi] = yDomain;
    return [0, 0.25, 0.5, 0.75, 1].map((t) => lo + t * (hi - lo));
  });

  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2));
</script>

<figure class="rounded-xl border border-white/5 bg-white/[0.02] p-4">
  <figcaption class="mb-2 flex items-center justify-between">
    <span class="text-sm font-medium text-slate-200">{title}</span>
    <span class="flex flex-wrap gap-3 text-xs text-slate-400">
      {#each series as s (s.label)}
        <span class="flex items-center gap-1.5">
          <span
            class="inline-block h-2 w-3 rounded-sm"
            style:background={s.dashed ? "transparent" : s.color}
            style:border={s.dashed ? `1.5px dashed ${s.color}` : "none"}
          ></span>
          {s.label}
        </span>
      {/each}
    </span>
  </figcaption>

  <svg viewBox={`0 0 ${W} ${height}`} class="w-full" role="img" aria-label={title}>
    {#each ticks as t (t)}
      <line
        x1={PAD.left}
        x2={W - PAD.right}
        y1={y(t)}
        y2={y(t)}
        stroke="rgba(255,255,255,0.06)"
        stroke-width="1"
      />
      <text x={PAD.left - 6} y={y(t) + 3} text-anchor="end" class="fill-slate-500 text-[9px]">
        {fmt(t)}
      </text>
    {/each}

    {#if yLabel}
      <text
        x={12}
        y={height / 2}
        text-anchor="middle"
        transform={`rotate(-90 12 ${height / 2})`}
        class="fill-slate-500 text-[9px]"
      >
        {yLabel}
      </text>
    {/if}

    {#each series as s (s.label)}
      {#if s.values.length > 0}
        <path
          d={path(s.values)}
          fill="none"
          stroke={s.color}
          stroke-width={s.dashed ? 1.5 : 2}
          stroke-dasharray={s.dashed ? "4 3" : "none"}
          stroke-linejoin="round"
          stroke-linecap="round"
        />
      {/if}
    {/each}
  </svg>
</figure>
