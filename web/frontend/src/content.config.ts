import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// The "Detailed Record" — six chapters, one per chess piece (Pawn → King).
// Each chapter is an MDX file in src/content/record/, free to embed Svelte
// widgets between the paragraphs.
const record = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/record" }),
  schema: z.object({
    order: z.number(), // 1..6, reading order (Pawn → King)
    piece: z.string(), // unicode glyph, e.g. "♟"
    pieceName: z.string(), // "Pawn", "Knight", ...
    title: z.string(), // chapter title
    theme: z.string(), // one-line thematic subtitle
    summary: z.string(), // short blurb for the index / cards
    draft: z.boolean().default(false), // true = stub, shown but flagged
  }),
});

export const collections = { record };
