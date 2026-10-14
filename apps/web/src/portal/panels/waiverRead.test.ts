/** WAIVER-FLAT — the lien card's two identical rows, and the COI horizon it asserted.
 *
 *  `MEASURED` is a response read back from a live server: four vendors posted through the real
 *  module workflows (`approve` → `pay` on `sub_invoice`, `receive` on `lien_waiver`) so the
 *  `conditional_only` and `no_waiver` states sit side by side, which no fixture in this repository
 *  had before — `services/api/test_payapp.py` asserted the first with no instance of the second
 *  beside it.
 */
import { describe, expect, it } from "vitest";

import type { CoiExpiry, LienExposure } from "../../api/counterpartyRisk";
import {
  SECURITY, TONE_CSS, coiHorizonLine, coiRows, exposureHeadline, exposureInstruction,
  exposureSplit, securityRows, settledNote, splitBasisNote,
} from "./waiverRead";

/** Plain and deterministic — the panel passes its own `money` in, so this only has to be legible. */
const money = (n: number) => `$${n.toLocaleString("en-US")}`;

const MEASURED: LienExposure = {
  vendor_count: 4,
  total_lien_exposure: 400000,
  vendors_at_risk: ["B", "C"],
  message: "2 vendor(s) paid without an unconditional lien waiver on file — collect waivers to "
    + "close the exposure.",
  vendors: [
    { vendor: "B", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 0,
      waived_conditional: 200000, exposure: 200000, status: "conditional_only",
      paid_invoices: 1, waivers: 1 },
    { vendor: "C", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 0,
      waived_conditional: 0, exposure: 200000, status: "no_waiver",
      paid_invoices: 1, waivers: 0 },
    { vendor: "A", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 200000,
      waived_conditional: 0, exposure: 0, status: "clear", paid_invoices: 1, waivers: 1 },
    { vendor: "D", billed: 500000, paid: 0, retainage: 0, waived_unconditional: 0,
      waived_conditional: 0, exposure: 0, status: "clear", paid_invoices: 0, waivers: 0 },
  ],
};

const NOTHING_OWED: LienExposure = {
  vendor_count: 2,
  total_lien_exposure: 0,
  vendors_at_risk: [],
  message: null,
  vendors: MEASURED.vendors.filter((v) => v.exposure === 0),
};

const EMPTY: LienExposure = {
  vendor_count: 0, total_lien_exposure: 0, vendors_at_risk: [], message: null, vendors: [],
};

/** The four cells the card rendered, in the order it rendered them. */
const shippedRow = (vendor: string) => {
  const v = MEASURED.vendors.find((x) => x.vendor === vendor)!;
  return [v.vendor, money(v.paid), money(v.waived_unconditional), money(v.exposure)];
};

describe("WAIVER-FLAT · the shipped row, as a reminder of what is being replaced", () => {
  it("rendered a $200,000 conditional release and a $200,000 naked exposure identically", () => {
    // The vendor name is the only cell that differs. Both rows were coloured --status-crit.
    expect(shippedRow("B").slice(1)).toEqual(shippedRow("C").slice(1));
    expect(shippedRow("B").slice(1)).toEqual(["$200,000", "$0", "$200,000"]);
    // ...and the field that distinguishes them was on the client type all along.
    expect(MEASURED.vendors[0]!.status).toBe("conditional_only");
    expect(MEASURED.vendors[1]!.status).toBe("no_waiver");
    expect(MEASURED.vendors[0]!.waived_conditional).toBe(200000);
    expect(MEASURED.vendors[1]!.waived_conditional).toBe(0);
  });
});

