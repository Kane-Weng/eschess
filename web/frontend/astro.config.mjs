// @ts-check
import { defineConfig } from "astro/config";
import svelte from "@astrojs/svelte";
import mdx from "@astrojs/mdx";
import tailwindcss from "@tailwindcss/vite";

// https://astro.build/config
export default defineConfig({
  site: "https://kane-weng.github.io",
  base: "/eschess",

  integrations: [svelte(), mdx()],
  vite: {
    plugins: [tailwindcss()],
  },
});
