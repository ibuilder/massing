/** In-app update engine — checks the GitHub Releases of the project for a newer version than the
 *  one baked in at build time, and surfaces a dismissible banner with a download link. Works for
 *  the desktop .exe, the Tauri build, and the browser; no backend or signing needed. (Fully silent
 *  self-install is the Tauri updater path — see docs/deploy.md — which additionally needs a signing
 *  key configured as a CI secret.) */

const REPO = "ibuilder/massing";

export function currentVersion(): string {
  return (import.meta.env.VITE_APP_VERSION as string | undefined) || "0.0.0";
}

function parts(v: string): number[] {
  return v.replace(/^v/, "").split(/[.\-+]/).map((n) => parseInt(n, 10) || 0);
}
/** Semver-ish compare: is `latest` strictly newer than `current`? */
export function isNewer(latest: string, current: string): boolean {
  const a = parts(latest), b = parts(current);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] || 0, y = b[i] || 0;
    if (x !== y) return x > y;
  }
  return false;
}

export interface UpdateInfo { version: string; url: string; notes: string; }

/** Returns release info if a newer published release exists, else null (also null when offline,
 *  rate-limited, or only a draft/prerelease exists — all handled gracefully). */
export async function checkForUpdates(current = currentVersion()): Promise<UpdateInfo | null> {
  try {
    const r = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (!r.ok) return null;                       // 404 until a non-draft release is published
    const d = await r.json() as { tag_name?: string; html_url?: string; body?: string };
    if (!d.tag_name || !isNewer(d.tag_name, current)) return null;
    return { version: d.tag_name.replace(/^v/, ""), url: d.html_url || "", notes: d.body || "" };
  } catch { return null; }
}

let banner: HTMLElement | null = null;

/** Persistent, dismissible top banner announcing an available update + a download link. */
export function showUpdateBanner(info: UpdateInfo): void {
  banner?.remove();
  banner = document.createElement("div");
  banner.style.cssText =
    "position:fixed;top:0;left:0;right:0;z-index:9999;display:flex;gap:12px;align-items:center;justify-content:center;"
    + "padding:8px 14px;font-size:13px;background:var(--accent);color:#fff;box-shadow:0 2px 10px #0006";
  const msg = document.createElement("span");
  msg.textContent = `Update available — v${info.version} (you have v${currentVersion()}).`;
  const dl = document.createElement("a");
  dl.href = info.url || `https://github.com/${REPO}/releases`; dl.target = "_blank"; dl.rel = "noopener";
  dl.textContent = "Download →";
  dl.style.cssText = "color:#fff;font-weight:600;text-decoration:underline";
  const x = document.createElement("button");
  x.textContent = "✕"; x.setAttribute("aria-label", "Dismiss");
  x.style.cssText = "background:transparent;border:none;color:#fff;cursor:pointer;font-size:14px;margin-left:4px";
  x.onclick = () => { banner?.remove(); banner = null; };
  banner.append(msg, dl, x);
  document.body.appendChild(banner);
}

/** Check on startup; show the banner only when a newer release is found. Safe to call anywhere. */
export async function autoCheck(): Promise<void> {
  const info = await checkForUpdates();
  if (info) showUpdateBanner(info);
}
