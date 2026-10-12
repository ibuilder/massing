import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import { buyoutOutcome, buyoutSkippedNote } from "./budget";

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
    expect(buyoutOutcome(42, 0)).toEqual({ kind: "no-packages", lineCount: 42, skipped: 0 });
  });

  it("reports packages when the grouping worked", () => {
    expect(buyoutOutcome(42, 7)).toEqual({ kind: "packages", packageCount: 7, skipped: 0 });
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

describe("TOTAL-EXCLUDED — the lines that could not be packaged at all", () => {
  it("THE CORRECTION: all lines unnameable is NOT a grouping problem", () => {
    // `buyout_packages` discards a line with no item, description, material or IFC class and
    // returns the tally; the field was declared nowhere in this client, so this case fell into
    // `no-packages`, whose message says "that is a grouping problem, not an empty project". That
    // sends an estimator to re-map trades when the fix is to NAME the line items. A message that
    // can misdiagnose is worse than silence, because somebody follows it.
    expect(buyoutOutcome(12, 0, 12)).toEqual({ kind: "unidentifiable", lineCount: 12, skipped: 12 });
    expect(buyoutOutcome(12, 0, 12).kind).not.toBe("no-packages");
  });

  it("but SOME unnameable with nothing grouped is still a grouping problem", () => {
    // The discriminator is whether the nameable lines failed to group. One skipped line out of
    // twelve leaves eleven that should have produced a package and did not.
    expect(buyoutOutcome(12, 0, 1)).toEqual({ kind: "no-packages", lineCount: 12, skipped: 1 });
  });

  it("the two tallies are independently derived, so skipped may EXCEED the priced lines", () => {
    // The panel counts priced lines; the engine also counts non-dict rows out. `>=` rather than
    // `===` is the honest comparison between two counts nobody reconciled — and with `===` this
    // case would fall back to the misdiagnosing branch.
    expect(buyoutOutcome(3, 0, 5).kind).toBe("unidentifiable");
  });

  it("carries the tally into the SUCCESS case too — a total that balances is not explained", () => {
    // The headline prints a package count and a dollar total, both over the lines that could be
    // named. `ProformaResult.sources_uses.loan_fees` is the precedent: its absence balanced.
    expect(buyoutOutcome(40, 7, 3)).toEqual({ kind: "packages", packageCount: 7, skipped: 3 });
  });

  it("no quantities outranks everything — there is nothing to have skipped", () => {
    expect(buyoutOutcome(0, 0, 9).kind).toBe("no-quantities");
  });

  it("junk and negative tallies normalise rather than reaching the message", () => {
    for (const bad of [-1, Number.NaN, undefined as unknown as number]) {
      expect(buyoutOutcome(40, 7, bad), String(bad)).toEqual({ kind: "packages", packageCount: 7, skipped: 0 });
    }
  });
});

describe("buyoutSkippedNote", () => {
  it("says the number is NOT in the figures above — the whole point of printing it", () => {
    const n = buyoutSkippedNote(4)!;
    expect(n).toContain("4 line(s)");
    expect(n).toContain("NOT in the count or the estimate above");
    expect(n).toContain("Name them");
  });

  it("is SILENT at zero — a permanent caveat is noise rather than an answer", () => {
    // Without this the assertion above passes for a note that always renders, which is the
    // failure mode `modelCaveat` and the review-cycles card were both written against.
    for (const none of [0, -3, Number.NaN, undefined as unknown as number]) {
      expect(buyoutSkippedNote(none), String(none)).toBeNull();
    }
  });
});

describe("the panel is WIRED to the tally — the pure tests above cannot see this", () => {
  // Source-level, and the limit is stated rather than discovered later: a call wrapped in
  // `if (false)` would pass these. The pure assertions above prove the decision; these prove the
  // decision is reached with the engine's number rather than a default. Anchored on `__file__`
  // because `vitest` and `run_tests.py` start from different directories.
  const SRC = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "budget.ts"), "utf-8");

  it("passes the engine's skipped tally into the outcome, not a default", () => {
    expect(SRC).toContain("buyoutOutcome(lines.length, b.packages.length, b.skipped_unidentifiable)");
  });

  it("renders the note in the SUCCESS path too, where the total is printed", () => {
    expect(SRC).toContain("const skippedNote = buyoutSkippedNote(b.skipped_unidentifiable)");
    expect(SRC).toContain("esc(skippedNote)");
    // THE NOTE ITSELF GATES THE RENDER. Asserting only that `esc(skippedNote)` appears survived a
    // mutation that replaced the condition with `false` — the string was still in the source,
    // inside a dead ternary. *A predicted limit is still a surviving mutation*, so the gate
    // expression is pinned too, not just the interpolation it guards.
    expect(SRC).toContain("+ (skippedNote");
  });

  it("and the client DECLARES the field, or no derivation over declarations can see it", () => {
    // The reason this defect outlived the 52-field asymmetry sweep: that derivation starts from
    // `apps/web/src/api/` declarations, and this field was in none of them. Nor in `schema.d.ts`,
    // because the route returns an untyped dict.
    const api = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../../api/procurement.ts"), "utf-8");
    expect(api).toContain("skipped_unidentifiable: number");
  });
});
