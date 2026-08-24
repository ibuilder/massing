/** Transport core for the API client (T2 extraction). Owns the base URL, the bearer token, and the
 *  low-level fetch helpers (JSON, multipart PDF POST, health). ApiClient extends this and adds the
 *  ~200 typed domain methods — keeping transport concerns separate from the endpoint surface. */
import { IS_DEMO, demoJson } from "../demo/demoApi";

// dev (Vite @ :5173): hit the API directly (CORS allows :5173).
// prod build: relative "/api" so nginx reverse-proxies same-origin (no CORS needed).
// VITE_API_URL overrides either, baked at build time.
const DEFAULT_API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "/api");

/** Handle for a resilient SSE subscription (see `HttpCore.liveStream`). */
export interface LiveStream { readonly connected: boolean; close(): void }

export class HttpCore {
  private token = localStorage.getItem("aec-token") || "";
  constructor(protected baseUrl = DEFAULT_API) {}

  /** Bearer token for authenticated requests (persisted). Empty string clears it.
   *  Also mirrored into the `aec_token` cookie the backend accepts for **SSE** — EventSource cannot
   *  send an Authorization header, so without the cookie every live stream (model/notifications/
   *  pull-plan) resolves anonymous under RBAC and dies in a reconnect loop. Same-origin only (the
   *  nginx prod layout); in cross-origin dev RBAC is off and streams work without it. */
  /** The current bearer token. Exposed to subclasses so cache keys can be scoped to the identity
   *  that wrote them — see `recordCache.identityScope`. */
  protected get authToken() { return this.token; }

  setToken(t: string) {
    const hadSession = !!this.token;
    this.token = t;
    if (t) localStorage.setItem("aec-token", t); else localStorage.removeItem("aec-token");
    // Signing out must not leave one person's project data readable on the device by whoever signs
    // in next — a real case here, where a browser is a shared kiosk in a site trailer. Record lists
    // are the first thing this product persists locally, so this is the first sign-out that has had
    // anything to erase. Fire-and-forget: a failed clear must never block a sign-out, and the keys
    // are identity-scoped so leftovers stay unreadable under a different session either way.
    if (hadSession && !t) {
      void import("./recordCache").then((m) => m.clearRecordCache()).catch(() => { /* best effort */ });
    }
    try {
      const secure = location.protocol === "https:" ? "; Secure" : "";
      document.cookie = t
        ? `aec_token=${encodeURIComponent(t)}; Path=/; SameSite=Lax; Max-Age=604800${secure}`
        : `aec_token=; Path=/; SameSite=Lax; Max-Age=0${secure}`;
    } catch { /* non-browser context (tests) — Bearer auth still works */ }
  }
  get authed() { return !!this.token; }
  /** Auth header to merge into any raw fetch (uploads, etc.). */
  authHeaders(): Record<string, string> {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {};
  }

  /** Absolute URL for a path (for <a href>/download links the browser fetches directly). */
  url(path: string): string {
    return this.baseUrl + path;
  }

  protected async json<T>(path: string, init?: RequestInit): Promise<T> {
    if (IS_DEMO) return demoJson<T>(path, init);   // viewer-only build: serve the bundled snapshot
    const res = await fetch(this.baseUrl + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...this.authHeaders(), ...(init?.headers || {}) },
    });
    if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
    return res.json() as Promise<T>;
  }

  /** Multipart POST returning a binary Blob (the server PDF ops: merge/split/rotate/extract/…). */
  protected async _pdfPost(path: string, build: (fd: FormData) => void): Promise<Blob> {
    const fd = new FormData(); build(fd);
    const r = await fetch(this.url(path), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
    return r.blob();
  }

  /** R24-PERF-BUDGET — report one client-side interval, in milliseconds, against a named budget.
   *
   * Lives on the base rather than in a feature mixin for two reasons. It is not a feature: it is
   * platform telemetry, sitting beside `health()` for the same reason that does. And `client.ts` is
   * exactly at its size pin, so a new mixin would have cost it an import line it does not have —
   * the ratchet pushing a genuinely infrastructural method to the infrastructural file, which is
   * what it is for.
   *
   * **Fire and forget by contract.** It swallows everything: a browser measuring the app must never
   * be able to break it, and the failure mode of a rejected promise nobody awaited is an unhandled
   * rejection in a user's console. A dropped beacon costs one observation out of a percentile.
   *
   * Silent in the demo build, which has no backend — the same guard every other call here carries.
   */
  reportClientInterval(budget: string, ms: number): void {
    if (IS_DEMO) return;
    try {
      void fetch(this.baseUrl + "/metrics/client", {
        method: "POST", keepalive: true,
        headers: { "Content-Type": "application/json", ...this.authHeaders() },
        body: JSON.stringify({ budget, ms }),
      }).catch(() => { /* a dropped beacon is one observation, not an error */ });
    } catch { /* fetch itself can throw synchronously on a malformed base URL */ }
  }

  async health(): Promise<boolean> {
    try {
      const res = await fetch(this.baseUrl + "/health");
      return res.ok;
    } catch {
      return false;
    }
  }

  /** Resilient SSE subscription. EventSource auto-retries transient network drops on its own, but a
   *  fatal close (the server answered with an HTTP error — deploy, restart, auth expiry) kills the
   *  stream permanently and silently. This helper re-subscribes with bounded backoff (5s → 60s) and
   *  surfaces status transitions so a UI can say "live updates disconnected" instead of going quiet. */
  protected liveStream(path: string, onMessage: (data: unknown) => void,
                     onStatus?: (s: "connected" | "reconnecting") => void): LiveStream {
    // Demo/Pages build has no backend: opening an EventSource there dies CLOSED and our backoff would
    // retry it forever (console-error spam in the public demo). Serve an inert stream instead — the
    // same guard every fetch method has via demoJson.
    if (IS_DEMO) return { get connected() { return false; }, close() { /* nothing to close */ } };
    let es: EventSource | null = null;
    let closed = false;
    let retryMs = 5000;
    let timer: number | undefined;
    let connected = false;
    const open = () => {
      if (closed) return;
      es = new EventSource(this.url(path));
      es.onmessage = (e) => {
        if (!connected) { connected = true; retryMs = 5000; onStatus?.("connected"); }
        try { onMessage(JSON.parse(e.data)); } catch { /* malformed frame — skip it, keep the stream */ }
      };
      es.onerror = () => {
        if (connected) { connected = false; onStatus?.("reconnecting"); }
        // CLOSED = fatal response → schedule our own re-subscribe; CONNECTING = browser is retrying.
        if (es && es.readyState === EventSource.CLOSED && !closed) {
          timer = window.setTimeout(open, retryMs);
          retryMs = Math.min(retryMs * 2, 60000);
        }
      };
    };
    open();
    return {
      get connected() { return connected; },
      close() { closed = true; if (timer !== undefined) clearTimeout(timer); es?.close(); },
    };
  }
}
