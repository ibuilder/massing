/**
 * SQL-CAP — the data browser prints its own row cap as a total, and the cap cannot be raised.
 *
 * `POST /connections/{cid}/query` is the read-only SELECT console in the Data-connections modal, and
 * the one screen in this product whose entire job is *look at the actual rows*. `connectors.query`
 * wraps the caller's SQL as `SELECT * FROM (<sql>) AS _q LIMIT {limit}` and returns
 * `row_count = len(rows)` — the length of the page, computed after the cap. `connectionsUI.ts`
 * rendered that as `` `${r.row_count} rows` ``, and passed a hardcoded `200` where the server clamps
 * to `min(limit, 1000)`.
 *
 * **The two responses are identical, and that is the finding.** Measured against a live route on a
 * seeded SQLite connection:
 *
 * | query | rows in the table | response |
 * |---|---|---|
 * | `SELECT * FROM big` | 5,000 | `{row_count: 200, limit: 200}` |
 * | `SELECT * FROM exact200` | 200 | `{row_count: 200, limit: 200}` |
 *
 * A table holding twenty-five times what was shown and a table shown in full came back byte-for-byte
 * the same, and the console printed **"200 rows"** over both. That is WAIVER-FLAT's shape — two
 * states the screen cannot distinguish because the response does not distinguish them — and it is
 * why `row_count >= limit` is not a fix: *an equality cannot separate two equal things.* The server
 * now fetches `limit + 1`, returns the first `limit`, and reports `truncated` as a fact, so the
 * caller is handed the distinction instead of guessing at it.
 *
 * **And the preview buttons are the worst case, not the edge case.** The table list renders one
 * button per table that runs `SELECT * FROM "<name>"` — an unbounded select on a real table, which
 * is precisely the query most likely to exceed the cap. The default path through this screen is the
 * one the cap hides.
 *
 * **The cap was also unraisable.** The console passed `200` with no control, so no query a user could
 * type reached past it: an inner `LIMIT 1000` is still wrapped by the outer `LIMIT 200`. Reporting
 * truncation honestly while leaving the user no way to act on it would have been half a fix, so the
 * row limit is selectable up to the server's own clamp.
 *
 * **`ledgerBrowse.ts` next door already names this class, for the other routes in the same modal.**
 * Its rule 2 is *"QuickBooks `count` is capped at 50 … so `count: 50` from QuickBooks is a floor, not
 * a total, and a company with 200 accounts sees 50 with no indication."* That was written for the
 * accounting reads while the SQL console one function away kept printing its cap as a total. *A
 * lesson learned on one route in a file is not a sweep of the file* — and the sibling module is the
 * reason this one exists in the same shape rather than as more inline string building.
 */

/** The hard clamp in `connectors.query`: `limit = max(1, min(int(limit or 200), 1000))`. */
import type { SqlQueryResponse } from "../api/connections";

/** Re-exported so a consumer of this module needs one import, not two. The shape is DECLARED once,
 *  in the api layer that owns the wire contract — a second copy here is what
 *  `api/noRespelledShapes.test.ts` exists to refuse. */
export type { SqlQueryResponse };

export const SERVER_MAX_LIMIT = 1000;

/** The server's own default, and what the console asked for before it could ask for anything else. */
export const DEFAULT_LIMIT = 200;

/** What the console offers. Bounded by `SERVER_MAX_LIMIT` — a higher choice would be clamped
 *  silently, which is the defect this module exists to remove, arriving from the other side. */
export const LIMIT_CHOICES = [200, 500, 1000] as const;

export type SqlOutcome =
  | { state: "error"; message: string }
  | { state: "empty"; columns: string[] }
  | { state: "rows"; columns: string[]; rows: unknown[][] };

/**
 * Error, empty, or rows — and `error` is checked first, on its own.
 *
 * A rejected query (`only SELECT / WITH queries are allowed`) is **HTTP 200** with `{error}` and no
 * `rows`, so testing `rows?.length` first would render every refusal as a table that matched
 * nothing. The same reasoning as `ledgerBrowse.outcome`, against a different route's failure shape.
 *
 * `empty` keeps the columns, because a query that ran and matched no rows should still show what it
 * would have returned — the header row is the evidence that the query was understood.
 */
export function outcome(res: SqlQueryResponse): SqlOutcome {
  if (typeof res.error === "string" && res.error.trim()) {
    return { state: "error", message: res.error.trim() };
  }
  const columns = Array.isArray(res.columns) ? res.columns : [];
  const rows = Array.isArray(res.rows) ? res.rows : [];
  return rows.length ? { state: "rows", columns, rows } : { state: "empty", columns };
}

/** How many rows came back. `row_count` is the server's own count; the rows are the fallback for a
 *  response that carries them without it, so the two can never disagree on screen. */
export function rowCount(res: SqlQueryResponse): number {
  if (typeof res.row_count === "number" && Number.isFinite(res.row_count)) return res.row_count;
  return Array.isArray(res.rows) ? res.rows.length : 0;
}

/** The cap this read ran under, falling back to the server's default when it is not reported. */
export function capOf(res: SqlQueryResponse): number {
  const n = res.limit;
  return typeof n === "number" && Number.isFinite(n) && n > 0 ? n : DEFAULT_LIMIT;
}

/**
 * Were rows discarded?
 *
 * `truncated` is the server's answer and is preferred whenever it is present. The fallback is the
 * old comparison, kept for a response that predates the flag — and it is reachable by this module's
 * own type, where every key is optional. It is deliberately the CONSERVATIVE reading: at the cap
 * with no flag, assume there may be more, because the alternative is the measurement above, where a
 * full table and a quarter-of-one-percent sample were the same bytes.
 */
export function isTruncated(res: SqlQueryResponse): boolean {
  if (typeof res.truncated === "boolean") return res.truncated;
  return rowCount(res) >= capOf(res);
}

/** True when truncation is being INFERRED rather than reported — the caption hedges in that case. */
export function truncationInferred(res: SqlQueryResponse): boolean {
  return typeof res.truncated !== "boolean" && rowCount(res) >= capOf(res);
}

/**
 * What the count actually means. Never the bare number.
 *
 * Three wordings, because there are three states and the screen had one: the whole result, a read
 * the server says was cut, and a read at the cap whose completeness is unknown. The third exists
 * only for a response with no `truncated` flag; against this server it is unreachable, and it is
 * here so that an absent flag cannot be read as "not truncated".
 */
export function rowCountLine(res: SqlQueryResponse): string {
  const n = rowCount(res);
  const cap = capOf(res);
  const unit = `${n} row${n === 1 ? "" : "s"}`;
  if (truncationInferred(res)) {
    return `${unit} — this read is AT the ${cap}-row cap and the server did not say whether more `
      + "were discarded, so treat it as a sample, not a total.";
  }
  if (isTruncated(res)) {
    return `${unit} shown — the result is LONGER than the ${cap}-row cap and the rest were `
      + "discarded. This is a sample, not a total: raise the row limit, add a WHERE clause, or "
      + "count with `SELECT count(*)`.";
  }
  return `${unit} — the whole result (under the ${cap}-row cap).`;
}

/** Wording for a refused or failed query, kept distinct from a query that matched nothing. */
export function errorLine(message: string): string {
  return `Query not run: ${message}. Nothing was read, so this says nothing about the table.`;
}

/** Wording for a query that ran and matched nothing — a real answer about the data. */
export function emptyLine(): string {
  return "The query ran and matched no rows. That is an answer about the data, not a failed read.";
}
