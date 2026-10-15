import { describe, expect, it } from "vitest";

import { cutCoverageNote, detailNote, elementRows, flattenedNote, flattenedStyles, graphicsHeadline,
  graphicsNote, heavierBy, sampleGuids, sideCell, styleRows } from "./vgRead";
import type { GraphicStyleBucket, ViewTemplateGraphics } from "../../api/model";

/** The response as a live route served it: a 50,000-element index, one object style raising the
 *  enclosure cut weight to 1.4 mm, `IfcDuctSegment` hidden. 42,857 visible, 7,143 hidden, 4 distinct
 *  styles. `services/api/test_vg_overrides.py` asserts the same shape at the route. */
function bucket(over: Partial<GraphicStyleBucket> = {}): GraphicStyleBucket {
  return {
    group: "structure", count: 21429, cut_count: 0,
    cut: { weight: 0.7, color: "#111111", pattern: "solid", halftone: false },
    projection: { weight: 0.25, color: "#444444", pattern: "solid", halftone: false },
    sample: ["0000000000000000000001", "0000000000000000000002"],
    ...over,
  };
}

function resp(over: Partial<ViewTemplateGraphics> = {}): ViewTemplateGraphics {
  const styles = over.styles ?? [
    bucket(),
    bucket({ group: "enclosure", count: 7143,
      cut: { weight: 1.4, color: "#111111", pattern: "solid", halftone: false },
      projection: { weight: 0.18, color: "#444444", pattern: "solid", halftone: false },
      sample: ["0000000000000000000000"] }),
    bucket({ group: "opening", count: 7143,
      cut: { weight: 0.35, color: "#111111", pattern: "solid", halftone: false },
      projection: { weight: 0.18, color: "#444444", pattern: "solid", halftone: false },
      sample: ["0000000000000000000004"] }),
    bucket({ group: "mep", count: 7142,
      cut: { weight: 0.25, color: "#111111", pattern: "solid", halftone: false },
      projection: { weight: 0.13, color: "#444444", pattern: "solid", halftone: false },
      sample: ["0000000000000000000006"] }),
  ];
  return {
    template: "t1", name: "Sheet Lines",
    visible_count: 42857, hidden_count: 7143, cut_count: 0, cut_supplied: false,
    styles, style_count: styles.length,
    graphics: {}, graphics_count: 42857, graphics_mode: "none",
    graphics_truncated: false, graphics_unknown: [], max_graphics: 2000,
    note: "Cut lines are heavier than projection lines — that weight difference, not colour, is how "
      + "a reader reads depth off a flat sheet.",
    ...over,
  };
}

describe("the graphics headline", () => {
  it("reports what the template HID, not only what it left visible", () => {
    // The card printed `42857 visible` alone, so a template hiding 7,143 elements and one hiding
    // none rendered identically.
    const h = graphicsHeadline(resp());
    expect(h.text).toContain("42,857 visible");
    expect(h.text).toContain("7,143 hidden (14.3% of 50,000)");
    expect(h.text).toContain("4 distinct style(s)");
  });

  it("calls out a template that resolves to an empty view", () => {
    const h = graphicsHeadline(resp({ visible_count: 0, hidden_count: 50000, styles: [] }));
    expect(h.tone).toBe("crit");
    expect(h.text).toContain("hides ALL 50,000");
  });

  it("distinguishes no model index from a template that hides everything", () => {
    const h = graphicsHeadline(resp({ visible_count: 0, hidden_count: 0, styles: [] }));
    expect(h.tone).toBe("warn");
    expect(h.text).toContain("No model index loaded");
  });

  it("does not claim a template is doing anything when it hides nothing", () => {
    expect(graphicsHeadline(resp({ hidden_count: 0 })).tone).toBe("");
  });
});

describe("the cut-side coverage", () => {
  it("says a cut list was never supplied rather than printing a bare 0", () => {
    // `cut_count: 0` has two causes and the card had one rendering for both.
    const n = cutCoverageNote(resp());
    expect(n).toContain("resolved for all 42,857");
    expect(n).toContain("no cut list was supplied");
    expect(n).toContain("honest answer for a 3D view");
  });

  it("separates a supplied list that matched nothing from one never supplied", () => {
    const n = cutCoverageNote(resp({ cut_supplied: true, cut_count: 0 }));
    expect(n).toContain("A cut list was supplied and none of its elements are visible");
    expect(n).not.toContain("no cut list was supplied");
  });

  it("reports the applied cut side when there is one", () => {
    expect(cutCoverageNote(resp({ cut_supplied: true, cut_count: 12 })))
      .toContain("12 of 42,857 visible element(s) are cut");
  });
});

