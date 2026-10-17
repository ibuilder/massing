import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { renderEvm } from "./evm";
import type { ModelEv, ModelProgress } from "./modelEvReading";
import {
  fullyDetermined, modelEvReading, modelEvRows, modelProgressReading,
} from "./modelEvReading";

/**
 * EVM-COVERAGE, the consumer half — the card made a front-loading accusation while reading a
 * boolean that is true after ONE element of the model has been surveyed.
 *
 * The engine half is `services/api/test_evm_coverage.py`, which replays the pre-fix rule and proves
 * it accused on thin coverage. This file asserts the screen: that coverage is answered before the
 * verdict, that the two states the old card collapsed are now distinguishable, and that the one
 * number the engine rounds away is carried by the counts beside it.
 */

const mk = (o: Partial<ModelEv> = {}): ModelEv => {
  const total = o.total_elements ?? 4000;
  const tracked = o.tracked_elements ?? 0;
  const installed = o.installed_elements ?? 0;
  const deviated = o.deviated_elements ?? 0;
  const determined = o.determined_elements ?? installed + deviated;
  const denom = total || tracked || 1;
  const pct = o.model_percent_complete ?? Math.round((1000 * installed) / denom) / 10;
  const pctMax = o.model_percent_complete_max ?? Math.round((1000 * (denom - deviated)) / denom) / 10;
  const bac = o.bac ?? 1_000_000;
  return {
    total_elements: total, installed_elements: installed, tracked_elements: tracked,
    determined_elements: determined, deviated_elements: deviated,
    coverage_pct: o.coverage_pct ?? Math.round((1000 * determined) / denom) / 10,
    basis: o.basis ?? (total ? "model elements" : tracked ? "surveyed elements" : "nothing"),
    model_percent_complete: pct, model_percent_complete_max: pctMax,
    has_field_data: o.has_field_data ?? tracked > 0,
    bac, ev_model: o.ev_model ?? (bac * pct) / 100, ev_model_max: o.ev_model_max ?? (bac * pctMax) / 100,
    ev_schedule: o.ev_schedule ?? 600_000,
    divergence: o.divergence ?? 600_000 - (bac * pct) / 100,
    divergence_unexplained: o.divergence_unexplained ?? 600_000 - (bac * pctMax) / 100,
    front_loaded_flag: o.front_loaded_flag ?? false,
    note: o.note ?? "",
  };
};

/** The shipped defect's input: 4,000 elements, one surveyed, schedule claiming 60%. */
const THIN = mk({ tracked_elements: 1, installed_elements: 1 });
/** Fully surveyed and genuinely behind — the accusation that must survive. */
const BEHIND = mk({ total_elements: 10, tracked_elements: 10, installed_elements: 1,
                    deviated_elements: 9, front_loaded_flag: true });
/**
 * Fully surveyed and in step. Six installed and FOUR DEVIATIONS, not six installed and four
 * untouched — "fully surveyed" means every element has a determined status, and six-of-ten installed
 * with nothing else said is a job where four inspections are still outstanding.
 */
const TRACKING = mk({ total_elements: 10, tracked_elements: 10, installed_elements: 6,
                      deviated_elements: 4, ev_schedule: 600_000 });

