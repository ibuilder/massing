import type { CxCell, CxMatrix, CxMatrixRow } from "../../api/types";

/**
 * CX-CELL-FLAT — the commissioning wall chart could not tell "not started" from "tested, awaiting
 * the Owner", and dropped a declared result state off every cell.
 *
 * Three defects, all measured against a live route before a line of this was written.
 *
 * ## 1. Two opposite cells rendered the same
 *
 * The cell was `` `${c.accepted}/${c.total}` + (c.fail ? ` ✗${c.fail}` : "") ``. Measured on two
 * systems of ten Functional tests each — AHU-1 with all ten **tested** by the contractor (five
 * Conditional, two Pass, one Fail, two with nothing recorded) and AHU-2 with **nothing done at
 * all**:
 *
 * > AHU-1 `Functional = 0/10 ✗1`   ·   AHU-2 `Functional = 0/10`
 *
 * The only difference on screen was the one Fail. Drop that test and the two rows are
 * byte-identical. `tested: 10` versus `tested: 0` was declared on the client type and read by
 * nothing. *On a wall chart whose entire job is to say where the work is, the two states a Cx agent
 * acts on differently — chase the contractor, or chase the owner's signature — were the same
 * string.* This is WAIVER-FLAT on commissioning rather than lien releases.
 *
 * ## 2. `Conditional` was counted nowhere
 *
 * The module declares three results — Pass / Fail / Conditional — and the cell carried the first
 * two. On the AHU-1 cell above: `pass: 2`, `fail: 1`, `total: 10`, and the other **seven** (five
 * Conditional, two unrecorded) in no bucket at all. A Conditional commissioning test is *accepted
 * with deficiencies*, which is what generates the punch work, so on a turnover chart it is the state
 * a reader most needs. STAKEHOLDER-MEDIUM is the same shape: a three-level scale rendered on two.
 *
 * ## 3. The row total exceeded the cells on screen
 *
 * `test_type` is a `select`, and `module_schema.validate_record` says in so many words that select
 * options are *"treated as suggestions, not a closed enum"*. So a test can carry no phase, or a
 * phase outside the five. The first was silently attributed to **Pre-Functional**, a phase nobody
 * chose; the second was counted in the row's `tests` and in `complete_pct`'s denominator and
 * rendered in **no column**. Measured on a two-test system: `tests: 2` above cells summing to 1.
 *
 * ## The distinction was already drawn one file away
 *
 * `closeout.commissioning_rollup` counts `conditional` as a first-class third state, buckets a
 * missing phase as `(unspecified)`, and takes its `pass_rate` over `passed + failed + conditional`
 * rather than over the total — and `closeoutSummary` **declares `conditional` twenty lines above
 * `cxMatrix` in the same client class**. All three answers existed in this tree; the matrix is the
 * one place none of them reached. *A rollup and its detail in one file, and only the rollup knew the
 * third state existed.* The engine now imports `UNSPECIFIED_PHASE` from there rather than
 * re-spelling it, so the two cannot drift.
 *
 * Every function here returns PLAIN TEXT: `operations.ts` interpolates into `innerHTML`, and
 * `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet.
 */

/** The four result states, in the order a reader acts on them. */
const RESULTS: { key: keyof CxCell; mark: string; word: string }[] = [
  { key: "fail", mark: "✗", word: "failed" },
  { key: "conditional", mark: "⊙", word: "conditional" },
  { key: "pass", mark: "✓", word: "passed" },
  { key: "no_result", mark: "·", word: "no result yet" },
];

/**
 * One cell, as plain text. `—` when the system has no test in that phase.
 *
 * The shape is `accepted/total` — unchanged, because that is the number a Cx agent reads first —
 * followed by `t<n>` for the contractor's half and then the result marks. The two cells in defect 1
 * now read `0/10 t10 ⊙5 ✗1 ✓2 ·2` and `0/10 ·10`.
 */
export function cxCell(c: CxCell | null | undefined): string {
  if (!c) return "—";
  const bits = [`${c.accepted}/${c.total}`];
  // `tested` is shown whenever it differs from `accepted`, which is exactly when the cell is
  // waiting on an owner signature. Equal means there is nothing in between to report.
  if (c.tested !== c.accepted) bits.push(`t${c.tested}`);
  for (const r of RESULTS) {
    const n = c[r.key] as number;
    if (n) bits.push(`${r.mark}${n}`);
  }
  return bits.join(" ");
}

