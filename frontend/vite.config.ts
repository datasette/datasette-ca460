import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// https://vite.dev/config/
export default defineConfig({
  server: {
    port: 5177,
    strictPort: true,
    cors: true,
    hmr: {
      host: "localhost",
      port: 5177,
      protocol: "ws",
    },
  },
  plugins: [svelte()],
  build: {
    manifest: "manifest.json",
    outDir: "../datasette_ca460",
    assetsDir: "static/gen",
    rollupOptions: {
      input: {
        index: "src/index_view.ts",
        document: "src/document_view.ts",
        page_detail: "src/page_detail_view.ts",
      },
    },
  },
});
