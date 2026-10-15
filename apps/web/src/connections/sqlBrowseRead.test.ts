import { describe, expect, it } from "vitest";

import {
  DEFAULT_LIMIT, LIMIT_CHOICES, SERVER_MAX_LIMIT, capOf, emptyLine, errorLine, isTruncated,
  outcome, rowCount, rowCountLine, truncationInferred,
  type SqlQueryResponse,
} from "./sqlBrowseRead";

/** The two responses measured against a live route: a 5,000-row table and a 200-row table, read at
 *  the console's cap of 200. Before the server reported `truncated` these were byte-identical. */
const BIG_AT_CAP: SqlQueryResponse = {
  columns: ["id", "name"], rows: Array.from({ length: 200 }, (_, i) => [i + 1, `row-${i + 1}`]),
  row_count: 200, limit: 200, truncated: true,
};
const WHOLE_AT_CAP: SqlQueryResponse = {
  columns: ["id"], rows: Array.from({ length: 200 }, (_, i) => [i + 1]),
  row_count: 200, limit: 200, truncated: false,
};

describe("outcome", () => {
  it("classifies a refusal as an error, not as a table that matched nothing", () => {
    // The server returns HTTP 200 with this body — `rows` is absent, so a rows-first check would
    // report "no rows" for a query that never ran.
    const r = outcome({ error: "only SELECT / WITH queries are allowed" });
    expect(r.state).toBe("error");
    expect(r.state === "error" && r.message).toBe("only SELECT / WITH queries are allowed");
  });

  it("does not treat a blank error string as a failure", () => {
    expect(outcome({ error: "   ", columns: ["a"], rows: [[1]] }).state).toBe("rows");
  });

  it("keeps the columns on an empty result, so the header still shows what was asked", () => {
    const r = outcome({ columns: ["id", "name"], rows: [], row_count: 0, limit: 200 });
    expect(r.state).toBe("empty");
    expect(r.state === "empty" && r.columns).toEqual(["id", "name"]);
  });

  it("survives a response carrying neither columns nor rows", () => {
    const r = outcome({});
    expect(r.state).toBe("empty");
    expect(r.state === "empty" && r.columns).toEqual([]);
  });

  it("returns the rows and the columns together", () => {
    const r = outcome(BIG_AT_CAP);
    expect(r.state).toBe("rows");
    expect(r.state === "rows" && r.rows.length).toBe(200);
    expect(r.state === "rows" && r.columns).toEqual(["id", "name"]);
  });
});

describe("rowCount / capOf", () => {
  it("prefers the server's count", () => {
    expect(rowCount({ row_count: 7, rows: [[1], [2]] })).toBe(7);
  });

  it("falls back to the rows when no count was sent", () => {
    expect(rowCount({ rows: [[1], [2]] })).toBe(2);
    expect(rowCount({})).toBe(0);
  });

  it("ignores a non-finite count rather than printing NaN", () => {
    expect(rowCount({ row_count: Number.NaN, rows: [[1]] })).toBe(1);
  });

  it("falls back to the server default cap, and refuses a nonsense one", () => {
    expect(capOf({})).toBe(DEFAULT_LIMIT);
    expect(capOf({ limit: 0 })).toBe(DEFAULT_LIMIT);
    expect(capOf({ limit: 1000 })).toBe(1000);
  });
});

describe("isTruncated", () => {
  // This is the whole point of the server change: the two measured responses differ ONLY in the
  // flag, so nothing computed from `row_count` and `limit` can separate them.
  it("separates the two responses an equality cannot", () => {
    expect(rowCount(BIG_AT_CAP)).toBe(rowCount(WHOLE_AT_CAP));
    expect(capOf(BIG_AT_CAP)).toBe(capOf(WHOLE_AT_CAP));
    expect(isTruncated(BIG_AT_CAP)).toBe(true);
    expect(isTruncated(WHOLE_AT_CAP)).toBe(false);
  });

  it("believes a reported `false` at the cap over its own comparison", () => {
    expect(isTruncated({ row_count: 200, limit: 200, truncated: false })).toBe(false);
    expect(truncationInferred({ row_count: 200, limit: 200, truncated: false })).toBe(false);
  });

  it("assumes there may be more when the flag is absent and the read is at the cap", () => {
    expect(isTruncated({ row_count: 200, limit: 200 })).toBe(true);
    expect(truncationInferred({ row_count: 200, limit: 200 })).toBe(true);
  });

  it("is false below the cap with no flag", () => {
    expect(isTruncated({ row_count: 7, limit: 200 })).toBe(false);
    expect(truncationInferred({ row_count: 7, limit: 200 })).toBe(false);
  });
});

describe("rowCountLine", () => {
  it("says sample, names the cap, and says what to do about it when rows were discarded", () => {
    const line = rowCountLine(BIG_AT_CAP);
    expect(line).toContain("200 rows shown");
    expect(line).toContain("LONGER than the 200-row cap");
    expect(line).toContain("sample, not a total");
    expect(line).toMatch(/raise the row limit/);
  });

  it("calls a complete read at the cap the whole result", () => {
    expect(rowCountLine(WHOLE_AT_CAP)).toBe("200 rows — the whole result (under the 200-row cap).");
  });

  it("gives the two measured responses DIFFERENT text", () => {
    // The defect was that these were the same pixels. Asserting the wordings differ is asserting
    // the fix at the only place a user meets it.
    expect(rowCountLine(BIG_AT_CAP)).not.toBe(rowCountLine(WHOLE_AT_CAP));
  });

  it("hedges when truncation is inferred rather than reported", () => {
    const line = rowCountLine({ row_count: 200, limit: 200 });
    expect(line).toContain("AT the 200-row cap");
    expect(line).toContain("did not say");
    expect(line).not.toContain("LONGER");
  });

  it("reports the whole result under the cap, with the cap named", () => {
    expect(rowCountLine({ row_count: 7, limit: 1000, truncated: false }))
      .toBe("7 rows — the whole result (under the 1000-row cap).");
  });

  it("is singular at one row", () => {
    expect(rowCountLine({ row_count: 1, limit: 200, truncated: false })).toContain("1 row —");
  });

  it("does not print undefined when the server sent no count", () => {
    expect(rowCountLine({ columns: ["n"], rows: [], truncated: false })).toContain("0 rows");
  });
});

describe("wording that must never collapse", () => {
  it("keeps a failed read and an empty one apart", () => {
    expect(errorLine("no such table: foo")).not.toBe(emptyLine());
    expect(errorLine("no such table: foo")).toContain("says nothing about the table");
    expect(emptyLine()).toContain("not a failed read");
  });
});

describe("the limit choices", () => {
  it("never offers more than the server will honour", () => {
    // A choice above the clamp would be silently reduced — the same defect from the other side.
    for (const n of LIMIT_CHOICES) expect(n).toBeLessThanOrEqual(SERVER_MAX_LIMIT);
    expect(LIMIT_CHOICES[0]).toBe(DEFAULT_LIMIT);
    expect(LIMIT_CHOICES).toContain(SERVER_MAX_LIMIT);
  });
});
