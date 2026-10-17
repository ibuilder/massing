import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import {
  hasStatedTotals, incomeFromT12, parseAmount, parseT12, renderT12Card, renderT12Result,
} from "./t12Card";

/**
 * T12-SELFTIE — `t12.py` exists for one refusal and the refusal is unreachable without a caller that
 * hands it real evidence.
 *
 * `normalize()`'s docstring: *"When the caller supplies source totals they are the reference the
 * mapping must reproduce; **without them the sum of the source lines is**."* Both sides then come from
 * the same mapped rows, so the deltas are zero by construction. Measured through the real engine, on
 * one T-12 with a single unmapped $90,000 line:
 *
 *     no stated totals    reconciles: true    deltas all 0.0    adjusted_noi: 3,180,000
 *     with stated totals  reconciles: false   expense −90,000   stopped: true · adjusted_noi: null
 *
 * So the response for a vacuous tie-out is **indistinguishable from a real pass** on every field the
 * card could read — `reconciles` is true either way. Only the CALLER knows which it handed over, which
 * is why `stated` is a parameter here and not something derived from the response.
 */

type T12 = Awaited<ReturnType<ApiClient["normalizeT12"]>>;

/** The engine's shape for a tie-out that "passed" — identical whether or not totals were supplied. */
const PASSED = (over: Partial<T12> = {}): T12 => ({
  line_count: 24,
  source_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  mapped_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  tie_out: { reconciles: true, deltas: { income: 0, expense: 0, noi: 0 }, tolerance: 1 },
  adjusted_noi: 2_140_000, unmapped_count: 0, unmapped: [],
  one_time_items: [{ description: "Legal settlement", amount: 50_000, kind: "expense" }],
  capital_items: [{ description: "Roof replacement", amount: 180_000 }],
  by_category: [{ category: "gross_potential_rent", label: "Gross potential rent",
                  amount: 3_600_000, run_rate: 3_648_000 },
                { category: "bad_debt", label: "Bad debt", amount: 41_000, run_rate: 52_000 }],
  run_rate_vs_trailing: [{ category: "bad_debt", label: "Bad debt", trailing: 41_000,
                           run_rate: 52_000, delta: 11_000 }],
  add_back_questions: [{ check: "management_fee", severity: "high",
                         finding: "no management fee in the statement",
                         question: "Is this owner-managed? Add a market management fee before pricing.",
                         amount: 0, pct_of_income: 0 }],
  note: "Tie-out passed",
  ...over,
} as T12);

const STOPPED = (over: Partial<T12> = {}): T12 => ({
  line_count: 24,
  source_totals: { income: 3_420_000, expense: 1_330_000, noi: 2_090_000 },
  mapped_totals: { income: 3_420_000, expense: 1_240_000, noi: 2_180_000 },
  tie_out: { reconciles: false, deltas: { income: 0, expense: -90_000, noi: 90_000 }, tolerance: 1 },
  stopped: true, adjusted_noi: null, unmapped_count: 1,
  unmapped: [{ description: "Owner draw — misc", amount: 90_000 }],
  reconciling_items: [{ issue: "unmapped line", description: "Owner draw — misc", amount: 90_000 }],
  note: "STOPPED: source and mapped totals do not reconcile",
  ...over,
} as T12);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("the paste parser", () => {
  it("splits on the LAST comma, because account names contain commas and amounts do not", () => {
    // Splitting on the first comma truncates the description AND reads the remainder as the amount,
    // which parses — so the failure would be a wrong number rather than an error.
    const { lines } = parseT12("Repairs, maintenance & turnover, 240000");
    expect(lines).toEqual([{ description: "Repairs, maintenance & turnover", amount: 240_000 }]);
  });

  it("prefers a tab when there is one", () => {
    const { lines } = parseT12("Repairs, maintenance\t240000");
    expect(lines[0]!.description).toBe("Repairs, maintenance");
  });

  it("reads what a spreadsheet paste actually contains", () => {
    expect(parseAmount("$3,600,000.00")).toBe(3_600_000);
    expect(parseAmount("(180,000)")).toBe(-180_000);   // parenthesised negative
    expect(parseAmount(" -1234.5 ")).toBe(-1234.5);
  });

  it("returns null rather than 0 for something it cannot read", () => {
    // 0 would enter the mapping as a real line worth nothing and shift no total, so a misread row
    // would be invisible in both the tie-out and the unmapped list.
    expect(parseAmount("n/a")).toBeNull();
    expect(parseAmount("")).toBeNull();
    expect(parseAmount("12,34,x")).toBeNull();
  });

  it("collects unreadable rows instead of dropping them", () => {
    const { lines, skipped } = parseT12("Rent, 100\nsomething odd\nTaxes, n/a\n\nInsurance\t2000");
    expect(lines.map((l) => l.description)).toEqual(["Rent", "Insurance"]);
    expect(skipped).toEqual(["something odd", "Taxes, n/a"]);
  });
});

