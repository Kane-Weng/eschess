<script lang="ts">
  type Course = {
    code: string;
    name: string;
    tag: string;
    summary: string;
    detail: string;
    upcoming?: boolean;
  };

  const courses: Course[] = [
    {
      code: "EECS 280",
      name: "Programming & Data Structures",
      tag: "Foundation",
      summary: "The C++ foundation.",
      detail:
        "The structural blueprints required to architect the core engine and manage memory safely.",
    },
    {
      code: "EECS 281",
      name: "Data Structures & Algorithms",
      tag: "Speed",
      summary: "The engine's speed.",
      detail:
        "Implementing the search logic, including Minimax, Alpha-Beta pruning, and Zobrist hashing, that allows the engine to look millions of nodes deep without stalling.",
    },
    {
      code: "EECS 270 / 370",
      name: "Logic Design & Computer Architecture",
      tag: "Bare metal",
      summary: "The bare metal.",
      detail:
        "Understanding bits, endianness, and caching translates directly into lightning-fast bitboard representations and transposition tables.",
    },
    {
      code: "EECS 445",
      name: "Machine Learning",
      tag: "Intuition",
      summary: "The intuition.",
      detail:
        "Moving beyond brute-force calculation to understand how modern engines (like Stockfish and AlphaZero) use neural networks to evaluate board states.",
    },
    {
      code: "EECS 504",
      name: "Computer Vision",
      tag: "Future scope",
      summary: "The future scope.",
      detail:
        "Exploring how Vision-Language-Action (VLA) models might eventually interpret the board visually, bridging the gap between digital state and physical perception.",
      upcoming: true,
    },
  ];

  // Open the first node by default so the widget reads clearly at a glance.
  let openIndex = $state<number | null>(0);

  function toggle(i: number) {
    openIndex = openIndex === i ? null : i;
  }
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-6 font-sans sm:p-7">
  <div class="mb-6 flex items-center justify-between">
    <span class="text-[11px] font-bold uppercase tracking-[0.2em] text-[#6ec2e8]">
      The Coursework Stack
    </span>
    <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
      Sophomore yr &rarr; Upcoming
    </span>
  </div>

  <ol class="relative flex flex-col">
    {#each courses as c, i (c.code)}
      {@const isOpen = openIndex === i}
      <li class="relative pl-9 pb-5 last:pb-0">
        <!-- connecting line -->
        {#if i < courses.length - 1}
          <span
            class="absolute left-[7px] top-5 -bottom-0 w-px {c.upcoming || courses[i + 1].upcoming
              ? 'border-l border-dashed border-slate-600/60'
              : 'bg-gradient-to-b from-[#6ec2e8]/60 to-[#6ec2e8]/15'}"
          ></span>
        {/if}

        <!-- node dot -->
        <span
          class="absolute left-0 top-[3px] flex h-[15px] w-[15px] items-center justify-center rounded-full border-2 {c.upcoming
            ? 'border-amber-400/70 bg-slate-900'
            : 'border-[#6ec2e8] bg-[#6ec2e8]/20'}"
        >
          {#if c.upcoming}
            <svg class="h-2 w-2 text-amber-400" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 1a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V6a5 5 0 0 0-5-5Zm3 8H9V6a3 3 0 1 1 6 0v3Z" />
            </svg>
          {:else}
            <span class="h-1.5 w-1.5 rounded-full bg-[#6ec2e8]"></span>
          {/if}
        </span>

        <button
          type="button"
          onclick={() => toggle(i)}
          class="group flex w-full flex-col gap-1 text-left"
          aria-expanded={isOpen}
        >
          <span class="flex flex-wrap items-center gap-2.5">
            <span class="font-mono text-sm font-bold {c.upcoming ? 'text-amber-300' : 'text-white'}">
              {c.code}
            </span>
            <span
              class="rounded-full border px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wider {c.upcoming
                ? 'border-amber-400/30 text-amber-400/80'
                : 'border-[#6ec2e8]/30 text-[#6ec2e8]/90'}"
            >
              {c.tag}
            </span>
            {#if c.upcoming}
              <span class="text-[0.6rem] font-semibold uppercase tracking-wider text-slate-500">
                Upcoming
              </span>
            {/if}
            <svg
              class="ml-auto h-4 w-4 shrink-0 text-slate-500 transition-transform duration-300 {isOpen ? 'rotate-90' : ''}"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </span>

          <span class="text-xs font-medium text-slate-400">{c.name}</span>

          <span class="grid transition-all duration-300 {isOpen ? 'mt-1 grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}">
            <span class="overflow-hidden">
              <span class="block text-sm leading-relaxed text-slate-300">
                <span class="font-semibold text-slate-200">{c.summary}</span>
                {c.detail}
              </span>
            </span>
          </span>
        </button>
      </li>
    {/each}
  </ol>
</div>
