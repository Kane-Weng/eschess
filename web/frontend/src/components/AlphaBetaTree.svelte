<script lang="ts">
  // Interactive alpha-beta walkthrough for the Pawn chapter.
  // A small fixed depth-3 game tree (MAX at the root) is searched by a real,
  // instrumented alpha-beta routine. Every enter / evaluate / window-update /
  // cutoff is captured as a snapshot, and the controls replay those snapshots so
  // you can watch the [alpha, beta] window tighten and pruned subtrees fade out.

  type Status = "idle" | "active" | "visited" | "pruned";

  interface TreeNode {
    id: string;
    depth: number;
    isMax: boolean;
    leaf?: number;
    children?: TreeNode[];
    x: number;
    y: number;
  }

  interface NodeState {
    status: Status;
    alpha: number;
    beta: number;
    value: number | null;
  }

  interface Snapshot {
    current: string;
    message: string;
    states: Record<string, NodeState>;
  }

  // Leaf scores, left to right. Chosen so the search makes two clear cutoffs:
  // a single leaf is pruned under one branch, a whole subtree under another.
  const LEAVES = [3, 5, 6, 9, 1, 2, 0, -1];

  const LEAF_GAP = 64;
  const Y_GAP = 90;
  const MARGIN_X = 32;
  const MARGIN_Y = 34;

  // ── Build the tree ─────────────────────────────────────────────────────────
  let counter = 0;
  let leafCursor = 0;
  function build(depth: number, isMax: boolean): TreeNode {
    const id = "n" + counter++;
    if (depth === 3) {
      return { id, depth, isMax, leaf: LEAVES[leafCursor++], x: 0, y: 0 };
    }
    return {
      id,
      depth,
      isMax,
      children: [build(depth + 1, !isMax), build(depth + 1, !isMax)],
      x: 0,
      y: 0,
    };
  }
  const root = build(0, true);

  // Post-order layout: leaves spread evenly, parents centre over their children.
  let nextLeaf = 0;
  function layout(node: TreeNode) {
    node.y = node.depth * Y_GAP + MARGIN_Y;
    if (!node.children) {
      node.x = nextLeaf++ * LEAF_GAP + MARGIN_X + 18;
      return;
    }
    node.children.forEach(layout);
    const xs = node.children.map((c) => c.x);
    node.x = (Math.min(...xs) + Math.max(...xs)) / 2;
  }
  layout(root);

  const allNodes: TreeNode[] = [];
  const edges: { from: TreeNode; to: TreeNode }[] = [];
  (function flatten(node: TreeNode) {
    allNodes.push(node);
    node.children?.forEach((c) => {
      edges.push({ from: node, to: c });
      flatten(c);
    });
  })(root);

  const W = 8 * LEAF_GAP + MARGIN_X * 2;
  const H = 3 * Y_GAP + MARGIN_Y * 2;

  // ── Instrumented alpha-beta: record a snapshot at every meaningful step ─────
  const states: Record<string, NodeState> = {};
  allNodes.forEach((n) => {
    states[n.id] = { status: "idle", alpha: -Infinity, beta: Infinity, value: null };
  });

  const snapshots: Snapshot[] = [];
  function snap(current: string, message: string) {
    snapshots.push({ current, message, states: structuredClone(states) });
  }

  const fmt = (v: number) =>
    v === Infinity ? "+∞" : v === -Infinity ? "−∞" : `${v}`;
  const kind = (n: TreeNode) => (n.isMax ? "MAX" : "MIN");

  function descendants(node: TreeNode, out: string[]) {
    out.push(node.id);
    node.children?.forEach((c) => descendants(c, out));
  }

  function search(node: TreeNode, alpha: number, beta: number): number {
    const s = states[node.id];
    s.status = "active";
    s.alpha = alpha;
    s.beta = beta;
    snap(node.id, `Enter ${kind(node)} node with window [${fmt(alpha)}, ${fmt(beta)}].`);

    if (node.leaf !== undefined) {
      s.value = node.leaf;
      s.status = "visited";
      snap(node.id, `Leaf evaluates to ${node.leaf}.`);
      return node.leaf;
    }

    let value = node.isMax ? -Infinity : Infinity;
    const children = node.children!;
    for (let i = 0; i < children.length; i++) {
      const childVal = search(children[i], alpha, beta);
      s.status = "active";

      if (node.isMax) {
        value = Math.max(value, childVal);
        alpha = Math.max(alpha, value);
        s.value = value;
        s.alpha = alpha;
        snap(node.id, `MAX keeps best ${fmt(value)}, raises α to ${fmt(alpha)}.`);
      } else {
        value = Math.min(value, childVal);
        beta = Math.min(beta, value);
        s.value = value;
        s.beta = beta;
        snap(node.id, `MIN keeps best ${fmt(value)}, lowers β to ${fmt(beta)}.`);
      }

      if (alpha >= beta && i < children.length - 1) {
        const pruned: string[] = [];
        for (let j = i + 1; j < children.length; j++) descendants(children[j], pruned);
        pruned.forEach((id) => (states[id].status = "pruned"));
        snap(
          node.id,
          `α ≥ β (${fmt(alpha)} ≥ ${fmt(beta)}): the rest of this branch cannot change the result, prune ${pruned.length} node${pruned.length === 1 ? "" : "s"}.`,
        );
        break;
      }
    }

    s.status = "visited";
    snap(node.id, `${kind(node)} node returns ${fmt(value)}.`);
    return value;
  }
  search(root, -Infinity, Infinity);
  snapshots.push({
    current: root.id,
    message: `Search complete: the root's best score is ${fmt(states[root.id].value ?? 0)}.`,
    states: structuredClone(states),
  });

  // ── Playback ───────────────────────────────────────────────────────────────
  let step = $state(0);
  let playing = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  const frame = $derived(snapshots[step]);
  const atEnd = $derived(step >= snapshots.length - 1);

  function stop() {
    playing = false;
    if (timer) clearInterval(timer);
    timer = null;
  }
  function next() {
    if (atEnd) {
      stop();
      return;
    }
    step += 1;
  }
  function prev() {
    stop();
    if (step > 0) step -= 1;
  }
  function reset() {
    stop();
    step = 0;
  }
  function togglePlay() {
    if (playing) {
      stop();
      return;
    }
    if (atEnd) step = 0;
    playing = true;
    timer = setInterval(next, 1100);
  }

  const fill = (st: Status, current: boolean) => {
    if (st === "pruned") return "#1e293b";
    if (current) return "var(--color-accent)";
    if (st === "visited") return "#334155";
    if (st === "active") return "#475569";
    return "#1e293b";
  };
