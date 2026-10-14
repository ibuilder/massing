import { describe, expect, it, vi } from "vitest";

import type { DesignStandardCheck, DesignStandardItem } from "../../api/types";
import type { PanelContext } from "../panelContext";
import {
  auditNote, inertNote, keywordlessRows, renderDesignStandards, statusRows, unscoredStatuses,
  violationRows,
} from "./designStandards";

/**
 * DESIGN-STD-DARK — the audit gains a reader, and the reader must not let a count read as a result.
 *
 * Four states, three of which are a zero that means something other than "clean": no model, no
 * keywords, and no approved set. The engine reports counts and no boolean; these assertions are what
 * stops the card inventing one.
 */

const ITEM = (over: Partial<DesignStandardItem> = {}): DesignStandardItem => ({
  name: "CLT panel", category: "assembly", status: "approved", discipline: "ARC",
  match_keyword: "clt", spec_reference: "06 17 00", ...over,
});

const C = (over: Partial<DesignStandardCheck> = {}): DesignStandardCheck => ({
  model_scored: true,
  elements: 420,
  prohibited_hits: 0,
  unapproved: 0,
  violations: [],
  ruleset: { count: 2, items: [ITEM(), ITEM({ name: "PVC pipe", status: "prohibited",
    match_keyword: "pvc" })],
    by_status: { approved: [ITEM()], preferred: [],
      prohibited: [ITEM({ name: "PVC pipe", status: "prohibited", match_keyword: "pvc" })] } },
  coverage: { flagged: 0, listed: 0, truncated: false, cap: 200, approved_declared: 1,
    prohibited_declared: 1, reason: "every declared standard was applied to every element in the index" },
  note: "Elements flagged when their type/material matches a prohibited standard.",
  ...over,
});

