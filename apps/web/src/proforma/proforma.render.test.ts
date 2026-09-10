/**
 * Characterization tests for ProformaUI's massing + test-fit render paths — the safety net the
 * Repowise plan requires BEFORE the god-class split (health 1.65, top-1% change entropy, 4
 * bug-fixes in 180 d). These pin the two tabs that are about to be extracted along the LCOM4
 * seam, through the seam itself: the render methods, driven with a mocked ApiClient.
 *
 * What is pinned, deliberately: the form's field inventory and defaults (what `params()` derives),
 * the estimate flow's request payload and result summary, the no-project guard on generate, the
 * ESCAPED error path (the 2026-08-02 innerHTML XSS fix — a server error detail can quote the
 * caller's own input), and the unit-mix editor's default mix + localStorage round-trip. When the
 * extraction lands, these tests move with the code and must not change behavior.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { ProformaUI } from "./proforma";

/** A ProformaUI whose root is a fresh container and whose api is a per-test mock. */
function mount(api: Partial<Record<string, unknown>>, pid: string | null = null) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  const setStatus = vi.fn();
  const ui = new ProformaUI(root, api as unknown as ApiClient, setStatus, () => pid);
  // the private render methods ARE the seam the split will cut along — reach them deliberately
  return { root, ui: ui as unknown as { renderMassing(): void; renderTestFit(): void }, setStatus };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

const btn = (root: HTMLElement, text: string): HTMLButtonElement => {
  const b = [...root.querySelectorAll("button")].find((x) => x.textContent === text);
  if (!b) throw new Error(`no button ${text}`);
  return b;
};

/** The canned massing result the estimate/generate paths summarize. */
const RESULT = {
  metrics: {
    floors: 5, building_height_m: 17.5, buildable_gfa_sf: 64583, units: 64,
    footprint_m2: 1200, binding_constraint: "coverage", far_achieved: 3.0,
  },
  proforma: {
    assumptions: {},
    returns: { equity_irr: 0.182, equity_multiple: 2.1 },
    sources_uses: { total_uses: 20_000_000, equity: 7_000_000 },
  },
};

