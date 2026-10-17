import { describe, expect, it, vi } from "vitest";

import type { RoundtripDiff } from "./roundtripDiffView";
import { applyLabel, renderRoundtripDiff, statusHtml, truncationNote } from "./roundtripDiffView";

/**
 * TRUNC-COUNTED, asserted on BEHAVIOUR rather than on the panel's source text.
 *
 * `services/api/test_trunc_counted.py` originally string-matched `qaSection.ts` for these three
 * decisions, which is the weakest form of check available — it cannot tell a rendered string from a
 * comment, and it passed twice while the thing under test was deleted. Extracting the view to make
 * `qaSection.ts` fit its down-only size ratchet made them testable for real, so this file owns the
 * behaviour and the Python gate keeps only the server shape and the client DECLARATIONS.
 *
 * The load-bearing case is `truncated`: Apply posts the PAGE, so on an overflowing sheet the button
 * must not name the total it is not going to write.
 */

const D = (over: Partial<RoundtripDiff> = {}): RoundtripDiff => ({
  checked: 40, unchanged: 10,
  changes: [{ guid: "3Rb$mtGnf8kQm0Xy1_ZzAB", pset: "Pset_WallCommon", prop: "FireRating",
              old: "1HR", new: "2HR" }],
  truncated: false, change_count: 1,
  unknown_guids: [], unknown_count: 0,
  rows_read: 40, rows_cap: 5000, rows_truncated: false,
  ...over,
} as RoundtripDiff);

/** A page of 1,000 changes out of 4,000 — the measured overflow shape. */
const OVERFLOW = () => D({
  changes: Array.from({ length: 1000 }, (_, i) => ({
    guid: `G${i}`, pset: "P", prop: "x", old: "a", new: "b" })),
  truncated: true, change_count: 4000, checked: 5000,
});

describe("the headline counts, never the page", () => {
  it("reports change_count, not changes.length", () => {
    expect(statusHtml(OVERFLOW())).toContain("<b>4000</b> change(s)");
    expect(statusHtml(OVERFLOW())).not.toContain("<b>1000</b> change(s)");
  });

  it("reports unknown_count, not unknown_guids.length", () => {
    const d = D({ unknown_guids: new Array(100).fill("G"), unknown_count: 5000 });
    expect(statusHtml(d)).toContain("<b>5000</b> unknown GUID(s)");
    expect(statusHtml(d)).not.toContain("<b>100</b> unknown GUID(s)");
  });

  it("says nothing about unknown GUIDs when there are none — a caveat always on is decoration", () => {
    expect(statusHtml(D())).not.toContain("unknown GUID");
  });

  it("names the SHEET bound, which nothing disclosed at all", () => {
    const d = D({ rows_read: 20000, rows_cap: 5000, rows_truncated: true });
    expect(statusHtml(d)).toContain("only the first 5000 rows of 20000 were read");
  });

  it("stays quiet about the sheet bound when the whole sheet was read", () => {
    expect(statusHtml(D())).not.toContain("rows of");
  });
});

describe("the button names what it will actually write", () => {
  // It posts `d.changes` — the page. Claiming the total here is the defect that made a partial
  // write read as a complete one.
  it("on an overflowing sheet, says the page AND the total", () => {
    expect(applyLabel(OVERFLOW())).toBe("✓ Apply the first 1000 of 4000 change(s) + republish");
  });

  it("on a whole sheet, says the plain count", () => {
    expect(applyLabel(D())).toBe("✓ Apply 1 change(s) + republish");
  });

  it("never claims the total it is not going to write", () => {
    expect(applyLabel(OVERFLOW())).not.toBe("✓ Apply 4000 change(s) + republish");
  });
});

describe("the warning beside it", () => {
  it("says the rest are left unwritten, and what to do", () => {
    const n = truncationNote(OVERFLOW());
    expect(n).toContain("4000 changes");
    expect(n).toContain("leaves the rest");
    expect(n).toContain("split the sheet");
  });

  it("is absent when nothing was truncated", () => {
    expect(truncationNote(D())).toBe("");
  });
});

describe("rendering", () => {
  const mount = () => {
    const status = document.createElement("div");
    const diffBox = document.createElement("div");
    document.body.replaceChildren(status, diffBox);
    return { status, diffBox };
  };

  it("returns no Apply button when there is nothing to apply", () => {
    const ctx = { ...mount(), apply: vi.fn() };
    expect(renderRoundtripDiff(D({ changes: [], change_count: 0 }), ctx)).toBeNull();
    expect(ctx.status.textContent).toContain("0 change(s)");
  });

  it("hands Apply the PAGE, which is all the server gave it", () => {
    const ctx = { ...mount(), apply: vi.fn() };
    const d = OVERFLOW();
    const btn = renderRoundtripDiff(d, ctx)!;
    btn.click();
    expect(ctx.apply).toHaveBeenCalledOnce();
    expect(ctx.apply.mock.calls[0]![0]).toHaveLength(1000);
  });

  it("escapes values that came out of a spreadsheet", () => {
    // The CSV is user-supplied and every cell reaches innerHTML.
    const ctx = { ...mount(), apply: vi.fn() };
    renderRoundtripDiff(D({ changes: [{ guid: "G", pset: "<img src=x onerror=1>", prop: "p",
                                        old: null, new: "<b>x</b>" }] }), ctx);
    expect(ctx.diffBox.innerHTML).not.toContain("<img src=x");
    expect(ctx.diffBox.querySelector("img")).toBeNull();
  });

  it("renders the truncation note into the box, not only into the label", () => {
    const ctx = { ...mount(), apply: vi.fn() };
    renderRoundtripDiff(OVERFLOW(), ctx);
    expect(ctx.diffBox.textContent).toContain("leaves the rest");
  });
});
