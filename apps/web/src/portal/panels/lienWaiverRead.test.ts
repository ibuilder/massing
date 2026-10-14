import { describe, expect, it } from "vitest";

import {
  PLACEHOLDER_FIELDS, readiness, unfilled, WAIVER_CSS, WAIVER_KINDS, waiverFields,
  type LienWaiver,
} from "./lienWaiverRead";

/** The body the server actually returns for a GET with no parameters — measured, not invented. */
const BARE_BODY =
  "Upon receipt by the undersigned of a check from [Customer] in the sum of $0.00 payable to "
  + "[Claimant], and when the check has been properly endorsed and has been paid by the bank on "
  + "which it is drawn, this document becomes effective to release and the undersigned releases any "
  + "progress payment mechanics lien, stop payment notice, or payment bond rights the undersigned "
  + "has on the job of [Owner] located at Lien Probe to the following extent: this release covers a "
  + "progress payment for all labor, services, equipment, or material furnished through [date].";

const FILLED_BODY = BARE_BODY
  .replaceAll("[Customer]", "Acme Development LLC")
  .replaceAll("[Owner]", "Acme Development LLC")
  .replaceAll("[Claimant]", "Northside Mechanical Inc")
  .replaceAll("[date]", "2026-09-30");

const W = (over: Partial<LienWaiver> = {}): LienWaiver => ({
  kind: "conditional_progress", title: "Conditional Waiver and Release on Progress Payment",
  conditional: true, final: false, amount: 412_000, body: FILLED_BODY,
  notice: "NOTICE: THIS DOCUMENT WAIVES RIGHTS UNCONDITIONALLY…",
  project_name: "Lien Probe", claimant: "Northside Mechanical Inc",
  customer: "Acme Development LLC", through_date: "2026-09-30", application_no: 7,
  exceptions: "Disputed claims and items not included above are excepted from this release.",
  signature_block: { claimant_title: "Claimant's Title", date: "Date of Signature" },
  ...over,
});

describe("LIEN-PLACEHOLDER", () => {
  it("THE SHIPPED STATE: a bare request leaves four placeholders in a signable document", () => {
    const bare = W({ body: BARE_BODY, claimant: "", customer: "", through_date: "", amount: 0 });
    expect(unfilled(bare).map((g) => g.token))
      .toEqual(["[Claimant]", "[Customer]", "[date]"]);     // [Owner] shares `customer`
    const r = readiness(bare);
    expect(r.ready).toBe(false);
    expect(r.tone).toBe("warn");
    expect(r.text).toContain("NOT READY TO SIGN");
    expect(r.text).toContain("mechanics-lien rights");
  });

  it("deduplicates by FIELD, so one empty box is not two missing fields", () => {
    // `[Customer]` and `[Owner]` are both filled by one input. Reporting both sends a reader
    // looking for a second box that does not exist.
    const bare = W({ body: BARE_BODY, claimant: "x", through_date: "y" });
    const gaps = unfilled(bare);
    expect(gaps.map((g) => g.field)).toEqual([...new Set(gaps.map((g) => g.field))]);
  });

  it("scans the NOTICE as well as the body", () => {
    // The statutory notice is prescribed text and may name the claimant. Checking only the body
    // would clear a document that still carries a bracket.
    const r = readiness(W({ notice: "NOTICE to [Claimant]: this document waives rights." }));
    expect(r.ready).toBe(false);
    expect(r.text).toContain("[Claimant]");
  });

  it("is READY only when no bracket survives in the server's own text", () => {
    const r = readiness(W());
    expect(r.ready).toBe(true);
    expect(r.tone).toBe("ok");
    // and it is the SERVER's text that decides, not the client's inputs: a document whose wording
    // introduced a new placeholder must go back to not-ready even with every box filled.
    expect(readiness(W({ body: `${FILLED_BODY} Retention held through [date].` })).ready).toBe(false);
  });

  it("shows the through date on a PROGRESS release and omits it on a FINAL one", () => {
    // On a progress release the through date is the whole bound — it covers work furnished through
    // that date and nothing after. A final release covers everything, so the row would be a blank
    // nobody should try to fill.
    expect(waiverFields(W()).some((f) => f.label === "Covers work through")).toBe(true);
    expect(waiverFields(W({ final: true })).some((f) => f.label === "Covers work through")).toBe(false);
  });

  it("marks an unfilled party as NOT GIVEN rather than printing an empty cell", () => {
    const rows = waiverFields(W({ claimant: "", customer: "" }));
    expect(rows.find((f) => f.label === "Claimant")!.value).toBe("— not given —");
    expect(rows.find((f) => f.label === "Customer / owner")!.value).toBe("— not given —");
  });

  it("states conditional/final as words rather than leaving two booleans to a reader", () => {
    const rows = waiverFields(W({ conditional: false, final: true }));
    expect(rows.find((f) => f.label === "Payment")!.value).toBe("Unconditional");
    expect(rows.find((f) => f.label === "Stage")!.value).toBe("Final");
  });

  it("offers the four statutory kinds the engine accepts, and no others", () => {
    expect(WAIVER_KINDS.map((k) => k.value)).toEqual([
      "conditional_progress", "unconditional_progress", "conditional_final", "unconditional_final",
    ]);
  });

  it("every placeholder token names a field a user can actually fill", () => {
    // A token mapped to a field with no input is a refusal nobody can clear — the shape of the
    // permanently-unsatisfiable checklist row PERMIT-BLIND closed.
    const inputs = new Set(["claimant", "customer", "through date", "project name"]);
    for (const p of PLACEHOLDER_FIELDS) expect(inputs.has(p.field)).toBe(true);
  });

  it("maps every tone to a CSS variable", () => {
    for (const t of ["ok", "warn"] as const) expect(WAIVER_CSS[t]).toMatch(/^var\(--/);
  });
});
