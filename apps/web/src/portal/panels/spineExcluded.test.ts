import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import type { SpineTraceability } from "../../api/types";
import { renderSpine } from "./operations";

/**
 * SCREEN-VS-REPORT — the Discipline Spine's coverage bars are taken over the ENFORCED spec
 * population, and the card never said so.
 *
 * `spine.traceability` returns `spec_count` (every section on the job) beside `coverage.specs` (the
 * sections the percentages are computed over) and names the difference in `withdrawn_excluded`. Its
 * own comment says why both travel: *"so the two numbers cannot look like a contradiction"*. This
 * card rendered `coverage.specs` alone, so a job with a void section showed a spec count that
 * silently disagreed with the spec register's, and nothing on the page accounted for the gap.
 *
 * The submittal-log card in `reportCenter.ts` has always rendered exactly this caveat, from an
 * engine that states the same invariant in the same words. *The two screens were written to the
 * same contract and only one of them kept it.*
 *
 * Both fields are `SCREEN-VS-REPORT` candidates from the type-aware DEAD-FIELD derivation, and they
 * are the only two of the fifty-two whose own declaring doc comment states the invariant they are
 * part of — which is what separated them from the forty-odd fields that are merely not displayed.
 */

const SPINE = (over: Partial<SpineTraceability> = {}): SpineTraceability => ({
  disciplines: [],
  coverage: { specs: 18, bid_packages: 4, cost_codes: 4, sheets: 30,
    specs_packaged_pct: 72.2, packages_costed_pct: 100, sheets_specced_pct: 90,
    spec_to_budget_pct: 61.1 },
  spec_count: 21,
  withdrawn_excluded: [
    { ref: "SPEC-007", section: "03 30 00", title: "Cast-in-place concrete" },
    { ref: "SPEC-011", section: "07 21 00", title: "Thermal insulation" },
    { ref: "SPEC-019", section: "09 91 00", title: "Painting" },
  ],
  // `counts` joined the response in TRUNC-COUNTED: the three lists are 100-row PAGES and the card
  // used to print the sum of their lengths as the broken-link total, beside percentages computed
  // over the full population. A fixture without it now blanks the card rather than showing a wrong
  // number, which is the intended direction — server and client ship from one build, so a response
  // missing this field is a bug, not a deployment skew to paper over.
  gaps: { specs_without_bid_package: [], bid_packages_without_cost_code: [], sheets_without_spec: [],
    counts: { specs_without_bid_package: 0, bid_packages_without_cost_code: 0,
      sheets_without_spec: 0, total: 0 } },
  chain: [],
  note: "",
  ...over,
} as SpineTraceability);

