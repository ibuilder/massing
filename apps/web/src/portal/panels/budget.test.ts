import { describe, expect, it } from "vitest";
import { buyoutOutcome } from "./budget";

/**
 * QTO-TRADE — the three buyout outcomes must stay distinguishable.
 *
 * The item this closes was not "buyout has no screen". It was that a screen over the old engine
 * would have rendered **"Buyout — 0 packages · $0"** for a fully-priced model, because
 * `buyout_packages` skipped every model-derived line and returned nothing. That reads as *this
 * project has nothing to buy out* rather than *this input is in the other dialect* — a confident
 * wrong answer, which is worse than no answer at all and is why the roadmap filed the whole
 * capability as unwireable rather than wiring it.
 *
 * So the distinction the fix has to preserve is not cosmetic:
 *   * **no-quantities** — nothing has been estimated yet. Go run an estimate.
 *   * **no-packages** — priced lines went in and nothing came out. That is a grouping failure and
 *     someone should look at it.
 *
 * Asserted against the decision function rather than the rendered HTML. A test that scanned the
 * source for two different strings would prove they are spelled differently, not that the right one
 * is chosen for the right input — and "spelled differently" is satisfied by a renderer that always
 * picks the first.
 */
describe("buyoutOutcome keeps the two empty states apart", () => {
  it("reports no-quantities when the model priced nothing", () => {
    expect(buyoutOutcome(0, 0)).toEqual({ kind: "no-quantities" });
  });

  it("reports no-packages when priced lines produced none — and carries the count", () => {
    // The count is the evidence that this is NOT an empty project, so it belongs in the result
    // rather than being re-read from a variable the message happens to have in scope.
    expect(buyoutOutcome(42, 0)).toEqual({ kind: "no-packages", lineCount: 42 });
  });

  it("reports packages when the grouping worked", () => {
    expect(buyoutOutcome(42, 7)).toEqual({ kind: "packages", packageCount: 7 });
  });

  it("never answers no-quantities when quantities exist — the confusion that filed this item", () => {
    // The specific regression: lines present, packages absent, reported as "nothing to buy out".
    expect(buyoutOutcome(42, 0).kind).not.toBe("no-quantities");
    // ...and its mirror, so this is not merely a one-directional assertion.
    expect(buyoutOutcome(0, 0).kind).not.toBe("no-packages");
  });

  it("treats a negative or absent count as no-quantities rather than throwing", () => {
    // `by_discipline` is optional on the wire; `(q.by_discipline ?? []).length` is 0, but a caller
    // passing a bad value must still get a defined branch rather than falling through to "packages".
    expect(buyoutOutcome(-1, 3).kind).toBe("no-quantities");
  });

  it("the three kinds are mutually exclusive across a grid of inputs", () => {
    // Vacuity guard on the whole set: every combination must land in exactly one branch, and all
    // three branches must actually be reachable — a function returning one kind for everything
    // would satisfy each individual assertion above only by accident of the cases chosen.
    const kinds = new Set<string>();
    for (const lines of [0, 1, 5]) {
      for (const pkgs of [0, 1, 3]) kinds.add(buyoutOutcome(lines, pkgs).kind);
    }
    expect([...kinds].sort()).toEqual(["no-packages", "no-quantities", "packages"]);
  });
});
