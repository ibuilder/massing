/** PREFIX-RANKED — the scope of a portfolio sweep, and what a prefix does to a ranking.
 *
 *  `PREFIX` is the measured response: three projects, the risk on the last one by name, swept at
 *  `?limit=2`. The full sweep put ZZZ Dangerous first at score 3 with one high-severity
 *  coordination item and a hotspot; the prefix sweep returned the two quiet ones, an empty
 *  hotspots list and zero across every total.
 */
import { describe, expect, it } from "vitest";

import {
  TONE_CSS, aggregatePrefixCaveat, coversPortfolio, rankedPrefixCaveat, scopeLine,
  type SweptScope,
} from "./portfolioScope";

/** Measured at `?limit=2` over three projects. */
const PREFIX: SweptScope = { project_count: 2, projects_available: 3, truncated: true };
/** Measured at `?limit=25` over the same three. */
const WHOLE: SweptScope = { project_count: 3, projects_available: 3, truncated: false };

const RISK_NOTE = "Projects × risk source, intensity = 3·high + 2·medium + 1·low, every cell from "
  + "the same board the project's own risk panel shows. When `truncated`, the scanned set is a "
  + "deterministic prefix of the caller's projects, not the riskiest ones — ranking is what the "
  + "sweep produces, so it cannot select what to sweep.";

describe("PREFIX-RANKED · the caption as it shipped", () => {
  it("was accurate about counts and silent about selection", () => {
    const shipped = ` · showing ${PREFIX.project_count} of ${PREFIX.projects_available}`;
    expect(shipped).toBe(" · showing 2 of 3");
    // Measured: the omitted project was the portfolio's ONLY risky one, and the heading beside this
    // caption read `0 high / 0 medium / 0 low`.
    expect(shipped).not.toContain("prefix");
    expect(shipped).not.toContain("riskiest");
  });
});

describe("PREFIX-RANKED · scopeLine", () => {
  it("states coverage rather than a count", () => {
    expect(scopeLine(PREFIX)).toBe("2 of 3 project(s) swept — 1 not examined.");
  });

  it("is silent when the sweep covered the portfolio", () => {
    expect(scopeLine(WHOLE)).toBeNull();
  });

  it("never reports a negative skip when the counts disagree", () => {
    expect(scopeLine({ project_count: 5, projects_available: 3, truncated: true }))
      .toBe("5 of 3 project(s) swept — 0 not examined.");
  });
});

describe("PREFIX-RANKED · rankedPrefixCaveat", () => {
  it("says plainly that these are NOT the riskiest, and why raising the limit is the fix", () => {
    const c = rankedPrefixCaveat(PREFIX, RISK_NOTE)!;
    expect(c.tone).toBe("crit");
    expect(c.text).toContain("These are NOT the 2 riskiest projects");
    expect(c.text).toContain("bounded before any scoring");
    expect(c.text).toContain("could each outrank every row below");
    expect(c.text).toContain("over the prefix, not the book");
    expect(c.text).toContain("Raise the limit");
  });

  it("renders the ENGINE's own sentence when it has one, rather than paraphrasing it", () => {
    // The engine owns the statement of its own basis — the same decision BASIS-UNREAD made.
    const c = rankedPrefixCaveat(PREFIX, RISK_NOTE)!;
    expect(c.text).toContain("When `truncated`, the scanned set is a deterministic prefix");
    expect(c.text).toContain("ranking is what the sweep produces, so it cannot select what to sweep");
    // ...and it does NOT drag in the unrelated first half of the note.
    expect(c.text).not.toContain("intensity = 3·high");
  });

  it("still carries the derivable half when the server sends no such note", () => {
    const c = rankedPrefixCaveat(PREFIX)!;
    expect(c.text).toContain("These are NOT the 2 riskiest projects");
    expect(c.text).not.toContain("When `truncated`");
    const other = rankedPrefixCaveat(PREFIX, "A note about something else entirely.")!;
    expect(other.text).not.toContain("something else entirely");
  });

  it("is silent when nothing was truncated", () => {
    expect(rankedPrefixCaveat(WHOLE, RISK_NOTE)).toBeNull();
  });

  it("is CRIT rather than warn, because a ranking that omits the worst row is simply wrong", () => {
    expect(rankedPrefixCaveat(PREFIX, RISK_NOTE)!.tone)
      .not.toBe(aggregatePrefixCaveat(PREFIX, "Peak")!.tone);
  });
});

describe("PREFIX-RANKED · aggregatePrefixCaveat", () => {
  it("names the figure as a lower bound and says which direction it can only move", () => {
    const c = aggregatePrefixCaveat(PREFIX, "Peak concurrent demand")!;
    expect(c.tone).toBe("warn");
    expect(c.text).toContain("Peak concurrent demand is a LOWER BOUND");
    expect(c.text).toContain("summed over 2 of 3 project(s)");
    expect(c.text).toContain("can only add to it");
    // The cross-project case the resourcing view exists for, which a prefix hides.
    expect(c.text).toContain("over-committed across an examined job and an unexamined one");
  });

  it("is authored here because that engine's note never mentions the prefix", () => {
    // `resource_portfolio`'s note explains the cross-project arithmetic and stops there, so unlike
    // the risk route there is no sentence to pass through. This takes no note argument at all.
    expect(aggregatePrefixCaveat(PREFIX, "Peak")!.text).toContain("LOWER BOUND");
  });

  it("is silent when nothing was truncated", () => {
    expect(aggregatePrefixCaveat(WHOLE, "Peak")).toBeNull();
  });
});

describe("PREFIX-RANKED · coversPortfolio", () => {
  it("is true only when the sweep reached every project", () => {
    expect(coversPortfolio(WHOLE)).toBe(true);
    expect(coversPortfolio(PREFIX)).toBe(false);
  });

  it("does not trust `truncated` alone", () => {
    // Both halves must agree: a response claiming untruncated while covering fewer projects than
    // are available is not a portfolio figure, whatever the flag says.
    expect(coversPortfolio({ project_count: 2, projects_available: 3, truncated: false }))
      .toBe(false);
  });
});

describe("PREFIX-RANKED · TONE_CSS", () => {
  it("is a literal tone map", () => {
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS[""]).toBe("");
  });
});
