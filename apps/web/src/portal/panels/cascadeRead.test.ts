import { describe, expect, it } from "vitest";

import { cascadeHeadline, coverageBasis, danglingRows, flowRows, missingLinkNotes, nodePageNote,
  orphanRows, rootNote, rowTone } from "./cascadeRead";
import type { CascadeNode, InfoRequirementsCascade } from "../../api/types";

const node = (over: Partial<CascadeNode> & { id: string }): CascadeNode => ({
  ref: over.id.toUpperCase(), title: `${over.id} title`, type: "EIR", tier: 2, state: "draft",
  derives_from: null, ...over,
});

/** The five-record register measured against a live route: one OIR root, a PIR and EIR beneath it,
 *  one EIR whose intermediate PIR was DELETED, and one AIR nobody ever linked.
 *  `services/api/test_cde.py` asserts the same shape at the route. */
function resp(over: Partial<InfoRequirementsCascade> = {}): InfoRequirementsCascade {
  const nodes = over.nodes ?? [
    node({ id: "r1", ref: "IR-001", type: "OIR", tier: 0 }),
    node({ id: "p1", ref: "IR-002", type: "PIR", tier: 1, derives_from: "r1" }),
    node({ id: "e1", ref: "IR-003", type: "EIR", tier: 2, derives_from: "p1" }),
    node({ id: "e2", ref: "IR-005", type: "EIR", tier: 2, derives_from: "ghost" }),
    node({ id: "a1", ref: "IR-006", type: "AIR", tier: 1 }),
  ];
  return {
    total: 5, expected: 4, linked: 2, coverage_pct: 50.0,
    coverage_basis: "`coverage_pct` is over `expected` — the requirements ISO 19650 says must trace "
      + "up — and NOT over `total`.",
    nodes, nodes_truncated: false, max_nodes: 2000,
    children: { r1: ["p1"], p1: ["e1"] },
    roots: [{ id: "r1", ref: "IR-001", type: "OIR", title: "r1 title" }],
    orphans: [{ id: "a1", ref: "IR-006", type: "AIR", title: "a1 title" }], orphan_count: 1,
    dangling: [{ id: "e2", ref: "IR-005", type: "EIR", title: "e2 title", missing_parent: "ghost" }],
    dangling_count: 1,
    misdirected: [],
    note: "ISO 19650 flow-down: OIR → PIR/AIR → EIR → MIDP/TIDP.",
    ...over,
  };
}

const EMPTY: Partial<InfoRequirementsCascade> = {
  children: {}, roots: [], orphans: [], orphan_count: 0, dangling: [], dangling_count: 0,
  misdirected: [],
};

describe("the cascade headline", () => {
  it("is over the requirements that should trace up, not the register", () => {
    const h = cascadeHeadline(resp());
    expect(h.text).toContain("2/4 of the requirements that should trace up do (50%)");
    expect(h.text).toContain("1 root requirement(s) sit above the cascade and are outside it");
  });

  it("reaches 100% on a textbook cascade, which the shipped denominator could not", () => {
    // Measured: 1 OIR → 1 PIR → 1 EIR read 66.7% as shipped, because the root was in the
    // denominator and could never be in the numerator.
    const h = cascadeHeadline(resp({ ...EMPTY, total: 3, expected: 2, linked: 2, coverage_pct: 100,
      roots: [{ id: "r1", ref: "IR-001", type: "OIR", title: "t" }] }));
    expect(h.tone).toBe("good");
    expect(h.text).toContain("2/2 of the requirements that should trace up do (100%)");
  });

  it("says nothing is expected yet rather than printing a 0% failure", () => {
    // Measured: one OIR and nothing else read `0/1 linked · 0%` beside "✅ every requirement traces
    // up to organizational intent", in the same box.
    const h = cascadeHeadline(resp({ ...EMPTY, total: 1, expected: 0, linked: 0, coverage_pct: null,
      roots: [{ id: "r1", ref: "IR-001", type: "OIR", title: "t" }], nodes: [] }));
    expect(h.tone).toBe("");
    expect(h.text).toContain("nothing is expected to trace up yet");
    expect(h.text).not.toContain("0%");
  });

  it("reports an empty register as empty", () => {
    expect(cascadeHeadline(resp({ ...EMPTY, total: 0, expected: 0, linked: 0, coverage_pct: null,
      nodes: [] }))).toEqual({ tone: "", text: "No information requirements registered yet." });
  });

  it("is crit when a link was UNDONE and warn when one was never made", () => {
    // A dangling reference outranks an orphan: somebody did the work and it was silently undone.
    expect(cascadeHeadline(resp()).tone).toBe("crit");
    expect(cascadeHeadline(resp({ dangling: [], dangling_count: 0, linked: 3 })).tone).toBe("warn");
  });
});

describe("the two ways a link is missing", () => {
  it("separates them, because the repairs differ", () => {
    const [first, second] = missingLinkNotes(resp());
    expect(first!.tone).toBe("crit");
    expect(first!.text).toContain("point at a parent that no longer exists");
    expect(first!.text).toContain("need re-pointing rather than a first link");
    expect(first!.text).toContain("EIR IR-005");
    expect(second!.tone).toBe("warn");
    expect(second!.text).toContain("have never been linked");
    expect(second!.text).toContain("AIR IR-006");
  });

  it("prints the COUNT, not the length of the list it shows", () => {
    const n = missingLinkNotes(resp({ orphan_count: 40 }))[1]!;
    expect(n.text).toContain("40 requirement(s) have never been linked");
    expect(n.text).toContain("…");
  });

  it("is empty on a healthy cascade", () => {
    expect(missingLinkNotes(resp({ ...EMPTY, linked: 4 }))).toEqual([]);
  });

  it("reports a link pointing at an equal or lower tier", () => {
    const n = missingLinkNotes(resp({ ...EMPTY,
      misdirected: [{ id: "x", ref: "IR-009", type: "EIR", parent_type: "EIR" }] }))[0]!;
    expect(n.text).toContain("1 link(s) point the wrong way");
    expect(n.text).toContain("EIR→EIR");
  });
});