describe("the style table", () => {
  it("renders both sides as separate columns, weight first", () => {
    const rows = styleRows(resp());
    expect(rows[0]!.cut).toBe("0.7 mm · #111111 · solid");
    expect(rows[0]!.projection).toBe("0.25 mm · #444444 · solid");
  });

  it("shows how much heavier the cut side draws", () => {
    expect(styleRows(resp())[0]!.heavier).toBe("2.8×");
    expect(styleRows(resp())[1]!.heavier).toBe("7.78×");
  });

  it("names a flattened style instead of printing a quiet 1x", () => {
    // An override applied as a full replacement would do this to everything it touched, which is the
    // defect `_norm_override` exists to prevent. If one reaches a sheet, say so.
    const flat = bucket({ cut: { weight: 0.25 }, projection: { weight: 0.25 } });
    expect(heavierBy(flat)).toBe("SAME — no cut/projection distinction");
    expect(heavierBy(bucket({ cut: { weight: 0.1 }, projection: { weight: 0.25 } })))
      .toBe("0.4× (cut is LIGHTER)");
  });

  it("returns — rather than a ratio when either side has no weight", () => {
    expect(heavierBy(bucket({ cut: { color: "#000000" } }))).toBe("—");
    expect(heavierBy(bucket({ projection: {} }))).toBe("—");
  });

  it("counts the cut elements within a style when there are any", () => {
    expect(styleRows(resp({ styles: [bucket({ cut_count: 9 })] }))[0]!.count).toBe("21,429 (9 cut)");
    expect(styleRows(resp({ styles: [bucket()] }))[0]!.count).toBe("21,429");
  });

  it("appends halftone only when it is on", () => {
    expect(sideCell({ weight: 0.5, color: "#111111", pattern: "solid", halftone: true }))
      .toContain("halftone");
    expect(sideCell({ weight: 0.5, color: "#111111", pattern: "solid", halftone: false }))
      .not.toContain("halftone");
  });
});

describe("the flattened-style finding", () => {
  it("is empty on the shipped defaults, which is the expected answer", () => {
    // Every category default ships cut-heavier, so a row here is an override that flattened one.
    expect(flattenedStyles(resp())).toEqual([]);
    expect(flattenedNote(resp())).toBeNull();
  });

  it("names the categories and the element count when one is flattened", () => {
    const n = flattenedNote(resp({ styles: [
      bucket({ group: "mep", count: 7142, cut: { weight: 0.13 }, projection: { weight: 0.13 } }),
      bucket(),
    ] }));
    expect(n).toContain("1 style(s) covering 7,142 element(s)");
    expect(n).toContain("(mep)");
    expect(n).toContain("lose the depth cue");
  });

  it("does not flag a style whose weights are simply unset", () => {
    expect(flattenedStyles(resp({ styles: [bucket({ cut: {}, projection: {} })] }))).toEqual([]);
  });
});

describe("the per-element detail", () => {
  it("names the resolved population when the map was not asked for", () => {
    // Never the length of what shipped: 8.9 MB of per-element state used to ship unasked.
    const n = detailNote(resp());
    expect(n).toContain("not requested");
    expect(n).toContain("42,857 element(s) are resolved server-side");
    expect(n).toContain("capped at 2,000");
  });

  it("distinguishes a truncated whole map from a complete one", () => {
    const t = detailNote(resp({ graphics_mode: "all", graphics_truncated: true,
      graphics: Object.fromEntries(Array.from({ length: 2000 }, (_, i) => [`g${i}`,
        { group: "structure", cut: {}, projection: {}, is_cut: false }])) }));
    expect(t).toContain("Showing 2,000 of 42,857");
    expect(detailNote(resp({ graphics_mode: "all", graphics_count: 1,
      graphics: { a: { group: "structure", cut: {}, projection: {}, is_cut: false } } })))
      .toBe("Showing all 1 resolved element(s).");
  });

  it("names the asked-for GlobalIds that are not visible under the template", () => {
    const n = detailNote(resp({ graphics_mode: "guids", graphics_unknown: ["NOPE"],
      graphics: { a: { group: "structure", cut: {}, projection: {}, is_cut: false } } }));
    expect(n).toContain("Showing 1 named element(s) of 42,857");
    expect(n).toContain("not visible under this template: NOPE");
  });

  it("renders which side each element draws on, because it is why the columns differ", () => {
    const rows = elementRows(resp({ graphics: {
      a: { group: "enclosure", cut: { weight: 1.4 }, projection: { weight: 0.18 }, is_cut: true },
      b: { group: "mep", cut: { weight: 0.25 }, projection: { weight: 0.13 }, is_cut: false } } }));
    expect(rows.map((r) => r.isCut)).toEqual(["cut", "seen beyond"]);
    expect(rows[0]!.cut).toBe("1.4 mm · — · —");
  });
});

describe("the sample GlobalIds", () => {
  it("come from the style buckets, deduplicated and bounded", () => {
    expect(sampleGuids(resp(), 3)).toEqual(["0000000000000000000001",
      "0000000000000000000002", "0000000000000000000000"]);
    expect(sampleGuids(resp({ styles: [] }))).toEqual([]);
  });

  it("does not repeat a GlobalId that two buckets happen to sample", () => {
    expect(sampleGuids(resp({ styles: [bucket({ sample: ["X"] }), bucket({ sample: ["X", "Y"] })] })))
      .toEqual(["X", "Y"]);
  });
});

describe("the engine's note", () => {
  it("is returned verbatim — the client does not paraphrase a basis", () => {
    expect(graphicsNote(resp())).toBe(resp().note);
  });
});
