import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { EffectiveRules, RuleRun } from "./ruleCheckView";
import {
  provenanceReading, renderEffectiveStandards, renderRuleCheck, sourceBadge,
} from "./ruleCheckView";

/**
 * FIRM-RULES-OPTIONAL, the screen half.
 *
 * `/rules/run` said *"0 of 3 rules failing"* in a pass tone on projects where nobody had authored a
 * rule: three SAMPLE rules ship as a starting point and both evaluators fell back to them, with
 * nothing in the response saying so. And the firm's own library — the whole point of
 * `firm_standards`, whose docstring names the failure mode as *"a firm discovering its standards
 * were quietly optional"* — was evaluated by neither.
 *
 * The three properties this file holds, each mutation-proved below:
 *
 *  1. **A clean result over samples is not toned as a pass.** That tone IS the misreading.
 *  2. **A failure a sample rule finds is still shown as a failure.** The samples are relabelled,
 *     never suppressed: a door with no fire rating is a door with no fire rating whoever wrote the
 *     rule that caught it.
 *  3. **Every row says where its rule came from**, and an override names what it displaced —
 *     because an override is legitimate and being invisible is not.
 */

const prov = (o: Partial<NonNullable<RuleRun["provenance"]>> = {}) => ({
  using_starter: o.using_starter ?? false,
  firm_count: o.firm_count ?? 0,
  inherited_count: o.inherited_count ?? 0,
  overridden_count: o.overridden_count ?? 0,
  project_only_count: o.project_only_count ?? 0,
  overridden: o.overridden ?? [],
  note: o.note ?? "",
});

const row = (o: Partial<RuleRun["rules"][number]> = {}): RuleRun["rules"][number] => ({
  id: o.id ?? "r1", name: o.name ?? "Fire doors carry a rating", severity: o.severity ?? "high",
  scope: o.scope ?? "IfcDoor", require: o.require ?? "Pset_DoorCommon.FireRating",
  scoped: o.scoped ?? 4, passed: o.passed ?? 4, failed: o.failed ?? 0,
  fail_guids: o.fail_guids ?? [], status: o.status ?? "pass",
  source: o.source, overrides: o.overrides,
});

const run = (o: Partial<RuleRun> = {}): RuleRun => ({
  model_scored: true,
  total_rules: o.total_rules ?? 3,
  failing_rules: o.failing_rules ?? 0,
  total_violations: o.total_violations ?? 0,
  by_severity: o.by_severity ?? {},
  provenance: o.provenance,
  rules: o.rules ?? [row()],
  ...o,
});

const host = () => document.createElement("div");
const notes = (el: HTMLElement) => [...el.querySelectorAll(".result-note")] as HTMLElement[];

describe("provenanceReading — samples are not a standard", () => {
  it("names the sample fallback and tones it as neither pass nor failure", () => {
    const r = provenanceReading(prov({ using_starter: true }));
    expect(r.kind).toBe("samples");
    expect(r.tone).toBe("warn");
    expect(r.tone).not.toBe("ok");
    expect(r.headline).toContain("SAMPLE");
  });

  it("says BOTH halves of the asymmetry, because either alone misleads", () => {
    const d = provenanceReading(prov({ using_starter: true })).detail;
    expect(d, "a clean result over samples must not read as a pass").toContain("not a pass");
    expect(d, "a failure found by a sample rule is still a real defect").toContain("still a");
  });

  it("distinguishes firm-only, project-only and mixed, because the advice differs", () => {
    expect(provenanceReading(prov({ inherited_count: 2, firm_count: 2 })).kind).toBe("firm");
    expect(provenanceReading(prov({ project_only_count: 2 })).kind).toBe("project");
    expect(provenanceReading(prov({ inherited_count: 1, project_only_count: 1, firm_count: 1 })).kind)
      .toBe("mixed");
  });

  it("counts an OVERRIDE as firm involvement — the firm's standard is in play either way", () => {
    // `overridden_count` without `inherited_count` is a project that replaced every firm rule.
    // Reading that as "project-only" would say the firm has no stake in this check, when the whole
    // reason the override is visible is that it does.
    expect(provenanceReading(prov({ overridden_count: 1, firm_count: 1 })).kind).toBe("firm");
    expect(provenanceReading(prov({ overridden_count: 1, firm_count: 1 })).detail)
      .toContain("override");
  });

  it("says the firm's standards are EVALUATED, not merely listed", () => {
    // The sentence is the item: they were listed, on a page nothing could open, and run by nobody.
    expect(provenanceReading(prov({ inherited_count: 2, firm_count: 2 })).detail)
      .toContain("evaluated");
  });
});

