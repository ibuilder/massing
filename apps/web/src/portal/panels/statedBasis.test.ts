/** BASIS-UNREAD — the envelope verdict's population and basis, and the cx punch count's.
 *
 *  `MIXED` is a measured response: six assemblies posted to a live server and
 *  `GET /projects/{pid}/envelope/audit` read back verbatim, including the engine's `note` and the
 *  one row that carries BOTH a requirement and an `issue` ("Lobby storefront" — a zone-4 window
 *  with no U-factor, so the engine knows what it needs and not what it has).
 *
 *  The two headline defects are asserted as the shipped strings, because each was produced by
 *  reading three of the four population keys and both read as good news:
 *  `4/4 assemblies compliant (100.0%)` over 40, and `no envelope assemblies registered` over 40.
 */
import { describe, expect, it } from "vitest";

import type { EnvelopeAudit, EnvelopeAssemblyCheck } from "../../api/model";
import {
  ASSEMBLY_PAGE, TONE_CSS, assemblyPageNote, assemblyRows, envelopeBasisNote,
  envelopeCoverageNote, envelopeHeadline, punchMentionNote,
} from "./statedBasis";

const NOTE = "Opaque assemblies vs IECC 2021 minimum R; fenestration vs maximum U, by climate "
  + "zone. Representative prescriptive values — a first-pass screen, not a stamped energy model.";

/** Measured. 6 registered, 4 evaluable, 2 of those compliant. */
const MIXED: EnvelopeAudit = {
  total: 6,
  checked: 4,
  compliant: 2,
  compliance_pct: 50.0,
  note: NOTE,
  results: [
    { name: "Exterior wall", element_type: "Wall", climate_zone: 4, r_value: 21.0, u_factor: null,
      compliant: true, required_min_r: 20, provided_r: 21.0, margin: 1.0 },
    { name: "Low roof", element_type: "Roof", climate_zone: 6, r_value: 25.0, u_factor: null,
      compliant: false, required_min_r: 30, provided_r: 25.0, margin: -5.0 },
    { name: "Curtain wall glazing", element_type: "Window", climate_zone: 5, r_value: null,
      u_factor: 0.3, compliant: true, required_max_u: 0.38, provided_u: 0.3, margin: 0.08 },
    { name: "Clerestory", element_type: "Skylight", climate_zone: 5, r_value: null, u_factor: 0.62,
      compliant: false, required_max_u: 0.5, provided_u: 0.62, margin: -0.12 },
    { name: "Party wall", element_type: "Wall", climate_zone: null, r_value: 19.0, u_factor: null,
      compliant: null, issue: "no valid climate zone (1–8)" },
    { name: "Lobby storefront", element_type: "Window", climate_zone: 4, r_value: null,
      u_factor: null, compliant: null, required_max_u: 0.38, provided_u: null,
      issue: "no U-factor or R-value given" },
  ],
};

/** Measured: 4 dimensioned walls, 30 with no climate zone, 6 with a zone and no thermal values. */
const THIN: EnvelopeAudit = {
  total: 40,
  checked: 4,
  compliant: 4,
  compliance_pct: 100.0,
  note: NOTE,
  results: [
    ...Array.from({ length: 4 }, (_, i): EnvelopeAssemblyCheck => ({
      name: `Good wall ${i}`, element_type: "Wall", climate_zone: 4, r_value: 21, u_factor: null,
      compliant: true, required_min_r: 20, provided_r: 21, margin: 1,
    })),
    ...Array.from({ length: 30 }, (_, i): EnvelopeAssemblyCheck => ({
      name: `Undimensioned ${i}`, element_type: "Wall", climate_zone: null,
      compliant: null, issue: "no valid climate zone (1–8)",
    })),
    ...Array.from({ length: 6 }, (_, i): EnvelopeAssemblyCheck => ({
      name: `No thermal ${i}`, element_type: "Roof", climate_zone: 5,
      compliant: null, required_min_r: 30, provided_r: null,
      issue: "no R-value or U-factor given",
    })),
  ],
};

