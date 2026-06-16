# Roadmap — Multi-platform packaging (web, Windows, macOS, iOS, Android)

Goal: ship the viewer + data platform beyond the browser to desktop and mobile, **without
forking the codebase**. The web app (`apps/web`, Vite + TS + Three.js + Fragments) stays the
single UI source; native targets wrap it.

## Current state
- **Web — done.** Vite/TS SPA served by nginx in the Docker stack; runs fully offline with
  local WASM (web-ifc) and self-hosted Fragments tiles (per CLAUDE.md). This is the canonical
  build everything else wraps.

## Strategy: one web core, thin native shells
| Target | Wrapper | Notes |
|--------|---------|-------|
| Web (PWA) | Vite build + service worker | Manifest + offline cache → installable on every platform; the SW also injects COOP/COEP so cross-origin isolation survives offline and static hosting. **Do this first.** |
| Windows / macOS / Linux | **Electron** (WebGL-safe) or **Tauri 2** (tiny) | Electron bundles Chromium → consistent WebGL/WASM/SharedArrayBuffer; ~120MB. Tauri 2 is ~10MB (Rust + system WebView) but the WebGL-heavy viewer + threaded WASM must be validated on each OS WebView first. |
| iOS / Android | **Capacitor** (or **Tauri 2 mobile**) | Wraps the same build in a native WebView; plugins for filesystem, share, camera (site photos → BCF). Tauri 2 now also targets mobile, so it *could* be one wrapper for desktop+mobile — pending the WebView validation above. |

Why not React Native / Flutter: would require rewriting the Three.js/Fragments viewer. The
WebView-wrapper path preserves the entire existing renderer and tool set.

### Research updates (June 2026)
- **Tauri 2 ships mobile (iOS/Android)** — one wrapper could cover desktop *and* mobile,
  shrinking the matrix. But its system-WebView model means the WebGL renderer + multithreaded
  WASM (SharedArrayBuffer) need per-OS validation (WKWebView on iOS is the historical risk).
  Electron's bundled Chromium remains the safe desktop fallback for the heavy viewer.
  Sources: Tauri/Electron 2026 comparisons (pkgpulse, tech-insider, gethopp).
- **Service worker = cross-origin isolation + offline in one** — a SW can add the COOP/COEP
  headers on navigations (the "coi-serviceworker" pattern), so SharedArrayBuffer works even on
  static hosts (e.g. GitHub Pages) and while offline. Combine it with Workbox precache so the
  PWA is genuinely offline-capable *and* isolated. Source: web.dev COOP/COEP; tomayac (2025).
- **web-ifc has a single-threaded fallback** (no SharedArrayBuffer) — the escape hatch if a
  given WebView can't be cross-origin isolated; only the in-browser IFC→Fragments import needs
  threads, and that path is rare (production streams server-converted .frag).
- The **lazy-loaded 3D viewer** (shipped) already helps mobile/low-bandwidth: the ~6MB engine
  loads only when the Model workspace opens.

## Phasing
1. **PWA hardening** *(in progress)* — web app manifest + icons (installable), a Workbox
   service worker that precaches the app shell + WASM/worker and runtime-caches .frag tiles,
   and the coi-serviceworker COOP/COEP injection so cross-origin isolation holds offline /
   on static hosts. Verify install prompt + offline load. Unlocks "install" on every platform.
2. **Tauri desktop** — wrap the build; wire native Open/Save dialogs to the existing
   Open ▾ / Save ▾ menus (replace the hidden `<input type=file>` with Tauri's `dialog` +
   `fs` APIs); bundle the local converter cache. Sign + notarize (Win Authenticode, macOS
   notarization).
3. **Capacitor mobile** — same build; add filesystem + share plugins; tune the responsive
   layout (already has an 820px breakpoint) for touch; on-site photo capture into BCF topics.
4. **Backend** — the FastAPI + Postgres + MinIO stack stays server-side (cloud or on-prem);
   native apps talk to it over HTTPS, or run a bundled local API for fully-offline desktop.

## Performance / offline notes
- Mega-model streaming (range-served .frag) must work over the WebView fetch stack — verify
  range requests on iOS WKWebView (historically finicky).
- WASM (web-ifc) must load from the bundle, not a CDN, to keep the offline guarantee.
- Keep geometry (.frag stream) and metadata (API) separate on every platform.

## "Claude remote" / background agents for native work
Desktop/mobile packaging is long-running, environment-specific (Xcode/macOS for iOS, Android
SDK, code-signing certs) and parallelizable across targets — a good fit for **background /
remote agents**: spin up per-platform build agents (Tauri-Windows, Tauri-macOS, Capacitor-iOS,
Capacitor-Android) that own their toolchain and CI, reporting back. Track each as its own
task/worktree so they don't block the main web line. Native signing secrets and store
credentials are **user-performed steps** (never automated): the agent prepares the build, the
user supplies certs and submits to the stores.
