import type { OptionRecord, OptionRecordSet } from "../../api/types";

/**
 * OPTION-DISAGREE — the scheme being quoted at a return its own deal does not solve to.
 *
 * `option_economics`'s module header names this finding itself: *"A scheme whose typed IRR is 400
 * bps above what its own scenario solves to is the single most useful thing this module can
 * surface, and it can only be surfaced by keeping both."* The engine does keep both, computes
 * `agrees_with_declared` per option, and publishes the named list as
 * `declared_disagrees_with_derived` — on `GET /projects/{pid}/design/options/economics`, which has
 * **no caller anywhere in `apps/web/src`** and is frozen in
 * `services/api/test_route_reachability.py` as uncalled.
 *
 * ## What the one wired route showed instead
 *
 * `/design/options/record` is the join the three option routes feed, and it is deliberately the
 * only one a screen calls — *"the record IS the join over the other three, so calling it replaces
 * reconciling three screens by eye rather than adding a fourth"*. Measured on two schemes sharing
 * one proforma scenario, one typing nothing and one typing 45.0% against a solved 32.16%:
 *
 * | option | typed | solved | record showed |
 * |---|---|---|---|
 * | A — linked | — | 32.16 | `returns 32.16 · economics: derived` |
 * | B — optimistic | **45.0** | 32.16 | `returns 32.16 · economics: derived` |
 *
 * **Byte-identical, on the screen where a scheme is chosen**, with 1,284 basis points of
 * disagreement between B's typed figure and its own deal. The join kept `economics_basis` for
 * exactly the right reason — its own comment says dropping it *"would turn a benchmarked carbon
 * figure and a measured one into the same number"* — and then dropped the stronger version of the
 * same concern. *A basis says how the number was got; it cannot say that somebody is quoting a
 * different one.*
 *
 * ## Widening the join, not wiring the dark route
 *
 * The fix carries `declared_returns`, `returns_agree` and `returns_delta_pct` through
 * `option_object.join`, which already reads the economics row — no new computation, and no fourth
 * screen. Wiring `/design/options/economics` would have added a second answer to one question,
 * which is the triage `test_route_reachability`'s own freeze note teaches: *a dark route can be a
 * duplicate rather than a hole, and the gate cannot tell the difference.* Here it was neither — the
 * route is a duplicate of everything except one field, and that field was the point of the module.
 *
 * Every function here returns PLAIN TEXT: `design.ts` interpolates into `innerHTML`, and
 * `apps/web/src/ui/innerHtmlGuard.test.ts` is the ratchet.
 */

/** Signed basis points, as a reader of a deal memo writes them. */
function bps(delta: number): string {
  return `${delta > 0 ? "+" : ""}${Math.round(delta * 100)} bps`;
}

/**
 * The banner line, or `null` when no scheme is being quoted against its own deal.
 *
 * Absent rather than a zero line: "0 options disagree" over a project with no typed figures at all
 * is a tick for a check nobody ran, which is the shape half this session's findings have had.
 */
export function disagreeBanner(r: OptionRecordSet): string | null {
  const n = r.declared_disagrees_count ?? 0;
  if (!n) return null;
  const worst = [...(r.declared_disagrees ?? [])]
    .sort((a, b) => Math.abs(b.delta_pct ?? 0) - Math.abs(a.delta_pct ?? 0))[0];
  const lead = `${n} scheme${n === 1 ? " is" : "s are"} carrying a typed return their own proforma `
    + "scenario does not solve to";
  if (!worst || worst.delta_pct == null) return `${lead}.`;
  return `${lead} — widest is ${worst.name} at ${worst.declared_returns?.toFixed(1)}% typed `
    + `against ${worst.derived_returns?.toFixed(1)}% solved, ${bps(worst.delta_pct)}.`;
}

/** One row's returns cell: the figure, and the typed one beside it when they disagree. */
export function returnsCell(o: OptionRecord): string {
  const v = o.axes?.returns;
  if (v == null) return "—";
  const shown = `${v.toFixed(1)}%`;
  // A typed figure that AGREES is not worth the ink: the basis column already says `derived`, and
  // printing both when they match trains the reader to skip the pair when they do not.
  if (o.returns_agree !== false) return shown;
  const d = o.declared_returns;
  const delta = o.returns_delta_pct;
  return `${shown} (typed ${d == null ? "?" : `${d.toFixed(1)}%`}`
    + `${delta == null ? "" : `, ${bps(delta)}`})`;
}

/** The `title` for that cell — the marks above are not self-explaining. */
export function returnsCellTitle(o: OptionRecord): string {
  const v = o.axes?.returns;
  if (v == null) return "No return figure — absent, and not zero.";
  const basis = o.economics_basis ?? "unknown";
  if (o.returns_agree === false) {
    return `Solved ${v.toFixed(1)}% from this option's own proforma scenario; ${
      o.declared_returns?.toFixed(1)}% was typed on the option. The typed figure is shown but never `
      + "used — a scheme quoted above what its deal solves to is the thing worth checking first.";
  }
  if (o.returns_agree === true) {
    return `Solved ${v.toFixed(1)}%, and the figure typed on the option agrees with it.`;
  }
  return `${v.toFixed(1)}% · basis: ${basis}. Nothing typed on the option to compare it against.`;
}

/** The rows, worst disagreement first — the order a reader wants them in. */
export function disagreeRows(r: OptionRecordSet): {
  name: string; typed: string; solved: string; delta: string;
}[] {
  return [...(r.declared_disagrees ?? [])]
    .sort((a, b) => Math.abs(b.delta_pct ?? 0) - Math.abs(a.delta_pct ?? 0)
      || a.name.localeCompare(b.name))
    .map((x) => ({
      name: x.name,
      typed: x.declared_returns == null ? "—" : `${x.declared_returns.toFixed(1)}%`,
      solved: x.derived_returns == null ? "—" : `${x.derived_returns.toFixed(1)}%`,
      delta: x.delta_pct == null ? "—" : bps(x.delta_pct),
    }));
}

/** What `returns` is and what the typed figure is for. The engine's own sentence, verbatim. */
export function returnsBasisNote(r: OptionRecordSet): string {
  return r.returns_basis_note ?? "";
}