/** The same cell as a sentence, for the `title` attribute — the marks are not self-explaining. */
export function cxCellTitle(c: CxCell | null | undefined): string {
  if (!c) return "No test recorded in this phase.";
  const parts = RESULTS.filter((r) => (c[r.key] as number) > 0)
    .map((r) => `${c[r.key] as number} ${r.word}`);
  const results = parts.length ? parts.join(", ") : "no results recorded";
  const owner = c.accepted === c.total
    ? "all accepted by the Owner"
    : `${c.accepted} accepted by the Owner, ${c.tested - c.accepted} tested and awaiting acceptance`;
  return `${c.total} test(s): ${owner}. Results: ${results}.`;
}

/** The legend. Without it the marks above are decoration. */
export function cxLegend(): string {
  return "accepted/total · t = tested by the contractor, awaiting Owner acceptance · "
    + "✗ failed · ⊙ conditional (accepted with deficiencies) · ✓ passed · · no result recorded";
}

/**
 * What the extra columns are, or `null` when the five phases covered everything.
 *
 * Named rather than silent because an extra column is a data-quality finding, not a layout quirk:
 * `(unspecified)` means somebody saved a test without choosing a phase, and anything else means a
 * phase outside the firm's five.
 */
export function cxPhaseNote(mx: CxMatrix): string | null {
  const extra = mx.extra_phases ?? [];
  if (!extra.length) return null;
  const unspecified = extra.includes("(unspecified)");
  const others = extra.filter((p) => p !== "(unspecified)");
  const bits: string[] = [];
  if (unspecified) bits.push("one or more tests carry no test type at all — the `(unspecified)` column");
  if (others.length) {
    bits.push(`${others.length} test type(s) outside the standard five: ${others.join(", ")}`);
  }
  return `${bits.join("; ")}. Each has its own column, so every test counted in a row total is on `
    + "the chart.";
}

/**
 * Does each row's `tests` equal the tests actually on screen?
 *
 * This is the parity check for defect 3, and it is kept even though the engine now derives the
 * column list from the data — because the thing that broke was precisely the assumption that the
 * column list covered the cells. A check that only holds while the assumption holds is not a check.
 * Returns `null` when every row agrees.
 */
export function cxParity(mx: CxMatrix): string | null {
  const bad: string[] = [];
  for (const s of mx.systems) {
    const shown = mx.phases.reduce((n, p) => n + (s.phases[p]?.total ?? 0), 0);
    if (shown !== s.tests) bad.push(`${s.system} (${s.tests} counted, ${shown} shown)`);
  }
  if (!bad.length) return null;
  return `⚠ ${bad.length} row(s) count tests that no column displays: ${bad.slice(0, 5).join(", ")}`
    + `${bad.length > 5 ? ` and ${bad.length - 5} more` : ""}. The % column is over the counted `
    + "tests, not the shown ones.";
}

/**
 * The one line that says what is waiting on whom, across the whole chart.
 *
 * `complete_pct` per row answers "how much has the Owner signed off", and nothing answered "how
 * much is sitting in the gap" — which is the chart's only actionable total.
 */
export function cxHandoffNote(mx: CxMatrix): string | null {
  const tests = mx.systems.reduce((n, s) => n + s.tests, 0);
  if (!tests) return null;
  const tested = mx.systems.reduce((n, s) => n + s.tested, 0);
  const accepted = mx.systems.reduce((n, s) => n + s.accepted, 0);
  const cond = mx.systems.reduce((n, s) => n + s.conditional, 0);
  const failed = mx.systems.reduce((n, s) => n + s.failed, 0);
  const bits = [`${tests} test(s)`, `${tested} tested`, `${accepted} accepted`];
  const waiting = tested - accepted;
  if (waiting > 0) bits.push(`${waiting} awaiting Owner acceptance`);
  if (tests - tested > 0) bits.push(`${tests - tested} not started`);
  if (cond) bits.push(`${cond} conditional`);
  if (failed) bits.push(`${failed} failed`);
  return bits.join(" · ");
}

/** A row's `%` with the basis it is over, since `complete_pct` is OWNER acceptance. */
export function cxRowPct(s: CxMatrixRow): string {
  return `${s.complete_pct}% accepted`;
}
