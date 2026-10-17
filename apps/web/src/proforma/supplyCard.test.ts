import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { SupplyAssessment, SupplyIndexResult } from "../api/creDeal";
import { EVIDENCE, bodyFor, excludedCount, isIndexResult, isVacuous,
         renderSupply } from "./supplyCard";

/**
 * CRE-SUPPLY, and the one thing this card exists to refuse.
 *
 * Measured through the real engine: a pipeline of four projects, none matching the subject's
 * product type, returns `counts.competing: 0`, `excluded.counts.wrong_product: 4`, and an index
 * whose band is **`"undersupplied"`** — the most favourable verdict it can produce, on no evidence,
 * and byte-identical to a market with genuinely no competition.
 *
 * So the load-bearing assertions here are the WITHHOLDINGS, and each is mutation-checked: printing
 * the band on a vacuous set, summing certain with rumored, or showing a 0.0% discount over a zero
 * raw are each a sentence the engine did not say.
 */

const P = (over: Partial<SupplyAssessment["competing"][number]> = {}) => ({
  name: "Alder Flats", units: 300, delivery_date: "2027-03-01", product_type: "multifamily",
  distance_mi: 1.2, evidence: "loan_recorded", evidence_label: "Construction loan recorded",
  weight: 1.0, from_status_label: false, weighted_units: 300, rumored: false, ...over,
});

const ASSESS = (over: Partial<SupplyAssessment> = {}): SupplyAssessment => ({
  window: { start: "2026-01-01", end: "2028-12-31" }, product_type: "multifamily",
  competing: [P(), P({ name: "Rumor Tower", units: 450, evidence: "announced",
                       evidence_label: "Announced / rendering only", weight: 0.05,
                       weighted_units: 22.5, rumored: true })],
  certain_supply_units: 300, rumored_supply_units: 450,
  raw_units: 750, weighted_units: 322.5, discount_pct: 57.0,
  by_evidence: [{ evidence: "loan_recorded", label: "Construction loan recorded", projects: 1,
                  units: 300, weighted: 300 }],
  excluded: { out_of_window: [], wrong_product: [], counts: { out_of_window: 0, wrong_product: 0 } },
  counts: { competing: 2, certain: 1, rumored: 1 },
  note: "Units are discounted by RECORDED evidence, not by status label.",
  ...over,
} as SupplyAssessment);

/** The measured case: everything supplied was filtered out. */
const VACUOUS = (): SupplyAssessment => ASSESS({
  competing: [], certain_supply_units: 0, rumored_supply_units: 0,
  raw_units: 0, weighted_units: 0, discount_pct: 0.0, by_evidence: [],
  counts: { competing: 0, certain: 0, rumored: 0 },
  excluded: {
    out_of_window: [], counts: { out_of_window: 0, wrong_product: 4 },
    wrong_product: [P({ name: "Retail Row", product_type: "retail",
                        excluded: "different product type" })],
  },
});

const INDEX = (s: SupplyAssessment, over: Partial<SupplyIndexResult> = {}): SupplyIndexResult => ({
  supply: s,
  weighted_index: { vdl: s.weighted_units, monthly_absorption: 25, equilibrium_months: 6,
                    months_of_supply: 12.9, lsi: 215, band: "oversupplied", note: "LSI note." },
  raw_index: { vdl: s.raw_units, monthly_absorption: 25, equilibrium_months: 6,
               months_of_supply: 30, lsi: 500, band: "oversupplied", note: "LSI note." },
  delta_months: 17.1, note: "The weighted index is the one to underwrite.",
  ...over,
} as SupplyIndexResult);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

const text = (s: SupplyAssessment, i?: SupplyIndexResult) =>
  renderSupply(mount(), s, i).textContent ?? "";

describe("the mirrored evidence table", () => {
  const PY = resolve(__dirname, "../../../../services/api/src/aec_api/supply_pipeline.py");

  /** `EVIDENCE` as the Python declares it, in rank order. */
  function pythonEvidence(): [string, string, number][] {
    const src = readFileSync(PY, "utf-8");
    const block = /^EVIDENCE: dict\[str, dict\[str, Any\]\] = \{([\s\S]*?)^\}/m.exec(src);
    expect(block, "EVIDENCE not found in supply_pipeline.py — the mirror below cannot be checked, "
      + "which is the state this test exists to prevent").toBeTruthy();
    const out: [string, string, number][] = [];
    for (const m of block![1]!.matchAll(
      /"(\w+)":\s*\{"label":\s*"([^"]+)",\s*"weight":\s*([\d.]+),\s*"rank":\s*(\d+)\}/g)) {
      out.push([m[1]!, m[2]!, Number(m[3])]);
    }
    return out;
  }

  it("parsed the Python at all — a short list makes every assertion below vacuous", () => {
    expect(pythonEvidence().length).toBeGreaterThanOrEqual(8);
  });

  it("matches key, label and WEIGHT, in rank order", () => {
    // The weight is load-bearing: a drift makes this card offer a discount the engine will not
    // apply, so the select would promise 85% and the total would come back at 50%.
    expect(EVIDENCE.map((e) => [...e])).toEqual(pythonEvidence().map((e) => [...e]));
  });

  it("agrees with the engine about which tiers are rumored", () => {
    const src = readFileSync(PY, "utf-8");
    const m = /^RUMORED = \(([^)]*)\)/m.exec(src);
    expect(m, "RUMORED not found").toBeTruthy();
    const rumored = [...m![1]!.matchAll(/"(\w+)"/g)].map((x) => x[1]);
    // Every rumored tier must be one this card can offer, or a user cannot express it.
    for (const r of rumored) expect(EVIDENCE.map(([k]) => k)).toContain(r);
  });
});

