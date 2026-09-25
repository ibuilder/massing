import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { coverageOf, gatherEvidence, renderDecisionGate } from "./decisionGateCard";

/**
 * CRE-DECISION-GATE composes the evidence the rest of this tab produces, and its contract is the
 * principle this session spent itself enforcing in consumers — implemented, for once, in the engine:
 *
 * > A gate whose evidence was not supplied is `unknown`, and unknown BLOCKS — absent evidence must
 * > never read as a pass. The actions list says what to do, not just what failed.
 *
 * So the card's job is not to add judgement but to avoid subtracting it. What is pinned here is that
 * `unknown` reads as blocking rather than as neutral, that the actions lead, and that a *vacuous*
 * pass is rendered with its reason — a gate that passed because nothing was required is not the same
 * claim as one that passed because it was tested.
 */

type Gate = Awaited<ReturnType<ApiClient["decisionGate"]>>;

const G = (gate: string, label: string, status: "pass" | "fail" | "unknown",
           detail: string, action = "") => ({ gate, label, status, detail, action });

const BLOCKED = (over: Partial<Gate> = {}): Gate => ({
  verdict: "blocked", ready: false,
  gates: [
    G("sourced", "Answers are sourced", "unknown", "no cited-answer contract was supplied",
      "Produce the answer through the cited-answer contract."),
    G("rent_roll_scrubbed", "Rent roll reconciles", "fail", "3 checks failed",
      "Resolve the rent-roll findings."),
    G("exhibits", "Required exhibits are present", "pass",
      "no exhibits were required for this package"),
  ],
  blocking: [], actions: [
    { gate: "sourced", action: "Produce the answer through the cited-answer contract." },
    { gate: "rent_roll_scrubbed", action: "Resolve the rent-roll findings." },
  ],
  counts: { total: 3, passed: 1, failed: 1, unknown: 1 },
  note: "A gate whose evidence was not supplied is `unknown`, and unknown BLOCKS.",
  ...over,
} as Gate);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("the verdict", () => {
  it("counts the no-evidence gates separately from the failures", () => {
    const t = renderDecisionGate(mount(), BLOCKED()).textContent ?? "";
    expect(t).toContain("Blocked — not ready for committee");
    expect(t).toContain("1 passed");
    expect(t).toContain("1 failed");
    expect(t).toContain("1 with no evidence");
  });

  it("says ready plainly when it is", () => {
    const t = renderDecisionGate(mount(), BLOCKED({
      verdict: "ready", ready: true, actions: [],
      gates: [G("exhibits", "Required exhibits are present", "pass", "all 3 present")],
      counts: { total: 1, passed: 1, failed: 0, unknown: 0 },
    })).textContent ?? "";
    expect(t).toContain("Ready for committee");
    expect(t).not.toContain("Blocked");
  });
});

describe("unknown is not neutral", () => {
  // The engine blocks on it, so a card that renders it as a shrug states something the engine did
  // not. Asserted on the rendered word AND the colour, because either alone passes a card that says
  // the right word in grey or the wrong word in amber.
  it("reads as blocking, in word and in colour", () => {
    const el = renderDecisionGate(mount(), BLOCKED());
    const cells = [...el.querySelectorAll("td")];
    const unknown = cells.find((c) => c.textContent?.includes("no evidence — blocks"));
    expect(unknown, "an unknown gate does not say it blocks").toBeTruthy();
    expect(unknown!.style.color).toBe("var(--status-warn)");
  });

  it("does not colour an unknown the same as a pass", () => {
    const el = renderDecisionGate(mount(), BLOCKED());
    const colourOf = (word: string) =>
      [...el.querySelectorAll("td")].find((c) => c.textContent === word)?.style.color;
    expect(colourOf("pass")).toBeTruthy();
    expect(colourOf("no evidence — blocks")).not.toBe(colourOf("pass"));
    expect(colourOf("fail")).not.toBe(colourOf("no evidence — blocks"));
  });
});

describe("the actions lead", () => {
  it("renders what to do, labelled by gate, above the gate table", () => {
    const el = renderDecisionGate(mount(), BLOCKED());
    const tables = [...el.querySelectorAll("table")];
    const first = [...tables[0]!.querySelectorAll("tr")].slice(1)
      .map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent));
    expect(first).toEqual([
      ["Answers are sourced", "Produce the answer through the cited-answer contract."],
      ["Rent roll reconciles", "Resolve the rent-roll findings."],
    ]);
  });

  it("uses the gate's label, not its key", () => {
    // `sourced` is the key; "Answers are sourced" is what a person reads.
    expect(renderDecisionGate(mount(), BLOCKED()).textContent).not.toContain("rent_roll_scrubbed");
  });
});

