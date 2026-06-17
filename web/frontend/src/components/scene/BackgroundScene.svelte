<script lang="ts">
  // Cinematic 3D chess background. Auto-plays Byrne vs. Fischer, 1956
  // ("The Game of the Century"), one move every ~1.5s, then loops.
  //
  // Each cycle: a beat of darkness (eyes shut) → the eyes blink open → the game
  // plays out → at game over the king topples forward onto the board → the eyes
  // close. Then back to darkness and replay.
  //
  // The camera holds a first-person vantage behind White's back rank. It never
  // retargets lookAt() (which used to degenerate when the focal point crossed
  // behind the eye); instead it only ever glides its position and turns its yaw
  // toward the fixed board center, so the look vector can never flip.
  //
  // Completely non-interactive (pointer-events: none) and darkened by an
  // overlay so landing-page text stays legible on top.
  import { Canvas, T } from "@threlte/core";
  import { Tween } from "svelte/motion";
  import { cubicInOut } from "svelte/easing";
  import { Chess } from "chess.js";
  import { onMount } from "svelte";
  import Board from "./Board.svelte";
  import Piece from "./Piece.svelte";
  import SquareHighlight from "./SquareHighlight.svelte";
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
  const DARK_MS = 1000; // beat of darkness before the eyes open (each cycle)
  const WAKE_MS = 2400; // eyelids open before the first move (matches lid-open)
  const FADE_MS = 900; // capture lift + fade duration before removal
  const END_PAUSE_MS = 1300; // hold the final (mate) position before toppling
  const FALL_MS = 1400; // king topples onto its side
  const CLOSE_MS = 1800; // eyelids slide shut over the fallen view

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

  // The move currently on the board — its from/to squares get the red glow.
  let lastMove = $state<{ from: string; to: string } | null>(null);

  // Animation phase. The eyes start shut and the icon glows until clicked.
  //   idle    → eyes closed, icon glowing, awaiting a click
  //   waking  → eyelids open with a blink
  //   playing → moves play out
  //   falling → game over; the king topples sideways
  //   closing → eyelids slide shut (vertical now, over the fallen view)
  type Phase = "idle" | "waking" | "playing" | "falling" | "closing";
  let phase = $state<Phase>("idle");

  // The white king is the camera (first-person), so its own mesh is not drawn.
  const visible = $derived(
    pieces.filter((p) => p.alive && !(p.color === "w" && p.type === "k")),
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

  function resetGame() {
    ply = 0;
    pieces = initialPieces();
    lastMove = null;
    generation += 1;
  }

  // ---- Sequencing -----------------------------------------------------------
  // A single self-rescheduling timer drives moves while playing; the same
  // handle carries the wake / topple / close beats so they can be cancelled.
  let timer: ReturnType<typeof setTimeout> | undefined;
  const clearTimer = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
  };

  function tick() {
    if (ply >= history.length) {
      endSequence();
      return;
    }
    const m = history[ply];
    lastMove = { from: m.from, to: m.to };
    applyMove(m);
    ply += 1;
    timer = setTimeout(tick, MOVE_MS);
  }

  // Open the eyes, then start playing. Called after each dark beat.
  function wake() {
    phase = "waking";
    clearTimer();
    timer = setTimeout(() => {
      phase = "playing";
      tick();
    }, WAKE_MS);
  }

  // Game over: hold the mate, topple the king forward, close the eyes, then
  // reset under cover of darkness, hold a dark beat, and replay.
  function endSequence() {
    clearTimer();
    lastMove = null;
    timer = setTimeout(() => {
      phase = "falling";
      fall.set(1); // the king topples forward onto the board
      timer = setTimeout(() => {
        phase = "closing"; // eyelids slide shut over the toppled, downcast view
        timer = setTimeout(() => {
          // Fully dark now — snap everything back where no one can see it.
          resetGame();
          fall.set(0, { duration: 0 });
          phase = "idle"; // a beat of darkness before the next cycle
          timer = setTimeout(wake, DARK_MS);
        }, CLOSE_MS);
      }, FALL_MS);
    }, END_PAUSE_MS);
  }

  // Start dark on load, then run the auto-replaying loop.
  onMount(() => {
    phase = "idle";
    timer = setTimeout(wake, DARK_MS);
    return () => clearTimer();
  });

  // ---- Camera ---------------------------------------------------------------
  // The eye sits behind White's back rank (where the king would stand — its mesh
  // is hidden, so we never look at ourselves), at a fixed height and pitch tilted
  // down so the board fills the lower frame. Position and yaw glide; pitch/roll
  // only move during the end-of-game topple.
  const HOME = { x: 0.5, z: 4.6 }; // home vantage behind e1
  const EYE_HEIGHT = 1.4;
  const BASE_PITCH = -0.18; // radians; tilt down toward the board

  // Topple: the king pivots about its base, so the eye — a head-height above
  // that base — swings forward and *down* in an arc, the way a real piece tips
  // over rather than dropping straight down. One 0→1 progress drives the arc.
  const FALL_ANGLE = 1.35; // radians it rotates onto the board (~77°)
  // Gravity-style acceleration into the board, then a small rebound on landing.
  const toppleEase = (t: number) => {
    if (t < 0.82) {
      const u = t / 0.82;
      return u * u;
    }
    const u = (t - 0.82) / 0.18;
    return 1 - Math.sin(u * Math.PI) * 0.07;
  };

  // The eye keeps a fixed offset *behind* the king's square — so at e1 it equals
  // HOME — and the camera glides to preserve that vantage as the king moves.
  const KING_E1 = squareToWorld("e1");
  const KING_DX = HOME.x - KING_E1.x;
  const KING_DZ = HOME.z - KING_E1.z;
  const eyeForKing = (sq: string) => {
    const s = squareToWorld(sq);
    return { x: s.x + KING_DX, z: s.z + KING_DZ };
  };

  // Yaw that points the eye at the board center so the whole field stays in
  // frame as the king wanders to the wings (f, g, h … or c, b). On the central
  // files (d/e) the king just looks straight ahead — turning there reads as a
  // needless wobble. Looking at a fixed point that's always ahead can't degenerate.
  const yawForKing = (sq: string) => {
    const file = sq[0];
    if (file === "d" || file === "e") return 0;
    const e = eyeForKing(sq);
    return Math.atan2(e.x, e.z); // toward center (0,0); -Z forward, +Y up
  };

  const eye = new Tween(eyeForKing("e1"), {
    duration: 1100,
    easing: cubicInOut,
  });
  const yaw = new Tween(yawForKing("e1"), {
    duration: 1100,
    easing: cubicInOut,
  });
  const fall = new Tween(0, { duration: FALL_MS, easing: toppleEase });

  // Live camera pose: the standing vantage composed with the topple arc. The
  // eye rotates about its base, so as it falls it both moves forward/down and
  // pitches down to keep looking where the head is now pointed.
  const camPose = $derived.by(() => {
    const a = fall.current * FALL_ANGLE;
    return {
      x: eye.current.x,
      y: EYE_HEIGHT * Math.cos(a),
      z: eye.current.z - EYE_HEIGHT * Math.sin(a),
      pitch: BASE_PITCH - a,
      yaw: yaw.current,
    };
  });

  // Follow the white king (the camera *is* the king). Whenever its square
  // changes — a king move or the reset to e1 — glide the eye and turn toward
  // center to match.
  const whiteKingSquare = $derived(
    pieces.find((p) => p.color === "w" && p.type === "k")?.square ?? "e1",
  );
  $effect(() => {
    eye.set(eyeForKing(whiteKingSquare));
    yaw.set(yawForKing(whiteKingSquare));
  });
