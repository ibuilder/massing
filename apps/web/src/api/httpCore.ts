/** Transport core for the API client (T2 extraction). Owns the base URL, the bearer token, and the
 *  low-level fetch helpers (JSON, multipart PDF POST, health). ApiClient extends this and adds the
 *  ~200 typed domain methods — keeping transport concerns separate from the endpoint surface. */
import { IS_DEMO, demoJson } from "../demo/demoApi";

// dev (Vite @ :5173): hit the API directly (CORS allows :5173).
// prod build: relative "/api" so nginx reverse-proxies same-origin (no CORS needed).
// VITE_API_URL overrides either, baked at build time.
const DEFAULT_API = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "/api");

/** What a live subscription is doing. `refused` is the third state and the whole point of it:
 *  `EventSource` reports a fatal close and a transient drop through the SAME `onerror` with no
 *  status, so a stream the server will never serve this caller looked exactly like a server that
 *  was briefly away — and the UI said *"reconnecting…"* about it for ever. */
export type LiveStatus = "connected" | "reconnecting" | "refused";

/** Handle for a resilient SSE subscription (see `HttpCore.liveStream`). */
export interface LiveStream {
  readonly connected: boolean;
  close(): void;
  /** Resume a subscription that went `refused`. Reversibility, the same way the offline queues
   *  offer *Try again* beside *Discard*: the probe below classifies from one status code and can be
   *  wrong, and *a judgement a person cannot overturn is a worse design than one that is
   *  occasionally wrong.* On a stream that is not refused this is a no-op. */
  retry(): void;
}

/** An HTTP failure that still carries its STATUS, not only a message describing it.
 *
 *  `json()` has always thrown `Error("POST /path -> 400")`, which puts the status somewhere only a
 *  string parse can reach. A caller that needs to tell a PERMANENT rejection from a transient one —
 *  the offline field queue is the first, and re-queueing a 400 forever is what it did — would have
 *  had to match on the message text. That is the same brittleness MONEY-SCOPE removed from a
 *  different scan: a predicate keyed on a spelling breaks the moment the spelling changes.
 *
 *  It extends `Error` and keeps the identical message, so every existing `catch` keeps working and
 *  nothing has to be migrated. Callers that care about the status opt in.
 */
export class HttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    // `new.target`, not the literal "HttpError": `CloudError` extends this, and a subclass that
    // reported its parent's name in a stack trace would be harder to place, not easier.
    this.name = new.target.name;
  }
}

/**
 * Why the server will NEVER accept this request, or `null` if the failure is worth retrying.
 *
 * 4xx means the request itself is wrong — a validation failure, or the sender no longer has access
 * to the project — and repeating it byte for byte cannot change the answer. 408 and 429 are the
 * exceptions: both explicitly invite a retry. Everything else (offline, DNS, 5xx, a proxy eating
 * the connection) is transient by default, because **guessing "permanent" wrongly destroys work
 * somebody did, and guessing "transient" wrongly only costs another attempt.** The asymmetry
 * decides the default, not a judgement about which failures are more likely.
 *
 * Lives here, beside `HttpError`, because it is the POLICY that reading a status is for, and it now
 * has two callers that must not drift apart: the field capture queue and the portal's offline
 * upload queue. It began inside `field/field.ts` with one caller — which is exactly how the pair of
 * queues came to disagree about everything else, each re-deriving "should I try this again" from
 * whatever its own `catch` happened to see.
 *
 * A non-`HttpError` reaches here as status 0 and is therefore transient, which is correct: an
 * offline `fetch` rejects with a `TypeError`, and that is the single most retryable failure there is.
 */
export function permanentRejection(e: unknown): string | null {
  const status = e instanceof HttpError ? e.status : 0;
  if (status < 400 || status >= 500 || status === 408 || status === 429) return null;
  // 401 is NOT permanent, and treating it as such was this rule's first real mistake: the token
  // expired, the person signs in again, and the very same request succeeds. Marking it refused
  // strands work that one ordinary user action would have sent. 403 stays permanent — the server
  // authenticated the caller and still said no, so a fresh token changes nothing.
  if (status === 401) return null;
  if (status === 403) return "No longer permitted on this project";
  if (status === 404) return "The project or record no longer exists";
  return `Refused by the server (${status})`;
}