/** Measured: 40 assemblies, none with a climate zone, so NOTHING is evaluable. */
const UNCHECKABLE: EnvelopeAudit = {
  total: 40,
  checked: 0,
  compliant: 0,
  compliance_pct: null,
  note: NOTE,
  results: Array.from({ length: 40 }, (_, i): EnvelopeAssemblyCheck => ({
    name: `W${i}`, element_type: "Wall", climate_zone: null,
    compliant: null, issue: "no valid climate zone (1–8)",
  })),
};

const EMPTY: EnvelopeAudit = {
  total: 0, checked: 0, compliant: 0, compliance_pct: null, note: NOTE, results: [],
};

/** The card as shipped: three of the four population keys, and `total` unread. */
const shipped = (a: EnvelopeAudit) =>
  a.checked ? `${a.compliant}/${a.checked} assemblies compliant (${a.compliance_pct}%)`
            : "no envelope assemblies registered";

describe("BASIS-UNREAD · the shipped headline, as a reminder of what is being replaced", () => {
  it("reported 100% over a tenth of the envelope", () => {
    expect(shipped(THIN)).toBe("4/4 assemblies compliant (100%)");
  });

  it("denied the register exists, over forty rows — the quieter defect and the worse one", () => {
    expect(shipped(UNCHECKABLE)).toBe("no envelope assemblies registered");
    // Indistinguishable from the genuinely empty case, which is the whole problem.
    expect(shipped(EMPTY)).toBe(shipped(UNCHECKABLE));
  });
});

describe("BASIS-UNREAD · envelopeHeadline", () => {
  it("names the population the percentage is over", () => {
    const h = envelopeHeadline(THIN);
    expect(h.text).toContain("4/4 compliant (100%)");
    expect(h.text).toContain("over 4 of 40 registered");
    expect(h.text).toContain("other 36 could not be checked");
    // 100% of what could be checked is still a coverage warning, never "good".
    expect(h.tone).toBe("warn");
  });

  it("distinguishes 'nothing evaluable' from 'nothing registered'", () => {
    const u = envelopeHeadline(UNCHECKABLE);
    const e = envelopeHeadline(EMPTY);
    expect(u.text).toContain("40 assembly(ies) registered and NONE could be checked");
    expect(u.tone).toBe("warn");
    expect(e.text).toBe("No envelope assemblies registered yet.");
    expect(e.tone).toBe("");
    expect(u.text).not.toBe(e.text);
  });

  it("a real IECC failure outranks a coverage gap", () => {
    const h = envelopeHeadline(MIXED);
    expect(h.text).toBe("2/4 compliant (50%), over 4 of 6 registered assembly(ies) — the other 2 "
      + "could not be checked.");
    expect(h.tone).toBe("crit");
  });

  it("is 'good' only when every registered assembly was checked and passed", () => {
    const all: EnvelopeAudit = { ...MIXED, total: 2, checked: 2, compliant: 2, compliance_pct: 100,
      results: MIXED.results.filter((r) => r.compliant === true) };
    const h = envelopeHeadline(all);
    expect(h.tone).toBe("good");
    expect(h.text).toContain("over all 2 registered");
  });
});

