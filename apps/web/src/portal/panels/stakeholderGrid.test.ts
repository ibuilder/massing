import { beforeEach, describe, expect, it, vi } from "vitest";

import type { StakeholderAnalysis, StakeholderBrief } from "../../api/types";
import { blockerRows, gridReading, renderStakeholderGrid } from "./stakeholderGrid";

const B = (over: Partial<StakeholderBrief> = {}): StakeholderBrief =>
  ({ ref: "SH-1", name: "City Planning", organization: "City", category: "Authority / Regulator",
     stance: "Neutral", power: "High", interest: "High", ...over });

const Q = (label: string, advice: string, stakeholders: StakeholderBrief[] = []) =>
  ({ label, advice, count: stakeholders.length, stakeholders });

const A = (over: Partial<StakeholderAnalysis> = {}): StakeholderAnalysis => ({
  total: 3, assessed: 3,
  quadrants: {
    manage_closely: Q("Manage closely", "High power + high interest.", [B()]),
    keep_satisfied: Q("Keep satisfied", "High power, lower interest."),
    keep_informed: Q("Keep informed", "High interest, lower power."),
    monitor: Q("Monitor", "Low power + low interest — monitor with minimal effort.",
               [B({ ref: "SH-2", power: "Medium", interest: "Medium" }),
                B({ ref: "SH-3", power: "Low", interest: "Low" })]),
    unassessed: Q("Not assessed", "Power or interest has not been recorded."),
  },
  stance: { Supporter: 1, Neutral: 2, Blocker: 0 },
  supporter_pct: 33.3,
  by_category: { "Authority / Regulator": 3 },
  blockers: [],
  high_power_blockers: [],
  grid: {
    high_level: "High", levels: ["High", "Medium", "Low"],
    by_level: { power: { High: 1, Medium: 1, Low: 1 }, interest: { High: 1, Medium: 1, Low: 1 } },
    unrecorded: { power: 0, interest: 0 }, unassessed: 0,
    reason: "every active stakeholder has a power and an interest level",
  },
  note: "Mendelow power/interest grid…",
  ...over,
});

describe("gridReading — what a wall of 'Monitor' can mean", () => {
  it("names the Medium scores that a 2×2 put on the low side", () => {
    const r = gridReading(A());
    expect(r.text).toContain("3 of 3 assessed");
    expect(r.text).toContain("2 Medium score(s)");
    expect(r.text).toContain("split at High");
    expect(r.tone).toBe("ok");
  });

  /** The defect in its purest form: a register nobody filled in used to read as "all monitor". */
  it("refuses to read an unassessed register as a grid", () => {
    const r = gridReading(A({
      total: 4, assessed: 0,
      grid: { ...A().grid, unassessed: 4,
              by_level: { power: { High: 0, Medium: 0, Low: 0 },
                          interest: { High: 0, Medium: 0, Low: 0 } },
              unrecorded: { power: 4, interest: 4 },
              reason: "4 of 4 active stakeholder(s) have no power or no interest level, so the grid cannot place them" },
    }));
    expect(r.text).toContain("NONE ASSESSED");
    expect(r.text).toContain("4");
    expect(r.tone).toBe("warn");
  });

  it("is WARN when the grid placed some and not others", () => {
    const r = gridReading(A({ total: 5, assessed: 3, grid: { ...A().grid, unassessed: 2 } }));
    expect(r.text).toContain("2 not assessed");
    expect(r.tone).toBe("warn");
  });

  it("is BAD on any blocker, at any power level — not only High", () => {
    const mediumBlocker = B({ ref: "SH-9", stance: "Blocker", power: "Medium", interest: "High" });
    const r = gridReading(A({ blockers: [mediumBlocker], high_power_blockers: [] }));
    expect(r.tone).toBe("bad");
    expect(r.text).toContain("1 blocker(s)");
    expect(r.text).not.toContain("at High power");    // there is none, and it must not claim one
  });

  it("says nothing of a grid with no active records rather than calling it clean", () => {
    const r = gridReading(A({ total: 0, assessed: 0 }));
    expect(r.text).toContain("No active stakeholders");
    expect(r.tone).toBe("warn");
  });
});

describe("blockerRows", () => {
  it("orders High, Medium, Low, then the ones with no level recorded", () => {
    const a = A({ blockers: [
      B({ ref: "L", stance: "Blocker", power: "Low" }),
      B({ ref: "X", stance: "Blocker", power: null }),
      B({ ref: "H", stance: "Blocker", power: "High" }),
      B({ ref: "M", stance: "Blocker", power: "Medium" }),
    ] });
    expect(blockerRows(a).map((b) => b.ref)).toEqual(["H", "M", "L", "X"]);
  });

  it("does not mutate the response it was handed", () => {
    const a = A({ blockers: [B({ ref: "L", power: "Low" }), B({ ref: "H", power: "High" })] });
    blockerRows(a);
    expect(a.blockers.map((b) => b.ref)).toEqual(["L", "H"]);
  });
});

describe("the card", () => {
  const apiFor = (a: StakeholderAnalysis | Error) =>
    ({ stakeholderAnalysis: vi.fn(async () => { if (a instanceof Error) throw a; return a; }) });
  const slot = () => { const h = document.createElement("div"); document.body.replaceChildren(h); return h; };

  beforeEach(() => { document.body.innerHTML = ""; });

  it("renders all five quadrant rows, zeros included", async () => {
    const host = slot();
    await renderStakeholderGrid(apiFor(A()), host, "p1");
    expect(host.querySelectorAll("tbody tr")).toHaveLength(5);
    expect(host.textContent).toContain("Not assessed");
  });

  it("lists a Medium-power blocker with its level, which the old response never mentioned", async () => {
    const host = slot();
    await renderStakeholderGrid(apiFor(A({
      blockers: [B({ ref: "SH-9", name: "Adjacent Owner", stance: "Blocker", power: "Medium" })],
      high_power_blockers: [],
    })), host, "p1");
    expect(host.textContent).toContain("Adjacent Owner");
    expect(host.textContent).toContain("Medium");
  });

  it("says 'power not recorded' rather than leaving a blocker's level blank", async () => {
    const host = slot();
    await renderStakeholderGrid(apiFor(A({
      blockers: [B({ ref: "SH-7", name: "Unknown Party", stance: "Blocker", power: null })],
    })), host, "p1");
    expect(host.textContent).toContain("power not recorded");
  });

  it("writes NOTHING into a slot the reader navigated away from", async () => {
    const host = document.createElement("div");       // never attached
    const api = apiFor(A());
    await renderStakeholderGrid(api, host, "p1");
    expect(api.stakeholderAnalysis).toHaveBeenCalled();
    expect(host.innerHTML).toBe("");
  });

  it("stays silent when the call fails — the grid is advisory, not a banner", async () => {
    const host = slot();
    await expect(renderStakeholderGrid(apiFor(new Error("503")), host, "p1")).resolves.toBeUndefined();
    expect(host.innerHTML).toBe("");
  });

  it("escapes a party name, which is free text a user typed", async () => {
    const host = slot();
    await renderStakeholderGrid(apiFor(A({
      blockers: [B({ name: "<img src=x onerror=alert(1)>", stance: "Blocker", power: "High" })],
    })), host, "p1");
    expect(host.querySelector("img")).toBeNull();
    expect(host.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
