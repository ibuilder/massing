import { describe, expect, it } from "vitest";

import { resourcingCard } from "./portfolio";

/** A resourcing response, defaulting to the healthy case so each test names only what it varies. */
const R = (o: Partial<Parameters<typeof resourcingCard>[0]> = {}) =>
  ({ available: true, trades: ["Ironworkers"], ...o });

/** The "Resourcing across the book" card's draw decision.
 *
 *  This exists because the guard was wrong, and wrong in the way a guard usually is: it decided
 *  what to LOOK at rather than what to report, so everything it excluded was invisible to its own
 *  output. `!available || !trades.length` returned early on a book with no resource demand — which
 *  is exactly the response that still carries `groups_error` when the install's configured grouping
 *  is malformed, and exactly the install most likely to have the typo, because it is the one being
 *  set up before any resourcing exists. The one screen that would ever report it stayed silent.
 *
 *  A review bot found it. What makes it not recur is that the decision is now named and asserted
 *  rather than being a boolean inside a `.then()`. */
describe("resourcingCard", () => {
  it("draws the full roll-up when there is demand to draw", () => {
    expect(resourcingCard(R())).toBe("full");
    // a grouping problem does not suppress a book that HAS demand — the trade table still stands,
    // which is the whole reason a bad configuration degrades rather than 422s.
    expect(resourcingCard(R({ groups_error: "trade 'x' is in both 'A' and 'B'" }))).toBe("full");
  });

  it("draws nothing when there is no demand and nothing to say about it", () => {
    expect(resourcingCard(R({ available: false, trades: [] }))).toBe("none");
    expect(resourcingCard(R({ available: false }))).toBe("none");
    expect(resourcingCard(R({ trades: [] }))).toBe("none");
  });

  // THE REGRESSION. Both halves of the empty case, because the API returns `available: false`
  // WITH `trades: []` together and a test that only covered one would pass on half the fix.
  it("still reports a broken configured grouping when there is no demand at all", () => {
    const why = "group 'Empty' names no trades";
    expect(resourcingCard(R({ available: false, trades: [], groups_error: why }))).toBe("warning-only");
    expect(resourcingCard(R({ available: false, groups_error: why }))).toBe("warning-only");
    expect(resourcingCard(R({ trades: [], groups_error: why }))).toBe("warning-only");
  });

  // An empty string is not a problem report. Nothing produces one today, but "" is what a naive
  // `?? ""` fallback yields, and a warning card reading "not applied — " helps nobody.
  it("treats an empty reason as no reason", () => {
    expect(resourcingCard(R({ available: false, trades: [], groups_error: "" }))).toBe("none");
  });
});