describe("whether the caller handed the engine a real reference", () => {
  it("needs BOTH totals — one alone leaves the other tied to itself", () => {
    expect(hasStatedTotals({ income: 3_420_000, expense: 1_330_000 })).toBe(true);
    expect(hasStatedTotals({ income: 3_420_000 })).toBe(false);
    expect(hasStatedTotals({ expense: 1_330_000 })).toBe(false);
    expect(hasStatedTotals({ income: NaN, expense: 1_330_000 })).toBe(false);
  });
});

describe("the tie-out verdict", () => {
  // THE ONE THIS CARD EXISTS FOR. Same response, same `reconciles: true`; only the caller knows.
  it("refuses to call a self-tie a pass", () => {
    const t = renderT12Result(mount(), PASSED({ unmapped_count: 1 }), false).textContent ?? "";
    expect(t).toContain("tied to itself");
    expect(t).not.toContain("Tie-out passed");
    expect(t).toContain("the same mapping");
    expect(t).toContain("1");                      // unmapped_count — the only signal left
    expect(t).toContain("Enter the statement's own totals");
  });

  it("…and DOES call it a pass on the identical response when totals were stated", () => {
    const t = renderT12Result(mount(), PASSED({ unmapped_count: 1 }), true).textContent ?? "";
    expect(t).toContain("Tie-out passed against the stated totals");
    expect(t).not.toContain("tied to itself");
  });

  it("renders a stopped tie-out with its deltas and reconciling items, and no adjusted NOI", () => {
    const t = renderT12Result(mount(), STOPPED(), true).textContent ?? "";
    expect(t).toContain("Tie-out STOPPED");
    expect(t).toContain("Owner draw");
    expect(t).toContain("$90,000");
    expect(t).not.toContain("Adjusted NOI");
  });

  it("says the derived views were never calculated, not merely hidden", () => {
    // `add_back_questions` and `run_rate_vs_trailing` are computed only past the gate, so "hidden"
    // would misdescribe what happened and invite someone to look for a toggle.
    expect(renderT12Result(mount(), STOPPED(), true).textContent).toContain("never calculated");
  });

  it("shows stated against mapped side by side, which is the whole comparison", () => {
    const t = renderT12Result(mount(), STOPPED(), true).textContent ?? "";
    expect(t).toContain("$1,330,000");   // stated expense
    expect(t).toContain("$1,240,000");   // mapped expense
  });
});

describe("past the gate", () => {
  it("renders the adjusted NOI, the treatments and the run-rate movers", () => {
    const t = renderT12Result(mount(), PASSED(), true).textContent ?? "";
    expect(t).toContain("$2,140,000");
    expect(t).toContain("Legal settlement");
    expect(t).toContain("Roof replacement");
    expect(t).toContain("Bad debt");
  });

  it("renders add-backs as QUESTIONS with the number behind each, never as applied", () => {
    const t = renderT12Result(mount(), PASSED(), true).textContent ?? "";
    expect(t).toContain("Questions to ask before you price it");
    expect(t).toContain("Is this owner-managed?");
    expect(t).toContain("never applied for you");
  });

  it("says when the unmapped list is a page of a larger set", () => {
    const t = renderT12Result(mount(), PASSED({
      unmapped_count: 120,
      unmapped: Array.from({ length: 50 }, (_, i) => ({ description: `L${i}`, amount: 10 })),
    }), true).textContent ?? "";
    expect(t).toContain("Showing 50 of 120 unmapped lines");
  });
});