export class HttpCore {
  private token = localStorage.getItem("aec-token") || "";
  constructor(protected baseUrl = DEFAULT_API) {}

  /** The current bearer token. Exposed to subclasses so cache keys can be scoped to the identity
   *  that wrote them — see `recordCache.identityScope`. */
  protected get authToken() { return this.token; }

  /** Bearer token for authenticated requests (persisted). Empty string clears it.
   *  Also mirrored into the `aec_token` cookie the backend accepts for **SSE** — EventSource cannot
   *  send an Authorization header, so without the cookie every live stream (model/notifications/
   *  pull-plan) resolves anonymous under RBAC and dies in a reconnect loop. Same-origin only (the
   *  nginx prod layout); in cross-origin dev RBAC is off and streams work without it. */
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
    if (!res.ok) {
      // CARRY THE SERVER'S OWN SENTENCE, not just the status. Until 2026-09-11 this threw
      // `POST /x -> 422` and dropped the body, so every handler that answers a refusal with a
      // deliberate fixed literal -- `prefab_kit.FREEZE_NO_MATCH`, `FREEZE_TRUNCATED`, and the
      // 422s across the module routers -- reached the user as a status code. Found by review on a
      // method whose own comment claimed the literal was being shown: **a comment asserting a
      // behaviour the platform does not have.**
      //
      // `models.ts` already did exactly this at its own call site; doing it here means the next
      // caller gets it without knowing to ask. Falls back to the old message when the body is not
      // JSON or carries no `detail`, so nothing loses information.
      const detail = await res.json().then((b) => (b as { detail?: unknown })?.detail)
        .catch(() => undefined);
      throw new HttpError(
        typeof detail === "string" && detail
          ? detail : `${init?.method ?? "GET"} ${path} -> ${res.status}`,
        res.status);
    }
    return res.json() as Promise<T>;
  }

  /** Multipart POST returning a binary Blob (the server PDF ops: merge/split/rotate/extract/…). */
  protected async _pdfPost(path: string, build: (fd: FormData) => void): Promise<Blob> {
    const fd = new FormData(); build(fd);
    const r = await fetch(this.url(path), { method: "POST", body: fd, headers: this.authHeaders() });
    if (!r.ok) throw new HttpError((await r.text()) || `HTTP ${r.status}`, r.status);
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

  /**
   * R41-UPLOAD-WARK — upload a large file resumably, deduplicating an unchanged re-upload.
   *
   * Lives on the base for the same reason `reportClientInterval` does: it is transport rather than a
   * feature, and `client.ts` is at its size pin. The chunking, hashing and resume logic are in
   * `resumableUpload.ts`, which is pure over injected transport so the protocol can be tested without
   * a network; this supplies the real fetches and the browser digest.
   */
  // Underscored because it is PLUMBING, not client surface: it moves bytes and returns a storage
  // key, which is not a thing any screen wants. The public method is `addProjectModelResumable`,
  // which turns that key into a model. The uncalled-methods gate excludes underscored members for
  // exactly this reason — a transport helper has no screen and never will.
  async _uploadResumable(pid: string, file: Blob, onProgress?: (sent: number, total: number) => void) {
    const { uploadResumable, sha256Hex } = await import("./resumableUpload");
    return uploadResumable(pid, file, {
      sha256: sha256Hex,
      onProgress,
      postJson: (path, body) => this.json(path, { method: "POST", body: JSON.stringify(body) }),
      putBytes: async (path, data, headers) => {
        const r = await fetch(this.baseUrl + path, {
          method: "PUT", body: data, headers: { ...this.authHeaders(), ...headers },
        });
        if (!r.ok) throw new HttpError((await r.text()) || `PUT ${path} -> ${r.status}`, r.status);
        return r.json();
      },
    });
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
   *  surfaces status transitions so a UI can say "live updates disconnected" instead of going quiet.
   *
   *  **AND IT RETRIED A REFUSAL FOR EVER, which is the third instance of the class the two offline
   *  queues closed.** `onerror` carries no status — a fatal close and a transient drop arrive
   *  identically — so a 403 on a project the caller has been removed from, or a 404 on one that was
   *  deleted, backed off to the 60-second ceiling and kept going, while the only UI that reads this
   *  said *"Live notifications disconnected — reconnecting…"* indefinitely. **The diagnosis was
   *  already written down twenty lines above, in `setToken`**: *"without the cookie every live
   *  stream … resolves anonymous under RBAC and dies in a reconnect loop."* Nothing acted on it.
   *  *A symptom named in a docstring beside the code that produces it is not a fixed defect, and
   *  it reads like one.*
   *
   *  So a fatal close is now CLASSIFIED: one `fetch` of the same path, whose status
   *  `permanentRejection` rules on — the same policy the field capture queue and the portal upload
   *  queue share, rather than a third opinion about which failures are worth repeating. Permanent →
   *  stop, and say why. Anything else, including a probe that cannot complete → back off and retry,
   *  because the asymmetry runs the same way here as it does for a queued capture: refusing to
   *  reconnect to a server that was merely away leaves somebody watching a dead screen. */
  protected liveStream(path: string, onMessage: (data: unknown) => void,
                     onStatus?: (s: LiveStatus, why?: string) => void): LiveStream {
    // Demo/Pages build has no backend: opening an EventSource there dies CLOSED and our backoff would
    // retry it forever (console-error spam in the public demo). Serve an inert stream instead — the
    // same guard every fetch method has via demoJson.
    if (IS_DEMO) {
      return { get connected() { return false; }, close() { /* nothing to close */ },
               retry() { /* nothing to retry */ } };
    }
    let es: EventSource | null = null;
    let closed = false;
    let refused = false;
    let retryMs = 5000;
    let timer: number | undefined;
    let connected = false;

    /** Ask the same URL what the status actually was. Returns the refusal reason, or `null` for
     *  "retry" — including when the probe itself fails, which is the transient case by default. */
    const classify = async (): Promise<string | null> => {
      try {
        const res = await fetch(this.url(path), { headers: this.authHeaders() });
        // The body is an endless stream; cancel it rather than reading it. Without this the probe
        // holds a connection open for as long as the server keeps the stream alive.
        res.body?.cancel().catch(() => { /* already gone */ });
        if (res.ok) return null;
        return permanentRejection(new HttpError(`${path} -> ${res.status}`, res.status));
      } catch {
        return null;                      // offline, DNS, a proxy eating it — all worth retrying
      }
    };

    const open = () => {
      if (closed || refused) return;
      es = new EventSource(this.url(path));
      es.onmessage = (e) => {
        if (!connected) { connected = true; retryMs = 5000; onStatus?.("connected"); }
        try { onMessage(JSON.parse(e.data)); } catch { /* malformed frame — skip it, keep the stream */ }
      };
      es.onerror = () => {
        if (connected) { connected = false; onStatus?.("reconnecting"); }
        // CLOSED = fatal response → classify, then re-subscribe or stop; CONNECTING = browser is
        // retrying on its own and there is nothing to classify yet.
        if (es && es.readyState === EventSource.CLOSED && !closed) {
          es.close();                     // a CLOSED source still holds its slot in the pool
          const wait = retryMs;
          retryMs = Math.min(retryMs * 2, 60000);
          void classify().then((why) => {
            // `closed` only — scheduling a timer on a closed stream leaks one firing that does
            // nothing. A concurrent refusal is caught by `open`'s own guard rather than duplicated
            // here: mutating `|| refused` out of this line changed no test, which is the signal
            // that it was redundant, and *an unmeasured branch is the thing this session keeps
            // paying for.* The race it looked like it covered is real and is tested — two fatal
            // closes in flight, one transient verdict and one permanent — but `open` is where it
            // has to be handled, because the timer has already been scheduled by then.
            if (closed) return;
            if (why) { refused = true; onStatus?.("refused", why); return; }
            timer = window.setTimeout(open, wait);
          });
        }
      };
    };
    open();
    return {
      get connected() { return connected; },
      close() { closed = true; if (timer !== undefined) clearTimeout(timer); es?.close(); },
      retry() {
        if (closed || !refused) return;
        refused = false;
        retryMs = 5000;
        onStatus?.("reconnecting");
        open();
      },
    };
  }
}
