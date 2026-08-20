import { brotliCompressSync, gzipSync } from "node:zlib";
import { createRequire } from "node:module";
import path from "node:path";
import { defineConfig, searchForWorkspaceRoot, type Plugin } from "vite";
import { VitePWA } from "vite-plugin-pwa";

import { vendorAlias } from "./vendorAlias";

// Emit .br + .gz siblings for every text asset so a self-hosted static server (nginx/caddy) or the
// desktop app can serve pre-compressed bytes — no runtime compression, no extra dependency (Node's
// zlib). Brotli is ~15-20% smaller than gzip for JS/CSS; both are written so a server can pick either.
const precompress: Plugin = {
  name: "precompress-assets",
  apply: "build",
  async writeBundle(opts, bundle) {
    const { writeFileSync } = await import("node:fs");
    const { join } = await import("node:path");
    const dir = opts.dir || "dist";
    for (const [name, out] of Object.entries(bundle)) {
      if (!/\.(js|mjs|css|html|svg|json)$/.test(name)) continue;
      const src = (out as { code?: string; source?: string | Uint8Array }).code
        ?? (out as { source?: string | Uint8Array }).source;
      if (src == null) continue;
      const buf = Buffer.from(src as string | Uint8Array);
      if (buf.length < 1024) continue;                 // not worth compressing tiny files
      writeFileSync(join(dir, `${name}.br`), brotliCompressSync(buf));
      writeFileSync(join(dir, `${name}.gz`), gzipSync(buf, { level: 9 }));
    }
  },
};

// GitHub Pages build (VITE_PAGES=1): served from a subpath, no server headers — so it can't
// set COOP/COEP. Inject the coi-serviceworker instead of the Workbox PWA SW (which would
// conflict), so web-ifc/@thatopen multithreaded WASM (SharedArrayBuffer) still works.
// `--mode demo` flips the same flag locally so the viewer-only demo (bundled sample data) can be
// previewed without setting an env var.
const BASE = process.env.VITE_BASE || "/";
// app version, baked in at build time so the in-app update check can compare against the latest
// GitHub release (kept in sync with package.json / tauri.conf.json).
const APP_VERSION = process.env.npm_package_version || "0.0.0";

// BUILD-WORKTREE-CHUNKS: a git worktree has no node_modules of its own. Vite's default
// fs-allow is searchForWorkspaceRoot(cwd), which is the worktree, so the main clone's
// hoisted three/@thatopen sit outside the sandbox. Same allow list vitest.config.ts already
// uses for pdfjs. createRequire walks to wherever the package actually resolved.
const hoistedNodeModules = path.join(
  path.dirname(createRequire(import.meta.url).resolve("three/package.json")),
  "..",
);

const coiInject: Plugin = {
  name: "coi-serviceworker-inject",
  transformIndexHtml: (html) =>
    html.replace("</head>", `  <script src="${BASE}coi-serviceworker.js"></script>\n</head>`),
};

export default defineConfig(({ mode }) => {
const PAGES = process.env.VITE_PAGES === "1" || mode === "demo";
// Pre-compress only for web-served builds. Desktop/mobile load from the native asset protocol (no
// br/gz negotiation), so the siblings would only bloat the installer.
const WEB_SERVED = !["desktop", "mobile"].includes(mode);
const compressPlugins = WEB_SERVED ? [precompress] : [];
return {
  base: BASE,
  // expose the Pages/demo flag to the client (no backend → skip API probes)
  define: {
    "import.meta.env.VITE_PAGES": JSON.stringify(PAGES),
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(APP_VERSION),
  },
  plugins: PAGES ? [coiInject, ...compressPlugins] : [
    ...compressPlugins,
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
    // The vendored massingifc kernel imports its siblings by package name; `vendorAlias` is the one
    // definition of what those names mean (see vendorAlias.ts).
    alias: { ...vendorAlias },
  },
  // web-ifc and the fragments worker ship their own WASM/worker assets; don't let
  // esbuild's dep pre-bundler rewrite them. `three` is excluded too: the @thatopen/*
  // packages above import it raw from node_modules, so pre-bundling the app's own `three`
  // separately would load a SECOND copy in dev ("Multiple instances of Three.js") — excluding
  // it (with the resolve.dedupe above) makes every importer share the one node_modules/three.
  optimizeDeps: {
    exclude: ["web-ifc", "@thatopen/fragments", "@thatopen/components", "three"],
  },
  server: {
    port: 5173,
    fs: { allow: [searchForWorkspaceRoot(process.cwd()), hoistedNodeModules] },
    // SharedArrayBuffer (used by web-ifc multithreaded WASM) needs cross-origin isolation.
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
    // Vite 8 renamed build.rollupOptions to build.rolldownOptions: the bundler underneath is
    // Rolldown now, with Oxc doing the transform. Vite 8 requires Node >= 22.12; we run 24.
    rolldownOptions: {
      output: {
        // Split heavy vendor libs into cacheable chunks — they change far less often than app code,
        // and three + the That Open stack are the bulk of the bundle.
        //
        // `advancedChunks` — Rolldown's NATIVE grouping, not the deprecated `manualChunks`.
        //
        // Vite 8 removed the object form of `manualChunks` and deprecated the function form. The
        // deprecated function still *runs*, and that is the trap: the build succeeds, still emits a
        // chunk named "three", and that chunk turns out to be a re-export shim while three.js itself
        // is folded into the thatopen chunk. Measured, not assumed — `WebGLRenderer` appeared 8× in
        // `thatopen-*.js` and 0× in `three-*.js`.
        //
        // A vendor split that silently stops splitting is the worst kind of build regression: the
        // bundle still works, so nothing fails, but three.js is no longer separately cacheable and
        // every That Open patch re-downloads it. Verify by grepping the OUTPUT, never by reading the
        // config and believing it.
        advancedChunks: {
          groups: [
            { name: "three", test: /[\\/]node_modules[\\/]three[\\/]/ },
            { name: "thatopen", test: /[\\/]@thatopen[\\/](components|components-front|fragments)[\\/]/ },
          ],
        },
      },
    },
  },
};
});
