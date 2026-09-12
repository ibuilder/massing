import { describe, expect, it } from "vitest";

import {
  type VendorRow, attributionLine, coiLine, isReassuring, lienExposure, ordered, summaryLine,
  verdictTone,
} from "./vendorScorecard";

const row = (over: Partial<VendorRow> = {}): VendorRow => ({
  vendor: "Acme Steel", verdict: "clear", project_count: 1, subcontract_value: 0, committed: 0,
  spent: 0, invoiced: 0, lien_waivers_value: 0, coi_expired: 0, coi_missing_expiry: 0,
  warranties_live: 0, record_counts: { coi: 1 }, ...over,
});

describe("an unknown vendor never renders as a vetted one", () => {
  it("gives no_history its own tone, not clear's", () => {
    expect(verdictTone("no_history").colour).not.toBe(verdictTone("clear").colour);
    expect(verdictTone("no_history").label).toBe("no history");
  });

  it("only `clear` is reassuring — the other two are not", () => {
    expect(isReassuring("clear")).toBe(true);
    expect(isReassuring("no_history")).toBe(false);
    expect(isReassuring("watch")).toBe(false);
  });

  it("a verdict this screen does not know is NOT given clear's colour", () => {
    // A fourth server-side verdict must not inherit green by falling through.
    expect(verdictTone("probation").colour).not.toBe(verdictTone("clear").colour);
    expect(isReassuring("probation")).toBe(false);
  });

  it("counts the unexamined vendors in the headline, not just the flagged ones", () => {
    const line = summaryLine({ vendors: [
      row({ verdict: "clear" }), row({ vendor: "B", verdict: "no_history" }),
      row({ vendor: "C", verdict: "watch" }),
    ] });
    expect(line).toMatch(/1 on watch/);
    expect(line, "'2 fine, 1 on watch' would be a claim about a vendor nobody has a record for")
      .toMatch(/NO recorded history/);
  });

  it("says nothing about unknowns when there are none", () => {
    expect(summaryLine({ vendors: [row()] })).not.toMatch(/NO recorded history/);
  });

  it("falls back to the server's own message on an empty set", () => {
    expect(summaryLine({ vendors: [], message: "No vendor history yet — subcontracts build it." }))
      .toMatch(/subcontracts build it/);
  });
});

describe("the scorecard states what it did not look at", () => {
  it("carries the server's attributable note through", () => {
    const line = attributionLine({ attributable: { note: "commercial and compliance history only. "
      + "`ncr` and `inspection` carry no vendor field" } });
    expect(line).toMatch(/ncr/);
    expect(line).toMatch(/Commercial and compliance only/);
  });

  it("states the caveat even when the payload omits it — silence is a property of the ROUTE", () => {
    // A missing caveat reads as no caveat, so this must never return "".
    const line = attributionLine({});
    expect(line.length).toBeGreaterThan(40);
    expect(line).toMatch(/not a pass/);
  });

  it("does not stutter the server's own opening clause", () => {
    expect(attributionLine({ attributable: { note: "commercial and compliance history only. X" } }))
      .not.toMatch(/commercial and compliance history only/i);
  });
});

describe("insurance: expired, unknown and none recorded are three things", () => {
  it("no certificate at all is unknown cover, not zero problems", () => {
    const line = coiLine(row({ record_counts: { coi: 0 } }));
    expect(line).toMatch(/unknown/);
    expect(line).not.toMatch(/\b0 expired/);
  });

  it("a certificate with no expiry is reported as unknown cover, separately from an expired one", () => {
    const line = coiLine(row({ record_counts: { coi: 3 }, coi_expired: 1, coi_missing_expiry: 2 }));
    expect(line).toMatch(/1 expired/);
    expect(line).toMatch(/2 with no expiry/);
  });

  it("a genuinely clean set says so, and says the dates are there", () => {
    const line = coiLine(row({ record_counts: { coi: 2 } }));
    expect(line).toMatch(/none expired/);
    expect(line).toMatch(/all carrying an expiry date/);
  });

  it("a missing record_counts is treated as no certificate, not as a clean one", () => {
    expect(coiLine(row({ record_counts: undefined }))).toMatch(/unknown/);
  });
});

describe("lien exposure", () => {
  it("is null when they have not billed — zero exposure and no billing are different", () => {
    expect(lienExposure(row({ invoiced: 0, lien_waivers_value: 0 }))).toBeNull();
  });

  it("is 0 when billing is fully waived", () => {
    expect(lienExposure(row({ invoiced: 1000, lien_waivers_value: 1000 }))).toBe(0);
  });

  it("is the gap when it is not", () => {
    expect(lienExposure(row({ invoiced: 1000, lien_waivers_value: 250.5 }))).toBe(749.5);
  });

  it("does not report a penny of float as exposure", () => {
    expect(lienExposure(row({ invoiced: 1000, lien_waivers_value: 999.995 }))).toBe(0);
  });
});

describe("worst first", () => {
  it("puts watch above unknown above clear, whatever the money says", () => {
    const rows = [
      row({ vendor: "Clear Big", verdict: "clear", subcontract_value: 9_000_000 }),
      row({ vendor: "Unknown", verdict: "no_history", subcontract_value: 0 }),
      row({ vendor: "Watch Small", verdict: "watch", subcontract_value: 1 }),
    ];
    expect(ordered(rows).map((r) => r.vendor)).toEqual(["Watch Small", "Unknown", "Clear Big"]);
  });

  it("breaks a tie by exposure, then by name — so the order is stable", () => {
    const rows = [
      row({ vendor: "B", verdict: "watch", subcontract_value: 100 }),
      row({ vendor: "A", verdict: "watch", subcontract_value: 100 }),
      row({ vendor: "C", verdict: "watch", subcontract_value: 500 }),
    ];
    expect(ordered(rows).map((r) => r.vendor)).toEqual(["C", "A", "B"]);
  });

  it("does not mutate its argument", () => {
    const rows = [row({ vendor: "A", verdict: "clear" }), row({ vendor: "B", verdict: "watch" })];
    ordered(rows);
    expect(rows.map((r) => r.vendor)).toEqual(["A", "B"]);
  });
});
