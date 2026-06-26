# Mobile app — framework & plan

**Status:** groundwork / plan (no native build wired into CI yet — that needs Xcode + the Android SDK
and signing identities, which aren't on the build runners). This is the deliberate "separate-app"
track flagged in the roadmap. The web app is **already mobile-capable** today (responsive layout,
installable PWA with an offline service worker, and the offline **field-capture** flow), so the
mobile app is a *wrapper*, not a rewrite.

## Approach — Capacitor wraps the existing web build

[Capacitor](https://capacitorjs.com) loads the built `apps/web/dist` in a native WebView shell and
exposes native APIs (camera, geolocation, filesystem, push) to the same TypeScript. We reuse the
viewer, portal, finance and field-capture code unchanged — only the *packaging* and a few native
plugin swaps are new.

Why Capacitor over a React-Native/Flutter rewrite: the value here is the **3D viewer + the 71
config-driven modules + finance**, all already built for the web. A rewrite throws that away;
Capacitor ships it. The desktop app already proves the "wrap the web build" model (Tauri).

## Config (drop-in)

`apps/web/capacitor.config.ts`:

```ts
import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.modelmaker.app",
  appName: "ModelMaker",
  webDir: "dist",                       // the vite build output
  server: { androidScheme: "https" },
  ios: { contentInset: "always" },
};
export default config;
```

The hosted API URL is supplied at build time via `VITE_API_URL` (the FastAPI sidecar is **not**
bundled into mobile — mobile talks to a hosted/self-hosted API, unlike the single-machine desktop
build). Auth is the existing Bearer-token flow.

## One-time setup

```bash
cd apps/web
npm i -D @capacitor/cli
npm i @capacitor/core @capacitor/ios @capacitor/android
npx cap init ModelMaker com.modelmaker.app --web-dir dist
VITE_API_URL=https://api.yourhost.com npm run build
npx cap add ios && npx cap add android
npx cap sync
npx cap open ios        # Xcode  → archive / TestFlight
npx cap open android    # Android Studio → bundle / Play
```

`npx cap sync` after every `npm run build` copies the fresh web bundle into the native projects.

## Native plugin swaps (progressive enhancement)

Each is a thin, capability-detected upgrade over the web fallback already in place:

| Capability | Web today | Native plugin | Win on device |
|---|---|---|---|
| Jobsite photos | `<input type=file capture>` ([field.ts](../apps/web/src/field/field.ts)) | `@capacitor/camera` | direct capture, no picker |
| Geotag observations | none | `@capacitor/geolocation` | stamp field records with GPS |
| Offline queue | localStorage + SW | `@capacitor/preferences` / `filesystem` | durable across app kills |
| Notifications | SSE (foreground) | `@capacitor/push-notifications` | RFI/approval pushes when backgrounded |

Pattern: `if (Capacitor.isNativePlatform()) { …native… } else { …existing web path… }` — so the same
build keeps working in a desktop browser.

## What's already mobile-ready (verified)

- **Responsive shell** — the 4-zone layout + collapsible rail already adapt to narrow viewports.
- **Offline** — `vite-plugin-pwa` (workbox) precaches the app shell + self-hosted WASM; the viewer
  runs with no network once cached.
- **Field capture** — offline photo → punchlist/observation, syncs on reconnect (the core jobsite
  loop), persona-gated to subcontractor/GC. A persistent IndexedDB upload queue survives app restarts.
- **Full platform, same build** — the mobile wrapper ships the *same* web app, so everything is on a
  phone: the GC portal (RFIs/submittals/change orders/daily reports), the **Schedule → Budget (GMP)**,
  **5D** cost-on-the-model + heatmap, pay apps, and the multi-user roles. Heavy authoring is desktop-first.

## Gaps to close before shipping a store build

1. Touch gestures in the 3D viewer (camera-controls supports touch; needs a device test pass).
2. A mobile-first nav for the rail/workspaces on phone widths (tabs → bottom bar).
3. The camera/geolocation/push plugin swaps above.
4. CI: a macОS runner with Xcode for iOS archives + an Android signing keystore (separate pipeline
   from the current Tauri desktop release).

## Recommendation

Ship the **PWA "Add to Home Screen"** path now (zero extra work — it already installs offline), and
treat the native Capacitor store apps as a fast-follow once the touch/nav polish (1–2 above) lands.
The PWA covers most jobsite needs immediately; the native shell adds camera/GPS/push.