describe("sourceBadge — no row is left unlabelled", () => {
  it("labels each origin distinctly", () => {
    const got = ["firm", "project", "starter", "space-pack"].map((s) => sourceBadge(s, null));
    expect(new Set(got).size).toBe(4);
    expect(sourceBadge("starter", null)).toContain("sample");
  });

  it("an OVERRIDE outranks its source — it is the more specific fact", () => {
    expect(sourceBadge("project", { id: "x", name: "n", scope: "s", require: "q", severity: "high" }))
      .toContain("override");
  });

  it("says origin unknown rather than guessing", () => {
    expect(sourceBadge(null, null)).toContain("unknown");
    expect(sourceBadge(undefined, null)).toContain("unknown");
  });
});

describe("renderRuleCheck — the tone of a clean sample run", () => {
  it("does NOT tone a clean result over samples as a pass", () => {
    const el = host();
    renderRuleCheck(run({ provenance: prov({ using_starter: true }) }), el, () => {});
    const rollup = notes(el).find((n) => n.textContent?.includes("of 3 rules failing"))!;
    expect(rollup, "the rollup note was not rendered — this test would pass vacuously")
      .toBeTruthy();
    expect(rollup.classList.contains("ok"),
           "a pass tone over three sample rules is the whole defect").toBe(false);
  });

  it("DOES tone a clean result over an authored library as a pass", () => {
    // The twin: suppressing the pass tone everywhere would be just as wrong, and a test of only
    // the first half passes happily under that change.
    const el = host();
    renderRuleCheck(run({ provenance: prov({ project_only_count: 3 }) }), el, () => {});
    const rollup = notes(el).find((n) => n.textContent?.includes("of 3 rules failing"))!;
    expect(rollup.classList.contains("ok")).toBe(true);
  });

  it("still shows a failure a SAMPLE rule found", () => {
    const el = host();
    renderRuleCheck(run({
      provenance: prov({ using_starter: true }), failing_rules: 1, total_violations: 7,
      by_severity: { high: 1 },
      rules: [row({ status: "fail", failed: 7, passed: 0, fail_guids: ["a", "b"] })],
    }), el, () => {});
    expect(el.textContent).toContain("Fire doors carry a rating");
    expect(el.textContent).toContain("7");
    expect(el.textContent).toContain("isolate failures");
  });

  it("renders the provenance note ABOVE the rollup", () => {
    // Ordering is the assertion: the sentence that reframes the number has to be read first.
    const el = host();
    renderRuleCheck(run({ provenance: prov({ using_starter: true }) }), el, () => {});
    const texts = notes(el).map((n) => n.textContent || "");
    expect(texts[0]).toContain("SAMPLE");
    expect(texts[1]).toContain("rules failing");
  });

  it("badges every rule row", () => {
    const el = host();
    renderRuleCheck(run({
      provenance: prov({ inherited_count: 1, project_only_count: 1, firm_count: 1 }),
      rules: [row({ id: "a", source: "firm" }), row({ id: "b", name: "Walls named", source: "project" })],
    }), el, () => {});
    expect(el.textContent).toContain("firm");
    expect(el.textContent).toContain("project");
  });

  it("an override row names the FIRM requirement it replaced", () => {
    const el = host();
    renderRuleCheck(run({
      provenance: prov({ overridden_count: 1, firm_count: 1 }),
      rules: [row({ source: "project", overrides: {
        id: "r1", name: "Firm: 90 min", scope: "IfcDoor",
        require: "Pset_DoorCommon.FireRating=90", severity: "high" } })],
    }), el, () => {});
    expect(el.textContent).toContain("override");
    expect(el.textContent).toContain("FireRating=90");
  });

  it("renders with no provenance at all, rather than throwing", () => {
    // An older server, or a cached response. A screen that threw here would lose the rule check
    // entirely over a missing annotation.
    const el = host();
    renderRuleCheck(run(), el, () => {});
    expect(el.textContent).toContain("Fire doors carry a rating");
  });

  it("escapes a rule name — names are user-authored", () => {
    const el = host();
    renderRuleCheck(run({ rules: [row({ name: "<img src=x onerror=alert(1)>" })] }), el, () => {});
    expect(el.querySelector("img")).toBeNull();
    expect(el.textContent).toContain("<img");
  });

  it("caps what it hands the isolate callback", () => {
    const seen: string[][] = [];
    const el = host();
    renderRuleCheck(run({
      rules: [row({ status: "fail", failed: 900, passed: 0,
                    fail_guids: Array.from({ length: 900 }, (_, i) => `g${i}`) })],
    }), el, (g) => seen.push(g));
    (el.querySelector("a") as HTMLAnchorElement).click();
    expect(seen[0]!.length).toBe(500);
  });
});

