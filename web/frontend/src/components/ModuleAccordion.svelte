<script lang="ts">
  // The four interactive modules of the Eschess web showcase.
  type Module = {
    piece: string; // unicode chess glyph
    title: string;
    summary: string;
    href: string;
    status: string; // short "coming soon" / "live" tag
  };

  const modules: Module[] = [
    {
      piece: "♞", // ♞ knight
      title: "Engine Sandbox",
      summary:
        "Play or watch the engines. C++/Rust compile to WebAssembly and search " +
        "client-side at near-native speed; Python/ML stream over a socket. Learning " +
        "mode overlays the searched branches and live evaluations; Competition mode " +
        "lets you tune depth, time, and style.",
      href: "#engine-sandbox",
      status: "Planned",
    },
    {
      piece: "♜", // ♜ rook
      title: "Detailed Record",
      summary:
        "An interactive engineering blog in six chapters — one per chess piece, " +
        "Pawn to King — walking from bitboards and alpha-beta up to ML and " +
        "orchestration, with live widgets embedded between the paragraphs.",
      href: "/record",
      status: "In progress",
    },
    {
      piece: "♛", // ♛ queen
      title: "Live Training & Dashboard",
      summary:
        "A telemetry room streaming a persistent self-play loop: moving averages of " +
        "policy loss, value loss, evolving win/loss ratios, and NPS — graphed in " +
        "real time over a WebSocket while a background server does the training.",
      href: "#training-dashboard",
      status: "Planned",
    },
    {
      piece: "♚", // ♚ king
      title: "LLM Chess Coach",
      summary:
        "A chat beside a board. Every move is scored by the engine — top-3 " +
        "principal variations and centipawn shifts — then packaged into a strict " +
        "prompt so an LLM can explain, in plain English, why a move was good or bad.",
      href: "#llm-coach",
      status: "Planned",
    },
  ];

  let locked = $state<number | null>(null);

  const isOpen = (i: number) => locked === i;

  function toggle(i: number) {
    locked = locked === i ? null : i;
  }
</script>

<div class="flex flex-col gap-3">
  {#each modules as m, i (m.title)}
    <div
      class="overflow-hidden rounded-xl border border-white/10 bg-slate-900/70 transition-colors duration-300 hover:border-[var(--color-accent)]/60"
      class:border-[var(--color-accent)]={locked === i}
    >
      <button
        type="button"
        class="group flex w-full items-center gap-5 px-6 py-5 text-left"
        aria-expanded={isOpen(i)}
        onclick={() => toggle(i)}
      >
        <span
          class="text-4xl leading-none text-[var(--color-accent)] transition-transform duration-300 group-hover:scale-110 group-focus:scale-110"
          class:scale-110={isOpen(i)}
          aria-hidden="true">{m.piece}</span
        >
        <span class="flex-1">
          <span class="flex items-center gap-3">
            <span class="font-[var(--font-display)] text-xl font-semibold tracking-tight"
              >{m.title}</span
            >
            <span
              class="rounded-full border border-white/10 px-2 py-0.5 text-[0.65rem] uppercase tracking-wider text-slate-400"
              >{m.status}</span
            >
          </span>
        </span>
        <span
          class="text-2xl text-slate-500 transition-transform duration-300"
          class:rotate-90={isOpen(i)}
          aria-hidden="true">&rsaquo;</span
        >
      </button>

      <div
        class="grid transition-all duration-300 ease-out"
        style:grid-template-rows={isOpen(i) ? "1fr" : "0fr"}
      >
        <div class="overflow-hidden">
          <div class="px-6 pb-6 pl-[4.75rem]">
            <p class="max-w-2xl text-sm leading-relaxed text-slate-300">{m.summary}</p>
            <a
              href={m.href}
              class="mt-4 inline-flex items-center gap-2 text-sm font-medium text-[var(--color-accent)] hover:underline"
            >
              Open module <span aria-hidden="true">&rarr;</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  {/each}
</div>
