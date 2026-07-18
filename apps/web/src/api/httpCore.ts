/** Transport core for the API client (T2 extraction). Owns the base URL, the bearer token, and the
 *  low-level fetch helpers (JSON, multipart PDF POST, health). ApiClient extends this and adds the
 *  ~200 typed domain methods — keeping transport concerns separate from the endpoint surface. */
import { IS_DEMO, demoJson } from "../demo/demoApi";

// dev (Vite @ :5173): hit the API directly (CORS allows :5173).
// prod build: relative "/api" so nginx reverse-proxies same-origin (no CORS needed).
// VITE_API_URL overrides either, baked at build time.
const DEFAULT_API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "/api");

export class HttpCore {
  private token = localStorage.getItem("aec-token") || "";
  constructor(protected baseUrl = DEFAULT_API) {}

  /** Bearer token for authenticated requests (persisted). Empty string clears it.
   *  Also mirrored into the `aec_token` cookie the backend accepts for **SSE** — EventSource cannot
   *  send an Authorization header, so without the cookie every live stream (model/notifications/
   *  pull-plan) resolves anonymous under RBAC and dies in a reconnect loop. Same-origin only (the
   *  nginx prod layout); in cross-origin dev RBAC is off and streams work without it. */
  setToken(t: string) {
    this.token = t;
    if (t) localStorage.setItem("aec-token", t); else localStorage.removeItem("aec-token");
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

  async health(): Promise<boolean> {
    try {
      const res = await fetch(this.baseUrl + "/health");
      return res.ok;
    } catch {
      return false;
    }
  }
}