</script>

<div class="not-prose my-8 rounded-xl border border-white/10 bg-slate-900/60 p-5">
  <svg viewBox={`0 0 ${W} ${H}`} class="w-full" role="img" aria-label="Alpha-beta search tree">
    <!-- edges -->
    {#each edges as edge}
      {@const childState = frame.states[edge.to.id]}
      {@const pruned = childState.status === "pruned"}
      <line
        x1={edge.from.x}
        y1={edge.from.y}
        x2={edge.to.x}
        y2={edge.to.y}
        stroke={pruned ? "#475569" : "#64748b"}
        stroke-width="1.5"
        stroke-dasharray={pruned ? "4 4" : "0"}
        class="ab-fade"
        opacity={pruned ? 0.25 : 0.7}
      />
    {/each}

    <!-- nodes -->
    {#each allNodes as node}
      {@const ns = frame.states[node.id]}
      {@const isCurrent = frame.current === node.id && ns.status !== "pruned"}
      {@const pruned = ns.status === "pruned"}
      <g class="ab-fade" opacity={pruned ? 0.3 : 1}>
        <circle
          cx={node.x}
          cy={node.y}
          r="18"
          fill={fill(ns.status, isCurrent)}
          stroke={isCurrent ? "var(--color-accent)" : "#475569"}
          stroke-width={isCurrent ? 3 : 1.5}
        />
        <text
          x={node.x}
          y={node.y + 4}
          text-anchor="middle"
          class="font-mono text-[12px]"
          fill={isCurrent ? "#0f172a" : "#e2e8f0"}
        >
          {ns.value !== null ? fmt(ns.value) : node.leaf !== undefined ? "?" : kind(node)}
        </text>

        <!-- alpha/beta window for interior nodes that have been entered -->
        {#if node.leaf === undefined && (ns.status === "active" || ns.status === "visited")}
          <text
            x={node.x}
            y={node.y - 24}
            text-anchor="middle"
            class="font-mono text-[9px]"
            fill="#94a3b8"
          >
            [{fmt(ns.alpha)}, {fmt(ns.beta)}]
          </text>
        {/if}
      </g>
    {/each}
  </svg>

  <!-- step readout -->
  <p class="mt-3 min-h-[2.5rem] text-sm leading-relaxed text-slate-300">
    {frame.message}
  </p>

  <!-- controls -->
  <div class="mt-3 flex flex-wrap items-center gap-2">
    <button
      type="button"
      onclick={togglePlay}
      class="rounded-md bg-[var(--color-accent)]/15 px-3 py-1.5 text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent)]/25"
    >
      {playing ? "pause" : atEnd ? "replay" : "play"}
    </button>
    <button
      type="button"
      onclick={prev}
      disabled={step === 0}
      class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10 disabled:opacity-30"
    >
      prev
    </button>
    <button
      type="button"
      onclick={next}
      disabled={atEnd}
      class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10 disabled:opacity-30"
    >
      next
    </button>
    <button
      type="button"
      onclick={reset}
      class="rounded-md bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10"
    >
      reset
    </button>
    <span class="ml-auto font-mono text-xs text-slate-500">
      step {step + 1} / {snapshots.length}
    </span>
  </div>

  <p class="mt-4 text-xs leading-relaxed text-slate-500">
    Squares show each node's type until it resolves to a score. The
    <span class="text-slate-400">[α, β]</span> label above a node is its live search
    window. When α reaches β the remaining children are unreachable, so they fade out
    unsearched. Same leaves, fewer nodes visited.
  </p>
</div>

<style>
  .ab-fade {
    transition:
      opacity 0.35s ease,
      stroke 0.2s ease;
  }
</style>