describe("the handoff into the rent-roll scrub", () => {
  it("supplies only the two fields a trailing twelve can honestly supply", () => {
    // `prior_bad_debt`, `occupancy_pct` and `prior_occupancy_pct` describe a PRIOR period and a unit
    // inventory. Filling them from this period to make a check run would be the defect the scrub is
    // written to refuse, committed from the outside — so the check that needs them stays not-run.
    expect(incomeFromT12(PASSED())).toEqual({ gross_potential_rent: 3_600_000, bad_debt: 41_000 });
  });

  it("supplies nothing when the mapping produced no categories", () => {
    expect(incomeFromT12(PASSED({ by_category: undefined }))).toEqual({});
  });
});

describe("AUTHORITY-DOWNSTREAM — a blocked operating statement withholds the PASS only", () => {
  const BLOCKED = { kind: "blocked" as const, blocks: [
    { fact_type: "operating_statement",
      why: "authoritative document is 140 day(s) past its 60-day freshness limit" }] };

  it("THE POINT: a passing tie-out is not stated as a pass", () => {
    const t = renderT12Result(mount(), PASSED(), true, BLOCKED).textContent ?? "";
    expect(t).toContain("140 day(s)");
    expect(t).toContain("Tie-out result withheld");
    expect(t).not.toContain("Tie-out passed against the stated totals");
  });

  it("AND THE ADJUSTED NOI GOES WITH IT — the figure a reader takes away", () => {
    // The first draft withheld the verdict SENTENCE and left the adjusted NOI printing in 20px bold
    // directly beneath it. A gate that suppresses the words and keeps the number is decorative.
    const r = PASSED({ adjusted_noi: 2_140_000 });
    const held = renderT12Result(mount(), r, true, BLOCKED).textContent ?? "";
    expect(held).toContain("Adjusted NOI withheld");
    expect(held).not.toContain("2,140,000");
    const clear = renderT12Result(mount(), r, true, { kind: "clear" }).textContent ?? "";
    expect(clear).toContain("2,140,000");
  });

  it("...and says so with a clear gate instead", () => {
    const t = renderT12Result(mount(), PASSED(), true, { kind: "clear" }).textContent ?? "";
    expect(t).toContain("Tie-out passed against the stated totals");
    expect(t).not.toContain("withheld");
  });

  it("the note claims nothing about this card in a branch that withholds nothing", () => {
    // STOPPED withholds nothing — the engine already refused. The first wording of the shared note
    // asserted "the conclusion is not stated" in every branch, which is the exact failure this
    // item's own roadmap entry names: a note explaining a withholding that is not happening.
    const t = renderT12Result(mount(), STOPPED(), true, BLOCKED).textContent ?? "";
    expect(t).toContain("Deal-room authority blocks this fact");
    expect(t).not.toContain("the conclusion is not stated");
  });

  it("a STOPPED tie-out still renders in full — a refusal is not an opinion of value", () => {
    // The gate stops work being published off a stale document. Suppressing the engine's own
    // refusal because the document is stale would hide the finding and leave nothing in its place.
    const t = renderT12Result(mount(), STOPPED(), true, BLOCKED).textContent ?? "";
    expect(t).toContain("Tie-out STOPPED");
    expect(t).toContain("never calculated");
  });

  it("the tied-to-itself warning also survives the block", () => {
    const t = renderT12Result(mount(), PASSED(), false, BLOCKED).textContent ?? "";
    expect(t).toContain("Tie-out tied to itself");
  });

  it("an undeclared table prints the pass with a note that it is ungoverned", () => {
    const t = renderT12Result(mount(), PASSED(), true, { kind: "undeclared" }).textContent ?? "";
    expect(t).toContain("Tie-out passed against the stated totals");
    expect(t).toContain("not governed by a source of record");
  });
});

