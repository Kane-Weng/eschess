<script lang="ts">
  // A single chess piece. Loads its mesh from the shared GLB by node name
  // (e.g. "White_King"), recenters it, and animates between squares.
  //  - sliding pieces glide along X/Z
  //  - knights hop in a vertical arc
  //  - captured pieces lift up and fade out before being removed
  import * as THREE from "three";
  import { T } from "@threlte/core";
  import { useGltf } from "@threlte/extras";
  import { Tween } from "svelte/motion";
  import { cubicInOut, cubicOut } from "svelte/easing";
  import { squareToWorld, PIECE_SCALE, PIECE_Y } from "../../lib/board";

  type Props = {
    type: string; // chess.js letter: p,n,b,r,q,k
    color: string; // "w" | "b"
    square: string; // algebraic, e.g. "e4"
    captured?: boolean; // true once taken — plays the death animation
  };
  let { type, color, square, captured = false }: Props = $props();

  const COLOR: Record<string, string> = { w: "White", b: "Black" };
  const TYPE: Record<string, string> = {
    p: "Pawn",
    n: "Knight",
    b: "Bishop",
    r: "Rook",
    q: "Queen",
    k: "King",
  };
  const nodeName = $derived(`${COLOR[color]}_${TYPE[type]}`);
  const isKnight = $derived(type === "n");

  const gltf = useGltf(`${import.meta.env.BASE_URL}/chess_pieces.glb`);

  const SLIDE_MS = 1050; // travel time between squares
  const JUMP_H = 0.95; // knight hop height

  // X/Z board translation.
  const start = squareToWorld(square);
  const pos = new Tween(
    { x: start.x, z: start.z },
    { duration: SLIDE_MS, easing: cubicInOut },
  );

  // Knight hop progress (0→1), retriggered each move. Rests at 1 (arc = 0).
  const hop = new Tween(1, { duration: SLIDE_MS, easing: cubicInOut });

  // Capture progress (0→1): drives the lift + fade.
  const dying = new Tween(0, { duration: 900, easing: cubicOut });

  let prevSquare = square;
  $effect(() => {
    if (square !== prevSquare) {
      prevSquare = square;
      pos.set(squareToWorld(square));
      if (isKnight) {
        hop.set(0, { duration: 0 });
        hop.set(1);
      }
    }
  });

  $effect(() => {
    if (captured) dying.target = 1;
  });

  // Clone the GLB node so the same mesh can appear many times. Recenter it to
  // the origin (X/Z centered, base on y=0) and give it its own material clones
  // so one piece can fade without affecting the others.
  let mesh = $state<any>(undefined);
  $effect(() => {
    const loaded = $gltf;
    const node = loaded?.nodes?.[nodeName];
    if (node) {
      const cloned = node.clone(true);
      cloned.traverse((o: any) => {
        o.castShadow = true;
        o.receiveShadow = false;
        if (o.material) {
          o.material = o.material.clone()

          if (color === "b") {
            o.material.emissive = new THREE.Color("#222222"); 
            o.material.emissiveIntensity = 0.8;
            
            // Optional: Lower roughness makes it shinier and catch ambient light better
            o.material.roughness = 0.5; 
          }
        };
      });

      cloned.updateMatrixWorld(true);
      const box = new THREE.Box3().setFromObject(cloned);
      const center = box.getCenter(new THREE.Vector3());
      cloned.position.x -= center.x;
      cloned.position.z -= center.z;
      cloned.position.y -= box.min.y;

      mesh = cloned;
    }
  });

  // Apply the fade to the (now per-piece) materials as the capture plays out.
  $effect(() => {
    const k = dying.current;
    if (mesh && captured) {
      mesh.traverse((o: any) => {
        if (o.material) {
          o.material.transparent = true;
          o.material.opacity = 1 - k;
          o.material.depthWrite = false;
        }
      });
    }
  });

  const arc = $derived(isKnight ? Math.sin(hop.current * Math.PI) * JUMP_H : 0);
  const yPos = $derived(PIECE_Y + arc + dying.current * 2.6);
</script>

{#if mesh}
  <!-- The group carries the animated position; the recentered mesh sits on it. -->
  <T.Group position={[pos.current.x, yPos, pos.current.z]} scale={PIECE_SCALE}>
    <T is={mesh} />
  </T.Group>
{/if}