describe("① no model is NOT a clean audit", () => {
  it("says NOT AUDITED and carries the engine's note", () => {
    const n = auditNote(C({ model_scored: false, elements: 0,
      note: "No model loaded — showing the ruleset only.",
      coverage: { flagged: 0, listed: 0, truncated: false, cap: 200, approved_declared: 1,
        prohibited_declared: 1, reason: "no model is loaded, so nothing was audited" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("NOT AUDITED");
    expect(n.html).toContain("No model loaded");
    expect(n.html).toContain("2 standard(s)");
    expect(n.html).not.toContain("No violations");
  });
});

describe("② a zero with nothing declared is not a zero with nothing failed", () => {
  it("no keyword anywhere reads as NOTHING TO AUDIT, with the engine's reason", () => {
    const n = auditNote(C({ coverage: { flagged: 0, listed: 0, truncated: false, cap: 200,
      approved_declared: 0, prohibited_declared: 0,
      reason: "no standard is declared with a match keyword, so nothing could be audited" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("NOTHING TO AUDIT");
    expect(n.html).toContain("nothing could be audited");
  });

  it("a clean audit WITH an approved set reads ok", () => {
    const n = auditNote(C());
    expect(n.kind).toBe("ok");
    expect(n.html).toContain("No violations");
    expect(n.html).toContain("420 element(s)");
    expect(n.html).not.toContain("not a measurement");
  });

  it("a clean audit with NO approved set is a WARN, and says the unapproved count measured nothing", () => {
    // The whole point of ②: `unapproved` is counted only `elif approved_kw and ...`, so 0 here means
    // "nothing to compare against". Rendering this as a pass is the defect.
    const n = auditNote(C({ coverage: { flagged: 0, listed: 0, truncated: false, cap: 200,
      approved_declared: 0, prohibited_declared: 1,
      reason: "no approved or preferred standard is declared, so 'unapproved' counts nothing" } }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("No approved set is declared");
    expect(n.html).toContain("not a measurement");
    expect(n.html).toContain("only prohibited matches were looked for");
  });
});

describe("③ the list is a page and the counts are the total", () => {
  it("uses coverage.flagged, not violations.length", () => {
    // The engine stops appending unapproved rows at the cap while still counting them, so these two
    // numbers differ BY DESIGN and only one of them is the total.
    const n = auditNote(C({ prohibited_hits: 3, unapproved: 497,
      violations: Array.from({ length: 200 }, (_, i) => ({ guid: `g${i}`, type: "IfcPipeSegment",
        issue: "no approved standard matched" })),
      coverage: { flagged: 500, listed: 200, truncated: true, cap: 200, approved_declared: 2,
        prohibited_declared: 1, reason: "every declared standard was applied to every element in the index" } }));
    expect(n.html).toContain("500 flagged");
    expect(n.html).toContain("Showing 200 of 500");
    expect(n.html).toContain("capped at 200");
    expect(n.html).not.toContain("200 flagged");
  });

  it("says nothing about a cap when nothing was dropped", () => {
    const n = auditNote(C({ unapproved: 2, violations: [
      { guid: "a", type: "IfcPipeSegment", issue: "no approved standard matched" },
      { guid: "b", type: "IfcPipeSegment", issue: "no approved standard matched" }],
      coverage: { flagged: 2, listed: 2, truncated: false, cap: 200, approved_declared: 2,
        prohibited_declared: 1, reason: "ok" } }));
    expect(n.html).not.toContain("Showing");
    expect(n.html).not.toContain("capped");
  });

  it("a prohibited match is BAD; unapproved alone is a warning", () => {
    const base = { flagged: 1, listed: 1, truncated: false, cap: 200, approved_declared: 2,
      prohibited_declared: 1, reason: "ok" };
    expect(auditNote(C({ prohibited_hits: 1, coverage: base,
      violations: [{ guid: "a", type: "IfcPipeSegment", issue: "prohibited: matches 'PVC pipe'" }] })).kind)
      .toBe("bad");
    expect(auditNote(C({ unapproved: 1, coverage: base,
      violations: [{ guid: "a", type: "IfcPipeSegment", issue: "no approved standard matched" }] })).kind)
      .toBe("warn");
  });
});

describe("a standard that cannot fire is named from the ruleset", () => {
  it("finds the rows with a bucketed status and no keyword", () => {
    const items = [ITEM(), ITEM({ name: "Blank", match_keyword: "  " }),
                   ITEM({ name: "Also blank", status: "prohibited", match_keyword: "" })];
    expect(keywordlessRows(items).map((i) => i.name)).toEqual(["Blank", "Also blank"]);
  });

  it("ignores a row whose status the audit never buckets — a different kind of inert", () => {
    const items = [ITEM({ name: "Draft", status: "under_review", match_keyword: "" })];
    expect(keywordlessRows(items)).toEqual([]);
    expect(unscoredStatuses(items)).toEqual(["under_review"]);
  });

  it("reports both kinds, and nothing when the ruleset is sound", () => {
    expect(inertNote(C())).toBeNull();
    const c = C({ ruleset: { count: 2, by_status: {},
      items: [ITEM({ name: "Blank", match_keyword: "" }),
              ITEM({ name: "Draft", status: "under_review" })] } });
    const note = inertNote(c)!;
    expect(note).toContain("carry no match keyword");
    expect(note).toContain("Blank");
    expect(note).toContain("under_review");
  });

  it("escapes a standard name — the register is user text in innerHTML", () => {
    const c = C({ ruleset: { count: 1, by_status: {},
      items: [ITEM({ name: "<img src=x>", match_keyword: "" })] } });
    expect(inertNote(c)!).not.toContain("<img");
  });
});

describe("the tables", () => {
  it("counts declared rows AND how many of them can fire, per status", () => {
    const rows = statusRows(C({ ruleset: { count: 3, items: [],
      by_status: { prohibited: [ITEM({ status: "prohibited" }),
                                ITEM({ status: "prohibited", name: "Blank", match_keyword: "" })],
                   approved: [ITEM()], preferred: [] } } }));
    expect(rows.find((r) => r.k === "prohibited")!.v).toContain("2 declared, 1 with a keyword");
    expect(rows.find((r) => r.k === "preferred")!.v).toBe("none declared");
  });

  it("names the element type and carries the engine's issue sentence and the GUID", () => {
    const [row] = violationRows(C({ violations: [{ guid: "2bKf", type: "IfcPipeSegment",
      issue: "prohibited: matches 'PVC pipe'" }] }));
    expect(row!.k).toBe("IfcPipeSegment");
    expect(row!.v).toContain("prohibited: matches 'PVC pipe'");
    expect(row!.v).toContain("2bKf");
  });

  it("says (untyped) rather than printing an empty cell", () => {
    expect(violationRows(C({ violations: [{ guid: "x", type: "", issue: "i" }] }))[0]!.k)
      .toBe("(untyped)");
  });
});

describe("the card", () => {
  const ctxFor = (api: object): PanelContext =>
    ({ host: { api } } as unknown as PanelContext);

  /** CONNECTED, because the real caller appends the slot before awaiting and the card checks
   *  `isConnected` before its late write. The first version of this harness used a detached
   *  `createElement` and both DOM tests failed with zero tables — the guard doing exactly what it
   *  says, and the harness not modelling the call. *A fixture that cannot reach the code is a test
   *  about the fixture*, so the slot is attached here and the guard gets an assertion of its own
   *  below rather than being satisfied by accident. */
  const slot = () => {
    const h = document.createElement("div");
    document.body.replaceChildren(h);
    return h;
  };

  it("renders the verdict, the ruleset table and the violations", async () => {
    const host = slot();
    const api = { designStandardsCheck: vi.fn(async () => C({ prohibited_hits: 1,
      violations: [{ guid: "2bKf", type: "IfcPipeSegment", issue: "prohibited: matches 'PVC pipe'" }],
      coverage: { flagged: 1, listed: 1, truncated: false, cap: 200, approved_declared: 1,
        prohibited_declared: 1, reason: "ok" } })) };
    await renderDesignStandards(ctxFor(api), host, "p1");
    expect(api.designStandardsCheck).toHaveBeenCalledWith("p1");
    expect(host.textContent).toContain("1 flagged");
    expect(host.textContent).toContain("IfcPipeSegment");
    expect(host.querySelectorAll("table")).toHaveLength(2);
  });

  it("renders no violations table when there are none", async () => {
    const host = slot();
    await renderDesignStandards(ctxFor({ designStandardsCheck: vi.fn(async () => C()) }), host, "p1");
    expect(host.querySelectorAll("table")).toHaveLength(1);
    expect(host.textContent).toContain("No violations");
  });

  it("reports a failure instead of leaving the card saying 'auditing…'", async () => {
    const host = slot();
    await renderDesignStandards(ctxFor({
      designStandardsCheck: vi.fn(async () => { throw new Error("project not found"); }) }), host, "p1");
    expect(host.textContent).toContain("project not found");
    expect(host.textContent).not.toContain("auditing…");
  });

  it("writes NOTHING into a slot the reader has navigated away from", async () => {
    // `root.innerHTML = ""` on the next panel detaches this slot, and `isConnected` is how the card
    // knows. The hazard is recorded in `standards.ts` from PR #527: a late write belongs in a node
    // appended up front, and must not land once that node is gone.
    const host = document.createElement("div");     // never attached — the navigated-away case
    const api = { designStandardsCheck: vi.fn(async () => C()) };
    await renderDesignStandards(ctxFor(api), host, "p1");
    expect(api.designStandardsCheck).toHaveBeenCalled();   // the fetch still happened
    expect(host.querySelectorAll("table")).toHaveLength(0);
    expect(host.textContent).not.toContain("No violations");
  });
});
