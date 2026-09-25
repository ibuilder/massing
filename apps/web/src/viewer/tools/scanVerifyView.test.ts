import { describe, expect, it } from "vitest";

import type { Deviation, Lod500 } from "./scanVerifyView";
import { refused, renderDeviation, renderLod500 } from "./scanVerifyView";

/**
 * SCAN-DARK. Both engines are sound and were measured before this card existed:
 *
 *   * `analyze` REFUSES to produce a deviation figure when the model reference was cut short, and
 *     that refusal is the whole of SCAN-TRUNC — rendering a zero, or an empty histogram, in its
 *     place would reinstate the defect from the consumer side.
 *   * `verify_from_scan` fails closed on a scan that covered nothing: `verified: 0, stamped: 0,
 *     uncovered: 50`. `within_tolerance` is `null` on an uncovered element, never `false`.
 *
 * So what is pinned here is that the card does not SUBTRACT that care. The two load-bearing ones
 * are the refusal rendering as a refusal, and `uncovered` carrying the same weight as `verified` —
 * a high verified count over a thin scan is precisely the number somebody would quote.
 */

const DEV = (over: Partial<Deviation> = {}): Deviation => ({
  point_count: 1000, reference_count: 200000, tolerance: 0.05,
  points_total: 1000, points_truncated: false, reference_truncated: false,
  within_pct: 97.5, within_tolerance: 975, out_of_tolerance: 25,
  mean_deviation: 0.012, max_deviation: 0.31, p95_deviation: 0.04,
  histogram: [{ band: "≤1×tol", count: 975 }, { band: ">3×tol", count: 25 }],
  note: "Nearest-surface deviation of each scan point.",
  ...over,
} as Deviation);

/** The SCAN-TRUNC refusal, as the engine really returns it. */
const REFUSAL = (): Deviation => ({
  point_count: 1000, reference_count: 200000,
  points_total: 1000, points_truncated: false, reference_truncated: true,
  within_pct: null, tolerance: 0.05,
  error: "the model reference was capped at 200,000 surface vertices, so part of the model is "
    + "absent from the comparison",
  note: "Absence of reference geometry is not evidence of deviation.",
} as Deviation);

/** The OTHER refusal branch: no readable points, or no model geometry. `within_pct` is null and
 *  `reference_truncated` is FALSE, so a predicate keyed on that flag misses it entirely — which a
 *  mutation proved, because every fixture above happened to set the two together. *Asserting the
 *  one case you thought of is not asserting the property.* */
const EMPTY_REFUSAL = (): Deviation => ({
  point_count: 0, reference_count: 200000,
  points_total: 0, points_truncated: false, reference_truncated: false,
  within_pct: null, error: "empty point cloud or reference",
} as Deviation);

const L = (over: Partial<Lod500> = {}): Lod500 => ({
  applied: false, verified: 2, stamped: 0, accuracy_recorded: 0,
  findings: [], findings_count: 0, uncovered: 0, uncovered_guids: [],
  tolerance: 0.05, note: "Verified elements are stamped WITH their measured deviation.",
  deviation: {} as Lod500["deviation"], elements: [],
  ...over,
} as Lod500);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};
const devText = (d: Deviation) => renderDeviation(mount(), d).textContent ?? "";
const lodText = (r: Lod500) => renderLod500(mount(), r).textContent ?? "";

describe("the refusal renders as a refusal", () => {
  it("is recognised from within_pct being null, not from a flag a future branch might omit", () => {
    expect(refused(REFUSAL())).toBe(true);
    expect(refused(DEV())).toBe(false);
    // THE SECOND BRANCH, and the reason the predicate reads the missing FIGURE rather than the
    // truncation flag: an empty cloud refuses too, with `reference_truncated` false.
    expect(refused(EMPTY_REFUSAL())).toBe(true);
    expect(EMPTY_REFUSAL().reference_truncated).toBe(false);
  });

  it("renders the empty-input refusal as a refusal too", () => {
    const el = renderDeviation(mount(), EMPTY_REFUSAL());
    expect(el.textContent).toContain("No deviation figure");
    expect(el.textContent).toContain("empty point cloud or reference");
    expect(el.querySelector("table")).toBeNull();
  });

  it("says there is no figure, and gives the engine's reason", () => {
    const t = devText(REFUSAL());
    expect(t).toContain("No deviation figure");
    expect(t).toContain("capped at 200,000 surface vertices");
  });

  it("prints NO percentage, band table or statistic — a zero here reinstates SCAN-TRUNC", () => {
    const el = renderDeviation(mount(), REFUSAL());
    expect(el.querySelector("table")).toBeNull();
    const t = el.textContent ?? "";
    expect(t).not.toContain("%");
    expect(t).not.toContain("mean");
  });
});

describe("the aggregate, when there IS a figure", () => {
  it("leads with the percentage and its tolerance", () => {
    expect(devText(DEV())).toContain("97.5% of scan points within 0.05 m");
  });

  it("renders the deviation bands", () => {
    const rows = [...renderDeviation(mount(), DEV()).querySelectorAll("tr")]
      .map((tr) => tr.textContent ?? "");
    expect(rows.some((r) => r.includes("≤1×tol") && r.includes("975"))).toBe(true);
  });

  it("says when only a region of the cloud was examined", () => {
    const t = devText(DEV({ point_count: 500000, points_total: 2000000, points_truncated: true }));
    expect(t).toContain("500,000 of 2,000,000");
    expect(t).toContain("REGION");
  });

  it("stays quiet about that when the whole cloud was read", () => {
    expect(devText(DEV())).not.toContain("REGION");
  });
});

describe("uncovered carries the same weight as verified", () => {
  it("names what was never scanned, and that it is not evidence", () => {
    const t = lodText(L({ verified: 2, uncovered: 48 }));
    expect(t).toContain("2 verified of 50");
    expect(t).toContain("48 never scanned");
    expect(t).toContain("absence of points is not evidence");
  });

  it("says so plainly when coverage was complete", () => {
    const t = lodText(L({ verified: 50, uncovered: 0 }));
    expect(t).toContain("Every element was covered");
    expect(t).not.toContain("never scanned");
  });

  it("does not let a thin scan read as a strong result — the count is of the WHOLE population", () => {
    // 2 of 50, not "2 verified" with the other 48 invisible.
    expect(lodText(L({ verified: 2, uncovered: 48 }))).not.toContain("2 verified of 2");
  });
});

describe("a finding is shown as NOT stamped", () => {
  it("lists it with its deviations and says why it was left alone", () => {
    const t = lodText(L({ verified: 1, findings_count: 1, uncovered: 0,
      findings: [{ guid: "3Rb$mtGnf8kQm0Xy1", ifc_class: "IfcSlab",
                   p95_deviation: 0.4, max_deviation: 0.6 }] }));
    expect(t).toContain("Verified as WRONG — not stamped");
    expect(t).toContain("IfcSlab");
    expect(t).toContain("0.4");
    expect(t).toContain("punch item, not a handover");
  });

  it("shows no findings table when there are none", () => {
    expect(renderLod500(mount(), L()).querySelector("table")).toBeNull();
  });
});

describe("a dry run says so", () => {
  it("distinguishes a plan from a write", () => {
    expect(lodText(L())).toContain("Dry run");
    expect(lodText(L({ applied: true, stamped: 2 }))).toContain("Stamped 2");
  });

  it("says when stamps carry their measured accuracy", () => {
    expect(lodText(L({ applied: true, stamped: 2, accuracy_recorded: 2 })))
      .toContain("states an accuracy rather than a bare claim");
  });
});
