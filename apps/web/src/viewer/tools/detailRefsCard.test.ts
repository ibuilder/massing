import { describe, expect, it, vi } from "vitest";

import type { DetailRefGraph } from "../../api/types";
import type { DetailRefsDeps } from "./detailRefsCard";
import {
  DANGLING_REASON, danglingRows, openDetailRefs, orphanRows, renderDetailRefs, unparseableRows,
  verdictNote,
} from "./detailRefsCard";

/**
 * DETAIL-REFS-DARK — the cross-reference graph gains a reader.
 *
 * The three-state verdict is the assertion that matters. `navigable` was
 * `not dangling and not orphans and not unparseable` until NEGATED-VERDICT fixed it —
 * unconditionally True on a register with no references — so a card written before that would have
 * shipped "navigable ✓" to somebody whose set had never been checked. Each state is driven from a
 * fixture here, and the unassessed one is checked for what it does NOT render as well.
 */

const G = (over: Partial<DetailRefGraph> = {}): DetailRefGraph => ({
  sheet_count: 12,
  detail_count: 40,
  reference_count: 38,
  resolved: 38,
  edges: Array.from({ length: 38 }, (_, i) => ({
    from_sheet: "A-101", to_sheet: "A-501", detail: String(i), label: `${i}/A-501` })),
  dangling: [],
  orphans: [],
  unparseable: [],
  assessed: true,
  navigable: true,
  unassessed_reason: null,
  ...over,
});

describe("the verdict has THREE states, and the third is why this card could not ship before", () => {
  it("UNCHECKED is not clean, and carries the engine's sentence verbatim", () => {
    const reason = "3 sheet(s) are registered and none records a detail or a callout, so there is "
      + "nothing to cross-reference. This is an UNCHECKED set, not a clean one";
    const n = verdictNote(G({ assessed: false, navigable: false, detail_count: 0,
      reference_count: 0, resolved: 0, edges: [], unassessed_reason: reason }));
    expect(n.kind).toBe("warn");
    expect(n.html).toContain("UNCHECKED");
    expect(n.html).toContain("not a clean one");
    expect(n.html).not.toContain("Navigable");
  });

  it("falls back to its own sentence if the engine sends none — never an empty verdict", () => {
    const n = verdictNote(G({ assessed: false, navigable: false, unassessed_reason: null }));
    expect(n.html).toContain("nothing to cross-reference");
  });

  it("a cross-referenced set reads navigable, with the scale it was judged at", () => {
    const n = verdictNote(G());
    expect(n.kind).toBe("ok");
    expect(n.html).toContain("Navigable");
    expect(n.html).toContain("12 sheet(s), 40 detail(s), 38 of 38 callout(s) resolve");
  });

  it("names every kind of breakage it found, and only those", () => {
    const n = verdictNote(G({ navigable: false, resolved: 35, reference_count: 38,
      dangling: [{ from_sheet: "A-101", to_sheet: "A-999", detail: "4", label: "4/A-999",
                   reason: "sheet_not_in_set" }],
      orphans: [{ sheet: "A-501", detail: "9", title: "Sill", scale: "1:5" }] }));
    expect(n.kind).toBe("bad");
    expect(n.html).toContain("NOT navigable");
    expect(n.html).toContain("1 dangling callout(s)");
    expect(n.html).toContain("1 orphan detail(s)");
    expect(n.html).not.toContain("unreadable");
  });

  it("the resolved ratio comes from the ENGINE's two numbers, not from `edges.length`", () => {
    // `reference_count` is resolved + dangling; `edges` is the resolved half. Printing the array's
    // length beside the word "references" is TRUNC-COUNTED at field level.
    const n = verdictNote(G({ navigable: false, reference_count: 38, resolved: 35, edges: [],
      dangling: [{ from_sheet: "A-1", to_sheet: "A-9", detail: "1", label: "1/A-9",
                   reason: "sheet_not_in_set" }] }));
    expect(n.html).toContain("35 of 38 callout(s) resolve");
    expect(n.html).not.toContain("0 of 38");
  });

  it("escapes the engine's sentence — it reaches innerHTML", () => {
    expect(verdictNote(G({ assessed: false, unassessed_reason: "<img src=x>" })).html)
      .not.toContain("<img");
  });
});

