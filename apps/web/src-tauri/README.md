# Desktop shell (Tauri 2)

Wraps the existing web build (`apps/web/dist`) in a native window — Windows/macOS/Linux,
and (with `tauri android`/`tauri ios`) mobile too. No app logic lives here; it's a thin shell.

This directory is a **build-ready scaffold**: it was authored without a Rust toolchain, so it
has not been compiled here. Build it on a machine with Rust + the Tauri CLI.

## Build

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

## App-specific notes (validate on the target WebView)
- **Cross-origin isolation** — `tauri.conf.json → app.security.headers` sets COOP/COEP so
  web-ifc's multithreaded WASM (SharedArrayBuffer) works in the WebView, mirroring nginx/Vite.
  If a given OS WebView won't isolate, web-ifc falls back to single-threaded (only the rare
  in-browser IFC import is affected; the viewer streams server-converted `.frag`).
- **Backend** — the bundled frontend is served from `tauri://` / asset protocol, so the
  production `/api` same-origin proxy is *not* present. Build with `VITE_API_URL` pointing at
  the hosted API (or add a Tauri sidecar that runs the API locally for fully-offline desktop).
  Note: COEP `require-corp` means the API must send CORP/appropriate CORS for cross-origin calls.
- **WebGL** — the system WebView (WebView2/WKWebView/WebKitGTK) must handle the Three.js/
  Fragments renderer; test on each target. Electron (bundled Chromium) is the fallback if a
  WebView underperforms (see `docs/roadmap-platforms.md`).
- **Native dialogs** — Open/Save already use `@tauri-apps/plugin-dialog` + `-fs` when running
  inside Tauri (browser keeps the `<input>`/download path); the plugins are registered in
  `Cargo.toml`, `src/lib.rs`, and `capabilities/default.json`.
