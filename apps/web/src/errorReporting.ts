// Global browser-error capture → posts to the server error-log feed so an operator can see when the
// front-end breaks (viewer crashes, unhandled promise rejections, failed API calls) instead of it
// dying silently in a user's console. Best-effort and self-throttling: a render-loop error can't spam
// the server, and a reporting failure never disrupts the app.

export interface ClientErrorPayload {
  message: string;
  kind?: string;
  path?: string;
  level?: "error" | "warning";
  detail?: Record<string, unknown>;
}

type Reporter = (e: ClientErrorPayload) => void;

const _seen = new Map<string, number>();     // signature → last-sent epoch ms (dedupe window)
const DEDUPE_MS = 30_000;
let _sentThisMinute = 0;
let _minuteStart = 0;
const MAX_PER_MIN = 20;                        // hard cap so a storm can't flood the endpoint

function _allow(sig: string, now: number): boolean {
  // per-minute ceiling
  if (now - _minuteStart > 60_000) { _minuteStart = now; _sentThisMinute = 0; }
  if (_sentThisMinute >= MAX_PER_MIN) return false;
  // dedupe identical errors within the window
  const last = _seen.get(sig);
  if (last && now - last < DEDUPE_MS) return false;
  _seen.set(sig, now);
  if (_seen.size > 200) _seen.clear();         // bound memory
  _sentThisMinute++;
  return true;
}

/** Wire window.onerror + unhandledrejection to `report`. Returns a manual `report` you can also call
 *  from catch blocks (e.g. a failed fetch). Uses performance.now-independent Date only via the reporter. */
export function installErrorReporting(report: Reporter): (e: ClientErrorPayload) => void {
  const send = (e: ClientErrorPayload) => {
    try {
      const now = Date.now();
      const sig = `${e.kind || ""}:${e.message}`.slice(0, 200);
      if (!_allow(sig, now)) return;
      report({ ...e, path: e.path ?? (location.hash || location.pathname) });
    } catch { /* never let the reporter throw into the app */ }
  };

  window.addEventListener("error", (ev: ErrorEvent) => {
    send({
      message: ev.message || String(ev.error || "unknown error"),
      kind: ev.error?.name || "Error",
      detail: { source: ev.filename, line: ev.lineno, col: ev.colno,
                stack: (ev.error?.stack || "").slice(0, 4000) },
    });
  });

  window.addEventListener("unhandledrejection", (ev: PromiseRejectionEvent) => {
    const reason = ev.reason;
    send({
      message: (reason?.message || String(reason) || "unhandled rejection").slice(0, 1000),
      kind: reason?.name || "UnhandledRejection",
      detail: { stack: (reason?.stack || "").slice(0, 4000) },
    });
  });

  return send;
}
