<script lang="ts">
  let { username = "kane12205263" } = $props<{ username?: string }>();

  // Profile and Data States
  let profile = $state<any>(null);
  let stats = $state<any>(null);
  let recentGames = $state<any[]>([]);
  let history = $state<{ time: number; rating: number; date: string }[]>([]);
  let loading = $state(true);
  
  // Navigation
  let activeTab = $state<'chart' | 'games'>('chart');

  // Chart Hover States
  let containerWidth = $state(0);
  let hoveredPoint = $state<{ x: number; y: number; rating: number; date: string } | null>(null);

  $effect(() => {
    async function fetchChessData() {
      try {
        const headers = { 'User-Agent': 'Eschess Blog - Client' };
        
        const [profRes, statRes, archRes] = await Promise.all([
          fetch(`https://api.chess.com/pub/player/${username}`, { headers }),
          fetch(`https://api.chess.com/pub/player/${username}/stats`, { headers }),
          fetch(`https://api.chess.com/pub/player/${username}/games/archives`, { headers })
        ]);

        profile = await profRes.json();
        stats = await statRes.json();
        const archivesData = await archRes.json();
        const archives = archivesData.archives || [];

        if (archives.length > 0) {
          const recentArchives = archives.slice(-4);    // Last 4 months
          const monthResponses = await Promise.all(
            recentArchives.map((url: string) => fetch(url, { headers }).then(r => r.json()))
          );

          const now = Math.floor(Date.now() / 1000);
          const ninetyDaysAgo = now - (90 * 24 * 60 * 60);

          const dataPoints: { time: number; rating: number; date: string }[] = [];
          let rawRecentGames: any[] = [];
          
          monthResponses.forEach((month, index) => {
            if (index === monthResponses.length - 1 && month.games) {
              rawRecentGames = month.games;
            }

            month.games?.forEach((g: any) => {
              if (g.rules === "chess" && g.time_class === "rapid" && g.end_time >= ninetyDaysAgo) {
                const isWhite = g.white.username.toLowerCase() === username.toLowerCase();
                const rating = isWhite ? g.white.rating : g.black.rating;
                const date = new Date(g.end_time * 1000).toLocaleDateString();
                
                const lastEntry = dataPoints[dataPoints.length - 1];
                if (lastEntry && lastEntry.date === date) {
                  lastEntry.rating = rating;
                  lastEntry.time = g.end_time;
                } else {
                  dataPoints.push({ time: g.end_time, rating, date });
                }
              }
            });
          });

          history = dataPoints;
          
          recentGames = rawRecentGames
            .filter((g: any) => g.rules === "chess" && g.time_class === "rapid")
            .slice(-10)
            .reverse();
        }
      } catch (e) {
        console.error("Failed to load chess data:", e);
      } finally {
        loading = false;
      }
    }
    
    fetchChessData();
  });

  const rapidElo = $derived(stats?.chess_rapid?.last?.rating ?? "---");
  const record = $derived(stats?.chess_rapid?.record ?? { win: 0, loss: 0, draw: 0 });
  const periodGain = $derived(history.length > 1 ? (Number(rapidElo) - history[0].rating) : 0);

  const minT = $derived(history.length ? history[0].time : 0);
  const maxT = $derived(history.length ? history[history.length - 1].time : 1);
  const rangeT = $derived(maxT - minT || 1);

  const minR = $derived(history.length ? Math.min(...history.map(d => d.rating)) - 30 : 0);
  const maxR = $derived(history.length ? Math.max(...history.map(d => d.rating)) + 30 : 100);
  const rangeR = $derived(maxR - minR || 1);

  const mappedPoints = $derived(
    history.map(d => ({
      x: ((d.time - minT) / rangeT) * 100,
      y: 100 - ((d.rating - minR) / rangeR) * 100,
      rating: d.rating,
      date: d.date
    }))
  );

  const polylineStr = $derived(mappedPoints.map(p => `${p.x},${p.y}`).join(' '));
  const polygonStr = $derived(`0,100 ${polylineStr} 100,100`);

  function handlePointerMove(e: PointerEvent) {
    if (!mappedPoints.length || !containerWidth) return;
    
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const relativeX = ((e.clientX - rect.left) / rect.width) * 100;
    
    let closest = mappedPoints[0];
    let minDiff = Infinity;
    
    for (const pt of mappedPoints) {
      const diff = Math.abs(pt.x - relativeX);
      if (diff < minDiff) {
        minDiff = diff;
        closest = pt;
      }
    }
    hoveredPoint = closest;
  }

  function handlePointerLeave() {
    hoveredPoint = null;
  }
