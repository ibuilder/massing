/** SET-REVISED — the controlled register issued a twice-revised sheet as "New".
 *
 *  `drawingset.register` classified issuance by counting drawing RECORDS per sheet number —
 *  `change = "new" if len(revs) == 1` — while `revise` keeps ONE record per sheet and appends to
 *  `data["revisions"]`. So a sheet revised twice through this application's own endpoint, with ASI
 *  and CCD deltas recorded against it, came back:
 *
 *  | | before | corrected |
 *  |---|---|---|
 *  | `sheet_index[].revisions` | **1** | 2 |
 *  | `sheet_index[].change` | **new** | revised |
 *  | `revised_count` | **0** | 1 |
 *  | `superseded_count` | **0** | 1 |
 *
 *  while `revisions()`, reading the same `data["revisions"]` in the same file, reported both deltas
 *  with their instruments. **Two engines over one record, disagreeing about whether the sheet had
 *  ever been revised** — and `transmittal_pdf` renders `change.title()` as the issuance column, so
 *  the transmittal told subcontractors a revised sheet was New. That flag is what decides whether a
 *  sub re-checks their shop drawings against it.
 *
 *  ### Why nothing went red, which is the part worth keeping
 *
 *  The one test of this classification builds its sheet as three SEPARATE drawing records — the
 *  drawing-log import model, which is the model `register` was written for. The test that sets up
 *  the delta model read only `/drawing-set/revisions`, the route that handles it. *A test that
 *  exercises one of two data models cannot see a function that handles only that one, and a handoff
 *  each side tests alone is a handoff nobody tests.*
 *
 *  ### The ordering question is reported, not answered
 *
 *  Across records the register has only labels to rank, and `_rev_key`'s docstring claimed numeric
 *  sorted after alpha while the body did the reverse — so a sheet whose records read `1, 2, A, B`
 *  named rev `2` current and listed `A` and `B` as "superseded by 2". Which kind is later is a firm
 *  convention, not a fact these labels state, so `order_ambiguous_sheets` names the sheets where
 *  the register's ranking is load-bearing instead of either guess being made silently.
 */
import type { DrawingRegister, DrawingRevision } from "./api/drawingSet";

/** The issuance headline. Never a bare "N new" without what "new" was counted over. */
export function issuanceLine(d: DrawingRegister): string {
  const sheets = d.sheet_count || 0;
  if (!sheets) return "No sheets in the set yet.";
  const parts = [`${d.current_count} current of ${sheets} sheet${sheets === 1 ? "" : "s"}`];
  parts.push(`${d.new_count} never revised`);
  if (d.revised_count) parts.push(`${d.revised_count} revised`);
  if (d.superseded_count) {
    parts.push(`${d.superseded_count} superseded revision${d.superseded_count === 1 ? "" : "s"}`);
  }
  return parts.join(" · ");
}

/** The superseded revisions, newest sheet-wise, as table rows. The dark half of this item: the
 *  register has always known which revisions a sheet had and no screen could show them. */
export function supersededRows(d: DrawingRegister): string[][] {
  return (d.superseded || []).map((r) => [
    r.sheet_number ?? "",
    r.revision ?? "—",
    r.superseded_by ?? "—",
    r.rev_date ?? "",
    r.description ?? "",
    r.instrument?.ref ?? "",
  ]);
}

/** The ordering caveat, or null when every sheet's order is recorded rather than ranked. */
export function orderWarning(d: DrawingRegister): string | null {
  const sheets = d.order_ambiguous_sheets || [];
  if (!sheets.length) return null;
  // The engine's own sentence, plus the sheets it is about — a reader told the order is a guess
  // needs to know WHICH sheets to check before issuing.
  const named = sheets.slice(0, 8).join(", ") + (sheets.length > 8 ? `, +${sheets.length - 8} more` : "");
  return `${d.order_note} Sheets: ${named}`;
}

/** True when something on this register should be checked before the set is issued. */
export function registerSuspect(d: DrawingRegister): boolean {
  return (d.order_ambiguous_sheets || []).length > 0;
}

/** A sheet's own revision history, oldest first — its superseded revisions then its current one.
 *  Derived from the two lists rather than from a third response field: the register already states
 *  both, and a third copy is a third thing to keep in agreement. */
export function sheetHistory(d: DrawingRegister, sheet: string): DrawingRevision[] {
  const older = (d.superseded || []).filter((r) => r.sheet_number === sheet);
  const cur = (d.current_set || []).filter((r) => r.sheet_number === sheet);
  return [...older, ...cur];
}
