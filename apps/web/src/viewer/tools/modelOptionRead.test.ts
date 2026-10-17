import { describe, expect, it } from "vitest";
import type { ModelOptionBranch, ModelOptionDiff, ModelOptionList } from "../../api/model";
import { activateCaveat, branchLine, branchSummary, classDeltaLine, diffHeadline, diffTruncation,
  snapshotCaveat } from "./modelOptionRead";

const br = (over: Partial<ModelOptionBranch> & { slug: string; name: string }): ModelOptionBranch => ({
  note: null, created_at: "2026-10-15T00:00:00+00:00", size_bytes: 2048, elements: 120,
  available: true, current: false, ...over,
});

const A = br({ slug: "scheme-a-base", name: "Scheme A — base", current: true });
const B = br({ slug: "scheme-b-steel", name: "Scheme B — steel", elements: 134, size_bytes: 3_200_000 });

const list = (over: Partial<ModelOptionList> = {}): ModelOptionList =>
  ({ options: [A, B], count: 2, ...over });

const diff = (over: Partial<ModelOptionDiff> = {}): ModelOptionDiff => ({
  option: "scheme-b-steel",
  added_in_current: ["g1", "g2"], added_count: 2,
  removed_in_current: [], removed_count: 0,
  class_deltas: { IfcWall: { current: 41, option: 40, delta: 1 } },
  current_element_count: 121, option_element_count: 120, identical: false, ...over,
});

describe("branchLine", () => {
  it("marks where you are", () => {
    expect(branchLine(A)).toContain("← current");
    expect(branchLine(B)).not.toContain("current");
  });

  it("says element count unavailable rather than implying zero", () => {
    const l = branchLine(br({ slug: "x", name: "X", elements: null }));
    expect(l).toContain("element count unavailable");
    expect(l).not.toContain("0 element");
  });

  it("flags an index entry whose file has gone", () => {
    expect(branchLine(br({ slug: "x", name: "X", available: false }))).toContain("file missing");
  });

  it("scales bytes rather than printing raw", () => {
    expect(branchLine(B)).toContain("3.1 MB");
    expect(branchLine(A)).toContain("2 KB");
    expect(branchLine(br({ slug: "x", name: "X", size_bytes: 512 }))).toContain("512 B");
  });

  it("carries the note when there is one", () => {
    expect(branchLine(br({ slug: "x", name: "X", note: "pre-VE" }))).toContain("pre-VE");
  });

  it("is plain text", () => {
    expect(branchLine(A)).not.toMatch(/[<>]/);
  });
});

describe("branchSummary", () => {
  it("is null with no branches rather than a zero line", () => {
    expect(branchSummary(list({ options: [], count: 0 }))).toBeNull();
  });

  it("names the current branch", () => {
    expect(branchSummary(list())!).toContain("current: Scheme A — base");
  });

  it("explains a NO-match instead of leaving it looking like an error", () => {
    // This is the normal state after any edit, and the reading it replaces said nothing at all.
    const s = branchSummary(list({ options: [{ ...A, current: false }, B] }))!;
    expect(s).toContain("matches no branch");
    expect(s).toContain("edited since the last snapshot");
  });

  it("reports several current branches rather than picking one", () => {
    // Two snapshots of the same bytes are both byte-identical to the working model; the engine
    // flags both, so a reading that printed one would be choosing arbitrarily.
    const s = branchSummary(list({ options: [A, { ...B, current: true }] }))!;
    expect(s).toContain("2 branches are byte-identical");
  });

  it("counts entries whose file is gone", () => {
    expect(branchSummary(list({ options: [A, { ...B, available: false }] }))!)
      .toContain("1 branch(es) have an index entry but no file");
  });
});

describe("snapshotCaveat — a branch is a HEAD, not an archive", () => {
  it("warns before overwriting an existing name", () => {
    const c = snapshotCaveat(list(), "Scheme A — base")!;
    expect(c).toContain("already exists");
    expect(c).toContain("overwrites it");
  });

  it("slugifies the way the server does, so a near-miss still warns", () => {
    // The server slug is lowercase, non-alphanumerics collapsed to '-'. These all hit the same one.
    for (const typed of ["scheme a base", "SCHEME-A---BASE", "  Scheme   A   Base  "]) {
      expect(snapshotCaveat(list(), typed), typed).not.toBeNull();
    }
  });

  it("is null for a genuinely new name", () => {
    expect(snapshotCaveat(list(), "Scheme C — timber")).toBeNull();
  });

  it("is null for a name that slugifies to nothing, which the server refuses anyway", () => {
    expect(snapshotCaveat(list(), "   ")).toBeNull();
    expect(snapshotCaveat(list(), "!!!")).toBeNull();
  });
});

