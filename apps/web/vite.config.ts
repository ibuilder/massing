import { defineConfig } from "vite";

export default defineConfig({
  // web-ifc and the fragments worker ship their own WASM/worker assets; don't let
  // esbuild's dep pre-bundler rewrite them.
  optimizeDeps: {
    exclude: ["web-ifc", "@thatopen/fragments", "@thatopen/components"],
  },
  server: {
    port: 5173,
    // SharedArrayBuffer (used by web-ifc multithreaded WASM) needs cross-origin isolation.
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
});