describe("BASIS-UNREAD · envelopeCoverageNote", () => {
  it("counts the unevaluable rows and groups them by the engine's own reason", () => {
    expect(envelopeCoverageNote(THIN)).toBe(
      "36 of 40 assembly(ies) carry no verdict and are outside every percentage above: "
      + "30 × no valid climate zone (1–8) · 6 × no R-value or U-factor given.");
  });

  it("orders the reasons by weight, biggest first", () => {
    const n = envelopeCoverageNote(MIXED)!;
    // One of each here, so the tie-break is alphabetical and therefore stable across runs.
    expect(n).toContain("1 × no U-factor or R-value given · 1 × no valid climate zone (1–8)");
    expect(n).toContain("2 of 6 assembly(ies)");
  });

  it("counts from the ROLLUP and declares when the reasons cover less than the count", () => {
    // `envelope.audit` returns every row today. If it ever paged them, a count taken from
    // `results.length` would be the page's size printed as the register's — TRUNC-COUNTED, one
    // layer down. The two derivations are separate and the shortfall is said out loud.
    const paged: EnvelopeAudit = { ...THIN, results: THIN.results.slice(0, 10) };
    const n = envelopeCoverageNote(paged)!;
    expect(n).toContain("36 of 40 assembly(ies) carry no verdict");
    expect(n).toContain("reasons cover the 6 returned in this response");
    // and it still reports the count when the response carries no rows at all to group.
    expect(envelopeCoverageNote({ ...THIN, results: [] }))
      .toBe("36 of 40 assembly(ies) carry no verdict and are outside every percentage above "
        + "(reasons cover the 0 returned in this response).");
  });

  it("is silent when every assembly got a verdict", () => {
    expect(envelopeCoverageNote({ ...MIXED, total: 4, checked: 4,
      results: MIXED.results.filter((r) => r.compliant != null) })).toBeNull();
    expect(envelopeCoverageNote(EMPTY)).toBeNull();
  });
});

describe("BASIS-UNREAD · envelopeBasisNote", () => {
  it("passes the engine's sentence through verbatim rather than paraphrasing it", () => {
    expect(envelopeBasisNote(MIXED)).toBe(NOTE);
    expect(envelopeBasisNote(MIXED)).toContain("not a stamped energy model");
  });

  it("says nothing on an empty register, where there is no number to qualify", () => {
    expect(envelopeBasisNote(EMPTY)).toBeNull();
  });

  it("survives a server that stops sending it", () => {
    expect(envelopeBasisNote({ ...MIXED, note: "" })).toBeNull();
  });
});

describe("BASIS-UNREAD · assemblyRows", () => {
  it("carries the requirement the verdict was measured against, in the right family's units", () => {
    const rows = assemblyRows(MIXED);
    const roof = rows.find((r) => r.name === "Low roof")!;
    expect(roof.requirement).toBe("R-30 min / R-25");
    expect(roof.result).toBe("FAIL — short 5 R");
    expect(roof.tone).toBe("crit");
    const sky = rows.find((r) => r.name === "Clerestory")!;
    expect(sky.requirement).toBe("U-0.5 max / U-0.62");
    expect(sky.result).toBe("FAIL — short 0.12 U");
    const win = rows.find((r) => r.name === "Curtain wall glazing")!;
    expect(win.requirement).toBe("U-0.38 max / U-0.3");
    expect(win.result).toBe("PASS — 0.08 U to spare");
    expect(win.tone).toBe("good");
  });

  it("puts failures first, then the rows with no verdict, then the passes", () => {
    expect(assemblyRows(MIXED).map((r) => r.name)).toEqual([
      "Low roof", "Clerestory",                    // compliant === false
      "Party wall", "Lobby storefront",            // compliant === null
      "Exterior wall", "Curtain wall glazing",     // compliant === true
    ]);
  });

  it("shows the engine's reason in the result column where there is no verdict", () => {
    const rows = assemblyRows(MIXED);
    const party = rows.find((r) => r.name === "Party wall")!;
    expect(party.result).toBe("no valid climate zone (1–8)");
    expect(party.tone).toBe("warn");
    expect(party.zone).toBe("—");
    // No zone means `check_assembly` returns before it looks a requirement up, so there is no
    // minimum to show — but the R-value IS there, and showing it says this is a one-field fix.
    expect(party.requirement).toBe("— / R-19");
  });

  it("keeps a requirement that IS known on a row with no verdict", () => {
    // Measured: a zone-4 window with no U-factor. The engine knows what it needs and not what it
    // has, and that half is worth showing — it is the number somebody has to go and find.
    const lobby = assemblyRows(MIXED).find((r) => r.name === "Lobby storefront")!;
    expect(lobby.requirement).toBe("U-0.38 max / —");
    expect(lobby.result).toBe("no U-factor or R-value given");
  });

  it("keeps the findings on the page the cap keeps — the whole point of the ordering", () => {
    const rows = assemblyRows(THIN);
    expect(rows).toHaveLength(ASSEMBLY_PAGE);
    // As shipped, `results.slice(0, 20)` on this register showed 4 verdicts and 16 blanks.
    expect(THIN.results.slice(0, ASSEMBLY_PAGE).filter((r) => r.compliant == null)).toHaveLength(16);
    // Ordered, the 20 rows lead with everything that needs doing.
    expect(rows.filter((r) => r.tone === "warn")).toHaveLength(20);
  });

  it("holds register order within a rank, so the page is reproducible", () => {
    const rows = assemblyRows(UNCHECKABLE, 3);
    expect(rows.map((r) => r.name)).toEqual(["W0", "W1", "W2"]);
  });
});