describe("WAIVER-FLAT · exposureSplit", () => {
  it("splits the total into conditionally covered and genuinely unreleased", () => {
    expect(exposureSplit(MEASURED)).toEqual({ covered: 200000, unsecured: 200000 });
  });

  it("counts a PARTIAL conditional waiver, which the per-vendor verdict does not", () => {
    // The verdict needs the conditional waivers to cover the WHOLE balance, so this vendor reads
    // `no_waiver` — correct as a verdict, and $50,000 of the exposure really is covered.
    const partial: LienExposure = {
      ...MEASURED, vendor_count: 1, total_lien_exposure: 200000, vendors_at_risk: ["P"],
      vendors: [{ vendor: "P", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 0,
                  waived_conditional: 50000, exposure: 200000, status: "no_waiver",
                  paid_invoices: 1, waivers: 1 }],
    };
    expect(exposureSplit(partial)).toEqual({ covered: 50000, unsecured: 150000 });
  });

  it("never counts more cover than there is exposure", () => {
    const over: LienExposure = {
      ...MEASURED, vendor_count: 1, total_lien_exposure: 1000, vendors_at_risk: ["Q"],
      vendors: [{ vendor: "Q", billed: 5000, paid: 1000, retainage: 0, waived_unconditional: 0,
                  waived_conditional: 5000, exposure: 1000, status: "conditional_only",
                  paid_invoices: 1, waivers: 1 }],
    };
    expect(exposureSplit(over)).toEqual({ covered: 1000, unsecured: 0 });
  });
});

describe("WAIVER-FLAT · exposureHeadline", () => {
  it("names the split and the population the exposure is spread over", () => {
    const h = exposureHeadline(MEASURED, money);
    expect(h.text).toBe("$400,000 exposed across 2 of 4 vendor(s) — $200,000 with no release on "
      + "file and $200,000 released only CONDITIONALLY.");
    expect(h.tone).toBe("crit");
  });

  it("is 'warn' rather than 'crit' when every exposed dollar has a conditional release", () => {
    const covered: LienExposure = {
      ...MEASURED, vendor_count: 3, total_lien_exposure: 200000, vendors_at_risk: ["B"],
      vendors: MEASURED.vendors.filter((v) => v.vendor !== "C"),
    };
    const h = exposureHeadline(covered, money);
    expect(h.tone).toBe("warn");
    expect(h.text).toContain("$0 with no release on file");
  });

  it("says so plainly when nothing is released at all", () => {
    const naked: LienExposure = {
      ...MEASURED, vendor_count: 3, total_lien_exposure: 200000, vendors_at_risk: ["C"],
      vendors: MEASURED.vendors.filter((v) => v.vendor !== "B"),
    };
    const h = exposureHeadline(naked, money);
    expect(h.text).toBe("$200,000 exposed across 1 of 3 vendor(s), none of it released by any "
      + "waiver.");
    expect(h.tone).toBe("crit");
  });

  it("distinguishes 'everything is released' from 'nothing is registered'", () => {
    const ok = exposureHeadline(NOTHING_OWED, money);
    expect(ok.tone).toBe("good");
    expect(ok.text).toContain("No lien exposure across 2 vendor(s)");
    const none = exposureHeadline(EMPTY, money);
    expect(none.tone).toBe("");
    expect(none.text).toBe("No vendor invoices or lien waivers registered yet.");
    expect(ok.text).not.toBe(none.text);
  });
});

describe("WAIVER-FLAT · the denominator's provenance", () => {
  it("takes the population from the ROLLUP and the numerator from the rows", () => {
    // Equal in every response the route has ever served — `payapp.reconcile` emits one row per
    // vendor and `vendor_count` is `len(rows)`, asserted in `services/api/test_payapp.py`. They
    // are read from their own sources anyway: TRUNC-COUNTED is three screens that printed the
    // length of a page as a total, and a denominator taken from the page is that defect waiting.
    expect(MEASURED.vendor_count).toBe(MEASURED.vendors.length);
    const paged: LienExposure = { ...MEASURED, vendors: MEASURED.vendors.slice(0, 2) };
    expect(exposureHeadline(paged, money).text).toContain("across 2 of 4 vendor(s)");
  });
});

