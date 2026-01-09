import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig({
  server: {
    cors: {
      origin: "http://localhost:8007",
    },
  },
  plugins: [svelte()],
  build: {
    manifest: "manifest.json",
    outDir: "../datasette_ca460",
    assetsDir: "static/gen",
    //emptyOutDir: true,
    
    rollupOptions: {
      input: {
        index: "src/index_view.ts",
        sync: "src/sync_view.ts",
      },
    },
  
  },
});
