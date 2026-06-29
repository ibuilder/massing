import type { CapacitorConfig } from "@capacitor/cli";

/**
 * Capacitor wrapper for the iOS / Android apps. Reuses the SAME web build (`dist`) as the desktop
 * and browser — one UI source, thin native shells (per the platform roadmap).
 *
 * A phone has no local Python backend, so the mobile build must point at a hosted API: build with
 * `npm run build:mobile` (vite --mode mobile reads `.env.mobile` → set VITE_API_URL to your cloud
 * API). Offline field use is covered by the PWA service worker; web-ifc/threaded-WASM in the model
 * viewer must be validated on each device's WebView (see docs/deploy.md → Mobile).
 */
const config: CapacitorConfig = {
  appId: "com.ibuilder.aecbim",
  appName: "Massing",
  webDir: "dist",
  // For live-reload during dev, uncomment and point at your machine:
  // server: { url: "http://192.168.1.x:5173", cleartext: true },
};

export default config;