describe("WAIVER-FLAT · splitBasisNote", () => {
  it("is silent while the verdict and the split cannot disagree", () => {
    expect(splitBasisNote(MEASURED)).toBeNull();
  });

  it("explains the disagreement when a NO WAIVER vendor is partly covered", () => {
    const partial: LienExposure = {
      ...MEASURED, vendor_count: 1, total_lien_exposure: 200000, vendors_at_risk: ["P"],
      vendors: [{ vendor: "P", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 0,
                  waived_conditional: 50000, exposure: 200000, status: "no_waiver",
                  paid_invoices: 1, waivers: 1 }],
    };
    const n = splitBasisNote(partial)!;
    expect(n).toContain("1 vendor(s) read NO WAIVER and still have part of the exposure");
    expect(n).toContain("(P)");
    expect(n).toContain("WHOLE balance");
  });
});

describe("WAIVER-FLAT · securityRows", () => {
  it("adds the conditional column, so the two rows stop being the same row", () => {
    const rows = securityRows(MEASURED);
    const b = rows.find((x) => x.vendor === "B")!;
    const c = rows.find((x) => x.vendor === "C")!;
    expect(b.conditional).toBe(200000);
    expect(c.conditional).toBe(0);
    expect(b.security).toBe("conditional only");
    expect(c.security).toBe("NO WAIVER");
    expect(b.tone).toBe("warn");
    expect(c.tone).toBe("crit");
    // the four cells the card used to show are still identical — the fix is the two it did not
    expect([b.paid, b.unconditional, b.exposure]).toEqual([c.paid, c.unconditional, c.exposure]);
  });

  it("orders worst security first, then by money", () => {
    expect(securityRows(MEASURED).map((x) => x.vendor)).toEqual(["C", "B"]);
  });

  it("keeps the vendors with no exposure out of the table, as before", () => {
    expect(securityRows(MEASURED)).toHaveLength(2);
    expect(securityRows(NOTHING_OWED)).toEqual([]);
  });

  it("does not mutate the response's vendor order", () => {
    const before = MEASURED.vendors.map((v) => v.vendor);
    securityRows(MEASURED);
    expect(MEASURED.vendors.map((v) => v.vendor)).toEqual(before);
  });
});

describe("WAIVER-FLAT · a status this build has never heard of", () => {
  it("renders it in the worst tone rather than crashing the card", () => {
    // Narrowing `status` to a union is a claim about a program on the other side of the wire. If
    // the engine grows a fourth state, `SECURITY[v.status]` is `undefined` and TypeScript does not
    // believe it can be — so reading `.label` off it would take down the whole lien card over a
    // missing column. The lookup has a runtime fallback, and this asserts it.
    const future: LienExposure = {
      ...MEASURED, vendor_count: 1, total_lien_exposure: 1000, vendors_at_risk: ["Z"],
      vendors: [{ vendor: "Z", billed: 1000, paid: 1000, retainage: 0, waived_unconditional: 0,
                  waived_conditional: 0, exposure: 1000,
                  status: "escrowed" as LienExposure["vendors"][number]["status"],
                  paid_invoices: 1, waivers: 0 }],
    };
    const rows = securityRows(future);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.security).toBe("escrowed");
    expect(rows[0]!.tone).toBe("crit");
  });

  it("sorts an unknown state WITH the unreleased ones, not off the end of the table", () => {
    const mixed: LienExposure = {
      ...MEASURED, vendor_count: 3, total_lien_exposure: 600000,
      vendors: [
        ...MEASURED.vendors.filter((v) => v.exposure > 0),
        { vendor: "Z", billed: 200000, paid: 200000, retainage: 0, waived_unconditional: 0,
          waived_conditional: 0, exposure: 200000,
          status: "escrowed" as LienExposure["vendors"][number]["status"],
          paid_invoices: 1, waivers: 0 },
      ],
    };
    expect(securityRows(mixed).map((x) => x.vendor)).toEqual(["Z", "C", "B"]);
  });
});

