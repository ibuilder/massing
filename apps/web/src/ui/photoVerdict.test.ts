/**
 * R22-PHOTO-CV — the display layer is where a hedged server answer becomes an unhedged UI claim.
 *
 * The backend goes to real trouble to state its own confidence: `change_score` carries a
 * `confidence` string saying it is screening-only, an undecodable photo is stored rather than
 * refused, and quality is reported separately from detection. All of that care is thrown away by one
 * template that renders "78% changed" in bold. So these tests assert the *framing*, not just the
 * numbers — that is the property that can regress silently while every value stays correct.
 */
import { describe, expect, it } from "vitest";

import { photoVerdict, photoVerdictSummary } from "./photoVerdict";

describe("photo upload verdict", () => {
  it("asks for a retake FIRST, because that is the only moment it is cheap", () => {
    const lines = photoVerdict({
      quality: { analysed: true, usable: false, reasons: ["out of focus or taken while moving"] },
      detected: { ran: true, summary: { people: 3, vehicles: 1, total: 4 } },
      change: { change_score: 0.9, near_identical: false },
    });
    expect(lines[0]!.tone).toBe("warn");
    expect(lines[0]!.actionable).toBe(true);
    expect(lines[0]!.text).toContain("Retake");
    // and the reason travels with it — "unusable" alone gives the person nothing to change
    expect(lines[0]!.text).toContain("out of focus");
  });

  it("says an unreadable photo was KEPT, so nobody reshoots something already stored", () => {
    // The HEIC case: analysed=false, usable=null. Telling someone only that it "could not be read"
    // implies rejection, and they will take the photo again for no reason.
    const lines = photoVerdict({
      quality: { analysed: false, usable: null, reasons: ["could not be decoded — the format may not be supported (iPhone HEIC cannot be read server-side); the photo was kept"] },
    });
    expect(lines[0]!.tone).toBe("warn");
    expect(lines[0]!.text.toLowerCase()).toContain("kept");
  });

  it("NEVER renders a change score as a bare percentage", () => {
    // The load-bearing assertion in this file. The server calls this screening-only; a naked "62%"
    // reads as a measurement and would be believed.
    const lines = photoVerdict({
      quality: { analysed: true, usable: true },
      change: { change_score: 0.62, near_identical: false, confidence: "screening only" },
    });
    const change = lines.find((l) => l.text.includes("62"));
    expect(change, "a change line should exist").toBeDefined();
    expect(change!.text).toMatch(/worth a look|not a conclusion/i);
    // it must not be phrased as a settled fact
    expect(change!.text).not.toMatch(/^\s*62% changed\s*$/);
  });

  it("states the TRUSTWORTHY direction plainly — near-identical is a strong claim", () => {
    const lines = photoVerdict({
      quality: { analysed: true, usable: true },
      change: { change_score: 0.01, near_identical: true },
    });
    const l = lines.find((x) => x.text.includes("Same as"));
    expect(l, "near_identical should be reported").toBeDefined();
    expect(l!.text).toContain("nothing has changed");
    // and it must NOT also emit the hedged percentage line — that would contradict itself
    expect(lines.some((x) => x.text.includes("%"))).toBe(false);
  });

  it("reports people and vehicles separately, and pluralises honestly", () => {
    const one = photoVerdict({ detected: { ran: true, summary: { people: 1, vehicles: 1, total: 2 } } });
    expect(one[0]!.text).toContain("1 person");
    expect(one[0]!.text).toContain("1 vehicle");
    const many = photoVerdict({ detected: { ran: true, summary: { people: 5, vehicles: 2, total: 7 } } });
    expect(many[0]!.text).toContain("5 people");
    expect(many[0]!.text).toContain("2 vehicles");
  });

  it("says NOTHING about detection when no model ran — silence, not a zero", () => {
    // The default deployment. Reporting "0 people" would assert the photo contains no one, which the
    // server never claimed: it said it could not look. A zero here is a lie of the cheapest kind.
    const lines = photoVerdict({
      quality: { analysed: true, usable: true },
      detected: { available: false, ran: false, reasons: ["AEC_PHOTO_MODEL is not set"], summary: { people: 0, vehicles: 0, total: 0 } },
    });
    expect(lines.some((l) => /person|people|vehicle|In frame/i.test(l.text))).toBe(false);
  });

  it("says nothing about detection when the model ran and found nobody", () => {
    // Distinct from the case above and deliberately treated the same way in the UI: an empty scene
    // needs no line. The DIFFERENCE is recoverable from the raw response for anyone who needs it.
    const lines = photoVerdict({
      quality: { analysed: true, usable: true },
      detected: { available: true, ran: true, summary: { people: 0, vehicles: 0, total: 0 } },
    });
    expect(lines.some((l) => /In frame/i.test(l.text))).toBe(false);
  });

  it("survives a server that returns none of the new fields", () => {
    // Older API, or a partial response. It must not throw — this runs in an upload handler.
    expect(() => photoVerdict({})).not.toThrow();
    expect(photoVerdict({ has_photo: true })).toEqual([]);
    expect(photoVerdictSummary({})).toBe("");
  });

  it("names the element a duplicate shot is already filed against", () => {
    const lines = photoVerdict({
      quality: { analysed: true, usable: true },
      duplicate: { guid: "1Ab$cDeFgHiJkLmNoPqRsT", compared_against: 12 },
    });
    const dup = lines.find((l) => /Already filed/.test(l.text));
    expect(dup?.text).toContain("1Ab$cDeFgHiJkLmNoPqRsT");
    expect(dup?.actionable).toBe(true);
    expect(dup?.tone).toBe("warn");
  });

  it("says NOTHING when no duplicate was found, however many photos were compared", () => {
    // The whole point. `compared_against` counts only photos fingerprinted since v0.3.1115 — the
    // column is not backfilled — so "no duplicate" is a claim this response frequently cannot
    // support. Saying nothing makes no claim; a reassuring "no duplicates" line would make one that
    // is false on every project with older photos.
    for (const compared_against of [0, 300]) {
      const lines = photoVerdict({
        quality: { analysed: true, usable: true },
        duplicate: { guid: null, compared_against },
      });
      expect(lines.some((l) => /duplicate|Already filed/i.test(l.text))).toBe(false);
    }
  });

  it("a duplicate outranks the idle statistics but not a retake prompt", () => {
    // Order is this file's design: what the person can still act on, while they can still act on it.
    // A retake is the one thing that stops being possible the moment they walk away.
    const lines = photoVerdict({
      quality: { analysed: true, usable: false, reasons: ["out of focus"] },
      duplicate: { guid: "2Bc$dEfGhIjKlMnOpQrStU", compared_against: 4 },
      change: { change_score: 0.6 },
      detected: { available: true, ran: true, summary: { people: 2, vehicles: 0, total: 2 } },
    });
    const at = (re: RegExp) => lines.findIndex((l) => re.test(l.text));
    expect(at(/Retake/)).toBe(0);
    expect(at(/Already filed/)).toBe(1);
    expect(at(/Already filed/)).toBeLessThan(at(/In frame/));
    expect(at(/Already filed/)).toBeLessThan(at(/Differs from/));
  });

  it("the summary line is the most actionable one, not merely the first field present", () => {
    const s = photoVerdictSummary({
      quality: { analysed: true, usable: false, reasons: ["blown out — shot into a light source"] },
      change: { change_score: 0.05, near_identical: true },
    });
    expect(s).toContain("Retake");
  });
});