describe("modelEvReading — coverage is answered before the verdict", () => {
  it("is the SHIPPED DEFECT's input and does NOT accuse anybody", () => {
    const r = modelEvReading(THIN);
    expect(r.kind).toBe("thin");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("1 of 4000 model elements");
    expect(r.headline).toContain("between 0%");           // and the ceiling above it
    // It MENTIONS front-loading, to say the finding cannot be made — which is the point. What it
    // must not do is assert it, so the assertion is on the refusal rather than on the absence of a
    // word: `not.toContain("front-load")` passed only until the refusal was written down.
    expect(r.detail).toContain("no front-loading finding can be made");
  });

  it("names the range as COVERAGE, not as disagreement", () => {
    const r = modelEvReading(THIN);
    expect(r.detail).toContain("survey coverage, not disagreement");
    expect(r.detail).toContain("closes as elements are verified");
  });

  it("keeps the accusation when the survey is complete and the gap is real", () => {
    const r = modelEvReading(BEHIND);
    expect(r.kind).toBe("front_loaded");
    expect(r.tone).toBe("bad");
    expect(r.headline).toContain("ahead of the building");
    // and it quotes the gap that SURVIVED the most favourable reading, not the raw one
    expect(r.detail).toContain("survives the most favourable reading");
  });

  it("reports agreement only when every element's status is known", () => {
    expect(modelEvReading(TRACKING).kind).toBe("tracking");
    expect(modelEvReading(TRACKING).tone).toBe("ok");
    // the same job with two elements unsurveyed is NOT an agreement claim
    const partial = mk({ total_elements: 10, tracked_elements: 8, installed_elements: 6 });
    expect(modelEvReading(partial).kind).toBe("thin");
  });

  it("distinguishes an un-surveyed job from a job with no model at all", () => {
    const unsurveyed = modelEvReading(mk({ total_elements: 4000, tracked_elements: 0 }));
    expect(unsurveyed.kind).toBe("unsurveyed");
    expect(unsurveyed.headline).toContain("of 4000 model elements");
    expect(unsurveyed.detail).toContain("no conclusion about the schedule follows");
    const absent = modelEvReading(mk({ total_elements: 0, tracked_elements: 0 }));
    expect(absent.kind).toBe("absent");
    expect(absent.headline).not.toContain("0 model elements");
  });

  it("says WHICH denominator the percentage is a share of", () => {
    // Eight installed elements. Against the surveyed set that is 80%; against a loaded index, 0.2%.
    const noIndex = mk({ total_elements: 0, tracked_elements: 10, installed_elements: 8,
                         deviated_elements: 2 });
    const withIndex = mk({ total_elements: 4000, tracked_elements: 10, installed_elements: 8,
                           deviated_elements: 2 });
    expect(modelEvReading(noIndex).headline).toContain("10 surveyed elements");
    expect(modelEvReading(withIndex).headline).toContain("4000 model elements");
    expect(noIndex.model_percent_complete).toBe(80);
    expect(withIndex.model_percent_complete).toBe(0.2);
  });

  it("does not lead with `coverage_pct`, which rounds a real survey to 0.0%", () => {
    // 1 of 4,000 → 0.0%, the same string an untouched job prints. The counts are the authority.
    expect(THIN.coverage_pct).toBe(0);
    const r = modelEvReading(THIN);
    expect(r.headline).toContain("1 of 4000");
    expect(r.headline).not.toContain("0%" + " of");
    expect(modelEvReading(mk({ total_elements: 4000, tracked_elements: 0 })).kind)
      .not.toBe(r.kind);                 // ...and the two 0.0% jobs read differently
  });
});

describe("fullyDetermined", () => {
  it("is false while anything is merely queued — a pending row is not evidence", () => {
    expect(fullyDetermined(mk({ total_elements: 10, tracked_elements: 10, determined_elements: 0 })))
      .toBe(false);
    expect(fullyDetermined(BEHIND)).toBe(true);
  });

  it("falls back to the surveyed set when there is no index, and refuses an empty one", () => {
    expect(fullyDetermined(mk({ total_elements: 0, tracked_elements: 4, installed_elements: 4 })))
      .toBe(true);
    expect(fullyDetermined(mk({ total_elements: 0, tracked_elements: 0 }))).toBe(false);
  });
});

describe("modelEvRows — the counts the percentage cannot carry", () => {
  it("splits 'awaiting inspection' from 'never looked at'", () => {
    const rows = modelEvRows(mk({ total_elements: 100, tracked_elements: 30,
                                  installed_elements: 10, deviated_elements: 2 }));
    const get = (k: string) => rows.find((r) => r.k === k)?.v;
    expect(get("Awaiting inspection")).toBe("18");       // 30 tracked − 12 determined
    expect(get("Never looked at")).toBe("70");           // 100 − 30 tracked
    expect(get("Denominator (model elements)")).toBe("100");
  });

  it("offers the EV band only while the survey is incomplete", () => {
    expect(modelEvRows(THIN).some((r) => r.k === "EV(model) range")).toBe(true);
    expect(modelEvRows(BEHIND).some((r) => r.k === "EV(model) range")).toBe(false);
  });

  it("never reports a negative count on an inconsistent response", () => {
    const weird = mk({ total_elements: 5, tracked_elements: 9, determined_elements: 12 });
    for (const r of modelEvRows(weird)) expect(Number(r.v)).not.toBeLessThan(0);
  });
});

/** ---- the card, through the real panel ---------------------------------------------------------- */

