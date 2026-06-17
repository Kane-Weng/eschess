<script lang="ts">
  // A red, gently-pulsing glow on a board square — used to flag the from/to
  // squares of the move currently playing. Two stacked planes: a crisp core and
  // a softer, larger halo, both unlit (toneMapped off) so the red stays vivid.
  import { T } from "@threlte/core";
  import { Tween } from "svelte/motion";
  import { sineInOut } from "svelte/easing";
  import { squareToWorld, SQUARE_SIZE } from "../../lib/board";

  let { square }: { square: string } = $props();
  const p = $derived(squareToWorld(square));

  // Ping-pong the intensity so the squares read as "glowing", not just painted.
  const glow = new Tween(0.55, { duration: 650, easing: sineInOut });
  $effect(() => {
    let on = false;
    const id = setInterval(() => {
      on = !on;
      glow.set(on ? 0.32 : 0.62);
    }, 650);
    return () => clearInterval(id);
  });
</script>

<!-- Halo: larger, fainter. -->
<T.Mesh position={[p.x, 0.012, p.z]} rotation={[-Math.PI / 2, 0, 0]}>
  <T.PlaneGeometry args={[SQUARE_SIZE * 1.25, SQUARE_SIZE * 1.25]} />
  <T.MeshBasicMaterial
    color="#ff1a2e"
    transparent
    opacity={glow.current * 0.4}
    depthWrite={false}
    toneMapped={false}
  />
</T.Mesh>

<!-- Core: square-sized, brighter. -->
<T.Mesh position={[p.x, 0.018, p.z]} rotation={[-Math.PI / 2, 0, 0]}>
  <T.PlaneGeometry args={[SQUARE_SIZE * 0.94, SQUARE_SIZE * 0.94]} />
  <T.MeshBasicMaterial
    color="#ff2a3c"
    transparent
    opacity={glow.current}
    depthWrite={false}
    toneMapped={false}
  />
</T.Mesh>
