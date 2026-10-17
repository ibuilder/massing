import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  baselineCaveat, feasibilityScope, schemeStateMark, verificationCoverageCard, type RankedScheme,
} from "./reportCenter";

/**
 * RESPONSE-UNDECLARED — `/verification/coverage` returns thirteen keys and `api/model.ts` declared
 * eight, so the five evidence fields could not be read by anything.
 *
 * A field the client never declares is worse than one it declares and ignores: no type error, no
 * lint, and no unread-field audit can see it, because every such audit starts from the client's
 * interfaces. This one was found by reading the route beside the panel, not by any derivation.
 *
 * The card showed "N verified · M deviations" with no indication of how much was photographed, while
 * the route computed `deviations_without_photo` under the comment *"the handover number. A deviation
 * with no photo is an assertion with nothing behind it."*
 */
const base = {
  total_elements: 400, tracked: 300, verified: 210, installed: 250, deviations: 12,
  verified_pct: 70.0, installed_pct: 83.3, with_photo: 180, evidence_pct: 60.0,
  deviations_without_photo: 9,
};

describe("verificationCoverageCard — the evidence half is on screen", () => {
  it("states how much of the tracked work is photographed, and against which denominator", () => {
    const html = verificationCoverageCard(base);
    expect(html).toContain("60% photographed (180 of 300 tracked)");
    // "of 300 tracked", not "of 400" — the route divides by tracked on purpose, and a percentage
    // whose denominator is left to the reader is the ambiguity this card is fixing.
    expect(html).not.toContain("of 400 tracked");
  });

  it("names unphotographed deviations — the handover number", () => {
    const html = verificationCoverageCard(base);
    expect(html).toContain("9 of 12 deviations have no photo");
    expect(html).toContain("not evidenced for handover");
  });

  it("says nothing about unphotographed deviations when every one is evidenced", () => {
    // The warning must be ABSENT, not zeroed: "0 of 12 deviations have no photo" is noise on a
    // card whose whole job is to surface the exception.
    const html = verificationCoverageCard({ ...base, deviations_without_photo: 0 });
    expect(html).not.toContain("no photo");
    expect(html).not.toContain("handover");
    expect(html).toContain("60% photographed");        // the coverage line still shows
  });

  it("agrees in number with a single unphotographed deviation", () => {
    const html = verificationCoverageCard({ ...base, deviations: 1, deviations_without_photo: 1 });
    expect(html).toContain("1 of 1 deviation has no photo");
  });

  it("still shows the headline the card has always shown", () => {
    const html = verificationCoverageCard(base);
    expect(html).toContain("70% verified · 83.3% installed");
    expect(html).toContain("210 verified · 250 installed · 12 deviations · of 400 elements");
  });
});

describe("TOTAL-EXCLUDED — feasibilityScope: what the scheme ranking is OVER", () => {
  it("THE WORST CASE: every scheme superseded told the user to add records they already have", () => {
    // `feasibility.compare` drops SUPERSEDED zoning records from the ranking and names them in
    // `superseded_excluded`. Neither field was declared in the client, so `count` reached 0 by two
    // completely different routes and the panel said "Add two or more Zoning & Site records (one
    // per scheme) to compare" for both. Advice that is actionable AND wrong is the expensive form
    // of the empty-versus-absent confusion.
    const s = feasibilityScope(0, 3);
    expect(s.empty).toContain("No LIVE scheme");
    expect(s.empty).toContain("3 recorded scheme(s)");
    expect(s.empty).toContain("SUPERSEDED");
    expect(s.empty, "it must not tell them to create what they already have")
      .not.toContain("Add two or more");
  });

  it("keeps the ORIGINAL advice when there genuinely is nothing recorded", () => {
    // Without this the assertion above is satisfied by replacing one wrong message with another:
    // a project with no zoning records does need to add some, and saying "superseded" there would
    // be the same defect pointing the other way.
    const s = feasibilityScope(0, 0);
    expect(s.empty).toContain("Add two or more");
    expect(s.empty).not.toContain("SUPERSEDED");
    expect(s.caveat).toBeNull();
  });

  it("states what the count is OVER when live schemes and superseded ones coexist", () => {
    const s = feasibilityScope(4, 2);
    expect(s.empty).toBeNull();
    expect(s.caveat).toContain("2 superseded scheme(s)");
    expect(s.caveat).toContain("not everything on record");
  });

  it("is SILENT when nothing was excluded — no permanent caveat", () => {
    const s = feasibilityScope(4, 0);
    expect(s.empty).toBeNull();
    expect(s.caveat).toBeNull();
  });

  it("normalises junk counts rather than printing them", () => {
    for (const bad of [-2, Number.NaN, undefined as unknown as number]) {
      expect(feasibilityScope(4, bad).caveat, String(bad)).toBeNull();
      expect(feasibilityScope(bad, 0).empty, String(bad)).toContain("Add two or more");
    }
  });
});