describe("BASIS-UNREAD · assemblyPageNote", () => {
  it("states the cap AND that the page is not register order", () => {
    expect(assemblyPageNote(THIN)).toBe(
      "Showing 20 of 40 assembly(ies), ordered worst first — failures, then assemblies with no "
      + "verdict, then passes.");
  });

  it("still declares the re-ordering when nothing was truncated", () => {
    // A re-ordered page presented as the register is a second silent claim on top of the cap.
    expect(assemblyPageNote(MIXED)).toBe(
      "Ordered worst first — failures, then assemblies with no verdict.");
  });

  it("names a page OF a page against the register total, not the response length", () => {
    const paged: EnvelopeAudit = { ...THIN, results: THIN.results.slice(0, 10) };
    expect(assemblyPageNote(paged)).toBe(
      "Showing 10 of 40 assembly(ies), ordered worst first — failures, then assemblies with no "
      + "verdict, then passes.");
  });

  it("is silent when there is nothing to re-order and nothing to cut", () => {
    const clean: EnvelopeAudit = { ...MIXED, total: 2, checked: 2, compliant: 2,
      results: MIXED.results.filter((r) => r.compliant === true) };
    expect(assemblyPageNote(clean)).toBeNull();
    expect(assemblyPageNote(EMPTY)).toBeNull();
  });
});

describe("BASIS-UNREAD · punchMentionNote", () => {
  it("carries the engine's substring caveat and says what the count is NOT", () => {
    const note = "Punch mentions are a substring match on description/location (the punchlist "
      + "module has no system field).";
    const out = punchMentionNote("Chilled water", 3, note)!;
    expect(out.startsWith(note)).toBe(true);
    expect(out).toContain('3 open punch item(s) whose text mentions "Chilled water"');
    expect(out).toContain("not 3 assigned to it");
  });

  it("says the derivable half even if the server sends no note", () => {
    expect(punchMentionNote("AHU-1", 2)).toContain('mentions "AHU-1"');
  });

  it("is silent when there are no mentions — nothing to qualify", () => {
    expect(punchMentionNote("Chilled water", 0, "x")).toBeNull();
  });

  it("falls back to a readable subject when the system name is blank", () => {
    expect(punchMentionNote("   ", 1)).toContain('mentions "this system"');
  });
});

describe("BASIS-UNREAD · TONE_CSS", () => {
  it("is a literal map — a runtime-built custom property resolves to nothing", () => {
    expect(TONE_CSS.crit).toBe("var(--status-crit)");
    expect(TONE_CSS[""]).toBe("");
    expect(Object.keys(TONE_CSS).sort()).toEqual(["", "crit", "good", "warn"]);
  });
});
