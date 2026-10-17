import { describe, expect, it } from "vitest";
import type { ModelHealth, ModelHealthLens } from "../../api/model";
import { healthCoverage, healthLensValue, healthNote, healthThin, healthUnscored,
  healthWeightBasis } from "./healthCoverRead";

/** The five weights, taken from `model_health._WEIGHTS` and asserted to sum to 1.0 there. */
const W = {
  hygiene: 0.25, information: 0.25, coordination: 0.2, verified: 0.15, readiness: 0.15,
} as const;

const LABELS: Record<keyof typeof W, string> = {
  hygiene: "Integrity & hygiene",
  information: "Information & delivery (ISO 19650)",
  coordination: "Coordination (clash issues)",
  verified: "Verified as-built",
  readiness: "Code & permit readiness",
};

/** Build a response with exactly the named lenses scored at 80 and the rest n/a. */
const health = (scored: (keyof typeof W)[], over: Partial<ModelHealth> = {}): ModelHealth => {
  const lenses: ModelHealthLens[] = (Object.keys(W) as (keyof typeof W)[]).map((k) => ({
    key: k, label: LABELS[k], tool: `tool_${k}`,
    score: scored.includes(k) ? 80 : null,
    status: scored.includes(k) ? "good" : "na",
    headline: scored.includes(k) ? "fine" : "no inputs yet",
    weight: W[k],
  }));
  const weight = scored.reduce((n, k) => n + W[k], 0);
  return {
    overall_score: scored.length ? 80 : null,
    band: scored.length ? "good" : "unscored",
    scored_lenses: scored.length,
    weight_scored: Math.round(weight * 1e6) / 1e6,
    model_available: true,
    lenses,
    note: "A composite of the model-quality checks (hygiene, ISO 19650 KPIs, clash coordination, "
      + "verified-as-built, and code/permit readiness).",
    weight_basis: "basis sentence",
    ...over,
  };
};

describe("healthCoverage — the count and the share are different questions", () => {
  it("prints the full basis when every lens scored", () => {
    const c = healthCoverage(health(["hygiene", "information", "coordination", "verified", "readiness"]))!;
    expect(c).toContain("5 of 5 lens(es) scored");
    expect(c).toContain("100% of the composite");
    expect(c).toContain("the full basis");
  });

  it("distinguishes the two '2 of 5' cases the shipped caption could not", () => {
    // Measured directly from `_WEIGHTS`: both of these report `overall_score: 80` and both read
    // `2 of 5 checks scored` on the shipped screen, over 30% and 50% of the composite.
    const light = healthCoverage(health(["verified", "readiness"]))!;
    const heavy = healthCoverage(health(["hygiene", "information"]))!;
    expect(light).toContain("30% of the composite");
    expect(heavy).toContain("50% of the composite");
    expect(light).not.toBe(heavy);
    // and the count — the only thing on screen before — is identical for the two
    expect(light).toContain("2 of 5");
    expect(heavy).toContain("2 of 5");
  });

  it("gives the 3-of-5 case its measured share", () => {
    expect(healthCoverage(health(["hygiene", "information", "coordination"]))!)
      .toContain("70% of the composite");
  });

  it("says the score is renormalised, not lowered — the thing a count cannot say", () => {
    const c = healthCoverage(health(["hygiene", "information"]))!;
    expect(c).toContain("not lowered by what was not");
  });

  it("is null when nothing scored, because there is no composite to qualify", () => {
    expect(healthCoverage(health([]))).toBeNull();
  });

  it("renders a weight with no false precision", () => {
    // 0.2 must not print as 20.000000000000004%
    expect(healthCoverage(health(["coordination"]))!).toContain("20% of the composite");
  });

  it("is plain text — the caller passes it to resultNote, which takes HTML", () => {
    for (const s of [["hygiene"], ["verified", "readiness"], []] as (keyof typeof W)[][]) {
      expect(healthCoverage(health(s)) ?? "").not.toMatch(/[<>]/);
    }
  });
});