describe("a vacuous set is not a favourable one", () => {
  it("withholds every supply total and says why", () => {
    const t = text(VACUOUS());
    expect(t).toContain("No competitive set");
    expect(t).toContain("This is not a finding of no competition.");
    // MUTATION: rendering the totals table anyway. Each of these would read as a measurement.
    expect(t).not.toContain("Certain");
    expect(t).not.toContain("Evidence-weighted");
  });

  it("withholds the BAND, which is the verdict that inverts", () => {
    const s = VACUOUS();
    const el = renderSupply(mount(), s, INDEX(s, {
      weighted_index: { vdl: 0, monthly_absorption: 25, equilibrium_months: 6,
                        months_of_supply: 0, lsi: 0, band: "undersupplied", note: "LSI note." },
      raw_index: { vdl: 0, monthly_absorption: 25, equilibrium_months: 6,
                   months_of_supply: 0, lsi: 0, band: "undersupplied", note: "LSI note." },
      delta_months: 0,
    }));
    // Scoped to the TABLES, not to the card's text. The explanation below names "undersupplied" as
    // the word it is refusing to print — asserting over the whole card would have been broken by
    // the very sentence that makes the withholding legible, which is the authority-card lesson
    // ("an assertion satisfied by a different code path") arriving from the other direction.
    const tables = [...el.querySelectorAll("table")].map((x) => x.textContent ?? "").join(" ");
    expect(tables).not.toContain("undersupplied");
    expect(tables).not.toContain("Months of supply");
    expect(el.textContent).toContain("the most favourable band it can return, on no evidence");
  });

  it("still lists what was excluded, with the reason", () => {
    const t = text(VACUOUS());
    expect(t).toContain("Retail Row");
    expect(t).toContain("different product type");
    expect(t).toContain("4 project(s) supplied were filtered out");
  });

  it("distinguishes 'nothing competed' from 'nothing was supplied'", () => {
    // Two different findings. The first says the filters ate the pipeline; the second says there
    // was no pipeline. Collapsing them sends somebody to widen a window that is already right.
    const empty = ASSESS({
      competing: [], certain_supply_units: 0, rumored_supply_units: 0, raw_units: 0,
      weighted_units: 0, by_evidence: [], counts: { competing: 0, certain: 0, rumored: 0 },
      excluded: { out_of_window: [], wrong_product: [],
                  counts: { out_of_window: 0, wrong_product: 0 } },
    });
    expect(text(empty)).toContain("No projects were supplied");
    expect(text(VACUOUS())).not.toContain("No projects were supplied");
  });
});

describe("coverage leads on a real set too", () => {
  it("says what the totals cover when anything was excluded", () => {
    const s = ASSESS({
      excluded: { out_of_window: [P({ name: "Old Mill", excluded: "delivers before the window" })],
                  wrong_product: [P({ name: "Retail Row", excluded: "different product type" })],
                  counts: { out_of_window: 1, wrong_product: 1 } },
    });
    const t = text(s);
    expect(t).toContain("2 competing project(s)");
    expect(t).toContain("2 excluded");
    expect(t).toContain("1 outside the delivery window");
    expect(t).toContain("1 a different product type");
    expect(t).toContain("not the 4 supplied");
  });

  it("says so plainly when nothing was excluded", () => {
    expect(text(ASSESS())).toContain("Nothing was excluded");
  });
});

describe("certain and rumored are never added", () => {
  it("reports two totals and labels the rumored one as excluded from the other", () => {
    // ASSERTED ON THE CELL, not on the card. The first draft of this test checked the engine's
    // WORDING, on the stated grounds that "300 + 450 = 750 is the raw total and is legitimately
    // shown, so the number is not checkable". The mutation proved that reasoning wrong: adding the
    // rumored units into the certain row printed 750 where 300 belongs — blending the two counts
    // the engine keeps apart on purpose — and every assertion still passed. The number IS
    // checkable; it just has to be read out of the row it belongs to.
    const el = renderSupply(mount(), ASSESS());
    const cells = (want: string) => [...el.querySelectorAll("tr")]
      .filter((tr) => tr.querySelector("td")?.textContent === want)
      .map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent));
    expect(cells("Certain")[0]?.[1]).toBe("300");
    expect(cells("Rumored")[0]?.[1]).toBe("450");
    expect(cells("Evidence-weighted")[0]?.[1]).toBe("323");
    expect(cells("Rumored")[0]?.[2]).toContain("added to certain");
  });

  it("names the rumored rows as rumored in the project table", () => {
    const el = renderSupply(mount(), ASSESS());
    const rows = [...el.querySelectorAll("tr")].map((tr) => tr.textContent ?? "");
    expect(rows.some((r) => r.includes("Rumor Tower") && r.includes("rumored"))).toBe(true);
    expect(rows.some((r) => r.includes("Alder Flats") && r.includes("rumored"))).toBe(false);
  });
});

