# Desktop shell (Tauri 2)

Wraps the existing web build (`apps/web/dist`) in a native window — Windows/macOS/Linux,
and (with `tauri android`/`tauri ios`) mobile too. No app logic lives here; it's a thin shell.

This directory is a **build-ready scaffold**. The app icons are committed (generated from
`public/icon.svg`); CI compiles it. You don't need a Rust toolchain locally:

- **Release** — push a tag like `v0.1.0`. The [`Desktop release`](../../../.github/workflows/desktop.yml)
  workflow builds Windows (`.msi`/`.exe`), macOS (universal `.dmg`/`.app`), and Linux
  (`.deb`/`.AppImage`) installers and attaches them to a **draft** GitHub Release for review.
- **Smoke test** — run the workflow manually (Actions → Desktop release → Run workflow) to
  build all three platforms and download the bundles as workflow artifacts, with no tag/release.

Builds are **unsigned** for now; Apple notarization / Windows Authenticode is a follow-up that
needs certificate secrets. To build locally instead:

## Build (local)

```bash
# one-time: Rust toolchain (https://rustup.rs) + Tauri CLI + platform deps
#   Windows: WebView2 (preinstalled on Win11) + MSVC build tools
#   macOS:   Xcode CLT     Linux: webkit2gtk, librsvg, etc. (see tauri.app/start/prerequisites)
cd apps/web
npm install -D @tauri-apps/cli

# generate the app icons from the existing SVG (writes src-tauri/icons/*)
npx tauri icon public/icon.svg

# dev (hot-reload against the Vite dev server) — point the client at your API:
VITE_API_URL=http://localhost:8000 npx tauri dev

# production installers (.msi/.exe, .dmg, .AppImage/.deb) in src-tauri/target/release/bundle:
VITE_API_URL=https://api.your-host npx tauri build
```

## Two build flavors

The same shell ships in two configurations:

1. **Pro / cloud client** — the frontend points at a hosted API (`VITE_API_URL=https://api.your-host`),
   accounts + admin gates on. This is what `npm run build` + the commands above produce.
2. **Free single-project app (offline)** — the shell bundles and spawns a **local API sidecar**
   so the whole platform runs on the machine with no server, à la Bluebeam controlling one site.

### Free single-project build (local sidecar)

The backend already runs as one self-contained process — see
[`services/api/src/aec_api/desktop.py`](../../../services/api/src/aec_api/desktop.py):
FastAPI serves both the API **and** the web app from one origin, backed by SQLite + local file
storage, in single-operator local mode (`AEC_LOCAL_MODE=1`, no login). Run it directly with
`python -m aec_api.desktop` (opens `http://127.0.0.1:8765`). The web side is built for it with:

```bash
cd apps/web && npm run build:desktop   # vite --mode desktop -> SPA calls the same-origin root
```

To wrap this as the `.exe`, the remaining packaging steps (toolchain-dependent, done in CI or on
the target machine — not in a sandbox):

1. **Freeze the API sidecar** — PyInstaller the `aec_api.desktop` entry into a per-platform binary
   (bundling `ifcopenshell`'s native libs is the fiddly part; build on each target OS).
2. **Declare the sidecar** in `tauri.conf.json → bundle.externalBin` and **spawn it on startup**
   from `src/lib.rs` (tauri-plugin-shell `Command::new_sidecar(...).spawn()`), pointing the window
   at `http://127.0.0.1:<port>` once `/health` responds.
3. **CI** — extend [`desktop.yml`](../../../.github/workflows/desktop.yml) to build the sidecar
   per platform before `tauri-action`, and use `build:desktop` for the frontend.

Until those land, `desktop.yml` builds the **Pro/cloud client** flavor (thin shell → remote API).

## App-specific notes (validate on the target WebView)
- **Cross-origin isolation** — `tauri.conf.json → app.security.headers` sets COOP/COEP so
  web-ifc's multithreaded WASM (SharedArrayBuffer) works in the WebView, mirroring nginx/Vite.
  If a given OS WebView won't isolate, web-ifc falls back to single-threaded (only the rare
  in-browser IFC import is affected; the viewer streams server-converted `.frag`).
- **Backend** — for the Pro/cloud client the frontend is served from `tauri://`, so build with
  `VITE_API_URL` pointing at the hosted API (COEP `require-corp` means it must send CORP / proper
  CORS). For the free offline app, the bundled sidecar serves API + SPA same-origin, so no CORS
  and no `/api` prefix — see "Free single-project build" above.
- **WebGL** — the system WebView (WebView2/WKWebView/WebKitGTK) must handle the Three.js/
  Fragments renderer; test on each target. Electron (bundled Chromium) is the fallback if a
  WebView underperforms (see `docs/roadmap-platforms.md`).
- **Native dialogs** — Open/Save already use `@tauri-apps/plugin-dialog` + `-fs` when running
  inside Tauri (browser keeps the `<input>`/download path); the plugins are registered in
  `Cargo.toml`, `src/lib.rs`, and `capabilities/default.json`.