</script>

<div class="bg-scene" aria-hidden="true" data-phase={phase}>
  <Canvas dpr={1.5}>
    <T.Color attach="background" args={["#0a0f18"]} />
    <T.FogExp2 attach="fog" args={["#0a0f18", 0.032]} />

    <T.PerspectiveCamera
      makeDefault
      fov={58}
      near={0.05}
      far={60}
      position={[camPose.x, camPose.y, camPose.z]}
      rotation={[camPose.pitch, camPose.yaw, 0, "YXZ"]}
    />

    <!-- Lighting: a hemisphere + ambient base so the dark pieces stay readable,
         a shadow-casting key light, a front fill that catches the black pieces,
         and a cool rim light for the high-tech mood. -->
    <T.HemisphereLight args={["#aebfe0", "#0c1018"]} intensity={0.75} />
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

    <!-- Red glow on the from/to squares of the move in play. -->
    {#if phase === "playing" && lastMove}
      <SquareHighlight square={lastMove.from} />
      <SquareHighlight square={lastMove.to} />
    {/if}

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

  <!-- Eyelids: top/bottom lids that blink open on wake and slide shut at the
       end. They stay horizontal throughout — at game over the head is tilted
       down (not on its side), so a normal horizontal close is what reads right. -->
  <div class="eyelids">
    <div class="eyelid eyelid-top"></div>
    <div class="eyelid eyelid-bottom"></div>
  </div>
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

  .eyelids {
    position: absolute;
    inset: 0;
    z-index: 2;
    pointer-events: none;
  }

  .eyelid {
    position: absolute;
    left: 0;
    right: 0;
    height: 0;
    background: #02040a;
    pointer-events: none;
  }
  .eyelid-top {
    top: 0;
  }
  .eyelid-bottom {
    bottom: 0;
  }

  /* idle: shut, no transition (also the resting state on first load). */
  .bg-scene[data-phase="idle"] .eyelid {
    height: 50%;
    transition: none;
  }
  /* waking: open with a blink. */
  .bg-scene[data-phase="waking"] .eyelid {
    height: 0;
    animation: lid-open 2.4s ease-in-out;
  }
  /* awake: open. */
  .bg-scene[data-phase="playing"] .eyelid,
  .bg-scene[data-phase="falling"] .eyelid {
    height: 0;
  }
  /* closing: slide shut over the fallen view. */
  .bg-scene[data-phase="closing"] .eyelid {
    height: 50%;
    transition: height 1.3s ease-in-out;
  }

  /* Closed → cracks open → quick blink → fully open. */
  @keyframes lid-open {
    0% {
      height: 50%;
    }
    32% {
      height: 9%;
    }
    46% {
      height: 26%;
    }
    100% {
      height: 0%;
    }
  }

  /* Respect reduced-motion: skip the eyelid theatrics. */
  @media (prefers-reduced-motion: reduce) {
    .eyelid {
      animation: none;
    }
    .eyelids {
      transition: none;
    }
  }

  /* Belt-and-suspenders: the canvas itself never intercepts pointer events. */
  .bg-scene :global(canvas) {
    pointer-events: none !important;
  }
</style>
