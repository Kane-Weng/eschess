<script lang="ts">
  // The training room: streams an RL run's metrics over a WebSocket and graphs
  // moving-average loss curves, evolving win/draw/loss ratios, and the gate
  // timeline. Replay mode pages through a recorded run; attach mode tails a live
  // run the local trainer is still writing.
  import { onDestroy, onMount } from "svelte";
  import {
    fetchRuns,
    movingAverage,
    openStream,
    type GenEvent,
    type MetricEvent,
    type RunInfo,
    type StreamMode,
    type TrainStream,
  } from "../../lib/training";
  import LineChart from "./LineChart.svelte";

  let runs = $state<RunInfo[]>([]);
  let selected = $state<string>("");
  let mode = $state<StreamMode>("replay");
  let speed = $state(8);
  let connState = $state<"idle" | "connecting" | "streaming" | "done" | "error">("idle");
  let detail = $state<string>("");

  // Per-generation history (one row per 'gen' event).
  let gens = $state<GenEvent[]>([]);
  // Per-epoch loss streams, in arrival order (for a finer-grained loss curve).
  let policyEpochs = $state<number[]>([]);
  let valueEpochs = $state<number[]>([]);
  let runMeta = $state<{ backend?: string; sims?: number; games_per_gen?: number }>({});

  let stream: TrainStream | null = null;

  const ACCENT = "#7dd3fc";
  const VALUE_COLOR = "#f0abfc";
  const WIN = "#4ade80";
  const DRAW = "#94a3b8";
  const LOSS = "#f87171";

  const policyLoss = $derived(gens.map((g) => g.policy_loss));
  const valueLoss = $derived(gens.map((g) => g.value_loss));
  const hasWdl = $derived(gens.some((g) => g.wins != null));

  // Loss charts: per-generation final loss plus a 3-wide moving-average overlay.
  const policySeries = $derived([
    { label: "policy loss", color: ACCENT, values: policyLoss },
    { label: "MA(3)", color: ACCENT, values: movingAverage(policyLoss, 3), dashed: true },
  ]);
  const valueSeries = $derived([
    { label: "value loss", color: VALUE_COLOR, values: valueLoss },
    { label: "MA(3)", color: VALUE_COLOR, values: movingAverage(valueLoss, 3), dashed: true },
  ]);

  function reset() {
    gens = [];
    policyEpochs = [];
    valueEpochs = [];
    runMeta = {};
  }

  function handleEvent(event: MetricEvent) {
    if (event.type === "run") {
      runMeta = {
        backend: event.backend,
        sims: event.sims,
        games_per_gen: event.games_per_gen,
      };
    } else if (event.type === "epoch") {
      if (event.phase === "policy") policyEpochs = [...policyEpochs, event.loss];
      else valueEpochs = [...valueEpochs, event.loss];
    } else if (event.type === "gen") {
      gens = [...gens, event];
    } else if (event.type === "done") {
      connState = "done";
    }
  }

  function start() {
    stream?.close();
    reset();
    if (!selected) return;
    connState = "connecting";
    detail = "";
    stream = openStream(selected, mode, speed, {
      onOpen: () => (connState = "streaming"),
      onEvent: handleEvent,
      onStatus: (status, d) => {
        if (status === "error") {
          connState = "error";
          detail = d ?? "stream error";
        } else if (connState !== "done") {
          connState = "done";
        }
      },
    });
  }

  function stop() {
    stream?.close();
    stream = null;
    if (connState === "streaming") connState = "idle";
  }

  onMount(async () => {
    try {
      runs = await fetchRuns();
      if (runs.length > 0) selected = runs[0].name;
    } catch (e) {
      connState = "error";
      detail = `could not reach backend at :8123 (${(e as Error).message})`;
    }
  });

  onDestroy(() => stream?.close());

  const last = $derived(gens.at(-1));
  const totalGames = $derived(
    gens.reduce((acc, g) => acc + (g.wins ?? 0) + (g.draws ?? 0) + (g.losses ?? 0), 0),
  );

  function pct(n: number, total: number): string {
    return total > 0 ? `${((100 * n) / total).toFixed(0)}%` : "0%";
  }
</script>

