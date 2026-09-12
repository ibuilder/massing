import { describe, expect, it } from "vitest";

import {
  ENTITIES, QB_PAGE, countLine, emptyLine, errorLine, outcome, rowId, rowLabel, vendorFor,
} from "./ledgerBrowse";

describe("which connections keep books", () => {
  it("maps the three vendor types, and only those", () => {
    expect(vendorFor("quickbooks")).toBe("quickbooks");
    expect(vendorFor("sage")).toBe("erp");
    expect(vendorFor("viewpoint")).toBe("erp");
    for (const t of ["postgres", "supabase", "procore", "acc", "local", ""]) {
      expect(vendorFor(t), `${t} keeps no ledger`).toBeNull();
    }
  });

  it("offers only the entities the server accepts", () => {
    // The route 400s on anything else; offering a fourth would build a button that cannot work.
    expect([...ENTITIES]).toEqual(["accounts", "vendors", "bills"]);
  });
});

describe("a failed read is never an empty ledger", () => {
  it("classifies a body-level error as an error, though the HTTP status was 200", () => {
    // The route catches the vendor exception and returns {"error": …} with 200. `rows` is absent,
    // so a check that looked at rows first would call this "no records".
    const r = outcome({ error: "401 Unauthorized" }, "accounts");
    expect(r.state).toBe("error");
    if (r.state === "error") expect(r.message).toBe("401 Unauthorized");
  });

  it("does not treat an error as empty even when an empty row list is ALSO present", () => {
    expect(outcome({ error: "token expired", accounts: [] }, "accounts").state).toBe("error");
  });

  it("ignores a blank error string — that is not a failure", () => {
    expect(outcome({ error: "   ", accounts: [{ Name: "Cash" }] }, "accounts").state).toBe("rows");
  });

  it("reports a genuine empty as empty", () => {
    expect(outcome({ kind: "quickbooks-accounts", count: 0, accounts: [] }, "accounts").state).toBe("empty");
  });

  it("treats a missing row key as empty, not as rows", () => {
    expect(outcome({ kind: "sage-bills", count: 0 }, "bills").state).toBe("empty");
  });

  it("drops non-object entries rather than rendering them", () => {
    const r = outcome({ accounts: [null, "oops", { Name: "Cash" }] }, "accounts");
    expect(r.state).toBe("rows");
    if (r.state === "rows") expect(r.rows).toEqual([{ Name: "Cash" }]);
  });

  it("the two failure wordings cannot be mistaken for each other", () => {
    const err = errorLine("quickbooks", "401 Unauthorized");
    const empty = emptyLine("accounts");
    expect(err).toMatch(/NOT an empty ledger/);
    expect(empty).toMatch(/real answer/);
    expect(err).not.toEqual(empty);
  });
});

describe("the count means different things on the two routes", () => {
  it("flags a full QuickBooks page as a possible truncation, not a total", () => {
    const line = countLine("quickbooks", "accounts", QB_PAGE);
    expect(line).toMatch(/maximum/);
    expect(line).toMatch(/no paging/);
    expect(line).toMatch(/sample, not a total/);
  });

  it("...and a short QuickBooks read as the whole ledger", () => {
    const line = countLine("quickbooks", "accounts", 12);
    expect(line).toMatch(/whole ledger/);
    expect(line).not.toMatch(/sample/);
  });

  it("never claims the ERP read is capped — it is not capped HERE", () => {
    const line = countLine("erp", "bills", 50);
    expect(line).not.toMatch(/maximum/);
    expect(line).toMatch(/not capped here/);
  });

  it("the same number reads differently by vendor, which is the whole point", () => {
    expect(countLine("quickbooks", "accounts", QB_PAGE)).not.toEqual(countLine("erp", "accounts", QB_PAGE));
  });

  it("a count ABOVE the page size is still flagged — the cap is a floor, not an equality", () => {
    // Defensive: if the server ever pages, a larger count must not silently read as a clean total.
    expect(countLine("quickbooks", "accounts", 120)).toMatch(/maximum/);
  });
});

describe("row keys are vendor-cased", () => {
  it("reads Intuit's capitalised keys", () => {
    expect(rowLabel({ Name: "Checking" })).toBe("Checking");
    expect(rowId({ Id: "42" })).toBe("42");
  });

  it("reads a generic ERP's lowercase keys", () => {
    expect(rowLabel({ name: "Checking" })).toBe("Checking");
    expect(rowId({ id: "42" })).toBe("42");
  });

  it("prefers the first present key rather than depending on object order", () => {
    expect(rowLabel({ name: "lower", Name: "Upper" })).toBe("Upper");
    expect(rowLabel({ Name: "Upper", name: "lower" })).toBe("Upper");
  });

  it("takes a numeric id, which JSON allows and the string check would drop", () => {
    expect(rowId({ id: 7 })).toBe("7");
  });

  it("says a row is unnamed rather than rendering a blank cell", () => {
    expect(rowLabel({ Id: "9" })).toBe("(unnamed · 9)");
    expect(rowLabel({})).toBe("(unnamed)");
    expect(rowLabel({ Name: "   " })).toBe("(unnamed)");
  });

  it("returns an empty id rather than inventing one", () => {
    expect(rowId({})).toBe("");
    expect(rowId({ Id: "  " })).toBe("");
  });
});