describe("a vacuous pass is rendered with its reason", () => {
  it("keeps the engine's detail beside a pass that was never tested", () => {
    // "no exhibits were required for this package" is a pass that tested nothing — exactly what the
    // other six gates exist to refuse elsewhere, so it must not render as a bare tick.
    expect(renderDecisionGate(mount(), BLOCKED()).textContent)
      .toContain("no exhibits were required for this package");
  });
});

describe("a gate's own coverage is not dropped", () => {
  /**
   * **This card shipped without this and its own sibling gate caught it.**
   * `services/api/test_verdict_coverage.py` — written one commit earlier, to derive exactly this
   * class — failed on `decisionGateCard.ts`. `_gate()` splats `**extra` onto the row, so
   * `rent_roll_scrubbed` arrives carrying `ran`, `failed` and `not_applicable`; the card declared
   * five fields and rendered `detail`, which expresses none of them.
   *
   * Measured through the real engine: a scrub with `ran: 1, not_applicable: 6, failed: 0` returns
   * **`status: "pass"`** and **`detail: "the scrub ran but found nothing"`** — where "nothing"
   * means "no problems found" and reads as "nothing was wrong", over six checks that never ran.
   */
  const SCRUBBED = () => BLOCKED({
    gates: [G("rent_roll_scrubbed", "The rent roll reconciles to income", "pass",
              "the scrub ran but found nothing")],
    counts: { total: 1, passed: 1, failed: 0, unknown: 0 },
  });
  const withCoverage = (over: Record<string, number>) => {
    const g = SCRUBBED();
    Object.assign(g.gates[0]!, over);
    return g;
  };

  it("renders what could not be checked beside the verdict", () => {
    const t = renderDecisionGate(mount(), withCoverage({ ran: 1, not_applicable: 6, failed: 0 }))
      .textContent ?? "";
    expect(t).toContain("1 of 7 check(s) ran");
    expect(t).toContain("6 could not");
  });

  it("says nothing when every check ran — silence must mean full coverage", () => {
    // The anti-vacuity twin. Without it, a `coverageOf` that always returned null would pass the
    // assertion above only by accident of the fixture, and this file would still read green.
    const t = renderDecisionGate(mount(), withCoverage({ ran: 7, not_applicable: 0, failed: 0 }))
      .textContent ?? "";
    expect(t).not.toContain("could not");
    expect(t).toContain("the scrub ran but found nothing");     // the row is still rendered
  });

  it("leaves the engine's own status word alone", () => {
    // The card declines to DROP what the engine measured; it does not overrule the engine. A card
    // that demoted this pass to a warning would be inventing a verdict the engine did not reach.
    const el = renderDecisionGate(mount(), withCoverage({ ran: 1, not_applicable: 6, failed: 0 }));
    const cells = [...el.querySelectorAll("td")];
    expect(cells.some((c) => c.textContent === "pass")).toBe(true);
  });

  it("is a rule over whatever coverage a row carries, not a special case for one gate", () => {
    expect(coverageOf({ ran: 2, not_applicable: 3 })).toBe("2 of 5 check(s) ran · 3 could not");
    expect(coverageOf({ ran: 5, not_applicable: 0 })).toBeNull();
    expect(coverageOf({})).toBeNull();
    // A row that reports only what could NOT run still has to report it — `ran` defaulting to 0 is
    // the worst case, not an absent one.
    expect(coverageOf({ not_applicable: 4 })).toBe("0 of 4 check(s) ran · 4 could not");
  });
});

describe("gathering evidence", () => {
  it("sends what this app can produce and leaves the rest absent", async () => {
    const api = {
      dealAuthority: vi.fn().mockResolvedValue({ gate: { passes: true } }),
      rentRollScrub: vi.fn().mockResolvedValue({ clean: true }),
    } as unknown as ApiClient;
    expect(await gatherEvidence(api, "p1")).toEqual({
      authority: { gate: { passes: true } }, rent_scrub: { clean: true },
    });
  });

  it("omits a source that failed rather than sending a half-answer", async () => {
    // An omitted key makes its gate `unknown`, which blocks. Sending a partial or invented payload
    // would make it pass or fail on something this card made up.
    const api = {
      dealAuthority: vi.fn().mockRejectedValue(new Error("no authority table")),
      rentRollScrub: vi.fn().mockResolvedValue({ clean: false }),
    } as unknown as ApiClient;
    expect(await gatherEvidence(api, "p1")).toEqual({ rent_scrub: { clean: false } });
  });

  it("returns nothing when both sources fail, rather than throwing", async () => {
    const api = {
      dealAuthority: vi.fn().mockRejectedValue(new Error("x")),
      rentRollScrub: vi.fn().mockRejectedValue(new Error("y")),
    } as unknown as ApiClient;
    expect(await gatherEvidence(api, "p1")).toEqual({});
  });
});