<div class="space-y-6">
  <!-- Controls -->
  <div class="flex flex-wrap items-end gap-4 rounded-xl border border-white/5 bg-white/[0.02] p-4">
    <label class="flex flex-col gap-1 text-xs text-slate-400">
      Run
      <select
        bind:value={selected}
        class="min-w-56 rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
      >
        {#if runs.length === 0}
          <option value="">no runs found</option>
        {/if}
        {#each runs as r (r.name)}
          <option value={r.name}>{r.stamp} ({r.format})</option>
        {/each}
      </select>
    </label>

    <label class="flex flex-col gap-1 text-xs text-slate-400">
      Mode
      <select
        bind:value={mode}
        class="rounded-md border border-white/10 bg-slate-900 px-2 py-1.5 text-sm text-slate-200"
      >
        <option value="replay">Replay</option>
        <option value="attach">Live (attach)</option>
      </select>
    </label>

    {#if mode === "replay"}
      <label class="flex flex-col gap-1 text-xs text-slate-400">
        Speed: {speed} gen/s
        <input type="range" min="1" max="30" bind:value={speed} class="accent-sky-400" />
      </label>
    {/if}

    <div class="flex gap-2">
      <button
        type="button"
        onclick={start}
        disabled={!selected}
        class="rounded-md bg-sky-500/90 px-4 py-1.5 text-sm font-medium text-slate-950 hover:bg-sky-400 disabled:opacity-40"
      >
        {connState === "streaming" ? "Restart" : "Start"}
      </button>
      <button
        type="button"
        onclick={stop}
        class="rounded-md border border-white/10 px-4 py-1.5 text-sm text-slate-300 hover:bg-white/5"
      >
        Stop
      </button>
    </div>

    <div class="ml-auto text-xs">
      <span
        class="rounded-full px-2.5 py-1 font-medium"
        class:bg-slate-700={connState === "idle"}
        class:bg-amber-500={connState === "connecting"}
        class:bg-emerald-500={connState === "streaming"}
        class:bg-sky-600={connState === "done"}
        class:bg-rose-600={connState === "error"}
        class:text-slate-950={connState === "streaming" || connState === "connecting"}
        class:text-white={connState !== "streaming" && connState !== "connecting"}
      >
        {connState}
      </span>
      {#if detail}
        <p class="mt-1 max-w-xs text-right text-rose-300">{detail}</p>
      {/if}
    </div>
  </div>

  <!-- Summary stat strip -->
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
    {#each [["generation", last ? `${last.gen}` : "—"], ["policy loss", last ? last.policy_loss.toFixed(3) : "—"], ["value loss", last ? last.value_loss.toFixed(3) : "—"], ["backend", runMeta.backend ?? "—"]] as [label, value] (label)}
      <div class="rounded-xl border border-white/5 bg-white/[0.02] p-3">
        <p class="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
        <p class="mt-0.5 font-mono text-lg text-slate-100">{value}</p>
      </div>
    {/each}
  </div>

  <!-- Loss curves -->
  <div class="grid gap-4 lg:grid-cols-2">
    <LineChart series={policySeries} title="Policy loss" yLabel="cross-entropy" />
    <LineChart series={valueSeries} title="Value loss" yLabel="MSE" />
  </div>

  <!-- Win / draw / loss -->
  {#if hasWdl}
    <div class="rounded-xl border border-white/5 bg-white/[0.02] p-4">
      <div class="mb-3 flex items-center justify-between">
        <span class="text-sm font-medium text-slate-200">Self-play results (White POV)</span>
        <span class="text-xs text-slate-400">{totalGames} games</span>
      </div>
      <div class="space-y-1.5">
        {#each gens as g (g.gen)}
          {@const tot = (g.wins ?? 0) + (g.draws ?? 0) + (g.losses ?? 0)}
          <div class="flex items-center gap-3">
            <span class="w-12 shrink-0 text-right font-mono text-xs text-slate-500">g{g.gen}</span>
            <div class="flex h-4 flex-1 overflow-hidden rounded-sm bg-slate-900">
              <div style:width={pct(g.wins ?? 0, tot)} style:background={WIN}></div>
              <div style:width={pct(g.draws ?? 0, tot)} style:background={DRAW}></div>
              <div style:width={pct(g.losses ?? 0, tot)} style:background={LOSS}></div>
            </div>
            <span class="w-28 shrink-0 font-mono text-[11px] text-slate-400">
              {g.wins ?? 0}/{g.draws ?? 0}/{g.losses ?? 0}
            </span>
          </div>
        {/each}
      </div>
      <div class="mt-3 flex gap-4 text-xs text-slate-400">
        <span class="flex items-center gap-1.5"
          ><span class="inline-block h-2 w-3 rounded-sm" style:background={WIN}></span>win</span
        >
        <span class="flex items-center gap-1.5"
          ><span class="inline-block h-2 w-3 rounded-sm" style:background={DRAW}></span>draw</span
        >
        <span class="flex items-center gap-1.5"
          ><span class="inline-block h-2 w-3 rounded-sm" style:background={LOSS}></span>loss</span
        >
      </div>
    </div>
  {/if}

  <!-- Gate timeline -->
  {#if gens.length > 0}
    <div class="rounded-xl border border-white/5 bg-white/[0.02] p-4">
      <span class="text-sm font-medium text-slate-200">Acceptance gate</span>
      <div class="mt-3 flex flex-wrap gap-1.5">
        {#each gens as g (g.gen)}
          <span
            class="rounded px-2 py-1 font-mono text-[11px]"
            class:bg-emerald-500={g.accepted}
            class:text-slate-950={g.accepted}
            class:bg-slate-800={!g.accepted}
            class:text-slate-400={!g.accepted}
            title={`gen ${g.gen}: gate ${g.gate_score ?? "n/a"}`}
          >
            g{g.gen}{g.gate_score != null ? ` ${g.gate_score.toFixed(2)}` : ""}
          </span>
        {/each}
      </div>
    </div>
  {/if}
</div>