describe("diffHeadline", () => {
  it("reports a real difference with both populations", () => {
    const h = diffHeadline(diff());
    expect(h).toContain("2 added in current");
    expect(h).toContain("1 class(es) differ");
    expect(h).toContain("current has 121 element(s), the branch 120");
  });

  it("omits a zero side rather than printing '0 removed'", () => {
    expect(diffHeadline(diff())).not.toContain("removed");
  });

  it("reports a match WITH the population it matched over", () => {
    const h = diffHeadline(diff({ identical: true, added_in_current: [], added_count: 0,
                                  class_deltas: {}, current_element_count: 120,
                                  option_element_count: 120 }));
    expect(h).toContain("No difference across 120 element(s)");
  });

  it("refuses to let a match over ZERO elements read as agreement", () => {
    // The engine deliberately returns `identical: true` here and says why; the population is what
    // a reader needs, and this is the case where its absence is actively misleading.
    const h = diffHeadline(diff({ identical: true, added_in_current: [], added_count: 0,
                                  class_deltas: {}, current_element_count: 0,
                                  option_element_count: 0 }));
    expect(h).toContain("BOTH models carry zero IfcElement");
    expect(h).toContain("a match over nothing");
  });

  it("is plain text in every branch", () => {
    for (const d of [diff(), diff({ identical: true, current_element_count: 0 })]) {
      expect(diffHeadline(d)).not.toMatch(/[<>]/);
    }
  });
});

describe("diffTruncation — the cap is 100 and the counts are not", () => {
  it("is null when neither list is capped", () => {
    expect(diffTruncation(diff())).toBeNull();
  });

  it("reports the added page against its total", () => {
    const t = diffTruncation(diff({
      added_in_current: Array.from({ length: 100 }, (_, i) => `g${i}`), added_count: 412,
    }))!;
    expect(t).toContain("100 of 412 added");
    expect(t).toContain("counts above are complete");
  });

  it("reports both sides when both are capped", () => {
    const t = diffTruncation(diff({
      added_in_current: Array.from({ length: 100 }, (_, i) => `a${i}`), added_count: 412,
      removed_in_current: Array.from({ length: 100 }, (_, i) => `r${i}`), removed_count: 250,
    }))!;
    expect(t).toContain("100 of 412 added");
    expect(t).toContain("100 of 250 removed");
  });

  it("does not fire when a list is short because the difference is small", () => {
    // The distinction that matters: a 2-element list with count 2 is complete, not truncated.
    expect(diffTruncation(diff({ added_in_current: ["a", "b"], added_count: 2 }))).toBeNull();
  });
});

describe("classDeltaLine", () => {
  it("is null when no class count differs", () => {
    expect(classDeltaLine(diff({ class_deltas: {} }))).toBeNull();
  });

  it("orders by magnitude so the biggest movement reads first", () => {
    const l = classDeltaLine(diff({ class_deltas: {
      IfcWall: { current: 41, option: 40, delta: 1 },
      IfcSlab: { current: 2, option: 14, delta: -12 },
    } }))!;
    expect(l.indexOf("IfcSlab")).toBeLessThan(l.indexOf("IfcWall"));
    expect(l).toContain("IfcSlab -12");
    expect(l).toContain("IfcWall +1");
  });

  it("names the direction, since a bare delta is ambiguous", () => {
    expect(classDeltaLine(diff())!).toContain("current − branch");
  });

  it("caps the list and says how many more", () => {
    const many: ModelOptionDiff["class_deltas"] = {};
    for (let i = 0; i < 12; i++) many[`IfcThing${i}`] = { current: i, option: 0, delta: i };
    expect(classDeltaLine(diff({ class_deltas: many }), 3)!).toContain("9 more class(es)");
  });
});

describe("activateCaveat", () => {
  it("says what the switch does BEFORE it is clicked", () => {
    const c = activateCaveat(B);
    expect(c).toContain("Scheme B — steel");
    expect(c).toContain("republishes the viewer geometry");
  });

  it("says it is one undo step, which is what makes it not destructive", () => {
    expect(activateCaveat(B)).toContain("ONE undo step");
    expect(activateCaveat(B)).toContain("not a destructive action");
  });
});
