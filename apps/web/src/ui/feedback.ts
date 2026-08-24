/** Lightweight UX feedback: transient toasts + a loading overlay. No dependencies. */

/** Escape a string for safe interpolation into innerHTML — prevents stored XSS when rendering
 *  user-entered values (connection names, IDs, DB cell data, etc.). Prefer textContent where the
 *  surrounding markup allows; use this when building an HTML string. */
export function escapeHtml(v: unknown): string {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

/** Escape a value for use as an `href`/`src` attribute, and neutralise dangerous schemes.
 *
 *  `escapeHtml` alone is NOT sufficient for a URL attribute: it stops an attacker breaking out of the
 *  quotes, but `javascript:alert(1)` contains no escapable character and still executes on click.
 *  Anything that is not a same-origin/relative or http(s)/mailto/tel URL collapses to "#". */
export function safeUrl(v: unknown): string {
  const raw = String(v ?? "").trim();
  if (!raw) return "#";
  return schemeAllowed(raw) ? escapeHtml(raw) : "#";
}

/**
 * The scheme check, shared by `safeUrl` and `safeHref` so the two cannot drift.
 *
 * Extracted rather than duplicated: two copies of an allowlist is how one of them quietly stops
 * matching the other, and the failure mode is a scheme that one caller blocks and the other does not.
 */
function schemeAllowed(raw: string): boolean {
  // strip control chars/whitespace that browsers ignore when resolving a scheme ("java\tscript:")
  const probe = raw.replace(/[^\x21-\x7E]/g, "").toLowerCase();
  if (/^(javascript|data|vbscript|blob|file):/.test(probe)) return false;
  if (/^[a-z][a-z0-9+.-]*:/.test(probe) && !/^(https?|mailto|tel):/.test(probe)) return false;
  return true;
}

/**
 * The same scheme guard, for **property or attribute assignment** — `a.href = …`, `setAttribute`.
 *
 * `safeUrl` is for interpolation into an HTML string, so it HTML-escapes. Reaching for it in a DOM
 * context is the plausible wrong move: it would rewrite `?a=1&b=2` into `?a=1&amp;b=2` and break the
 * link, because the browser is not parsing HTML at that point. Same allowlist, no escaping.
 *
 * Why this exists at all: an `href` is a sink that neither `textContent` nor the `innerHTML` ratchet
 * covers. `javascript:alert(1)` contains nothing to escape, so an escape-based defence sees a clean
 * string — and `innerHtmlGuard.test.ts` only watches `.innerHTML` interpolation, so an unguarded
 * `href` assignment passes every gate in the repo. Found by review on the job tray's Download link,
 * where the URL is server-derived today only in the sense that a *fixed path* is built from an id.
 */
export function safeHref(v: unknown): string {
  const raw = String(v ?? "").trim();
  if (!raw) return "#";
  return schemeAllowed(raw) ? raw : "#";
}

let toastHost: HTMLElement | null = null;

function host(): HTMLElement {
  if (!toastHost) {
    toastHost = document.createElement("div");
    toastHost.className = "toast-host";
    // a polite live region so screen readers announce toasts as they appear (they were silent before);
    // error toasts opt into assertive announcement via role="alert" on the element itself.
    toastHost.setAttribute("role", "status");
    toastHost.setAttribute("aria-live", "polite");
    toastHost.setAttribute("aria-atomic", "false");
    document.body.appendChild(toastHost);
  }
  return toastHost;
}

export type ToastKind = "info" | "success" | "error";

export function toast(message: string, kind: ToastKind = "info", ms = 3200): void {
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  if (kind === "error") el.setAttribute("role", "alert");  // interrupt: errors are announced at once
  el.textContent = message;
  host().appendChild(el);
  // animate in
  requestAnimationFrame(() => el.classList.add("show"));
  const remove = () => {
    el.classList.remove("show");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 400);
  };
  el.onclick = remove;
  if (ms > 0) setTimeout(remove, ms);
}

// --- loading overlay (one global, scoped to the viewer container) ------------
let overlay: HTMLElement | null = null;
let depth = 0;

function ensureOverlay(container: HTMLElement): HTMLElement {
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.className = "loading-overlay";
    // announce the loading state + label changes (e.g. download progress) to assistive tech
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML = `<div class="spinner" aria-hidden="true"></div><div class="loading-label"></div>`;
    container.appendChild(overlay);
  }
  return overlay;
}

/** Run an async task with a loading overlay + label; toasts on failure. Returns the result. */
export async function withLoading<T>(container: HTMLElement, label: string,
                                     task: () => Promise<T>): Promise<T | undefined> {
  const ov = ensureOverlay(container);
  (ov.querySelector(".loading-label") as HTMLElement).textContent = label;
  depth++;
  ov.classList.add("show");
  try {
    return await task();
  } catch (err) {
    // A still-running job is the wait walking away, not a failed run. The job tray owns it.
    const name = err && typeof err === "object" ? (err as { name?: string }).name : "";
    if (name === "JobStillRunning") {
      toast((err as Error).message, "info", 5000);
      return undefined;
    }
    toast(`${label} failed: ${(err as Error).message}`, "error", 5000);
    return undefined;
  } finally {
    if (--depth <= 0) ov.classList.remove("show");
  }
}

/** Update the active loading overlay's label mid-task (e.g. download progress). */
export function setLoadingLabel(container: HTMLElement, text: string): void {
  const el = container.querySelector(".loading-label") as HTMLElement | null;
  if (el) el.textContent = text;
}

/** Fetch an ArrayBuffer while reporting download progress (streams the body). Falls back to a
 *  plain buffer when the body can't be streamed or Content-Length is absent. The browser still
 *  handles ETag/304 transparently, so cached re-opens resolve instantly. */
export async function fetchArrayBufferWithProgress(
  url: string, init: RequestInit, onProgress: (loaded: number, total: number) => void,
): Promise<ArrayBuffer> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const total = Number(res.headers.get("content-length") || 0);
  if (!res.body || !total) return res.arrayBuffer();
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value); loaded += value.length; onProgress(loaded, total);
  }
  const out = new Uint8Array(loaded);
  let off = 0;
  for (const c of chunks) { out.set(c, off); off += c.length; }
  return out.buffer;
}