describe("renderEffectiveStandards — the door for /rules/effective", () => {
  const eff = (o: Partial<EffectiveRules> = {}): EffectiveRules => ({
    rules: o.rules ?? [],
    count: o.count ?? 0, firm_count: o.firm_count ?? 0, inherited_count: o.inherited_count ?? 0,
    overridden_count: o.overridden_count ?? 0, project_only_count: o.project_only_count ?? 0,
    overridden: o.overridden ?? [], note: o.note ?? "a note from the server",
    ...o,
  });

  it("warns when NOTHING is authored anywhere, and says what that costs", () => {
    const el = host();
    renderEffectiveStandards(eff(), el);
    expect(el.textContent).toContain("SAMPLE");
    expect(notes(el).some((n) => n.classList.contains("warn"))).toBe(true);
  });

  it("lists each rule with its origin and its selectors", () => {
    const el = host();
    renderEffectiveStandards(eff({
      count: 1, firm_count: 1, inherited_count: 1,
      rules: [{ id: "f1", name: "L1 doors are rated", scope: "IfcDoor",
                require: "Pset_DoorCommon.FireRating=90", severity: "high", source: "firm" }],
    }), el);
    expect(el.textContent).toContain("L1 doors are rated");
    expect(el.textContent).toContain("firm");
    expect(el.textContent).toContain("Pset_DoorCommon.FireRating=90");
    expect(el.textContent).not.toContain("SAMPLE");
  });

  it("spells out each override as a firm-versus-project pair", () => {
    const el = host();
    renderEffectiveStandards(eff({
      count: 1, firm_count: 1, overridden_count: 1,
      rules: [{ id: "f1", name: "Client standard", scope: "IfcDoor",
                require: "Pset_DoorCommon.FireRating=60", severity: "high", source: "project" }],
      overridden: [{ id: "f1", name: "L1 doors are rated",
                     firm_require: "Pset_DoorCommon.FireRating=90",
                     project_require: "Pset_DoorCommon.FireRating=60" }],
    }), el);
    expect(el.textContent).toContain("FireRating=90");
    expect(el.textContent).toContain("FireRating=60");
  });

  it("escapes the server's note and the rule text", () => {
    const el = host();
    renderEffectiveStandards(eff({ note: "<img src=x onerror=alert(1)>" }), el);
    expect(el.querySelector("img")).toBeNull();
  });
});

/** The pins: the controls exist, and the rendering left `qaSection.ts` rather than being copied. */
const here = dirname(fileURLToPath(import.meta.url));
const qa = readFileSync(resolve(here, "qaSection.ts"), "utf8");
const client = readFileSync(resolve(here, "../../api/model.ts"), "utf8");

describe("the panel asks, and asks the right route", () => {
  const view = readFileSync(resolve(here, "ruleCheckView.ts"), "utf8");

  it("declares a client method for the effective-standards route", () => {
    expect(client).toMatch(/rulesEffective\(pid: string\)/);
    expect(client).toContain("/rules/effective");
  });

  it("gives the rule check and the standards listing their own controls", () => {
    expect(qa).toContain("Rule check (rule library)");
    expect(qa).toContain("Standards that apply here");
  });

  it("asks both routes — from THIS module, which is the lazy side of the seam", () => {
    expect(view).toMatch(/api\.rulesRun\(pid\)/);
    expect(view).toMatch(/api\.rulesEffective\(pid\)/);
  });

  it("keeps the whole control body off the eager path, not just the rendering", () => {
    // The shell came out 5 bytes over 224 KB with only the rendering deferred. Deferring the
    // render and keeping the handler is the half-measure the previous item on this branch paid for
    // twice, one layer up — so the fetch, the toast, the status line and the `showResult` call are
    // all on the lazy side, and the panel holds two `await import`s and nothing else.
    expect(qa).toMatch(/await import\("\.\/ruleCheckView"\)/);
    expect(qa, "a static import puts this module back in the shell")
      .not.toMatch(/^import .*from "\.\/ruleCheckView"/m);
    expect(qa, "the fetch belongs on the lazy side").not.toMatch(/api\.rulesRun\(/);
    expect(qa, "...and so does the result call for it").not.toContain('showResult("Rule library check"');
  });

  it("MOVED the rendering rather than copying it", () => {
    // `qaSection.ts` is on an exact line pin in `services/api/test_file_sizes.py`, and a copy is
    // not a move: two renderers for one result means a change lands in the one nobody is looking
    // at. The old body's distinctive lines must be gone from the panel.
    expect(qa).not.toContain("rules failing · ");
    expect(qa).not.toContain('const sev: Record<string, string> = { high: "🔴"');
    expect(view).toMatch(/renderRuleCheck\(r, body, isolate\)/);
  });
});
