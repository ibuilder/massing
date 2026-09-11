import { describe, it, expect } from "vitest";
import {
  saveGate, saveConfirm, saveSummary, rfqGate, rfqConfirm, rfqSummary,
  type GroupedPackage, type SavedPackage,
} from "./buyoutKeep";

const GROUPED: GroupedPackage[] = [
  { package: "Concrete", line_count: 12, est_cost: 480_000 },
  { package: "Steel", line_count: 7, est_cost: 1_250_500 },
];

const SAVED: SavedPackage[] = [
  { id: 41, ref: "PKG-0001", name: "Concrete", est_cost: 480_000, line_count: 12 },
  { id: 42, ref: "PKG-0002", name: "Steel", est_cost: 1_250_500, line_count: 7 },
];

describe("keeping nothing is refused, not reported as a save", () => {
  it("refuses an empty grouping with the reason", () => {
    const g = saveGate(0);
    expect(g.can).toBe(false);
    expect(g.why).toContain("no packages to keep");
  });

  it("offers the save when there is something to keep", () => {
    expect(saveGate(2)).toEqual({ can: true, why: "" });
  });
});

describe("the confirmation names the blast radius, not the mechanics", () => {
  it("says these become project-wide records, not a browser draft", () => {
    const c = saveConfirm(GROUPED, "trade");
    expect(c).toContain("RECORD");
    expect(c).toContain("whole project");
    expect(c).toContain("not a draft in");
  });

  it("states the count and the money so a mis-grouping is caught before twelve records exist", () => {
    const c = saveConfirm(GROUPED, "trade");
    expect(c).toContain("2 buyout packages");
    expect(c).toContain("$1,730,500");
    expect(c).toContain("trade");
  });

  it("warns that keeping again ADDS a set rather than replacing one", () => {
    expect(saveConfirm(GROUPED, "trade")).toContain("SECOND set");
  });

  it("counts one package in the singular", () => {
    const c = saveConfirm([GROUPED[0]!], "trade");
    expect(c).toContain("1 buyout package");
    expect(c).not.toContain("1 buyout packages");
  });
});

describe("the save summary reports what was created", () => {
  it("names the refs, because a ref is what somebody quotes later", () => {
    const s = saveSummary(SAVED);
    expect(s).toContain("PKG-0001");
    expect(s).toContain("PKG-0002");
    expect(s).toContain("Kept 2 buyout packages");
  });

  it("reports an empty write as nothing kept — the server answers 200 for it", () => {
    const s = saveSummary([]);
    expect(s).toContain("Nothing was kept");
    expect(s).not.toContain("Kept");
  });

  it("flags a count that differs from the one the confirmation named", () => {
    const s = saveSummary(SAVED, 3);
    expect(s).toContain("3 packages were offered and 2 were created");
    expect(s).toContain("re-grouped at write time");
  });

  it("says nothing extra when the count matches", () => {
    expect(saveSummary(SAVED, 2)).not.toContain("NOTE");
  });

  it("truncates a long list rather than printing forty refs", () => {
    const many = Array.from({ length: 9 }, (_, i) => ({
      ...SAVED[0]!, id: i, ref: `PKG-000${i}`,
    }));
    expect(saveSummary(many)).toContain("+5 more");
  });
});

describe("an RFQ cannot be sent for a package that was never kept", () => {
  it("refuses when the record has no id — the route is keyed on it and would 404", () => {
    const g = rfqGate({ id: null, state: "draft" });
    expect(g.can).toBe(false);
    expect(g.why).toContain("not been kept");
  });

  it("refuses an empty-string id the same way", () => {
    expect(rfqGate({ id: "", state: "draft" }).can).toBe(false);
  });

  it("allows it for a kept package still in draft", () => {
    expect(rfqGate({ id: 41, state: "draft" })).toEqual({ can: true, why: "" });
  });

  it("treats a missing state as draft rather than blocking a fresh record", () => {
    expect(rfqGate({ id: 41 }).can).toBe(true);
  });
});

describe("the double-send trap", () => {
  // THE load-bearing rule. The server mints the solicitation UNCONDITIONALLY and transitions only a
  // draft package. So a second send produces a second ITB and no state change, and a client that
  // reports success from a resolved promise hides a duplicate solicitation nobody asked for.
  it("refuses a package whose RFQ has already gone out, and says which state it is in", () => {
    const g = rfqGate({ id: 41, state: "rfq_sent" });
    expect(g.can).toBe(false);
    expect(g.why).toContain("rfq sent");
  });

  it("refuses an awarded package too — every state past draft", () => {
    expect(rfqGate({ id: 41, state: "awarded" }).can).toBe(false);
  });

  it("refuses an UNKNOWN state with its own reason, not 'already sent'", () => {
    // Found in review on PR #528. The panel carries `unknown` through when the server answered
    // without a state; saying "its RFQ has gone out" would assert the one thing that response
    // failed to establish.
    const g = rfqGate({ id: 41, state: "unknown" });
    expect(g.can).toBe(false);
    expect(g.why).toContain("did not report");
    expect(g.why).toContain("reload");
    expect(g.why).not.toContain("gone out");
  });

  it("reports a successful send as the move it made", () => {
    const s = rfqSummary({ solicitation: { id: 7, ref: "ITB-0007" }, package: "PKG-0001",
                           package_state: "rfq_sent" });
    expect(s).toContain("ITB-0007");
    expect(s).toContain("moved to RFQ sent");
    expect(s).not.toContain("did NOT");
  });

  it("reports a send that did NOT move the package as the half-success it is", () => {
    const s = rfqSummary({ solicitation: { id: 8, ref: "ITB-0008" }, package: "PKG-0001",
                           package_state: "quotes_in" });
    expect(s).toContain("did NOT move");
    expect(s).toContain("quotes in");
    expect(s).toContain("minted anyway");
  });

  it("handles an unreported state without claiming the move happened", () => {
    const s = rfqSummary({ solicitation: { id: 9, ref: "ITB-0009" }, package: "PKG-0001",
                           package_state: null });
    expect(s).toContain("did NOT move");
    expect(s).not.toContain("moved to RFQ sent.");
  });
});

describe("the RFQ confirmation names BOTH writes", () => {
  it("says a solicitation is minted and the package moves", () => {
    const c = rfqConfirm(SAVED[0]!);
    expect(c).toContain("Bid Solicitation");
    expect(c).toContain("draft to RFQ sent");
    expect(c).toContain("PKG-0001");
  });

  it("carries the due date when one was given", () => {
    expect(rfqConfirm(SAVED[0]!, "2026-10-01")).toContain("due 2026-10-01");
  });
});
