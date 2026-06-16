<script lang="ts">
  // Cinematic 3D chess background. Auto-plays Byrne vs. Fischer, 1956
  // ("The Game of the Century"), one move every ~1.5s, then loops.
  //
  // The camera holds a single fixed first-person vantage behind White's back
  // rank — no panning, no piece-chasing. (An earlier version retargeted
  // lookAt() at each move and the look vector degenerated whenever the focal
  // point crossed near/behind the eye on the back rank, making the view flip,
  // freeze, or snap. A static camera can't degenerate.)
  //
  // Completely non-interactive (pointer-events: none) and darkened by an
  // overlay so landing-page text stays legible on top.
  import { Canvas, T } from "@threlte/core";
  import { Tween } from "svelte/motion";
  import { cubicInOut } from "svelte/easing";
  import { Chess } from "chess.js";
  import Board from "./Board.svelte";
  import Piece from "./Piece.svelte";
  import { squareToWorld } from "../../lib/board";

  const PGN = `[Event "Third Rosenwald Trophy"]
[Site "New York, NY USA"]
[Date "1956.10.17"]
[Round "8"]
[White "Donald Byrne"]
[Black "Robert James Fischer"]
[Result "0-1"]
[ECO "D92"]
[PlyCount "82"]

1. Nf3 Nf6 2. c4 g6 3. Nc3 Bg7 4. d4 O-O 5. Bf4 d5 6. Qb3 dxc4 7. Qxc4 c6 8. e4 Nbd7 9. Rd1 Nb6 10. Qc5 Bg4 11. Bg5 Na4 12. Qa3 Nxc3 13. bxc3 Nxe4 14. Bxe7 Qb6 15. Bc4 Nxc3 16. Bc5 Rfe8+ 17. Kf1 Be6 18. Bxb6 Bxc4+ 19. Kg1 Ne2+ 20. Kf1 Nxd4+ 21. Kg1 Ne2+ 22. Kf1 Nc3+ 23. Kg1 axb6 24. Qb4 Ra4 25. Qxb6 Nxd1 26. h3 Rxa2 27. Kh2 Nxf2 28. Re1 Rxe1 29. Qd8+ Bf8 30. Nxe1 Bd5 31. Nf3 Ne4 32. Qb8 b5 33. h4 h5 34. Ne5 Kg7 35. Kg1 Bc5+ 36. Kf1 Ng3+ 37. Ke1 Bb4+ 38. Kd1 Bb3+ 39. Kc1 Ne2+ 40. Kb1 Nc3+ 41. Kc1 Rc2# 0-1`;

  const MOVE_MS = 1500; // cadence between moves (the piece slide is 1050ms)
  const START_DELAY = 2700; // let the eyes open before the first move
  const FADE_MS = 900; // capture lift + fade duration before removal
  const LOOP_PAUSE_MS = 4500; // pause on the final position before restarting

  // Parse the game once into a list of verbose moves.
  const parser = new Chess();
  parser.loadPgn(PGN);
  const history = parser.history({ verbose: true });

  // A pristine start position we re-read whenever the loop restarts.
  const START = new Chess();

  type Tracked = {
    id: number;
    color: string;
    type: string;
    square: string;
    alive: boolean; // still rendered (true through the capture animation)
    captured: boolean; // taken — playing the lift+fade, no longer occupies
  };

  function initialPieces(): Tracked[] {
    const out: Tracked[] = [];
    let id = 0;
    for (const row of START.board()) {
      for (const cell of row) {
        if (cell) {
          out.push({
            id: id++,
            color: cell.color,
            type: cell.type,
            square: cell.square,
            alive: true,
            captured: false,
          });
        }
      }
    }
    return out;
  }

  let pieces = $state<Tracked[]>(initialPieces());
  let generation = $state(0); // bump on restart to remount pieces cleanly
  let ply = 0;

  // The white king is the camera (first-person), so its own mesh is not drawn.
  const visible = $derived(
    pieces.filter(
      (p) => p.alive && !(p.color === "w" && p.type === "k"),
    ),
  );

  // A captured piece no longer occupies its square (so the captor can land there).
  const pieceAt = (sq: string) =>
    pieces.find((p) => p.alive && !p.captured && p.square === sq);

  // Begin the capture animation, then remove the piece once it has faded.
  function capture(p: Tracked | undefined) {
    if (!p) return;
    p.captured = true;
    setTimeout(() => {
      p.alive = false;
    }, FADE_MS + 150);
  }

  // Apply one verbose move to our tracked-piece model, handling captures,
  // en passant, castling (move the rook too), and promotion.
  function applyMove(m: (typeof history)[number]) {
    if (m.flags.includes("e")) {
      // en passant: captured pawn is behind the destination square
      capture(pieceAt(m.to[0] + m.from[1]));
    } else if (m.captured) {
      capture(pieceAt(m.to));
    }

    const mover = pieceAt(m.from);
    if (mover) {
      mover.square = m.to;
      if (m.promotion) mover.type = m.promotion;
    }

    if (m.flags.includes("k") || m.flags.includes("q")) {
      const rank = m.color === "w" ? "1" : "8";
      const kingside = m.flags.includes("k");
      const rook = pieceAt((kingside ? "h" : "a") + rank);
      if (rook) rook.square = (kingside ? "f" : "d") + rank;
    }
  }

  function restart() {
    ply = 0;
    pieces = initialPieces();
    generation += 1;
  }

  // Drive the game with a self-rescheduling timer: apply one move every
  // MOVE_MS, and when the game ends, pause then restart. The camera is fully
  // independent of this (see below) — moves just play out in front of it.
  $effect(() => {
    let timer: ReturnType<typeof setTimeout>;

    function tick() {
      if (ply >= history.length) {
        timer = setTimeout(() => {
          restart();
          timer = setTimeout(tick, START_DELAY);
        }, LOOP_PAUSE_MS);
        return;
      }
      applyMove(history[ply]);
      ply += 1;
      timer = setTimeout(tick, MOVE_MS);
    }

    timer = setTimeout(tick, START_DELAY);
    return () => clearTimeout(timer);
  });

  // ---- Camera ---------------------------------------------------------------
  // The eye sits behind White's back rank (where the king would stand — its mesh
  // is hidden, so we never look at ourselves), at a fixed height and pitch tilted
  // down so the board fills the lower frame. The pitch/orientation stays fixed;
  // only the ground position moves. (Moving the position is safe — the old
  // flip/freeze came from retargeting lookAt(), not from moving the eye.)
  const HOME = { x: 0.5, z: 4.0 }; // home vantage behind e1
  const EYE_HEIGHT = 1.4;
  const BASE_PITCH = -0.18; // radians; tilt down toward the board

  // The eye keeps a fixed offset *behind* the king's square — so at e1 it equals
  // HOME — and the camera glides to preserve that vantage as the king moves.
  const KING_E1 = squareToWorld("e1");
  const KING_DX = HOME.x - KING_E1.x;
  const KING_DZ = HOME.z - KING_E1.z;
  const eyeForKing = (sq: string) => {
    const s = squareToWorld(sq);
    return { x: s.x + KING_DX, z: s.z + KING_DZ };
  };

  // Eased eye position, fed to the camera's `position` prop. Calling eye.set(...)
  // glides the camera there; the prop updates reactively from eye.current.
  const eye = new Tween(eyeForKing("e1"), {
    duration: 1100,
    easing: cubicInOut,
  });

  // Follow the white king (the camera *is* the king — its mesh is hidden). The
  // king's square lives in the tracked-piece model; whenever it changes — a king
  // move, castling, or the reset to e1 on restart — glide the eye to match.
  const whiteKingSquare = $derived(
    pieces.find((p) => p.color === "w" && p.type === "k")?.square ?? "e1",
  );
  $effect(() => {
    eye.set(eyeForKing(whiteKingSquare));
  });
