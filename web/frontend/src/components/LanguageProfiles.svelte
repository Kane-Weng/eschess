<script>
  import { fade, fly } from 'svelte/transition';

  const profiles = {
    python: {
      name: 'Python',
      title: 'The Architect',
      icon: `${import.meta.env.BASE_URL}/python.svg`,
      strengths: 'Rapid iteration, massive ML ecosystem.',
      weakness: 'The Global Interpreter Lock and slow hot-loops.',
      role: 'Drafting search algorithms and training the neural network via PyTorch.',
      color: 'text-blue-400'
    },
    cpp: {
      name: 'C++',
      title: 'The Benchmark',
      icon: `${import.meta.env.BASE_URL}/cplusplus.svg`,
      strengths: 'Raw execution speed, industry standard for chess engines.',
      weakness: 'Manual memory management and verbose build systems.',
      role: 'Standalone UCI executable for rigorous engine-vs-engine testing.',
      color: 'text-indigo-400'
    },
    rust: {
      name: 'Rust',
      title: 'The FFI Core',
      icon: `${import.meta.env.BASE_URL}/rust.svg`,
      strengths: 'Memory safety, fearless concurrency, zero-cost bindings.',
      weakness: 'The strict borrow checker learning curve.',
      role: 'High-speed self-play pipeline natively bound back to Python via PyO3.',
      color: 'text-orange-400'
    }
  };

  let selected = 'python';
</script>

<div class="my-6 overflow-hidden rounded-xl border border-white/10 bg-slate-900/50 not-prose shadow-sm">
  <div class="flex items-center gap-1 border-b border-white/10 px-2 pt-2">
    {#each Object.entries(profiles) as [key, profile]}
      <button
        class="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 text-sm font-medium transition-colors rounded-t-md
        {selected === key 
          ? 'bg-white/10 text-[var(--color-accent)]' 
          : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'}"
        on:click={() => selected = key}
      >
        <img src={profile.icon} alt="{profile.name} logo" class="w-4 h-4 object-contain opacity-90" />
        <span class="hidden sm:inline">{profile.name}</span>
      </button>
    {/each}
  </div>

  <div class="p-6 md:p-8 grid">
    {#key selected}
      <div
        class="col-start-1 row-start-1 flex flex-col gap-6"
        in:fly={{ y: 10, duration: 300, delay: 150 }}
        out:fade={{ duration: 150 }}
      >
        <div class="flex items-center gap-4">
          <div class="w-14 h-14 flex-shrink-0 bg-white/5 rounded-full flex items-center justify-center p-2 border border-white/10">
            <img src={profiles[selected].icon} alt="{profiles[selected].name} logo" class="w-8 h-8 object-contain" />
          </div>
          <div>
            <h3 class="m-0 text-xl font-bold text-slate-200">{profiles[selected].name}</h3>
            <p class="m-0 text-sm font-bold uppercase tracking-wider {profiles[selected].color}">{profiles[selected].title}</p>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Strengths</h4>
            <p class="m-0 text-sm text-slate-300 leading-relaxed">{profiles[selected].strengths}</p>
          </div>
          <div>
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Weakness</h4>
            <p class="m-0 text-sm text-slate-300 leading-relaxed">{profiles[selected].weakness}</p>
          </div>
          
          <div class="md:col-span-2 bg-white/5 p-4 rounded-lg border border-white/10">
            <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">Eschess Role</h4>
            <p class="m-0 text-sm font-medium text-slate-200 leading-relaxed">{profiles[selected].role}</p>
          </div>
        </div>
      </div>
    {/key}
  </div>
</div>