</script>

<div class="not-prose my-8 overflow-hidden rounded-xl bg-[#2b2826] shadow-xl font-sans" style="color: #e2e8f0;">
  {#if loading}
    <div class="flex min-h-[260px] items-center justify-center text-sm font-medium opacity-60">
      <span class="animate-pulse">Compiling recent data logs...</span>
    </div>
  {:else}
    <div class="flex flex-col md:flex-row">
      
      <div class="flex w-full flex-col gap-6 border-b border-white/10 p-6 md:w-[30%] md:border-b-0 md:border-r">
        <div class="flex items-center gap-4 md:flex-col md:items-start">
          <div class="h-16 w-16 overflow-hidden rounded-xl border border-white/10 bg-black/20 shadow-inner">
            {#if profile?.avatar}
              <img src={profile.avatar} alt="Avatar" class="h-full w-full object-cover" />
            {/if}
          </div>
          <div class="flex flex-col">
            <span class="text-lg font-bold text-white leading-tight">{profile?.name || username}</span>
            <a href={profile?.url} target="_blank" rel="noopener noreferrer" class="text-xs font-semibold text-[#b3b0ad] hover:text-white transition-colors mt-0.5">
              @{username}
            </a>
          </div>
        </div>

        <div class="flex flex-row justify-between gap-4 border-t border-white/5 pt-4 md:flex-col md:gap-5">
          <div class="flex flex-col gap-0.5">
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#b3b0ad]">Current Rating</span>
            <span class="font-mono text-3xl font-black text-white">{rapidElo}</span>
          </div>
          <div class="flex flex-col gap-0.5">
            <span class="text-[10px] font-bold uppercase tracking-wider text-[#b3b0ad]">W / L / D</span>
            <span class="font-mono text-sm font-bold">
              <span class="text-[#81b64c]">{record.win}W</span>
              <span class="text-neutral-500 mx-1">/</span>
              <span class="text-rose-400">{record.loss}L</span>
              <span class="text-neutral-500 mx-1">/</span>
              <span class="text-neutral-400">{record.draw}D</span>
            </span>
          </div>
        </div>
      </div>

      <div class="flex w-full flex-col p-6 md:w-[70%] bg-black/10">
        
        <div class="mb-5 flex gap-6 border-b border-white/5">
          <button 
            onclick={() => activeTab = 'chart'}
            class="pb-3 text-xs font-bold uppercase tracking-wider transition-all {activeTab === 'chart' ? 'border-b-2 border-[#6ec2e8] text-white' : 'text-[#b3b0ad] hover:text-white'}"
          >
            90-Day Trend
          </button>
          <button 
            onclick={() => activeTab = 'games'}
            class="pb-3 text-xs font-bold uppercase tracking-wider transition-all {activeTab === 'games' ? 'border-b-2 border-[#6ec2e8] text-white' : 'text-[#b3b0ad] hover:text-white'}"
          >
            Recent Games
          </button>
        </div>

        <div class="relative flex-1">
          
          {#if activeTab === 'chart'}
            {#if history.length > 2}
              <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2 text-xs font-semibold text-[#b3b0ad]">
                  <svg class="w-4 h-4 text-[#81b64c]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <circle cx="12" cy="13" r="8"></circle>
                    <path d="M12 9v4l2 2"></path>
                  </svg>
                  <span>90-Day Timeline</span>
                </div>
                {#if periodGain > 0}
                  <div class="flex items-center gap-0.5 text-xs font-bold text-[#81b64c]">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18"></path>
                    </svg>
                    <span>+{periodGain} Gain</span>
                  </div>
                {:else if periodGain < 0}
                  <div class="flex items-center gap-0.5 text-xs font-bold text-rose-400">
                    <svg class="w-3.5 h-3.5 transform rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="3">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18"></path>
                    </svg>
                    <span>{periodGain}</span>
                  </div>
                {/if}
              </div>

              <div 
                class="relative h-[160px] w-full cursor-crosshair touch-none select-none"
                bind:clientWidth={containerWidth}
                onpointermove={handlePointerMove}
                onpointerleave={handlePointerLeave}
              >
                <svg class="absolute inset-0 h-full w-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 100 100">
                  <polygon points={polygonStr} fill="rgba(110, 194, 232, 0.12)" />
                  <polyline 
                    points={polylineStr} 
                    fill="none" 
                    stroke="#6ec2e8" 
                    stroke-width="1.5" 
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    vector-effect="non-scaling-stroke" 
                  />
                  
                  {#if hoveredPoint}
                    <line 
                      x1="{hoveredPoint.x}%" y1="0" 
                      x2="{hoveredPoint.x}%" y2="100%" 
                      stroke="rgba(255,255,255,0.15)" 
                      stroke-width="1" 
                      vector-effect="non-scaling-stroke"
                    />
                  {/if}
                </svg>

                {#if hoveredPoint}
                  <div 
                    class="pointer-events-none absolute h-[9px] w-[9px] rounded-full border-2 border-[#2b2826] bg-[#6ec2e8] shadow-[0_0_8px_rgba(110,194,232,0.8)] transform -translate-x-1/2 -translate-y-1/2 transition-all duration-75"
                    style="left: {hoveredPoint.x}%; top: {hoveredPoint.y}%;"
                  ></div>

                  <div 
                    class="pointer-events-none absolute top-1 rounded bg-black/90 border border-white/5 px-2.5 py-1 shadow-xl text-center transform -translate-x-1/2 transition-all duration-75"
                    style="left: {Math.max(12, Math.min(88, hoveredPoint.x))}%;"
                  >
                    <div class="text-[10px] font-bold text-[#b3b0ad] tracking-wide">{hoveredPoint.date}</div>
                    <div class="text-sm font-black text-white font-mono leading-none mt-0.5">{hoveredPoint.rating}</div>
                  </div>
                {/if}
              </div>
            {:else}
              <div class="flex h-[160px] items-center justify-center text-xs font-semibold text-neutral-500">
                Insufficient historic data matching parameters.
              </div>
            {/if}
            
          {:else}
            <div class="flex flex-col gap-1.5 max-h-[180px] overflow-y-auto pr-1">
              {#each recentGames.slice(0, 4) as game}
                {@const isWhite = game.white.username.toLowerCase() === username.toLowerCase()}
                {@const myResult = isWhite ? game.white.result : game.black.result}
                {@const isWin = myResult === 'win'}
                {@const isDraw = ['agreed', 'repetition', 'stalemate', 'insufficient', '50move'].includes(myResult)}
                
                <a 
                  href={game.url} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  class="group flex items-center justify-between rounded-lg border border-white/5 bg-white/[0.02] p-2.5 transition-all hover:border-white/10 hover:bg-white/[0.05]"
                >
                  <div class="flex items-center gap-2.5">
                    <div class="h-1.5 w-1.5 rounded-full {isWin ? 'bg-[#81b64c]' : isDraw ? 'bg-neutral-400' : 'bg-rose-400'}"></div>
                    <span class="text-xs font-bold text-neutral-300 group-hover:text-white transition-colors">
                      vs {isWhite ? game.black.username : game.white.username}
                    </span>
                  </div>
                  <div class="flex items-center gap-3 text-[11px] font-bold text-neutral-500">
                    <span class="font-mono text-neutral-400">{isWhite ? game.white.rating : game.black.rating} Elo</span>
                    <span class="font-mono uppercase text-xs {isWin ? 'text-[#81b64c]' : isDraw ? 'text-neutral-400' : 'text-rose-400'}">{myResult}</span>
                  </div>
                </a>
              {/each}
              {#if recentGames.length === 0}
                <div class="flex h-[140px] items-center justify-center text-xs font-semibold text-neutral-500">
                  No match records compiled inside this context window.
                </div>
              {/if}
            </div>
          {/if}

        </div>
      </div>
    </div>
  {/if}
</div>