describe("the STATUS LINE withholds too", () => {
  // The card printed "Tie-out result withheld" and hid the adjusted NOI while the status bar said
  // "T-12 tie-out passed" — the withheld verdict reappearing two inches away, in the one place a
  // reader glances at. `covenantCard` already had the `withholds(gate)` branch; applying it to one
  // card and not its sibling is how a withholding becomes advisory.
  //
  // Found by review BECAUSE nothing here drove `renderT12Card` — every assertion above calls the
  // pure renderer, so the whole status-setting path had no test. *A defect in the caller is
  // invisible to a suite that only tests the callee.*
  const drive = async (authority: unknown) => {
    const status: string[] = [];
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const api = {
      normalizeT12: async () => PASSED(),
      dealAuthority: async () => authority,
    } as unknown as ApiClient;
    renderT12Card(root, { api, projectId: () => "p1", setStatus: (m) => status.push(m) });
    const ta = root.querySelector("textarea")!;
    ta.value = "Gross potential rent, 3600000\nRepairs, 240000";
    const nums = root.querySelectorAll<HTMLInputElement>('input[type="number"]');
    nums[0]!.value = "3600000";
    nums[1]!.value = "240000";
    root.querySelector<HTMLButtonElement>("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    return { status, text: root.textContent ?? "" };
  };

  const BLOCKED = {
    entries: [{ fact_type: "operating_statement", document: "T12.xlsx", as_of: "2026-01-01",
                authoritative: true, freshness_days: 60, supersedes: [] }],
    gate: { passes: false, blocking: [{ fact_type: "operating_statement", why: "140 day(s) stale" }],
            advisory: [] },
  };

  it("THE DEFECT: a blocked gate must not leave 'tie-out passed' in the status bar", async () => {
    const { status, text } = await drive(BLOCKED);
    expect(text).toContain("Tie-out result withheld");
    expect(status.at(-1)).toContain("withheld");
    expect(status).not.toContain("T-12 tie-out passed");
  });

  it("...and still says passed when the gate is clear", async () => {
    const { status, text } = await drive({ entries: BLOCKED.entries,
                                           gate: { passes: true, blocking: [], advisory: [] } });
    expect(text).toContain("Tie-out passed against the stated totals");
    expect(status.at(-1)).toBe("T-12 tie-out passed");
  });

  it("an unreadable authority table does not withhold — it is ungoverned, not blocked", async () => {
    const { status } = await drive(Promise.reject(new Error("boom")) as unknown);
    expect(status.at(-1)).toBe("T-12 tie-out passed");
  });
});

describe("a new normalisation invalidates whatever the previous one produced", () => {
  // The caller's generation token advanced only when a new SCRUB started, so a scrub still in
  // flight from one T-12 landed under a NEWLY normalised one, captioned "run against the normalised
  // T-12 above" — a figure attributed to a statement it was never computed from, which is the one
  // thing this pair of cards exists to prevent. The card has to say when it starts, because the
  // caller cannot otherwise know. Found by review.
  it("THE HOOK: onNormaliseStart fires before the request, not after it resolves", async () => {
    const order: string[] = [];
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const api = {
      normalizeT12: async () => { order.push("request"); return PASSED(); },
      dealAuthority: async () => ({ entries: [], gate: { blocking: [] } }),
    } as unknown as ApiClient;
    renderT12Card(root, {
      api, projectId: () => "p1", setStatus: () => {},
      onNormaliseStart: () => order.push("invalidate"),
    });
    root.querySelector("textarea")!.value = "Gross potential rent, 3600000";
    root.querySelector<HTMLButtonElement>("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    // Before, not after: an in-flight scrub has to be discarded while it is still in flight.
    expect(order).toEqual(["invalidate", "request"]);
  });

  it("is optional — a caller that does not pass it still normalises", async () => {
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const api = {
      normalizeT12: async () => PASSED(),
      dealAuthority: async () => ({ entries: [], gate: { blocking: [] } }),
    } as unknown as ApiClient;
    renderT12Card(root, { api, projectId: () => "p1", setStatus: () => {} });
    root.querySelector("textarea")!.value = "Gross potential rent, 3600000";
    root.querySelector<HTMLButtonElement>("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(root.textContent).toContain("Tie-out");
  });

  it("does NOT fire when the paste cannot be parsed — nothing was normalised", async () => {
    // Invalidating here would clear a scrub that is still correctly attributed to the statement on
    // screen, because that statement has not changed.
    let fired = 0;
    const root = document.createElement("div");
    document.body.replaceChildren(root);
    const api = {
      normalizeT12: async () => PASSED(),
      dealAuthority: async () => ({ entries: [], gate: { blocking: [] } }),
    } as unknown as ApiClient;
    renderT12Card(root, {
      api, projectId: () => "p1", setStatus: () => {},
      onNormaliseStart: () => { fired++; },
    });
    root.querySelector("textarea")!.value = "nothing parsable here";
    root.querySelector<HTMLButtonElement>("button")!.click();
    await new Promise((r) => setTimeout(r, 0));
    expect(fired).toBe(0);
    expect(root.textContent).toContain("No parsable lines");
  });
});
