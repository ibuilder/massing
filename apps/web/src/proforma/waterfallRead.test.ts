/** WF-BASIS — the capital base, and the four cases the card could not tell apart.
 *
 *  Every fixture below is a measured response from the same $8m LP / $2m GP cap table at a $20m
 *  exit, except the uneven one, which is the measured LP Big / LP Small case.
 */
import { describe, expect, it } from "vitest";
import type { WaterfallScenario } from "../api/finance";
import {
  TONE_CSS, basisLine, investorRows, returnsLine, splitNote, uncalledNote,
} from "./waterfallRead";

const wf = (over: Partial<WaterfallScenario> = {}): WaterfallScenario => ({
  total_distributable: 20_000_000,
  lp_distributions: 18_302_056, gp_distributions: 1_697_944,
  lp_irr: 0.1799, gp_irr: null, lp_equity_multiple: 2.29, gp_equity_multiple: 0.85,
  lp_unreturned: 0, pref_rate: 0.08, style: "american",
  periods: [],
  per_investor: [
    { id: "a", investor: "LP One", investor_class: "LP", commitment: 8_000_000,
      contributed: 8_000_000, distribution: 18_302_056,
      commitment_share: 1, contributed_share: 1 },
    { id: "b", investor: "GP", investor_class: "GP", commitment: 2_000_000,
      contributed: 2_000_000, distribution: 1_697_944,
      commitment_share: 1, contributed_share: 1 },
  ],
  lp_basis: "contributed", gp_basis: "contributed",
  lp_contrib: 8_000_000, gp_contrib: 2_000_000,
  lp_commitment: 8_000_000, gp_commitment: 2_000_000,
  split_basis: "commitment", split_mismatch: [],
  ...over,
});

/** Nothing called. Byte-identical returns to the fully funded case — the whole finding. */
const UNCALLED = wf({
  lp_basis: "committed", gp_basis: "committed",
  per_investor: wf().per_investor.map((p) => ({ ...p, contributed: 0, contributed_share: null })),
});

/** LPs funded, GP not. One waterfall on two bases. */
const MIXED = wf({ gp_basis: "committed" });

/** LP Big $8m committed / $1m funded; LP Small $2m / $2m. The measured allocation. */
const UNEVEN = wf({
  lp_contrib: 3_000_000, lp_commitment: 10_000_000,
  per_investor: [
    { id: "a", investor: "LP Big", investor_class: "LP", commitment: 8_000_000,
      contributed: 1_000_000, distribution: 13_490_617,
      commitment_share: 0.8, contributed_share: 0.333333 },
    { id: "b", investor: "LP Small", investor_class: "LP", commitment: 2_000_000,
      contributed: 2_000_000, distribution: 3_372_654,
      commitment_share: 0.2, contributed_share: 0.666667 },
  ],
  split_mismatch: [
    { investor: "LP Big", commitment_share: 0.8, contributed_share: 0.333333 },
    { investor: "LP Small", commitment_share: 0.2, contributed_share: 0.666667 },
  ],
});

describe("the capital base is on the card, because every figure rests on it", () => {
  it("names the contributed base and the commitment behind it", () => {
    const b = basisLine(wf({ lp_contrib: 4_000_000, lp_commitment: 8_000_000 }));
    expect(b?.text).toContain("LP $4,000,000 contributed of $8,000,000 committed");
    expect(b?.tone).toBe("");
  });

  it("says COMMITTED, loudly, when nothing has been called", () => {
    // THE DEFECT: this case and the fully funded one produced identical distributions, IRRs and
    // multiples, so the old card showed the same screen for both.
    const b = basisLine(UNCALLED);
    expect(b?.text).toContain("COMMITTED (not yet called)");
    expect(b?.tone).toBe("crit");
  });

  it("names a MIXED basis, because the two sides fall back independently", () => {
    const b = basisLine(MIXED);
    expect(b?.text).toContain("DIFFERENT bases");
    expect(b?.text).toContain("LP $8,000,000 contributed");
    expect(b?.text).toContain("GP $2,000,000 COMMITTED");
    expect(b?.tone).toBe("crit");
  });

  it("omits the 'of X committed' clause when the capital is fully in", () => {
    expect(basisLine(wf())?.text).not.toContain("committed");
  });

  it("is null when the server sends no basis — an older one, or no cap table at all", () => {
    // `distwaterfall` returns `lp_basis: null` on the no-cap-table branch, where no waterfall ran:
    // naming a basis there would describe a calculation that did not happen.
    expect(basisLine(wf({ lp_basis: null, gp_basis: null }))).toBeNull();
    expect(basisLine(wf({ lp_basis: undefined, gp_basis: undefined }))).toBeNull();
  });
});

