// Shared geometry for the 3D chess background.
//
// The board is centered on the world origin. Each square is SQUARE_SIZE units,
// so the 8x8 grid spans [-4, 4] on both X and Z.

export const SQUARE_SIZE = 1;

// The GLB nodes are normalized to scale 1.0; tune this if the pieces render
// too large or too small relative to a single square.
export const PIECE_SCALE = 1;

// Vertical offset for pieces (lift them slightly if they sink into the board).
export const PIECE_Y = 0;

/**
 * Map an algebraic square ("a1".."h8") to 3D world coordinates.
 * File a→h runs along +X; rank 1 sits toward +Z (nearer the camera), rank 8 at -Z.
 */
export function squareToWorld(square: string): { x: number; z: number } {
  const file = square.charCodeAt(0) - 97; // 'a' -> 0 ... 'h' -> 7
  const rank = Number(square[1]) - 1; //     '1' -> 0 ... '8' -> 7
  return {
    x: (file - 3.5) * SQUARE_SIZE,
    z: (3.5 - rank) * SQUARE_SIZE,
  };
}
