/** MODEL-CI — the stored quality gate, and the state its renderer had never been handed.
 *
 *  `ciRun` executes the check pack (rule library, data completeness, clash, pinned IDS, quantity
 *  drift) and **persists the report**; the tool's own footnote says why: *"the badge is stored so
 *  every model version carries a quality gate."* `ciLatest` reads that stored report back, and was
 *  callerless — so the only way to see the last result was to compute it again. **A result persisted
 *  specifically so it need not be recomputed, reachable only by recomputing it.**
 *
 *  WIRING IT EXPOSED A STATE THE RENDERER COULD NOT DESCRIBE. `ciRun` always returns a real report,
 *  so the inline version never met an unrun project — but `ciLatest` returns
 *  `{overall: "none", badge: "NONE", checks: [], note: "No CI run yet."}`, and the old line
 *  `${r.passed ?? 0}/${r.total_checks ?? r.checks.length} passed` renders that as **"0/0 passed"**,
 *  which reads as a result rather than as an absence. *A renderer is only as sound as the states it
 *  has been handed*, and it had been handed one. So `isUnrun` is a branch, not a caveat: an unrun
 *  project gets the engine's own sentence and no score.
 *
 *  The engine itself is clean and was measured before any of this — `overall: "none"`, `badge:
 *  "NONE"`, and a note saying so. It already refuses to let a no-run read as a pass, which is the
 *  whole thesis of this session's sweep, implemented before I arrived.
 */
import type { ApiClient } from "../../api/client";
import { escapeHtml } from "../../ui/feedback";
import { resultNote } from "../../ui/result";

export type CiReport = Awaited<ReturnType<ApiClient["ciLatest"]>>;

const MARK: Record<string, string> = {
  pass: "✅", warn: "🟡", fail: "🔴", skip: "➖", none: "➖",
};

/** Has this project never run CI? `ciRun` cannot produce this; `ciLatest` can. */
export function isUnrun(r: CiReport): boolean {
  return r.overall === "none" || (!r.checks.length && r.ran_at == null);
}

/** The headline, in the engine's own terms. */
export function headline(r: CiReport): string {
  if (isUnrun(r)) {
    return `${MARK.none} <b>Not run yet</b> — ${escapeHtml(r.note || "no stored report for this model")}`;
  }
  return `Overall <b>${MARK[r.overall] || ""} ${escapeHtml(r.badge)}</b>`
    + (r.ran_at ? ` · ${escapeHtml(r.ran_at)}` : "")
    + ` · ${r.passed ?? 0}/${r.total_checks ?? r.checks.length} passed`;
}

export function headlineKind(r: CiReport): "ok" | "bad" | "warn" | "" {
  if (isUnrun(r)) return "warn";
  return r.overall === "fail" ? "bad" : r.overall === "pass" ? "ok" : "";
}

/** Render a report — stored or freshly run; they are the same `ModelCiReport` shape. */
export function renderCiReport(body: HTMLElement, r: CiReport): void {
  body.appendChild(resultNote(headline(r), headlineKind(r)));
  for (const chk of r.checks) {
    body.appendChild(resultNote(
      `${MARK[chk.status] || "•"} <b>${escapeHtml(chk.label)}</b> — ${escapeHtml(chk.summary)}`,
      chk.status === "fail" ? "" : "ok"));
  }
  body.appendChild(resultNote(
    isUnrun(r)
      ? "Nothing has been checked against this model yet. Running the pack stores a badge that "
        + "every later version carries, so this panel opens on the stored result instead of "
        + "recomputing the rule library, completeness, clash, IDS and quantity-drift checks."
      : "Checks compose the rule library + data-completeness gates; the badge is stored so every "
        + "model version carries a quality gate. Add rules via the ✔ Rule check tool.", ""));
}
