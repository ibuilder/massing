/** POST a PDF and save it. Cookie-bearing GET is how SameSite=Lax leaks a session. */
import { HttpError } from "./httpCore";
export async function downloadPostedPdf(
  api: { url(path: string): string; authHeaders(): Record<string, string> },
  path: string,
  fallbackName: string,
  /**
   * OPTION-BOARD-DARK added this. Both routes that render a PDF from a POST body — the design
   * option board, and anything that follows it — need the body to be the SAME value the screen was
   * drawn from, so it is passed in rather than rebuilt here. `undefined` sends no body at all,
   * which is what the CAM statement has always done: a route that takes its input from the URL
   * must not start receiving `{}`, because FastAPI's `Body(..., embed=True)` would then 422 on a
   * missing key instead of reading the path.
   */
  body?: unknown,
): Promise<void> {
  const r = await fetch(api.url(path), {
    method: "POST",
    headers: body === undefined ? api.authHeaders()
      : { ...api.authHeaders(), "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!r.ok) throw new HttpError((await r.text()) || `HTTP ${r.status}`, r.status);
  const blob = await r.blob();
  const a = document.createElement("a");
  const cd = r.headers.get("Content-Disposition") || "";
  const named = /filename="([^"]+)"/.exec(cd)?.[1];
  a.href = URL.createObjectURL(blob);
  a.download = named || fallbackName;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function camStatementPath(pid: string, rid: string): string {
  return `/projects/${pid}/cam/statement/${rid}.pdf`;
}

/**
 * OPTION-BOARD-DARK — the client-facing artifact of a GEN-SCORE run.
 *
 * `POST /projects/{pid}/design/options/board.pdf` renders the scored option set as a one-page deck:
 * title, recommendation, the comparison table and the composite score bars. The server's own
 * docstring calls it *"the client-facing artifact of a GEN-SCORE run"* — and nothing called it, so
 * an architect could rank four massing options on screen and had no way to produce the single
 * document the ranking exists to support.
 *
 * It was invisible to `services/api/test_route_reachability.py` for a reason that gate records
 * about itself: the leaf `board.pdf` is genuinely built elsewhere, by
 * `/projects/{pid}/pull-plan/board.pdf` in `api/schedule.ts`, so the rule read the leaf as called —
 * by something else. *A leaf is not a name*, and this is the sibling-leaf collision, found a
 * seventh time.
 */
export function optionsBoardPath(pid: string): string {
  return `/projects/${pid}/design/options/board.pdf`;
}

/**
 * The deck's request body: the option set that was SCORED, passed through untouched.
 *
 * The route scores the set it is handed, so three values were available at the click and two of
 * them are wrong — the scored OUTPUT (already-scored dicts re-scored) and a freshly generated set
 * (re-generated from inputs the reader may have edited since the table was drawn). *A deliverable
 * derived from a different input than the screen it is taken from is a second opinion wearing the
 * first one's name.* `weights` travels with it for the same reason, and is omitted rather than sent
 * as `undefined`, because the route reads it with `Body(default=None, embed=True)` and a declared
 * key is not the same as an absent one.
 *
 * A function rather than an inline object so the pass-through is assertable: the panel that owns
 * the choice has no test file, and `downloadPdf.test.ts` pins the source-level half beside this.
 */
export function optionsBoardBody(
  set: { options: Record<string, unknown>[]; weights?: Record<string, number> },
): { options: Record<string, unknown>[]; weights?: Record<string, number> } {
  return { options: set.options, ...(set.weights ? { weights: set.weights } : {}) };
}
