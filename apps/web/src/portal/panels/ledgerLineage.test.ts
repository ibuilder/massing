import { describe, expect, it } from "vitest";

import { lineageHeading } from "./ledger";

/** The ledger's "Import lineage" heading decision.
 *
 *  This exists because of a defect that TYPECHECKED. `GET /projects/{pid}/finance/imports` was
 *  changed from a bare array to an envelope so a capped window could say it was capped; the panel
 *  still asked `imports.length`, which on an object is `undefined`. Falsy. The entire lineage
 *  section vanished from the ledger while imports existed — the exact "nothing here while
 *  something is there" failure the server-side change was fixing, reintroduced one layer up by the
 *  fix itself.
 *
 *  `tsc` could not see it: the client's return type is a hand-written claim about what the server
 *  sends, not a derivation from it, so both sides typechecked while disagreeing. A review bot found
 *  it. What stops it recurring is that the decision is named and asserted here rather than being a
 *  truthiness check inside a `try`. */
describe("lineageHeading", () => {
  it("draws nothing when there are no batches", () => {
    expect(lineageHeading({ imports: [], import_total: 0, truncated: false })).toBeNull();
  });

  it("THE DEFECT: an envelope of batches draws, it does not read as empty", () => {
    // The pre-fix panel asked `history.length` here and got undefined, so this section — the
    // answer to "where did these numbers come from" — was simply absent from the page.
    expect(lineageHeading({ imports: [{ filename: "budget.csv" }], import_total: 1,
      truncated: false })).toBe("Import lineage");
  });

  it("says so when it is a window rather than the whole history", () => {
    expect(lineageHeading({ imports: Array(100).fill({ filename: "b.csv" }), import_total: 150,
      truncated: true })).toBe("Import lineage — newest 100 of 150");
  });

  it("survives a response missing the array entirely rather than throwing", () => {
    // A stale server, or a failed shape assumption like the one above: report nothing, don't crash
    // the whole ledger panel on a section that is context.
    expect(lineageHeading({})).toBeNull();
  });
});
