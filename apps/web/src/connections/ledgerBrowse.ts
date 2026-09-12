/**
 * LEDGER-BROWSE — reading an accounting connection's books, and saying what the reading is worth.
 *
 * `GET /connections/{cid}/quickbooks/{entity}` and `GET /connections/{cid}/erp/{entity}` have been
 * finished server-side and callable by nothing. They were dark for two different reasons, and only
 * one of them was visible: `erp`'s leaf is three characters, under the reachability gate's
 * `MIN_SEGMENT`, so the short-leaf ratchet held it. `quickbooks` is ten characters, IS assessed,
 * and the gate believed it called — off the string `"quickbooks"` in `connectionsUI.ts`'s
 * connection-TYPE `<select>`. A product vocabulary word, not a URL.
 *
 * Three rules below, and each exists because the server's answer and the obvious rendering of it
 * say different things.
 *
 * 1. **A vendor failure is HTTP 200 with `{"error": …}`.** The route catches the vendor exception
 *    and returns the message in the body, so `res.ok` is true and `rows` is absent. Rendering that
 *    as an empty table tells an accountant their books are EMPTY when the truth is that we could
 *    not read them. Those two states must never reach the same pixels — `outcome()` refuses to
 *    collapse them.
 *
 * 2. **QuickBooks `count` is capped at 50 and there is no pagination.** `_qb_query` issues
 *    `select * from <Entity> maxresults 50`; nothing pages past it. So `count: 50` from QuickBooks
 *    is a floor, not a total, and a company with 200 accounts sees 50 with no indication. The ERP
 *    read is uncapped and tenant-dependent, so **the same field means different things on the two
 *    routes** and the caller must be told which one it is looking at.
 *
 * 3. **Row keys are vendor-cased.** QuickBooks returns Intuit's `Name` / `Id`; the generic ERP read
 *    returns whatever the tenant emits, which is why `_info_erp` on the server already hedges with
 *    `a.get("name") or a.get("Name")`. A renderer that assumes one casing silently blanks the other
 *    vendor's column — the COL-PAIR defect class.
 */

/** The three vendors whose connections carry books. `erp` covers Sage and Viewpoint alike. */
export type LedgerVendor = "quickbooks" | "erp";

/** What the route can return. `count` and the rows live under the entity's own name. */
export interface LedgerResponse {
  kind?: string;
  count?: number;
  error?: string;
  [entity: string]: unknown;
}

export type LedgerOutcome =
  | { state: "error"; message: string }
  | { state: "empty" }
  | { state: "rows"; rows: Record<string, unknown>[] };

/** Which vendor a connection type reads its books through, or null if it keeps none. */
export function vendorFor(connectionType: string): LedgerVendor | null {
  if (connectionType === "quickbooks") return "quickbooks";
  if (connectionType === "sage" || connectionType === "viewpoint") return "erp";
  return null;
}

/**
 * Error, empty, or rows — never error silently becoming empty.
 *
 * The `error` key is checked FIRST and on its own. A response carrying both an error and an absent
 * row list is the normal failure shape, so testing `rows?.length` first would classify every
 * vendor failure as "no records".
 */
export function outcome(res: LedgerResponse, entity: string): LedgerOutcome {
  if (typeof res.error === "string" && res.error.trim()) {
    return { state: "error", message: res.error.trim() };
  }
  const raw = res[entity];
  if (!Array.isArray(raw)) return { state: "empty" };
  const rows = raw.filter((r): r is Record<string, unknown> => !!r && typeof r === "object");
  return rows.length ? { state: "rows", rows } : { state: "empty" };
}

/** The QuickBooks page size the server asks Intuit for. Not configurable, and not paged past. */
export const QB_PAGE = 50;

/**
 * What the count actually means — which differs by vendor, so it is never printed bare.
 *
 * At exactly `QB_PAGE` on QuickBooks the number is indistinguishable from a truncation, and saying
 * "50 accounts" there is a claim about someone's books that the request cannot support.
 */
export function countLine(vendor: LedgerVendor, entity: string, count: number): string {
  if (vendor === "quickbooks" && count >= QB_PAGE) {
    return `${count} ${entity} shown — this is the maximum a single read returns (${QB_PAGE}), `
      + "and there is no paging, so the ledger may hold more. Treat it as a sample, not a total.";
  }
  if (vendor === "quickbooks") return `${count} ${entity} — the whole ledger (under the ${QB_PAGE}-row read limit).`;
  return `${count} ${entity}, as returned by the tenant. This read is not capped here; if the ERP `
    + "itself paginates, its own default applies.";
}

/** Human wording for a failed read, kept distinct from an empty one. */
export function errorLine(vendor: LedgerVendor, message: string): string {
  const who = vendor === "quickbooks" ? "QuickBooks" : "the ERP";
  return `Could not read ${who}: ${message}. This is NOT an empty ledger — nothing was returned, `
    + "so no conclusion about the books follows from it.";
}

/** Wording for a genuinely empty read, kept distinct from a failed one. */
export function emptyLine(entity: string): string {
  return `The connection answered, and reported no ${entity}. That is a real answer about the `
    + "ledger, not a failed request.";
}

/**
 * One row's display name, tolerant of both vendors' casing.
 *
 * Intuit capitalises; a generic REST ERP usually does not. Checked in order and stopping at the
 * first present key, so a row carrying both does not depend on object order.
 */
export function rowLabel(row: Record<string, unknown>): string {
  for (const k of ["Name", "name", "DisplayName", "displayName", "FullyQualifiedName", "title"]) {
    const v = row[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const id = rowId(row);
  return id ? `(unnamed · ${id})` : "(unnamed)";
}

/** One row's identifier, same tolerance. Returns "" when the vendor sent none. */
export function rowId(row: Record<string, unknown>): string {
  for (const k of ["Id", "id", "ID", "code", "Code", "number"]) {
    const v = row[k];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number") return String(v);
  }
  return "";
}

/** The entities both routes accept. The server 400s on anything else, so the UI offers only these. */
export const ENTITIES = ["accounts", "vendors", "bills"] as const;