describe("the two dangling reasons are kept apart, in words", () => {
  it("an unknown sheet reads as a typo or an unissued sheet", () => {
    const [row] = danglingRows([{ from_sheet: "A-101", to_sheet: "A-999", detail: "4",
      label: "4/A-999", reason: "sheet_not_in_set" }]);
    expect(row!.k).toBe("A-101 → 4/A-999");
    expect(row!.v).toContain("not in the set");
    expect(row!.v).toContain("nobody issued");
  });

  it("a known sheet missing the number reads as an un-propagated renumber, WITH the numbers that exist", () => {
    // `available` is the shortest route to the right number, and the only field that says what to do.
    const [row] = danglingRows([{ from_sheet: "A-101", to_sheet: "A-501", detail: "4",
      label: "4/A-501", reason: "detail_not_on_sheet", available: ["3", "5", "6"] }]);
    expect(row!.v).toContain("renumber");
    expect(row!.v).toContain("on A-501: 3, 5, 6");
  });

  it("the two reasons do not say the same thing", () => {
    expect(DANGLING_REASON.sheet_not_in_set).not.toBe(DANGLING_REASON.detail_not_on_sheet);
    expect(Object.keys(DANGLING_REASON).sort()).toEqual(["detail_not_on_sheet", "sheet_not_in_set"]);
  });

  it("an unrecognised reason is NAMED rather than rendered blank", () => {
    const [row] = danglingRows([{ from_sheet: "A-1", to_sheet: "A-2", detail: "1", label: "1/A-2",
      reason: "something_new" as never }]);
    expect(row!.v).toContain("unrecognised reason something_new");
  });

  it("omits the available list when the engine sent none", () => {
    const [row] = danglingRows([{ from_sheet: "A-1", to_sheet: "A-2", detail: "1", label: "1/A-2",
      reason: "detail_not_on_sheet" }]);
    expect(row!.v).not.toContain(" · on ");
  });
});

describe("the other two findings", () => {
  it("an orphan is identified by what is drawn on the sheet", () => {
    const [row] = orphanRows(G({ orphans: [{ sheet: "A-501", detail: "9", title: "Sill",
      scale: "1:5" }] }));
    expect(row!.k).toBe("9/A-501");
    expect(row!.v).toBe("Sill · 1:5 — nothing points at it");
  });

  it("says (untitled) and (no scale) rather than printing an empty field", () => {
    const [row] = orphanRows(G({ orphans: [{ sheet: "A-501", detail: "9", title: "", scale: "" }] }));
    expect(row!.v).toContain("(untitled)");
    expect(row!.v).toContain("(no scale)");
  });

  it("an unreadable callout shows its raw text, which IS the finding", () => {
    const [row] = unparseableRows(G({ unparseable: [{ from_sheet: "A-101", text: "SEE DETAIL" }] }));
    expect(row!.k).toBe("A-101");
    expect(row!.v).toContain("SEE DETAIL");
  });
});

describe("what the card renders", () => {
  const host = () => {
    const h = document.createElement("div");
    document.body.replaceChildren(h);
    return h;
  };
  const notes = () => [...document.querySelectorAll(".result-note")].map((n) => n.textContent ?? "");

  it("renders the UNCHECKED verdict and no tables on an unassessed set", () => {
    // Renamed, because the first version of this test claimed to prove a GUARD and did not.
    // `renderDetailRefs` had an `if (!g.assessed) return;` and deleting it passed all 18 tests —
    // the engine defines `assessed` as `bool(targets or edges or dangling or unparseable)`, so no
    // fixture can put a finding on an unassessed graph without contradicting it, and the branch was
    // unreachable. The guard is gone; what this test proves is the VERDICT, and the invariant the
    // card leans on is asserted in `services/api/test_detail_refs.py` where it belongs.
    renderDetailRefs(host(), G({ assessed: false, navigable: false, detail_count: 0,
      reference_count: 0, resolved: 0, edges: [], unassessed_reason: "nothing recorded" }));
    expect(document.querySelectorAll("table")).toHaveLength(0);
    expect(notes().some((t) => t.includes("UNCHECKED"))).toBe(true);
  });

  it("renders a table per finding kind, and none for the kinds with no findings", () => {
    renderDetailRefs(host(), G({ navigable: false, resolved: 36,
      dangling: [{ from_sheet: "A-101", to_sheet: "A-999", detail: "4", label: "4/A-999",
                   reason: "sheet_not_in_set" }],
      unparseable: [{ from_sheet: "A-102", text: "SEE DETAIL" }] }));
    expect(document.querySelectorAll("table")).toHaveLength(2);
    expect(notes().some((t) => t.includes("Dangling callouts"))).toBe(true);
    expect(notes().some((t) => t.includes("Unreadable callouts"))).toBe(true);
    expect(notes().some((t) => t.includes("Orphan details"))).toBe(false);
  });

  it("a navigable set renders the verdict and nothing else", () => {
    renderDetailRefs(host(), G());
    expect(document.querySelectorAll("table")).toHaveLength(0);
    expect(notes()).toHaveLength(1);
    expect(notes()[0]).toContain("Navigable");
  });

  it("fetches through the declared client method and renders what came back", async () => {
    const api = { detailReferences: vi.fn(async () => G({ navigable: false, resolved: 37,
      orphans: [{ sheet: "A-501", detail: "9", title: "Sill", scale: "1:5" }] })) };
    const h = host();
    await openDetailRefs(h, { api: api as unknown as DetailRefsDeps["api"], pid: "p1" });
    expect(api.detailReferences).toHaveBeenCalledWith("p1");
    expect(h.textContent).toContain("NOT navigable");
    expect(h.textContent).toContain("Sill");
  });
});