describe("healthUnscored — what is missing, and what it is worth", () => {
  it("is null when every lens scored", () => {
    expect(healthUnscored(health(["hygiene", "information", "coordination", "verified", "readiness"])))
      .toBeNull();
  });

  it("orders by weight, heaviest first — the one worth fixing first", () => {
    const u = healthUnscored(health(["verified", "readiness"]))!;
    expect(u.indexOf("Integrity & hygiene")).toBeLessThan(u.indexOf("Coordination"));
    expect(u).toContain("Integrity & hygiene (25%)");
    expect(u).toContain("Coordination (clash issues) (20%)");
  });

  it("breaks a weight tie by label so the order is stable", () => {
    const u = healthUnscored(health(["coordination", "verified", "readiness"]))!;
    expect(u.indexOf("Information & delivery")).toBeLessThan(u.indexOf("Integrity & hygiene"));
  });

  it("caps the list and says how many more", () => {
    expect(healthUnscored(health([]), 2)!).toContain("3 more");
  });

  it("points at the tools rather than naming the gap alone", () => {
    expect(healthUnscored(health(["hygiene"]))!).toContain("tool in this rail");
  });
});

describe("healthLensValue — every row says what the row is worth", () => {
  const lens = (over: Partial<ModelHealthLens> = {}): ModelHealthLens => ({
    key: "readiness", label: "Code & permit readiness", tool: "approvability",
    score: 64, status: "warn", headline: "2 check(s) to fix: egress, rating", weight: 0.15, ...over,
  });

  it("carries the score, the weight and the headline", () => {
    const v = healthLensValue(lens());
    expect(v).toBe("64/100 · 15% of the score — 2 check(s) to fix: egress, rating");
  });

  it("says n/a without implying zero, and still says what the lens is worth", () => {
    const v = healthLensValue(lens({ score: null, status: "na", headline: "load a model to check" }));
    expect(v).toContain("n/a");
    expect(v).toContain("15% of the score");
    expect(v).not.toContain("0/100");
  });
});

describe("healthThin — the threshold is on the WEIGHT, which is the whole item", () => {
  it("fires below half the composite", () => {
    const t = healthThin(health(["verified", "readiness"]))!;   // 30%
    expect(t).toContain("Less than half");
    expect(t).toContain("30%");
    expect(t).toContain("80/100 describes the part that was");
  });

  it("does NOT fire at exactly half, even though that is only 2 of 5 lenses", () => {
    // This is the assertion that proves the threshold is not the count: 2 of 5 is 40% of the
    // lenses and 50% of the composite, and the second is what decides.
    expect(healthThin(health(["hygiene", "information"]))).toBeNull();
  });

  it("gives two IDENTICAL counts opposite verdicts, which is the whole demonstration", () => {
    // Two lenses scored, both times. `hygiene + information` is 50% and reads as sound;
    // `verified + readiness` is 30% and does not. A threshold on the count cannot produce this.
    expect(healthThin(health(["hygiene", "information"]))).toBeNull();
    expect(healthThin(health(["verified", "readiness"]))).not.toBeNull();
  });

  it("can only ever fire at two lenses or fewer — measured, not assumed", () => {
    // The three lightest weights are coordination .20 + verified .15 + readiness .15 = .50, so
    // ANY three lenses clear the threshold and the warning is reachable only at one or two. Worth
    // asserting because it bounds the claim above: the two numbers disagree in a window, not
    // everywhere, and a bound checked is worth more than a severity asserted.
    const keys = ["hygiene", "information", "coordination", "verified", "readiness"] as const;
    for (let i = 0; i < keys.length; i++) {
      for (let j = i + 1; j < keys.length; j++) {
        for (let k = j + 1; k < keys.length; k++) {
          expect(healthThin(health([keys[i]!, keys[j]!, keys[k]!]))).toBeNull();
        }
      }
    }
    // and at least one PAIR does fire, so the window is not empty
    expect(healthThin(health(["verified", "readiness"]))).not.toBeNull();
  });

  it("is null when nothing scored — the caller says that separately", () => {
    expect(healthThin(health([]))).toBeNull();
  });
});

describe("the engine's own sentences are passed through, never restated", () => {
  it("returns note verbatim", () => {
    const h = health(["hygiene"]);
    expect(healthNote(h)).toBe(h.note);
  });

  it("names all five lenses — the hardcoded caption named four", () => {
    // The shipped caption read "integrity/hygiene, ISO 19650 KPIs, clash coordination, and
    // verified-as-built" and omitted code/permit readiness, 15% of the composite.
    expect(healthNote(health(["hygiene"]))).toContain("code/permit readiness");
  });

  it("returns weight_basis verbatim", () => {
    const h = health(["hygiene"]);
    expect(healthWeightBasis(h)).toBe(h.weight_basis);
  });
});
