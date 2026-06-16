<script lang="ts">
  // Left vertical evaluation bar. Mirrors `python/eval_probe.py`: White's share
  // of the bar is 0.5 + 0.5*tanh(score/4); null score renders neutral grey.
  interface Props {
    score: number | null; // pawns, White POV
  }
  const { score }: Props = $props();

  const fraction = $derived(score === null ? 0.5 : 0.5 + 0.5 * Math.tanh(score / 4));
  const label = $derived(
    score === null
      ? ""
      : score >= 999
        ? "+M"
        : score <= -999
          ? "-M"
          : (score >= 0 ? "+" : "") + score.toFixed(1),
  );
  // White text sits at the bottom of the bar; flip its colour once the white
  // fill is tall enough to sit behind it.
  const labelDark = $derived(score !== null && fraction > 0.08);
</script>

<div
  class="relative w-7 shrink-0 self-stretch overflow-hidden rounded-sm border-2 border-slate-500 bg-[#2a2a30]"
  role="img"
  aria-label={score === null ? "Evaluation unavailable" : `Evaluation ${label}`}
>
  {#if score !== null}
    <div
      class="absolute inset-x-0 bottom-0 bg-[#ededed] transition-[height] duration-300"
      style:height={`${fraction * 100}%`}
    ></div>
  {:else}
    <div class="absolute inset-0 bg-[#3c3c42]"></div>
  {/if}
  <!-- midline -->
  <div class="absolute inset-x-0 top-1/2 h-px bg-slate-500/70"></div>
  {#if label}
    <span
      class="absolute inset-x-0 bottom-1 text-center text-[0.6rem] font-bold tabular-nums"
      class:text-slate-900={labelDark}
      class:text-slate-100={!labelDark}
    >
      {label}
    </span>
  {/if}
</div>