function ctxFor(mev: ModelEv | null) {
  const root = document.createElement("div");
  document.body.replaceChildren(root);
  const api = {
    evm: async () => ({
      totals: {
        bac: 1_000_000, ev: 600_000, ac: 600_000, cv: 0, sv: 0, cpi: 1, spi: 1,
        cpi_band: "good", spi_band: "good", percent_complete: 60, percent_spent: 60,
        forecast: {
          eac: { cpi: 1_000_000, at_plan: 1_000_000, cpi_spi: 1_000_000 },
          eac_working: 1_000_000, etc: 400_000, vac: 0,
          tcpi_bac: 1, tcpi_eac: 1, tcpi_warning: false,
          recommended: { stage: "mid", recommended_eac: "cpi", guidance: "—" },
        },
      },
      control_accounts: [], earned_schedule: null,
    }),
    evmScurve: async () => null,
    evmModelEv: async () => { if (!mev) throw new Error("no model ev"); return mev; },
    evmTrend: async () => null,
    reportUrl: () => "#",
  };
  return {
    root,
    bar: (t: string) => { const d = document.createElement("div"); d.textContent = t; return d; },
    activeKey: null as string | null,
    renderHome: () => undefined,
    buildNav: () => undefined,
    host: { projectId: () => "p1", api: api as never },
  } as unknown as Parameters<typeof renderEvm>[0];
}

const text = () => document.body.textContent ?? "";

describe("the EVM panel's model-EV card", () => {
  it("prints the coverage band rather than a bare percentage", async () => {
    await renderEvm(ctxFor(THIN));
    expect(text()).toContain("1 of 4000 model elements");
    expect(text()).toContain("Awaiting inspection");
    expect(text()).not.toContain("front-loaded SOV");
  });

  // THE REASON HAS TO REACH THE SCREEN, not merely the reading. Found by mutation: deleting the
  // `detail` line from the card left every assertion above green, because they all read the
  // headline. `roomTabs.renderLiveRefusal` paid for this exact thing — a reason carried in the data
  // and not rendered is the defect this branch is about, committed in the fix for it.
  it("renders the DETAIL line, which is where the band's reason lives", async () => {
    await renderEvm(ctxFor(THIN));
    expect(text()).toContain("survey coverage, not disagreement");
    expect(text()).toContain("no front-loading finding can be made");
  });

  it("still shows the front-loading finding, with the crit edge", async () => {
    await renderEvm(ctxFor(BEHIND));
    expect(text()).toContain("ahead of the building");
    // ...and the basis for it, not just the claim
    expect(text()).toContain("survives the most favourable reading");
    const card = [...document.querySelectorAll(".dash-card")]
      .find((c) => c.textContent?.includes("Model-based EV"))!;
    expect((card as HTMLElement).style.cssText).toContain("--status-crit");
  });

  it("renders the card with NO model index, where it used to render nothing", async () => {
    // The old gate was `mev.total_elements > 0`, so the one state in which the percentage means
    // something else produced no card and no explanation.
    await renderEvm(ctxFor(mk({ total_elements: 0, tracked_elements: 10, installed_elements: 8,
                                deviated_elements: 2 })));
    expect(text()).toContain("10 surveyed elements");
  });

  it("drops the card entirely when the request fails, without failing the panel", async () => {
    await renderEvm(ctxFor(null));
    expect(text()).not.toContain("Model-based EV");
    expect(text()).toContain("CPI");                      // the rest of the panel still rendered
  });
});

/** ---- the SECOND site: `wipModelProgress`, which drives earned revenue ------------------------- */

const mp = (o: Partial<ModelProgress> = {}): ModelProgress => ({
  available: o.available ?? true, method: o.method ?? "units-installed",
  total_elements: o.total_elements ?? 4000,
  installed_elements: o.installed_elements ?? 1,
  determined_elements: o.determined_elements,
  deviated_elements: o.deviated_elements ?? 0,
  coverage_pct: o.coverage_pct,
  percent_complete: o.percent_complete ?? 0,
  percent_complete_count: o.percent_complete_count ?? 0,
  percent_complete_max: o.percent_complete_max ?? 100,
  percent_complete_count_max: o.percent_complete_count_max ?? 100,
  fully_determined: o.fully_determined,
  note: o.note ?? "",
  ...o,
});

