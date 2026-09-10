import { describe, expect, it } from "vitest";

import { verificationCoverageCard } from "./reportCenter";

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
