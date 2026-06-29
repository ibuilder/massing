import { defineConfig, type Plugin } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// GitHub Pages build (VITE_PAGES=1): served from a subpath, no server headers — so it can't
// set COOP/COEP. Inject the coi-serviceworker instead of the Workbox PWA SW (which would
// conflict), so web-ifc/@thatopen multithreaded WASM (SharedArrayBuffer) still works.
// `--mode demo` flips the same flag locally so the viewer-only demo (bundled sample data) can be
// previewed without setting an env var.
const BASE = process.env.VITE_BASE || "/";
// app version, baked in at build time so the in-app update check can compare against the latest
// GitHub release (kept in sync with package.json / tauri.conf.json).
const APP_VERSION = process.env.npm_package_version || "0.0.0";

const coiInject: Plugin = {
  name: "coi-serviceworker-inject",
  transformIndexHtml: (html) =>
    html.replace("</head>", `  <script src="${BASE}coi-serviceworker.js"></script>\n</head>`),
};

export default defineConfig(({ mode }) => {
const PAGES = process.env.VITE_PAGES === "1" || mode === "demo";
return {
  base: BASE,
  // expose the Pages/demo flag to the client (no backend → skip API probes)
  define: {
    "import.meta.env.VITE_PAGES": JSON.stringify(PAGES),
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(APP_VERSION),
  },
  plugins: PAGES ? [coiInject] : [
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Massing + GC Portal",
        short_name: "Massing",
        description: "Web BIM viewer + general-contracting portal + development proforma.",
        theme_color: "#1e1f22",
        background_color: "#16171a",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
        ],
        shortcuts: [
          { name: "Field capture", short_name: "Capture", description: "Snap a photo → punch / observation / progress",
            url: "/?capture=1", icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml" }] },
        ],
      },
      workbox: {
        // precache only the lean app shell; the heavy viewer libs (three/@thatopen/worker),
        // WASM, and streamed .frag tiles are runtime-cached on first use so the precache and
        // the per-deploy background download stay small.
        globPatterns: ["**/*.{css,html,svg}", "assets/index-*.js", "assets/app-*.js"],
        navigateFallbackDenylist: [/^\/api\//],            // never serve the API from cache
        runtimeCaching: [
          { urlPattern: /\/assets\/(three|thatopen|worker)-.*\.(js|mjs)$/, handler: "CacheFirst",
            options: { cacheName: "viewer-libs", expiration: { maxEntries: 10 } } },
          { urlPattern: /\/wasm\/.*\.(wasm|js|mjs)$/, handler: "CacheFirst",
            options: { cacheName: "wasm", expiration: { maxEntries: 20 } } },
          { urlPattern: /\.frag$/, handler: "CacheFirst",
            options: { cacheName: "fragments", expiration: { maxEntries: 30, maxAgeSeconds: 2592000 } } },
        ],
      },
    }),
  ],
  // force a single copy of three — the app, @thatopen/* and camera-controls each
  // depend on it; without this they can resolve to different instances ("Multiple
  // instances of Three.js being imported"), bloating the bundle and breaking
  // instanceof checks across the boundary.
  resolve: {
    dedupe: ["three"],
  },
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
  build: {
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        // split heavy vendor libs into cacheable chunks (they change far less than app code)
        manualChunks: {
          three: ["three"],
          thatopen: ["@thatopen/components", "@thatopen/components-front", "@thatopen/fragments"],
        },
      },
    },
  },
};
});
