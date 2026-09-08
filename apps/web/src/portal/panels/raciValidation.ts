import type { ResponsibilityMatrix } from "../../api/client";

/**
 * RESP-ORPHAN — the RACI rule, computed over the columns the user can actually SEE.
 *
 * ## Why this exists as its own module
 *
 * The rule lives in two languages and cannot be deduplicated across that boundary. The server
 * computes it in `services/api/src/aec_api/responsibility.py::_validate` and returns it as
 * `matrix.validation`; the panel needs it again locally because a cell edit repaints the banner
 * without a round-trip. Two copies of one rule is a defect waiting to happen, and it already had:
 * the panel's inline copy counted `Object.values(r.assignments)` — **every** assignment — while the
 * grid renders only `m.roles`.
 *
 * A role column can go away under rows that reference it. `apply_template` appends rows and used to
 * replace the columns; removing or renaming a column patches each row one request at a time, so a
 * failure part-way leaves the rest behind. Either way an assignment can end up keyed by a role that
 * is not a column — and it is then **invisible**, because the grid has no cell to draw it in. The
 * old count still saw it, so a row whose every letter had been orphaned reported *"exactly one
 * Accountable and at least one Responsible"* while the user looked at a blank line.
 *
 * So: `missing`/`noR` are counted over VISIBLE assignments only, and the orphans are reported
 * separately as `unknown` rather than discarded — that list is the only thing that explains why the
 * row looks empty. `load` is likewise over visible columns, since crediting a role that is not in
 * the matrix overstates a real person's ownership.
 *
 * ## Parity is asserted, not assumed
 *
 * `raciValidation.test.ts` runs the cases in `raciValidationCases.json`, and
 * `services/api/test_responsibility.py` is where the same rule is proved server-side. The shared
 * fixture is what stops the two implementations drifting apart again; extracting this function from
 * the panel is what makes it testable at all.
 */
export interface RaciVerdict {
  /** Rows without exactly one Accountable, counted over visible columns. */
  missing: { ref: string | null; activity: string; count: number }[];
  /** Rows with no doer (R in RACI, D in DACI), counted over visible columns. */
  noR: { ref: string | null; activity: string }[];
  /** Assignments keyed by a role that is not a column — invisible in the grid. */
  unknown: { ref: string | null; activity: string; role: string; letter: string }[];
  /** How many activities each visible role is Accountable for. */
  load: Record<string, number>;
  /** The rule verdict. Orphans are reported but do not by themselves make a row invalid. */
  clean: boolean;
}

/**
 * Role columns a matrix may carry. **Mirrors `MAX_ROLES` in
 * `services/api/src/aec_api/responsibility.py`**, which truncates any longer list rather than
 * refusing it — so a caller that sends more silently loses the tail. `test_responsibility.py`
 * asserts the two constants agree, because a client guard set to the wrong number is worse than
 * no guard: it would refuse valid restores while still letting the real overflow through.
 */
export const MAX_ROLES = 16;

export function validateMatrix(m: ResponsibilityMatrix): RaciVerdict {
  const roles = new Set(m.roles ?? []);
  const missing: RaciVerdict["missing"] = [];
  const noR: RaciVerdict["noR"] = [];
  const unknown: RaciVerdict["unknown"] = [];
  const load: Record<string, number> = {};
  for (const r of m.rows ?? []) {
    const entries = Object.entries(r.assignments ?? {});
    const visible = entries.filter(([role]) => roles.has(role));
    const a = visible.filter(([, v]) => v === "A").length;
    const d = visible.filter(([, v]) => v === m.doer).length;
    if (a !== 1) missing.push({ ref: r.ref ?? null, activity: r.activity, count: a });
    if (d < 1) noR.push({ ref: r.ref ?? null, activity: r.activity });
    for (const [role, letter] of entries) {
      if (!roles.has(role)) unknown.push({ ref: r.ref ?? null, activity: r.activity, role, letter });
      else if (letter === "A") load[role] = (load[role] ?? 0) + 1;
    }
  }
  return { missing, noR, unknown, load, clean: !missing.length && !noR.length };
}

/** The distinct role names that rows reference but the matrix has no column for. */
export function orphanedRoles(v: RaciVerdict): string[] {
  return [...new Set(v.unknown.map((u) => u.role))].sort();
}