describe("modelProgressReading — the WIP percentage is a FLOOR while anything is unsurveyed", () => {
  it("is the shipped shape: 1 of 4000 walked, and it refuses to call that a measurement", () => {
    const r = modelProgressReading(mp({ determined_elements: 1, fully_determined: false }));
    expect(r.kind).toBe("floor");
    expect(r.tone).toBe("warn");
    expect(r.headline).toContain("at least 0%");
    expect(r.headline).toContain("at most 100%");
    expect(r.detail).toContain("1 of 4000");
    expect(r.detail).toContain("is a FLOOR");
  });

  it("names WHY an unwalked element is not a missing one", () => {
    const r = modelProgressReading(mp({ determined_elements: 1, fully_determined: false }));
    expect(r.detail).toContain("counts here exactly like one inspected and found absent");
  });

  it("calls it a measurement only when every status is determined", () => {
    const r = modelProgressReading(mp({
      total_elements: 10, installed_elements: 6, deviated_elements: 4,
      determined_elements: 10, fully_determined: true, percent_complete: 60,
      percent_complete_max: 60,
    }));
    expect(r.kind).toBe("measured");
    expect(r.tone).toBe("ok");
    expect(r.headline).toContain("60% complete");
    expect(r.detail).toContain("every one of them inspected");
  });

  it("takes the ceiling from the RESPONSE, never from the element counts", () => {
    // Quantity-weighted: one unsurveyed 400 m³ pour is a single element and most of the concrete,
    // so a ceiling recomputed from counts would print a bound that is not one.
    const r = modelProgressReading(mp({
      total_elements: 3, installed_elements: 1, determined_elements: 2, fully_determined: false,
      quantity: "NetVolume", percent_complete: 2, percent_complete_max: 20,
      percent_complete_count: 33.3, percent_complete_count_max: 66.7,
    }));
    expect(r.headline).toContain("at most 20%");
    expect(r.headline).not.toContain("66.7");
  });

  it("prefers the engine's `fully_determined` over re-deriving it", () => {
    // Counts say complete; the engine says otherwise. The engine wins — it knows about `pending`.
    const r = modelProgressReading(mp({ total_elements: 10, determined_elements: 10,
                                        fully_determined: false, percent_complete: 30 }));
    expect(r.kind).toBe("floor");
  });

  it("keeps 'unavailable is not 0%' and owns that branch now", () => {
    const r = modelProgressReading(mp({ available: false, note: "No model loaded." }));
    expect(r.kind).toBe("absent");
    expect(r.tone).toBe("");
    expect(r.detail).toContain("No model loaded.");
    expect(r.detail).toContain("not 0% complete");
  });

  it("degrades to 'measured' on a response predating the coverage fields", () => {
    // A cached or older response carries no `fully_determined` and no `determined_elements`; the
    // fallback must not paint every historical response as a floor with a 100% ceiling.
    const r = modelProgressReading({ available: true, method: "units-installed",
                                     total_elements: 10, installed_elements: 4,
                                     percent_complete: 40, note: "" } as ModelProgress);
    expect(r.kind).toBe("measured");
    expect(r.headline).toContain("40% complete");
  });
});

describe("the budget panel is WIRED to the reading — the pure tests above cannot see this", () => {
  // Source-level, and the limit is stated rather than discovered later: a render wrapped in
  // `if (false)` would pass these. Added because two mutations survived — dropping the warn tone
  // and dropping the `detail` line both left all 41 tests green, which is the same hole the EVM
  // card's own `detail` mutation opened one file over. *The second consumer needed its own pin;
  // the first one's tests could not see it.* Anchored on `__file__`, because `vitest` and
  // `run_tests.py` start from different directories.
  const SRC = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "budget.ts"), "utf-8");

  it("builds the card from `modelProgressReading`, not from the raw percentage", () => {
    expect(SRC).toContain("const r = modelProgressReading(w);");
    expect(SRC).toContain("esc(r.headline)");
  });

  it("renders the DETAIL line, which is where 'this is a FLOOR' lives", () => {
    expect(SRC).toContain("${esc(r.detail)}</div>");
  });

  it("colours the floor case, so a bound does not read as a measurement", () => {
    expect(SRC).toContain('r.tone === "warn" ? ";color:var(--status-warn)" : ""');
  });

  it("no longer keeps its own copy of the unavailable branch", () => {
    // That string moved into `modelProgressReading`. Two statements of what an unavailable model
    // means is how two screens come to disagree, and this one had already been corrected once.
    expect(SRC).not.toContain("It needs a model with installed quantities to measure against.");
  });

  it("and the client DECLARES the coverage fields, or no derivation over declarations sees them", () => {
    const api = readFileSync(
      resolve(dirname(fileURLToPath(import.meta.url)), "../../api/accounting.ts"), "utf-8");
    expect(api).toContain("determined_elements?: number");
    expect(api).toContain("percent_complete_max?: number");
    expect(api).toContain("model_percent_complete_max: number");
  });
});