describe("the organizational intent", () => {
  it("is NAMED rather than asserted", () => {
    // "✅ every requirement traces up to organizational intent" used to print without ever saying
    // what the intent was — `roots` was declared and read by nothing.
    expect(rootNote(resp())!.text).toBe("Organizational intent: IR-001 r1 title");
  });

  it("calls out a cascade with no top at all", () => {
    const r = rootNote(resp({ roots: [] }))!;
    expect(r.tone).toBe("warn");
    expect(r.text).toContain("No top-level requirement (OIR) is registered");
  });

  it("says nothing about an empty register", () => {
    expect(rootNote(resp({ total: 0 }))).toBeNull();
  });
});

describe("the flow-down rows — the thing the card is named after", () => {
  it("walks depth-first from each root and names the parent by ref", () => {
    const rows = flowRows(resp());
    expect(rows.slice(0, 3).map((r) => [r.depth, r.ref, r.parent]))
      .toEqual([[0, "IR-001", "—"], [1, "IR-002", "IR-001"], [2, "IR-003", "IR-002"]]);
  });

  it("marks a dangling parent as deleted rather than printing a raw id", () => {
    const row = flowRows(resp()).find((r) => r.ref === "IR-005")!;
    expect(row.parent).toBe("(deleted)");
    expect(row.status).toBe("dangling");
    expect(rowTone(row)).toBe("crit");
  });

  it("renders a never-linked requirement at the top level, with its own status", () => {
    const row = flowRows(resp()).find((r) => r.ref === "IR-006")!;
    expect(row).toMatchObject({ depth: 0, parent: "—", status: "orphan" });
    expect(rowTone(row)).toBe("warn");
  });

  it("emits every node exactly once, so nothing is silently dropped", () => {
    const rows = flowRows(resp());
    expect(rows).toHaveLength(5);
    expect(new Set(rows.map((r) => r.ref)).size).toBe(5);
  });

  it("terminates on a CYCLE — `derives_from` has no acyclicity check anywhere", () => {
    // Two requirements naming each other is accepted by the server today, so a naive recursive walk
    // would hang the panel. Each node is emitted once and the second visit stops.
    const rows = flowRows(resp({
      ...EMPTY,
      total: 2, expected: 2, linked: 2, coverage_pct: 100,
      nodes: [node({ id: "a", ref: "IR-A", tier: 1, derives_from: "b" }),
              node({ id: "b", ref: "IR-B", tier: 2, derives_from: "a" })],
      children: { a: ["b"], b: ["a"] },
    }));
    expect(rows.map((r) => r.ref)).toEqual(["IR-A", "IR-B"]);
  });

  it("renders a sub-tree hanging off an orphan rather than losing it", () => {
    // A row missing from a tree is indistinguishable from a row that does not exist.
    const rows = flowRows(resp({
      ...EMPTY,
      total: 2, expected: 2, linked: 1, coverage_pct: 50,
      nodes: [node({ id: "o", ref: "IR-O", type: "PIR", tier: 1 }),
              node({ id: "k", ref: "IR-K", tier: 2, derives_from: "o" })],
      children: { o: ["k"] },
      orphans: [{ id: "o", ref: "IR-O", type: "PIR", title: "t" }], orphan_count: 1,
    }));
    expect(rows.map((r) => [r.depth, r.ref])).toEqual([[0, "IR-O"], [1, "IR-K"]]);
  });

  it("falls back to a short id and a placeholder title when a record has neither", () => {
    const rows = flowRows(resp({
      ...EMPTY, total: 1, expected: 1, linked: 0, coverage_pct: 0,
      nodes: [node({ id: "abcdefgh-9999", ref: null, title: null, state: null, tier: 1 })],
      orphans: [{ id: "abcdefgh-9999", ref: null, type: "EIR", title: null }], orphan_count: 1,
    }));
    expect(rows[0]).toMatchObject({ ref: "abcdefgh", title: "(untitled)", state: "—" });
  });
});

describe("the bounded node list", () => {
  it("says nothing while the tree is whole", () => {
    expect(nodePageNote(resp())).toBeNull();
  });

  it("prints the page against the FULL total, and names the cap", () => {
    const n = nodePageNote(resp({ nodes_truncated: true, total: 9000 }));
    expect(n).toContain("Showing 5 of 9,000");
    expect(n).toContain("caps the tree at 2,000");
    expect(n).toContain("Every count above is over all 9,000");
  });
});

describe("the basis and the brief lists", () => {
  it("returns the engine's basis verbatim", () => {
    expect(coverageBasis(resp())).toBe(resp().coverage_basis);
  });

  it("hands the two finding lists through unchanged", () => {
    expect(danglingRows(resp())[0]!.missing_parent).toBe("ghost");
    expect(orphanRows(resp())[0]!.ref).toBe("IR-006");
  });
});