describe("WAIVER-FLAT · settledNote", () => {
  it("separates 'released' from 'not yet paid' — the card filtered both out identically", () => {
    expect(settledNote(MEASURED)).toBe("2 vendor(s) carry no exposure: 1 released by an "
      + "unconditional waiver · 1 not yet paid, so nothing to release.");
  });

  it("is silent when every vendor carries exposure", () => {
    expect(settledNote({ ...MEASURED,
      vendors: MEASURED.vendors.filter((v) => v.exposure > 0) })).toBeNull();
    expect(settledNote(EMPTY)).toBeNull();
  });
});

describe("WAIVER-FLAT · exposureInstruction", () => {
  it("renders the engine's own instruction verbatim", () => {
    expect(exposureInstruction(MEASURED)).toBe("2 vendor(s) paid without an unconditional lien "
      + "waiver on file — collect waivers to close the exposure.");
  });

  it("is silent when the engine sends none, and on an explicit null", () => {
    expect(exposureInstruction(NOTHING_OWED)).toBeNull();
    expect(exposureInstruction({ ...MEASURED, message: undefined })).toBeNull();
  });
});

const COI: CoiExpiry = {
  expired_count: 1,
  expiring_count: 1,
  soon_days: 30,
  expired: [{ vendor: "Ace Mechanical", coverage_type: "General Liability", carrier: "Travelers",
              ref: "COI-004", expires: "2026-09-30", days: -14 }],
  expiring_soon: [{ vendor: "Best Electric", coverage_type: "Workers Comp", carrier: "Hartford",
                    ref: "COI-011", expires: "2026-11-01", days: 18 }],
};

describe("WAIVER-FLAT · coiHorizonLine", () => {
  it("reads the horizon the server used instead of restating the default", () => {
    expect(coiHorizonLine(COI)).toBe("1 expired · 1 expiring within 30 day(s)");
    // The card printed "≤30d" as literal text. Correct only because the one caller passes 30 —
    // a restatement of a parameter, not a reading of the answer.
    expect(coiHorizonLine({ ...COI, soon_days: 90 }))
      .toBe("1 expired · 1 expiring within 90 day(s)");
  });
});

describe("WAIVER-FLAT · coiRows", () => {
  it("shows an expired certificate as an age, not a negative countdown", () => {
    const rows = coiRows(COI);
    expect(rows[0]!.kind).toBe("EXPIRED");
    expect(rows[0]!.age).toBe("14d ago");
    expect(rows[0]!.tone).toBe("crit");
    expect(rows[1]!.age).toBe("in 18d");
    expect(rows[1]!.tone).toBe("warn");
  });

  it("carries the carrier, which was sent and undeclared and is who you telephone", () => {
    expect(coiRows(COI).map((x) => x.carrier)).toEqual(["Travelers", "Hartford"]);
  });

  it("names a missing vendor rather than rendering a blank cell", () => {
    expect(coiRows({ ...COI, expired: [{ expires: "2026-01-01", days: -5 }], expiring_soon: [] })[0]!)
      .toMatchObject({ vendor: "(no vendor)", coverage: "—", carrier: "—" });
  });
});

describe("WAIVER-FLAT · SECURITY and TONE_CSS", () => {
  it("covers exactly the engine's three states", () => {
    expect(Object.keys(SECURITY).sort()).toEqual(["clear", "conditional_only", "no_waiver"]);
    expect(SECURITY.conditional_only.meaning).toContain("once the payment clears");
    expect(SECURITY.no_waiver.meaning).toContain("no release of any kind");
  });

  it("is a literal tone map — a runtime-built custom property resolves to nothing", () => {
    expect(TONE_CSS.warn).toBe("var(--status-warn)");
    expect(TONE_CSS[""]).toBe("");
  });
});