describe("the discount", () => {
  it("is shown when there is something to discount", () => {
    expect(text(ASSESS())).toContain("57.0% discount");
  });

  it("is withheld when raw units are zero — 0.0% there means 'nothing weighed'", () => {
    // `discount_pct` is `round(...) if raw else 0.0`, so a zero raw yields the same 0.0 as a
    // pipeline that genuinely needed no discount.
    const s = ASSESS({ competing: [P({ units: 0, weighted_units: 0 })], raw_units: 0,
                       weighted_units: 0, discount_pct: 0.0, certain_supply_units: 0,
                       rumored_supply_units: 0, counts: { competing: 1, certain: 1, rumored: 0 } });
    // `% discount`, not `discount` — the engine's own note ends "...are discounted by RECORDED
    // evidence", so the bare word is in every response by construction.
    expect(text(s)).not.toContain("% discount");
    expect(text(ASSESS())).toContain("% discount");     // the check is not vacuous
  });
});

describe("evidence inferred from a label is marked", () => {
  it("names the projects whose tier came from a status string", () => {
    const t = text(ASSESS({
      competing: [P({ name: "Deck Tower", from_status_label: true })],
      counts: { competing: 1, certain: 1, rumored: 0 },
    }));
    expect(t).toContain("tiered from a STATUS LABEL");
    expect(t).toContain("Deck Tower");
  });

  it("says nothing when every tier came from a recorded flag", () => {
    expect(text(ASSESS())).not.toContain("STATUS LABEL");
  });
});

describe("the index", () => {
  it("shows weighted and raw side by side with the gap between them", () => {
    const s = ASSESS();
    const t = text(s, INDEX(s));
    expect(t).toContain("Evidence-weighted — underwrite this");
    expect(t).toContain("Raw, undiscounted");
    expect(t).toContain("12.9 mo · LSI 215");
    expect(t).toContain("30.0 mo · LSI 500");
    expect(t).toContain("17.1 month(s)");
  });

  it("renders the engine's reason instead of a band when absorption was not positive", () => {
    const s = ASSESS();
    const t = text(s, INDEX(s, {
      weighted_index: { vdl: 322.5, monthly_absorption: 0, months_of_supply: null, lsi: null,
                        band: "unknown", note: "Need a positive absorption rate." },
    }));
    expect(t).toContain("Need a positive absorption rate.");
    expect(t).not.toContain("unknown");
  });
});

describe("what the card sends", () => {
  it("expands the evidence tier into the boolean flag the engine prefers", () => {
    // `evidence_of` checks explicit flags BEFORE falling back to a status string, so sending the
    // flag is what makes `from_status_label` false.
    expect(bodyFor([{ name: "A", units: 10, delivery_date: "2027-01-01",
                      product_type: "multifamily", evidence: "permit_issued" }], {}))
      .toEqual({ projects: [{ name: "A", units: 10, delivery_date: "2027-01-01",
                              product_type: "multifamily", permit_issued: true }] });
  });

  it("sends no flag for the unknown tier, which has none", () => {
    const b = bodyFor([{ name: "A", units: 10, delivery_date: "", product_type: "",
                         evidence: "unknown" }], {});
    expect(Object.keys(b.projects[0] as object)).toEqual(
      ["name", "units", "delivery_date", "product_type"]);
  });

  it("omits an empty window, product type and a non-positive absorption", () => {
    const b = bodyFor([], { windowStart: "", productType: "  ".trim(), absorption: 0 });
    expect(b).toEqual({ projects: [] });
  });

  it("sends absorption only when it is positive, because that is what adds the index", () => {
    expect(bodyFor([], { absorption: 25 }).monthly_absorption).toBe(25);
  });
});

describe("telling the two response shapes apart", () => {
  it("recognises the index wrapper by the field only it carries", () => {
    expect(isIndexResult(INDEX(ASSESS()))).toBe(true);
    expect(isIndexResult(ASSESS())).toBe(false);
  });
});

describe("the two predicates the card withholds on", () => {
  it("isVacuous is about the COMPETING count, not about the totals", () => {
    // A pipeline of real projects that all have zero units has zero totals and is not vacuous —
    // it was measured and the answer was zero. Reading the totals would conflate the two.
    expect(isVacuous(VACUOUS())).toBe(true);
    expect(isVacuous(ASSESS({ raw_units: 0, weighted_units: 0 }))).toBe(false);
  });

  it("excludedCount adds both filters", () => {
    expect(excludedCount(ASSESS({
      excluded: { out_of_window: [], wrong_product: [],
                  counts: { out_of_window: 2, wrong_product: 3 } },
    }))).toBe(5);
  });
});