describe("a committed basis says what it means for the figures above", () => {
  it("names both sides and every figure it affects", () => {
    const n = uncalledNote(UNCALLED);
    expect(n).toContain("LP and GP capital has not been called");
    expect(n).toContain("both sides");
    expect(n).toContain("preferred return");
    expect(n).toContain("money nobody has contributed yet");
    // The comparison that makes it concrete.
    expect(n).toContain("the same figures as one fully funded");
  });

  it("names one side when only one fell back", () => {
    const n = uncalledNote(MIXED);
    expect(n).toContain("GP capital has not been called");
    expect(n).toContain("the GP");
    expect(n).not.toContain("both sides");
  });

  it("is silent when both sides are on contributed capital", () => {
    expect(uncalledNote(wf())).toBeNull();
    expect(uncalledNote(wf({ lp_basis: undefined, gp_basis: undefined }))).toBeNull();
  });
});

describe("the split-basis disagreement is reported, not silently repaired", () => {
  it("names each investor with BOTH shares", () => {
    const n = splitNote(UNEVEN);
    expect(n).toContain("pro-rata to commitment");
    expect(n).toContain("ran on contributed capital");
    expect(n).toContain("LP Big (80.0% of commitments vs 33.3% of capital in)");
    expect(n).toContain("LP Small (20.0% of commitments vs 66.7% of capital in)");
    // The action, which is not "trust this number".
    expect(n).toContain("confirm against the operating agreement");
  });

  it("is silent when the two shares agree, which is the ordinary case", () => {
    expect(splitNote(wf())).toBeNull();
    expect(splitNote(wf({ split_mismatch: undefined }))).toBeNull();
  });
});

describe("each investor row carries both shares, so the figure can be checked", () => {
  it("renders the distribution with the commitment, the capital in, and both shares", () => {
    const rows = investorRows(UNEVEN);
    expect(rows[0]).toEqual({
      investor: "LP Big", distribution: "$13,490,617", commitment: "$8,000,000",
      contributed: "$1,000,000", shares: "80.0% committed / 33.3% funded", tone: "warn",
    });
    // The measured injustice, in two adjacent rows: more funded, less distributed.
    expect(rows[1]!.contributed).toBe("$2,000,000");
    expect(rows[1]!.distribution).toBe("$3,372,654");
  });

  it("marks only the mismatched investors", () => {
    expect(investorRows(wf()).map((r) => r.tone)).toEqual(["", ""]);
  });

  it("renders an em-dash for a funded share that does not exist yet", () => {
    // `contributed_share` is null when nothing has been called on that side; `usd`/`pct` must not
    // turn that into a confident 0%.
    expect(investorRows(UNCALLED)[0]!.shares).toBe("100.0% committed / — funded");
  });
});

describe("the returns line keeps its substance", () => {
  it("renders distributions, IRRs, multiples, pref and style", () => {
    expect(returnsLine(wf())).toBe(
      "LP $18,302,056 (IRR 18.0%, 2.29x) · GP $1,697,944 (0.85x) · pref 8.0% american");
  });

  it("renders an em-dash for a null IRR rather than 0%", () => {
    expect(returnsLine(wf({ lp_irr: null }))).toContain("IRR —");
  });
});

describe("the tone tokens are literal", () => {
  it("names properties the stylesheets define", () => {
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS[""]).toBe("");
  });
});
