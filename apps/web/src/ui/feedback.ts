/** Lightweight UX feedback: transient toasts + a loading overlay. No dependencies. */

/** Escape a string for safe interpolation into innerHTML — prevents stored XSS when rendering
 *  user-entered values (connection names, IDs, DB cell data, etc.). Prefer textContent where the
 *  surrounding markup allows; use this when building an HTML string. */
export function escapeHtml(v: unknown): string {
  return String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}

let toastHost: HTMLElement | null = null;

function host(): HTMLElement {
  if (!toastHost) {
    toastHost = document.createElement("div");
    toastHost.className = "toast-host";
    document.body.appendChild(toastHost);
  }
  return toastHost;
}

export type ToastKind = "info" | "success" | "error";

export function toast(message: string, kind: ToastKind = "info", ms = 3200): void {
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
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
    overlay.innerHTML = `<div class="spinner"></div><div class="loading-label"></div>`;
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