</script>

<div class="bg-scene" aria-hidden="true">
  <Canvas dpr={1.5}>
    <T.Color attach="background" args={["#0a0f18"]} />
    <T.FogExp2 attach="fog" args={["#0a0f18", 0.032]} />

    <T.PerspectiveCamera
      makeDefault
      fov={58}
      near={0.05}
      far={60}
      position={[eye.current.x, EYE_HEIGHT, eye.current.z]}
      rotation={[BASE_PITCH, 0, 0, "YXZ"]}
    />

    <!-- Lighting: a hemisphere + ambient base so the dark pieces stay readable,
         a shadow-casting key light, a front fill that catches the black pieces,
         and a cool rim light for the high-tech mood. -->
    <T.HemisphereLight
      args={["#aebfe0", "#0c1018"]}
      intensity={0.75}
    />
    <T.AmbientLight intensity={0.45} />
    <T.DirectionalLight
      position={[6, 13, 5]}
      intensity={1.6}
      castShadow
      shadow.mapSize.width={1024}
      shadow.mapSize.height={1024}
      shadow.bias={-0.0005}
      shadow.camera.near={1}
      shadow.camera.far={40}
      shadow.camera.left={-8}
      shadow.camera.right={8}
      shadow.camera.top={8}
      shadow.camera.bottom={-8}
    />
    <!-- Front fill from the camera side — lights the near faces of dark pieces. -->
    <T.DirectionalLight position={[-3, 5, 9]} intensity={0.8} color="#bcd0ff" />
    <T.SpotLight
      position={[-9, 7, -7]}
      intensity={140}
      angle={0.6}
      penumbra={0.7}
      color="#6f9bff"
    />

    <Board />

    {#each visible as p (`${generation}:${p.id}`)}
      <Piece
        type={p.type}
        color={p.color}
        square={p.square}
        captured={p.captured}
      />
    {/each}
  </Canvas>

  <div class="bg-overlay"></div>

  <!-- Wake-up "eyelids": closed at load, then open with a blink as the king
       comes to. Pairs with the camera's head-raise. -->
  <div class="eyelid eyelid-top"></div>
  <div class="eyelid eyelid-bottom"></div>
</div>

<style>
  .bg-scene {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    background-color: #0a0f18;
  }

  /* Darkening / vignette: keep the top dark for hero text, lighter lower down
     so the board and the dark pieces stay visible. */
  .bg-overlay {
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background:
      linear-gradient(
        to bottom,
        rgba(8, 11, 18, 0.72) 0%,
        rgba(8, 11, 18, 0.28) 42%,
        rgba(8, 11, 18, 0.5) 100%
      ),
      radial-gradient(
        120% 80% at 50% 0%,
        rgba(8, 11, 18, 0.08),
        rgba(8, 11, 18, 0.5)
      );
  }

  .eyelid {
    position: absolute;
    left: 0;
    right: 0;
    height: 0;
    z-index: 2;
    background: #02040a;
    pointer-events: none;
  }
  .eyelid-top {
    top: 0;
    animation: lid-open 2.6s ease-in-out forwards;
  }
  .eyelid-bottom {
    bottom: 0;
    animation: lid-open 2.6s ease-in-out forwards;
  }

  /* Closed → cracks open → quick blink → fully open. */
  @keyframes lid-open {
    0% {
      height: 52%;
    }
    32% {
      height: 9%;
    }
    46% {
      height: 28%;
    }
    100% {
      height: 0%;
    }
  }

  /* Respect reduced-motion: skip the eyelid theatrics. */
  @media (prefers-reduced-motion: reduce) {
    .eyelid {
      animation: none;
      height: 0;
    }
  }

  /* Belt-and-suspenders: the canvas itself never intercepts pointer events. */
  .bg-scene :global(canvas) {
    pointer-events: none !important;
  }
</style>