describe("the feasibility panel is WIRED to the excluded list", () => {
  const HERE = dirname(fileURLToPath(import.meta.url));
  const SRC = readFileSync(resolve(HERE, "reportCenter.ts"), "utf-8");

  it("derives the scope from superseded_excluded rather than from count alone", () => {
    expect(SRC).toContain("feasibilityScope(c.count, (c.superseded_excluded ?? []).length)");
  });

  it("the empty message comes from the helper, not from a literal in the branch", () => {
    // The defect was a hard-coded "Add two or more…" in the `!c.count` branch, which could not
    // tell *nothing recorded* from *everything superseded*.
    expect(SRC).toContain("if (scope.empty)");
    expect(SRC).not.toContain('if (!c.count) { body.innerHTML = `<div class="meta">Add two or more');
  });

  it("and the client DECLARES both fields the engine returns", () => {
    const api = readFileSync(resolve(HERE, "api/entitlements.ts"), "utf-8");
    expect(api).toContain("superseded_excluded?:");
    expect(api).toContain("note?: string");
  });
});

/**
 * DRAFT-BASELINE — the deltas are measured against whichever scheme ranks first, and a DRAFT can
 * rank first. `MEASURED` is a response read back from a live server: two zoning schemes on one
 * 20,000 SF site, the FAR-8 scheme left in `draft` and the FAR-4 scheme approved.
 */
const MEASURED: RankedScheme[] = [
  { ref: "ZON-002", workflow_state: "draft", unit_yield: 136, allowed_gfa_sf: 144000,
    delta_units: 0, delta_gfa_sf: 0 },
  { ref: "ZON-001", workflow_state: "approved", unit_yield: 68, allowed_gfa_sf: 72000,
    delta_units: -68, delta_gfa_sf: -72000 },
];

describe("DRAFT-BASELINE · what the table showed before", () => {
  it("printed the approved scheme as a 68-unit shortfall with no state anywhere", () => {
    // The shipped columns, in order. No state, and `delta_gfa_sf` was computed and dropped.
    const shipped = MEASURED.map((s) => [s.ref, s.unit_yield, s.delta_units]);
    expect(shipped).toEqual([["ZON-002", 136, 0], ["ZON-001", 68, -68]]);
    expect(MEASURED[0]!.workflow_state).toBe("draft");
    expect(MEASURED[1]!.delta_gfa_sf).toBe(-72000);
  });
});

describe("DRAFT-BASELINE · baselineCaveat", () => {
  it("names the unapproved baseline and how many approved schemes it is measuring", () => {
    const c = baselineCaveat(MEASURED)!;
    expect(c).toContain("The baseline every delta is measured against — ZON-002 — is DRAFT");
    expect(c).toContain("1 approved scheme(s) below it are shown as a shortfall");
    // The engine ranks a draft ON PURPOSE. The caveat says so rather than implying a bug.
    expect(c).toContain("Ranking a draft is deliberate");
  });

  it("is silent when the top-ranked scheme is approved", () => {
    const approvedFirst: RankedScheme[] = [
      { ...MEASURED[1]!, delta_units: 0, delta_gfa_sf: 0 },
      { ...MEASURED[0]!, delta_units: 68, delta_gfa_sf: 72000 },
    ];
    expect(baselineCaveat(approvedFirst)).toBeNull();
  });

  it("says so plainly when NOTHING in the comparison is approved", () => {
    const allDraft = MEASURED.map((s) => ({ ...s, workflow_state: "draft" }));
    const c = baselineCaveat(allDraft)!;
    expect(c).toContain("No scheme in this comparison is approved.");
    expect(c).not.toContain("shortfall");
  });

  it("treats a missing state as unapproved rather than assuming the good case", () => {
    const c = baselineCaveat([{ ref: "ZON-009", unit_yield: 10 }])!;
    expect(c).toContain("is NO RECORDED STATE, not approved");
  });

  it("is silent on an empty comparison — there is no baseline to be about", () => {
    expect(baselineCaveat([])).toBeNull();
  });

  it("is case- and whitespace-insensitive about the state the server sends", () => {
    expect(baselineCaveat([{ ref: "Z", workflow_state: " Approved " }])).toBeNull();
  });
});

describe("DRAFT-BASELINE · schemeStateMark", () => {
  it("marks the pair that actually reaches a consumer", () => {
    expect(schemeStateMark("approved")).toBe("✅ approved");
    expect(schemeStateMark("draft")).toBe("✏️ DRAFT");
  });

  it("renders a dash for no state and passes an unknown one through", () => {
    // `superseded` never arrives here — `compare` drops those into `superseded_excluded` — but a
    // state this build has not heard of is shown as itself rather than silently as approved.
    expect(schemeStateMark(undefined)).toBe("—");
    expect(schemeStateMark("")).toBe("—");
    expect(schemeStateMark("withdrawn")).toBe("withdrawn");
  });
});