describe("renderMassing (characterization)", () => {
  beforeEach(() => localStorage.clear());

  it("builds the zoning form: use-type select, 14 numeric fields with the documented defaults, 6 toggles, parking, 2 actions", () => {
    const { root, ui } = mount({});
    ui.renderMassing();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host).toBeTruthy();
    expect(host.querySelectorAll("select").length).toBe(1);
    const nums = [...host.querySelectorAll(".pf-form input[type=number]")] as HTMLInputElement[];
    expect(nums.length).toBe(14);
    expect(nums[0]?.value).toBe("50");                       // lot width (m)
    expect(nums.map((i) => i.value)).toContain("225");       // hard $/sf default
    expect(host.querySelectorAll("input[type=checkbox]").length).toBe(6); // dome/frame/units/envelope/core/corridor
    expect(btn(host, "Estimate yield")).toBeTruthy();
    expect(btn(host, "Generate IFC model + apply")).toBeTruthy();
  });

  it("estimate: sends params derived from the form (height_limit 0 → null) and summarizes the result", async () => {
    const previewMassing = vi.fn().mockResolvedValue(RESULT);
    const { root, ui } = mount({ previewMassing });
    ui.renderMassing();
    btn(root, "Estimate yield").click();
    await flush();
    expect(previewMassing).toHaveBeenCalledTimes(1);
    const sent = previewMassing.mock.calls[0]?.[0];
    expect(sent).toMatchObject({ use_type: "residential", lot_width: 50, lot_depth: 40, far: 3,
                                 height_limit: null, frame: false, units: false });
    expect(sent.parking).toBeUndefined();                    // 0 stalls → key omitted
    const out = root.querySelector("#pf-massing")?.textContent ?? "";
    expect(out).toContain("5 floors");
    expect(out).toContain("64,583 sf");
    expect(out).toContain("bound by coverage");
    expect(out).toContain("18.2%");                          // equity IRR formatted
  });

  // PARCEL-SHAPE — the wiring claim, end to end through the real tab. `parcelBoundary.test.ts`
  // proves the control; this proves the tab SENDS what the control holds. Deleting
  // `if (parcel) p.lot_polygon = parcel.ring` leaves every assertion in this file green but one.
  it("estimate with a parcel loaded: sends the RING, and says which lot the figures are on", async () => {
    const previewMassing = vi.fn().mockResolvedValue(RESULT);
    const parcelAnalyze = vi.fn().mockResolvedValue({
      ring_m: [[0, 0], [50, 0], [50, 20], [20, 20], [20, 50], [0, 50]],
      area_m2: 1600, area_acres: 0.395, bounding_rect_m2: 2500,
      lot_width_m: 50, lot_depth_m: 50, vertices: 6, coordinates_were_lonlat: false,
    });
    const { root, ui } = mount({ previewMassing, parcelAnalyze });
    ui.renderMassing();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    (host.querySelector("textarea") as HTMLTextAreaElement).value =
      '{"type":"Polygon","coordinates":[[[1000,2000],[1050,2000],[1050,2020],[1020,2020],[1020,2050],[1000,2050]]]}';
    btn(host, "Use this parcel").click();
    await flush();
    expect(parcelAnalyze).toHaveBeenCalledTimes(1);
    // The two rectangle inputs are superseded, not silently left showing a stale 50 x 40.
    const nums = [...host.querySelectorAll(".pf-form input[type=number]")] as HTMLInputElement[];
    expect(nums[0]?.value).toBe("50");
    expect(nums[1]?.value, "lot depth becomes the parcel's own bbox extent").toBe("50");
    expect(nums[0]?.disabled && nums[1]?.disabled, "and neither can be edited past the parcel")
      .toBe(true);

    btn(host, "Estimate yield").click();
    await flush();
    const sent = previewMassing.mock.calls[0]?.[0];
    expect(sent.lot_polygon, "the ring is what makes the server offset a real parcel")
      .toEqual([[0, 0], [50, 0], [50, 20], [20, 20], [20, 50], [0, 50]]);
    const out = host.textContent ?? "";
    expect(out, "a GFA on 1,600 m2 and one on 2,500 m2 look identical unless the panel says")
      .toContain("on the real parcel");
    expect(out).toContain("1,600 m²");
    expect(out).toContain("2,500 m²");
  });

  it("estimate with NO parcel: no lot_polygon key at all, and no claim about a parcel", async () => {
    // Without this the case above passes for the wrong reason: a tab that always sent some polygon
    // would satisfy it, and would then overrule the rectangle the user actually typed.
    const previewMassing = vi.fn().mockResolvedValue(RESULT);
    const { root, ui } = mount({ previewMassing });
    ui.renderMassing();
    btn(root, "Estimate yield").click();
    await flush();
    expect(previewMassing.mock.calls[0]?.[0].lot_polygon).toBeUndefined();
    expect(root.querySelector("#pf-massing")?.textContent ?? "").not.toContain("on the real parcel");
  });

  it("generate without a project: guard message, api never called", async () => {
    const generateMassing = vi.fn();
    const { root, ui } = mount({ generateMassing }, null);
    ui.renderMassing();
    btn(root, "Generate IFC model + apply").click();
    await flush();
    expect(generateMassing).not.toHaveBeenCalled();
    expect(root.querySelector("#pf-massing")?.textContent).toContain("Open or create a project first");
  });

  it("an error detail is ESCAPED into the output, never parsed as markup (2026-08-02 XSS regression)", async () => {
    const previewMassing = vi.fn().mockRejectedValue(new Error('<img src=x onerror="window.__pwned=1">'));
    const { root, ui } = mount({ previewMassing });
    ui.renderMassing();
    btn(root, "Estimate yield").click();
    await flush();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host.querySelector("img")).toBeNull();            // markup neutralized…
    expect(host.textContent).toContain("<img src=x");        // …but the message still shown verbatim
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("the generate error path escapes too (sink 2 of 4 from the same fix)", async () => {
    const generateMassing = vi.fn().mockRejectedValue(new Error("<b>422</b> detail quoting caller input"));
    const { root, ui } = mount({ generateMassing }, "p1");
    ui.renderMassing();
    btn(root, "Generate IFC model + apply").click();
    await flush();
    const host = root.querySelector("#pf-massing") as HTMLElement;
    expect(host.querySelector("b")).toBeNull();
    expect(host.textContent).toContain("<b>422</b>");
  });

  it("SOURCE PIN: every error-message innerHTML sink in proforma/ stays on the escaped path", async () => {
    // The four sinks fixed on 2026-08-02 took `(e as Error).message` into innerHTML unescaped.
    // Two are exercised above; the other two live in panels that need a deep api mock to drive,
    // so pin ALL of them at the source level, DERIVED not enumerated: an interpolation of an
    // error message into innerHTML must go through escapeHtml (textContent/setStatus are exempt —
    // they don't parse markup). Down-to-zero is the required state; any new unescaped sink fails.
    const { readFileSync, readdirSync } = await import("node:fs");
    const { join } = await import("node:path");
    const offenders: string[] = [];
    for (const f of readdirSync(__dirname).filter((n) => n.endsWith(".ts") && !n.endsWith(".test.ts"))) {
      const src = readFileSync(join(__dirname, f), "utf-8");
      for (const [i, line] of src.split("\n").entries()) {
        if (/innerHTML\s*[+]?=/.test(line) && /\((e|err) as Error\)\.message/.test(line)
            && !/escapeHtml\(\((e|err) as Error\)\.message\)/.test(line)) {
          offenders.push(`${f}:${i + 1}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("renderTestFit (characterization)", () => {
  beforeEach(() => localStorage.clear());

  it("renders the plate form and the default Studio/1BR/2BR mix summing to 100%", () => {
    const { root, ui } = mount({});
    ui.renderTestFit();
    const host = root.querySelector("#pf-testfit") as HTMLElement;
    expect(host).toBeTruthy();
    const plates = [...host.querySelectorAll(".pf-form input[type=number]")] as HTMLInputElement[];
    expect(plates.map((i) => i.value)).toEqual(["40", "18", "6"]);   // width / depth / floors
    const names = [...host.querySelectorAll("input:not([type=number]):not([type=checkbox])")]
      .map((i) => (i as HTMLInputElement).value);
    expect(names).toEqual(["Studio", "1BR", "2BR"]);         // the default mix, one text input per row
    expect(host.textContent).toContain("mix Σ 100%");
  });

  it("the mix editor adds a unit type and Save persists it for the next mount", () => {
    const first = mount({});
    first.ui.renderTestFit();
    let host = first.root.querySelector("#pf-testfit") as HTMLElement;
    btn(host, "+ unit type").click();
    expect(host.textContent).toContain("mix Σ 110%");        // 100% + the new 10% row, flagged live
    btn(host, "Save mix").click();
    expect(first.setStatus).toHaveBeenCalledWith("unit mix saved");

    const second = mount({});
    second.ui.renderTestFit();
    host = second.root.querySelector("#pf-testfit") as HTMLElement;
    expect(host.textContent).toContain("mix Σ 110%");        // round-tripped through localStorage
  });
});

/**
 * RESERVE-SUGGESTION-UNVERIFIED — the banner must not present an unverified figure as a target.
 *
 * `reserve.py` solves the level contribution and then RE-RUNS it against the schedule to confirm it
 * clears; `suggestion_clears_horizon` is that second answer. This banner printed the number in bold
 * as a recommendation and never read the flag, so a figure that failed verification looked exactly
 * like one that passed — at the moment a user would act on it.
 *
 * Read as `=== false`. The field is optional, and an older server that omits it means "not checked",
 * which must not render as "does not work".
 */
const STUDY = {
  horizon: { from: 2026, to: 2051 }, components: 12, components_missing_data: 0,
  events: [], schedule: [], total_outflows: 900_000,
  first_underfunded_year: 2033, adequately_funded: false,
  suggested_level_contribution: 42_000, note: "",
};

describe("reserve study — an unverified suggestion says so", () => {
  const mountAsset = async (study: Record<string, unknown>) => {
    const { root, ui } = mount({ reserveStudy: vi.fn(async () => study) }, "P1");
    const host = document.createElement("div"); root.appendChild(host);
    await (ui as unknown as { renderAssetMgmt(h: HTMLElement): Promise<void> }).renderAssetMgmt(host);
    await flush(); await flush();
    return host;
  };

  it("warns when the solved figure did not clear the horizon", async () => {
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: false });
    expect(host.textContent).toContain("did not clear the horizon when re-run");
    expect(host.textContent, "the figure is still shown — it is unreliable, not absent")
      .toContain("42,000");
  });

  it("stays silent when the figure verified — the paired control", async () => {
    // Without this the assertion above could pass with the warning rendered unconditionally.
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: true });
    expect(host.textContent).toContain("42,000");
    expect(host.textContent).not.toContain("did not clear the horizon");
  });

  it("stays silent when the server did not answer — absent is not failed", async () => {
    // An older server omits the field. Inventing a warning from a missing value is its own wrong
    // answer, and one false alarm here costs trust in the figure every other time it is right.
    const host = await mountAsset(STUDY);
    expect(host.textContent).toContain("42,000");
    expect(host.textContent).not.toContain("did not clear the horizon");
  });

  it("says only what the flag licenses — no invented cause", async () => {
    // The first draft read "No flat contribution does; the shortfall needs a higher opening
    // balance...". That is FALSE: `need` is the exact closed-form minimum, so a failed verification
    // means the solved figure disagreed with the schedule, not that the horizon is unclearable.
    // Explaining a cause it cannot know is the same defect this banner exists to fix.
    const host = await mountAsset({ ...STUDY, suggestion_clears_horizon: false });
    expect(host.textContent).not.toContain("No flat contribution");
    expect(host.textContent).toContain("unreliable");
  });
});

/**
 * R35-DEAL-MEMORY — the $/SF strip must describe the hard cost that is on screen NOW.
 *
 * Review finding, 2026-08-27: the strip was painted once by `renderBudget()`, so editing
 * "Hard cost $" left a comparison for the PREVIOUS hard cost sitting beside the new number. That is
 * the defect class this whole release is about — a report that misdescribes what it reports on —
 * and it is worse on an underwriting screen than most places, because the two numbers are adjacent
 * and the stale one looks like it was computed from the fresh one.
 *
 * Driven through `refreshDealMemory`, the seam the fix created, rather than through a keystroke:
 * the debounce is `window.setTimeout` and pinning a timer would test the scheduler, not the sum.
 */
describe("the deal-memory strip follows the hard cost", () => {
  function mountBudget(pid: string | null = "P1") {
    const api = {
      dealMemoryBeside: vi.fn().mockResolvedValue({
        metric: "cost_per_sf", status: "insufficient_history", entered: null,
      }),
    };
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const ui = new ProformaUI(root, api as unknown as ApiClient, vi.fn(), () => pid);
    const priv = ui as unknown as {
      a: { cost_lines: { category: string; amount: number }[] };
      memoryEl?: HTMLElement;
      refreshDealMemory(): void;
    };
    // mount a connected element for the strip — `refreshDealMemory` refuses to paint a detached one
    const el = document.createElement("div"); root.appendChild(el); priv.memoryEl = el;
    return { api, priv };
  }

  it("sends the CURRENT hard-cost total, not the one from first render", () => {
    const { api, priv } = mountBudget();
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 20_000_000);

    // the edit the reviewer described: change the hard line, refresh, expect the NEW total
    const hard = priv.a.cost_lines.find((c) => c.category === "hard")!;
    hard.amount = 26_500_000;
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 26_500_000);
  });

  it("sums every hard line rather than reading cost_lines[1]", () => {
    // The default deal happens to put hard cost second. A budget synced from the GC's does not, and
    // an index would have compared the wrong line against the firm's own history — silently, since
    // any number looks plausible in a $/SF strip.
    const { api, priv } = mountBudget();
    priv.a.cost_lines.push({ category: "hard", amount: 1_000_000 } as never);
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).toHaveBeenLastCalledWith("P1", 21_000_000);
  });

  it("asks nothing when there is no project", () => {
    const { api, priv } = mountBudget(null);
    priv.refreshDealMemory();
    expect(api.dealMemoryBeside).not.toHaveBeenCalled();
  });
});

/**
 * DEAD-FIELD / renderAppraisal — the valuation panel says what the PDF of the same response says.
 *
 * Found by a TYPE-AWARE unread-field pass (the TS compiler API resolving each property access to its
 * declaring `PropertySignature`, rather than matching identifiers). Every field asserted below is one
 * the server computes, `report_builders/finance.py` prints, and this screen did not read — so a user
 * comparing the on-screen valuation with the exported valuation report saw less on screen.
 *
 * The worst case is the first test. `reconcile()` drops any approach whose value is zero and returns
 * `value: 0.0` when none is usable, and the panel printed `money(0)` — "$0" in 28px as an opinion of
 * value. A property that could not be appraised was displayed as a property worth nothing, while the
 * PDF printed "(insufficient data)". It is reachable with no exception in the way: `appraisal_inputs`
 * coalesces every input through `float(x or 0.0)` and `income_approach` guards its own divide.
 */
describe("renderAppraisal — the screen no longer says less than the PDF", () => {
  const ZERO_APPROACH = { approach: "", value: 0 };
  const base = (over: Record<string, unknown> = {}) => ({
    inputs: { replacement_cost_new: 0, land_value: 0, depreciation_pct: 0, stabilized_noi: 0,
              cap_rate: 0, subject_sqft: 0, subject_units: null, has_proforma: false },
    cost: { ...ZERO_APPROACH, approach: "cost", replacement_cost_new: 0, depreciation_pct: 0,
            depreciation_amount: 0, depreciated_improvements: 0, land_value: 0 },
    income: { ...ZERO_APPROACH, approach: "income", stabilized_noi: 0, cap_rate: 0,
              method: "direct_capitalization" },
    sales_comparison: { ...ZERO_APPROACH, approach: "sales_comparison", comp_count: 0, basis: "none",
                        median_price_psf: null, median_price_per_unit: null, implied_cap_rate: null },
    reconciliation: { value: 0, contributions: [], approaches_used: [],
                      range: { low: 0, high: 0, spread_pct: 0 } },
    comp_count: 0,
    ...over,
  });

  /** Render the valuation tab against a canned appraisal response and return its text. */
  const paint = async (v: Record<string, unknown>) => {
    const { root, ui } = mount({ appraisal: vi.fn().mockResolvedValue(v), reportUrl: () => "#" }, "p1");
    const host = document.createElement("div"); root.appendChild(host);
    await (ui as unknown as { renderAppraisal(h: HTMLElement): Promise<void> }).renderAppraisal(host);
    await flush();
    /** The value cell of the approach-table row whose label cell is exactly `label`.
     *
     *  Reading the row rather than the page text on purpose: adjacent `<td>`s concatenate with no
     *  separator, so `textContent` gives "Cap rate—" and an assertion written the natural way silently
     *  never matches. Worse, a substring assertion over the whole panel can be satisfied by a DIFFERENT
     *  card — "$0" appears in all three — so it would pass whatever the row under test said. */
    const cell = (label: string): string | null => {
      for (const tr of host.querySelectorAll("tr")) {
        const [k, val] = tr.querySelectorAll("td");
        if (k?.textContent?.trim() === label) return val?.textContent?.trim() ?? null;
      }
      return null;
    };
    return { host, cell, txt: (host.textContent ?? "").replace(/\s+/g, " ") };
  };

  it("a project nothing could value shows an em dash and why — never '$0' as an opinion of value", async () => {
    const { host, txt } = await paint(base());
    expect(txt).toContain("Insufficient data");
    expect(txt).toContain("No proforma is saved");                 // reads `inputs.has_proforma`
    // The headline itself must not be a money figure. Assert on the ELEMENT, not the page text:
    // "$0" appears legitimately in the approach cards below, and matching the whole panel would pass
    // whatever the headline said.
    const headline = host.querySelector('div[style*="font-size:28px"]');
    expect(headline?.textContent).toBe("—");
  });

  it("names which approaches reconciled into the value, and says the rest were excluded", async () => {
    const { txt } = await paint(base({
      inputs: { ...base().inputs, has_proforma: true },
      cost: { ...base().cost, value: 4_000_000 },
      income: { ...base().income, value: 5_000_000, cap_rate: 0.055, stabilized_noi: 275_000 },
      reconciliation: { value: 4_600_000, approaches_used: ["income", "cost"],
                        contributions: [{ approach: "income", value: 5_000_000, weight: 0.6 },
                                        { approach: "cost", value: 4_000_000, weight: 0.4 }],
                        range: { low: 4_000_000, high: 5_000_000, spread_pct: 0.217 } },
    }));
    expect(txt).toContain("Reconciled from 2 of 3 approaches: income, cost");
    expect(txt).toContain("the rest produced no value and were excluded");
  });

  it("does not claim approaches were excluded when all three reconciled", async () => {
    const { txt } = await paint(base({
      reconciliation: { value: 5_000_000, approaches_used: ["income", "sales_comparison", "cost"],
                        contributions: [], range: { low: 4e6, high: 6e6, spread_pct: 0.4 } },
    }));
    expect(txt).toContain("Reconciled from 3 of 3 approaches");
    expect(txt).not.toContain("were excluded");
  });

  it("shows the median that MATCHES the basis — a $/unit basis is not a blank $/SF row", async () => {
    const { cell } = await paint(base({
      sales_comparison: { ...base().sales_comparison, basis: "$/unit", comp_count: 4,
                          median_price_psf: null, median_price_per_unit: 210_000, value: 8_400_000 },
      reconciliation: { value: 8_400_000, approaches_used: ["sales_comparison"], contributions: [],
                        range: { low: 8_400_000, high: 8_400_000, spread_pct: 0 } },
    }));
    expect(cell("Median $/unit")).toBe("$210,000");
    expect(cell("Median $/SF"), "the $/SF row must be GONE, not merely blank").toBeNull();
  });

  it("labels a raw-median basis as a sale price rather than a $/SF that is not one", async () => {
    const { cell } = await paint(base({
      sales_comparison: { ...base().sales_comparison, basis: "median price", comp_count: 3,
                          value: 3_100_000 },
    }));
    expect(cell("Median sale price")).toBe("$3,100,000");
    expect(cell("Median $/SF")).toBeNull();
  });

  it("shows the implied cap rate the comparables carry, and a dash when they carry none", async () => {
    const withCap = await paint(base({
      sales_comparison: { ...base().sales_comparison, basis: "$/SF", median_price_psf: 310,
                          implied_cap_rate: 0.0545, comp_count: 5, value: 5_100_000 },
    }));
    expect(withCap.cell("Implied cap rate")).toBe("5.45%");
    const without = await paint(base());
    expect(without.cell("Implied cap rate")).toBe("—");
  });

  it("shows the depreciation PERCENTAGE beside the amount deducted", async () => {
    const { cell } = await paint(base({
      cost: { ...base().cost, replacement_cost_new: 10_000_000, depreciation_pct: 0.15,
              depreciation_amount: 1_500_000, depreciated_improvements: 8_500_000, value: 8_500_000 },
    }));
    expect(cell("Less depreciation")).toBe("-$1,500,000 (15%)");
  });

  it("shows a cap rate of zero as a dash, not as a 0.00% capitalisation rate", async () => {
    const { cell, txt } = await paint(base());
    expect(cell("Cap rate")).toBe("—");
    expect(txt).not.toContain("0.00%");
  });

  it("names comparables the appraiser excluded, so a shrunken sample is a decision and not a mood", async () => {
    const { txt } = await paint(base({
      excluded_comparables: [{ id: "c1", ref: "COMP-004", reason: "excluded by the appraiser" },
                             { id: "c2", ref: "COMP-009", reason: "excluded by the appraiser" }],
    }));
    expect(txt).toContain("2 comparables were excluded by the appraiser");
    expect(txt).toContain("COMP-004, COMP-009");
  });

  it("says nothing about exclusions when the server named none", async () => {
    const { txt } = await paint(base());
    expect(txt).not.toContain("excluded by the appraiser");
  });
});
