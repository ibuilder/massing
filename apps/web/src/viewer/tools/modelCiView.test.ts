import { describe, expect, it } from "vitest";

import type { CiReport } from "./modelCiView";
import { headline, headlineKind, isUnrun, renderCiReport } from "./modelCiView";

/**
 * CI-LATEST-DARK. `ciRun` was wired and `ciLatest` was not, so the stored badge — persisted
 * precisely so it need not be recomputed — could only be seen by recomputing it.
 *
 * Wiring it handed the renderer a state `ciRun` can never produce. `model_ci.latest` returns
 * `{overall: "none", badge: "NONE", checks: [], note: "No CI run yet."}` for a project that has
 * never run, and the old inline line `${r.passed ?? 0}/${r.total_checks ?? r.checks.length} passed`
 * renders that as **"0/0 passed"** — a score, for something never scored. That is the case pinned
 * hardest here, because it is the one the previous renderer had never been asked about.
 */

const R = (over: Partial<CiReport> = {}): CiReport => ({
  overall: "pass", badge: "PASS", ran_at: "2026-09-25T07:00:00Z",
  total_checks: 5, passed: 5, failed: 0, warned: 0,
  checks: [{ key: "rules", label: "Rule library", status: "pass", summary: "12/12 rules pass" }],
  ...over,
} as CiReport);

/** Exactly what `/ci/latest` returns for a project that has never run CI — measured, not invented. */
const UNRUN = (): CiReport =>
  ({ overall: "none", badge: "NONE", checks: [], note: "No CI run yet." } as CiReport);

const mount = () => {
  const el = document.createElement("div");
  document.body.replaceChildren(el);
  return el;
};

/** A real run that had nothing applicable to check: `ran_at` set, a verdict, and no checks. This is
 *  NOT "never run", and a mutation proved the distinction was unasserted — `isUnrun` reduced to
 *  `!r.checks.length` passed every test here, because no fixture had an empty `checks` on a report
 *  that had actually run. *Run it* and *it ran and found nothing to check* are different findings,
 *  and conflating them is the same defect this whole session is about, one level down. */
const RAN_EMPTY = (): CiReport =>
  ({ overall: "pass", badge: "PASS", ran_at: "2026-09-25T07:00:00Z",
     total_checks: 0, passed: 0, checks: [] } as CiReport);

describe("a project that never ran CI is not a project that scored zero", () => {
  it("is recognised", () => {
    expect(isUnrun(UNRUN())).toBe(true);
    expect(isUnrun(R())).toBe(false);
  });

  it("is not confused with a run that had nothing to check", () => {
    expect(isUnrun(RAN_EMPTY())).toBe(false);
    expect(headline(RAN_EMPTY())).not.toContain("Not run yet");
    expect(headline(RAN_EMPTY())).toContain("PASS");
  });

  it("shows NO score — '0/0 passed' is a result, and there is no result", () => {
    const h = headline(UNRUN());
    expect(h).not.toContain("passed");
    expect(h).not.toContain("0/0");
  });

  it("says so in the engine's own words", () => {
    expect(headline(UNRUN())).toContain("Not run yet");
    expect(headline(UNRUN())).toContain("No CI run yet.");
  });

  it("is not coloured as a pass", () => {
    expect(headlineKind(UNRUN())).toBe("warn");
    expect(headlineKind(UNRUN())).not.toBe("ok");
  });

  it("tells the reader what running it would buy", () => {
    const el = mount();
    renderCiReport(el, UNRUN());
    expect(el.textContent).toContain("stores a badge");
    expect(el.textContent).toContain("instead of recomputing");
  });
});

describe("a real report reads as it always did", () => {
  it("keeps the overall badge, the timestamp and the score", () => {
    const h = headline(R());
    expect(h).toContain("PASS");
    expect(h).toContain("2026-09-25T07:00:00Z");
    expect(h).toContain("5/5 passed");
  });

  it("colours a failure as bad and a pass as ok", () => {
    expect(headlineKind(R({ overall: "fail", badge: "FAIL" }))).toBe("bad");
    expect(headlineKind(R())).toBe("ok");
    expect(headlineKind(R({ overall: "warn", badge: "WARN" }))).toBe("");
  });

  it("falls back to the check count when the server sent no total", () => {
    expect(headline(R({ total_checks: undefined, passed: 1 }))).toContain("1/1 passed");
  });

  it("lists every check", () => {
    const el = mount();
    renderCiReport(el, R({ checks: [
      { key: "rules", label: "Rule library", status: "pass", summary: "12/12" },
      { key: "clash", label: "Clash", status: "fail", summary: "3 hard clashes" }] }));
    expect(el.textContent).toContain("Rule library");
    expect(el.textContent).toContain("3 hard clashes");
  });

  it("escapes a summary, which carries rule text an author wrote", () => {
    const el = mount();
    renderCiReport(el, R({ checks: [{ key: "k", label: "<img src=x onerror=1>", status: "fail",
                                      summary: "<b>x</b>" }] }));
    expect(el.querySelector("img")).toBeNull();
  });
});

describe("the two shapes are one shape", () => {
  it("a stored report and a fresh run render through the same path", () => {
    // `ciRun` and `ciLatest` both return ModelCiReport — no re-spelling, so one renderer serves
    // both and a drift in either would show up here rather than in only one of two copies.
    const a = mount(); renderCiReport(a, R());
    const b = mount(); renderCiReport(b, R({ ran_at: undefined }));
    expect(a.textContent).toContain("5/5 passed");
    expect(b.textContent).toContain("5/5 passed");
    expect(b.textContent).not.toContain("undefined");
  });
});