function harness(t: SpineTraceability) {
  const root = document.createElement("div");
  const ctx: PanelContext = {
    root,
    host: {
      projectId: () => "p1",
      api: {
        spineTraceability: vi.fn(async () => t),
        // rejected on purpose: the model index is optional here and its own `.catch` swallows it,
        // so a test that stubbed it would be asserting over a path this card does not require.
        elementsByDiscipline: vi.fn(async () => { throw new Error("no property index"); }),
      },
    } as unknown as PanelContext["host"],
    mods: [],
    activeKey: "__spine__",
    bar: (title: string) => { const b = document.createElement("div"); b.textContent = title; return b; },
    buildNav: () => undefined,
    renderHome: async () => undefined,
    openModule: async () => undefined,
    navigate: () => undefined,
    hasDest: () => true,
  };
  return { ctx, root };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

async function run(t: SpineTraceability) {
  const { ctx, root } = harness(t);
  await renderSpine(ctx);
  await flush(); await flush();
  return root;
}

describe("SCREEN-VS-REPORT: the Discipline Spine's excluded sections", () => {
  it("THE DEFECT: the enforced population was the only number on the card", async () => {
    const root = await run(SPINE());
    // The bars still say 18 — they are computed over the enforced set and that is correct.
    expect(root.textContent, "the bar caption is not the thing under test and must still be there")
      .toContain("18 specs");
    // …and the card now also says what 18 is a subset OF, which is what was missing.
    expect(root.textContent).toContain("21 spec sections on the job");
    expect(root.textContent).toContain("3 withdrawn (excluded)");
    expect(root.textContent, "the caveat must say which population the bars are taken over, or it "
      + "is two numbers on a page rather than a reconciliation").toContain("taken over 18");
    // TWO of the four bars, not all four. `sheets_specced_pct` divides by `len(drawings)` and
    // `packages_costed_pct` by `len(packages)`; only `specs_packaged_pct` and `spec_to_budget_pct`
    // use `len(specs)`. The first draft of the caveat said "every bar above", which review caught —
    // *a caveat that overstates its own reach is this item's own defect, in the sentence written to
    // fix it.* This assertion is what stops it being rewritten back.
    expect(root.textContent, "the caveat may not claim a reach it does not have")
      .toContain("the two spec bars");
    expect(root.textContent).not.toContain("every bar above");
  });

  it("names the withdrawn sections where a KEYBOARD reader can reach them", async () => {
    const root = await run(SPINE());
    const b = [...root.querySelectorAll("b")].find((e) => e.textContent?.includes("withdrawn"));
    expect(b, "the withdrawn count is not rendered as its own element").toBeTruthy();

    // The first draft put the section names in a `title` on this non-focusable `<b>` — reachable by
    // pointer and by nothing else, so the actionable half of the caveat was invisible to anyone
    // navigating by keyboard. Review caught it. *A disclosure only some readers can open is not a
    // disclosure.* The names live in a `<details>` now, which is focusable and toggles on Enter.
    expect(b!.getAttribute("title"),
      "the names are back in a pointer-only tooltip").toBeNull();

    const det = root.querySelector("details");
    expect(det, "no disclosure — the section names are unreachable again").toBeTruthy();
    expect(det!.querySelector("summary"),
      "a `details` with no `summary` has nothing to focus").toBeTruthy();
    const items = [...det!.querySelectorAll("li")].map((li) => li.textContent ?? "");
    expect(items).toHaveLength(3);
    expect(items[0]).toBe("03 30 00 — Cast-in-place concrete");
    expect(items[2]).toBe("09 91 00 — Painting");
  });

  it("falls back to the ref when a withdrawn section carries no section number", async () => {
    // `spine.py` reads `section_number` out of the record's data blob, which an early-draft section
    // need not have. Without this the hover would read " Painting" with a leading space and no
    // identity at all — the row exists to be findable.
    const root = await run(SPINE({ withdrawn_excluded: [{ ref: "SPEC-044", section: "", title: "" }] }));
    const items = [...root.querySelectorAll("details li")].map((li) => li.textContent ?? "");
    expect(items).toEqual(["SPEC-044"]);
  });

  it("says nothing extra when nothing was withdrawn — a caveat that is always on is decoration",
    async () => {
      const root = await run(SPINE({ spec_count: 18, withdrawn_excluded: [] }));
      expect(root.textContent).toContain("18 spec sections on the job");
      expect(root.textContent).not.toContain("withdrawn");
      expect(root.textContent).not.toContain("taken over");
      expect(root.querySelector("details"),
        "an empty disclosure is worse than none — it promises a list and opens on nothing").toBeNull();
    });

  it("reads ONE spec section as singular", async () => {
    const root = await run(SPINE({ spec_count: 1, withdrawn_excluded: [] }));
    expect(root.textContent).toContain("1 spec section on the job");
    expect(root.textContent).not.toContain("1 spec sections");
  });

  it("survives a server that sends no withdrawn list at all", async () => {
    // The field is required by the interface and the engine always sends it; this is the
    // older-server case, where the honest degradation is the total alone rather than a crash.
    const root = await run(SPINE({ withdrawn_excluded: undefined as unknown as [] }));
    expect(root.textContent).toContain("21 spec sections on the job");
    expect(root.textContent).not.toContain("withdrawn");
  });
});
