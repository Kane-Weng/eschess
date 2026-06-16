<script lang="ts">
  // Procedurally generated 8x8 board: a dark metallic base slab plus 64
  // checkered tiles. Built entirely from Threlte primitives — no model needed.
  import { T } from "@threlte/core";
  import { SQUARE_SIZE } from "../../lib/board";

  type Tile = { x: number; z: number; dark: boolean };

  const tiles: Tile[] = [];
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      tiles.push({
        x: (f - 3.5) * SQUARE_SIZE,
        z: (3.5 - r) * SQUARE_SIZE,
        dark: (r + f) % 2 === 1,
      });
    }
  }

  const BOARD = 8 * SQUARE_SIZE;
</script>

<!-- Base slab, sitting just below the tiles so its rim frames the board.
     Low metalness: with no environment map, high metalness renders black. -->
<T.Mesh receiveShadow position={[0, -0.14, 0]}>
  <T.BoxGeometry args={[BOARD + 0.6, 0.24, BOARD + 0.6]} />
  <T.MeshStandardMaterial color="#080b12" metalness={0.25} roughness={0.6} />
</T.Mesh>

<!-- 64 checkered tiles, laid flat (rotated to face up). A small gap leaves the
     dark base showing as grid lines. -->
{#each tiles as tile (`${tile.x}:${tile.z}`)}
  <T.Mesh receiveShadow position={[tile.x, 0, tile.z]} rotation={[-Math.PI / 2, 0, 0]}>
    <T.PlaneGeometry args={[SQUARE_SIZE * 0.97, SQUARE_SIZE * 0.97]} />
    <T.MeshStandardMaterial
      color={tile.dark ? "#1a2433" : "#9aa9c2"}
      metalness={0.2}
      roughness={0.55}
      emissive={tile.dark ? "#0a1626" : "#2b3a52"}
      emissiveIntensity={0.35}
    />
  </T.Mesh>
{/each}
