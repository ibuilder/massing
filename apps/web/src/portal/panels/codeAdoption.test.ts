import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";

import type { PanelContext } from "../panelContext";
import type { Adoptions } from "./codeAdoption";
import { renderJurisdiction } from "./jurisdictionPanel";
import { adoptionRows, adoptionScope, primaryCaveat, seededHint } from "./codeAdoption";

/**
 * CODE-ADOPT-DARK — `/codes/adoptions` had no client caller, and the field that makes its answer
 * honest is PER-FAMILY, not the top-level flag.
 *
 * The engine is careful: `resolved`, an `as_of` year, a `verify` note on every answer, and a
 * `source` of `"seed"` or `"baseline"` on each code family. Nothing read any of it. The defect a
 * first consumer would have shipped is rendering `resolved` — or worse `primary` — as though it
 * spoke for the whole answer.
 *
 * **Measured against the shipped seed rather than assumed** (see the last block, which reads
 * `codes.py`): six jurisdictions are seeded and ALL SIX are mixed — CA 4 of 8, FL 4, NY 3, TX 3,
 * WA 3, IL **1 of 8**. `resolved: true` has never once meant "every edition here is this
 * jurisdiction's", so a screen keyed on the flag states the national baseline as Illinois law for
 * seven families, against a seed whose own comment on that row reads *"no statewide building code;
 * home-rule adopts"*.
 *
 * **`A117.1` is seeded by nobody** — and it is one of the three in `primary`, so the accessibility
 * edition is the baseline everywhere, and an unseeded state returns the identical `primary` to a
 * project with no jurisdiction at all.
 */

const VERIFY = "Adoption facts change each code cycle and are overridden by local amendments — "
  + "confirm the edition in force with the Authority Having Jurisdiction (AHJ).";

const BASELINE: Record<string, number> = {
  "A117.1": 2017, IBC: 2021, IEBC: 2021, IECC: 2021, IFC: 2021, IMC: 2021, IPC: 2021, IRC: 2021,
};
const NAMES: Record<string, string> = {
  IBC: "International Building Code", IRC: "International Residential Code",
  IECC: "International Energy Conservation Code", IFC: "International Fire Code",
  IPC: "International Plumbing Code", IMC: "International Mechanical Code",
  IEBC: "International Existing Building Code",
  "A117.1": "ICC A117.1 Accessible and Usable Buildings and Facilities",
};

/** Compose a response the way `codes.resolve` does: baseline overlaid by the jurisdiction's seed. */
function resolve(jurisdiction: string | null, seed: Record<string, number> | null): Adoptions {
  const adopted = { ...BASELINE, ...(seed ?? {}) };
  return {
    jurisdiction,
    resolved: Boolean(seed),
    as_of: seed ? 2024 : null,
    codes: Object.keys(adopted).sort().map((fam) => ({
      family: fam, edition: adopted[fam]!, name: NAMES[fam] ?? fam,
      source: seed && fam in seed ? "seed" : "baseline",
    })),
    primary: { IBC: adopted.IBC!, IECC: adopted.IECC!, "A117.1": adopted["A117.1"]! },
    verify: VERIFY,
  };
}

/** Illinois, as shipped: ONE family seeded of eight. */
const IL = resolve("IL", { IBC: 2021 });
/** California, as shipped: four of eight. */
const CA = resolve("CA", { IBC: 2021, IRC: 2021, IECC: 2021, IFC: 2021 });
/** Wyoming: nothing seeded. */
const WY = resolve("WY", null);

describe("adoptionScope — the flag does not speak for the whole answer", () => {
  it("IL reports 1 of 8, NOT a resolved adoption", () => {
    const s = adoptionScope(IL, "IL");
    expect(IL.resolved).toBe(true);                 // the flag a naive consumer would have read
    expect(s.kind).toBe("mixed");
    expect(s.tone).toBe("warn");
    expect(s.seeded).toBe(1);
    expect(s.total).toBe(8);
    expect(s.headline).toBe("1 of 8 edition(s) are IL's as of 2024");
    expect(s.detail).toContain("national baseline");
  });

  it("CA is mixed too — every seeded jurisdiction is", () => {
    const s = adoptionScope(CA, "CA");
    expect(s.kind).toBe("mixed");
    expect(s.seeded).toBe(4);
    expect(s.headline).toContain("4 of 8 edition(s) are CA's");
  });

  it("an unseeded jurisdiction says every edition is the baseline", () => {
    const s = adoptionScope(WY, "WY");
    expect(s.kind).toBe("unseeded");
    expect(s.tone).toBe("warn");
    expect(s.headline).toBe("No adoption is seeded for WY");
    expect(s.detail).toContain("all 8 edition(s)");
  });

  it("no jurisdiction asks the server NOTHING and says why", () => {
    const s = adoptionScope(null, null);
    expect(s.kind).toBe("none");
    expect(s.tone).toBe("");
    expect(s.headline).toBe("No jurisdiction set");
    expect(s.detail).toContain("not a fact about anywhere");
  });

  it("`ok` is reachable ONLY when every family is this jurisdiction's", () => {
    // No jurisdiction in the shipped seed reaches this, which is why it is constructed: a branch no
    // input can reach is a branch that will be wrong when one can.
    const all = resolve("ZZ", { ...BASELINE });
    const s = adoptionScope(all, "ZZ");
    expect(s.kind).toBe("complete");
    expect(s.tone).toBe("ok");
    expect(s.headline).toContain("All 8 edition(s) are ZZ's");
    expect(`${s.headline} ${s.detail}`).not.toContain("baseline");
  });

  it("a `resolved: true` carrying no seeded family is treated as unseeded", () => {
    // Belt and braces on a disagreement between the flag and the rows: the ROWS decide, because
    // they are what the screen shows.
    const lying = { ...WY, resolved: true, as_of: 2024 };
    expect(adoptionScope(lying, "WY").kind).toBe("unseeded");
  });

  it("carries NO markup, because the panel escapes it", () => {
    // The first draft returned one `html` string with `<b>` emphasis and `innerHtmlGuard.test.ts`
    // refused it: the only interpolated value is the jurisdiction, which comes from the project
    // record. Asserted here so the shape cannot drift back.
    for (const s of [adoptionScope(IL, "IL"), adoptionScope(WY, "WY"), adoptionScope(null, null)]) {
      expect(`${s.headline}${s.detail}`).not.toMatch(/[<>]/);
    }
  });

  it("lowercases are normalised — a jurisdiction is a USPS code however it was typed", () => {
    expect(adoptionScope(resolve("il", { IBC: 2021 }), "il").headline).toContain("are IL's");
  });
});

describe("adoptionRows — the provenance is on the ROW", () => {
  it("labels each family as adopted or baseline", () => {
    const rows = adoptionRows(IL, "IL");
    const ibc = rows.find((r) => r.k.startsWith("IBC"))!;
    const a117 = rows.find((r) => r.k.startsWith("A117.1"))!;
    expect(ibc.v).toContain("adopted in IL");
    expect(ibc.strong).toBe(true);
    expect(a117.v).toContain("national baseline, NOT IL's adoption");
    expect(a117.strong).toBe(false);
  });

  it("carries the edition in the key, so a row cannot be read without one", () => {
    expect(adoptionRows(CA, "CA").map((r) => r.k)).toContain("IECC 2021");
  });
});

describe("primaryCaveat — the shortcut is where the provenance gets lost", () => {
  it("names the baseline members of `primary`, A117.1 among them", () => {
    const c = primaryCaveat(IL, "IL")!;
    expect(c).toContain("IECC");
    expect(c).toContain("A117.1");
    expect(c).not.toMatch(/\bIBC\b/);             // IBC *is* Illinois's
    expect(c).toContain("seeded for no jurisdiction at all");
  });

  it("CA's accessibility edition is still the baseline", () => {
    const c = primaryCaveat(CA, "CA")!;
    expect(c).toContain("A117.1");
    expect(c).not.toMatch(/\bIECC\b/);            // CA seeds IECC
  });

  it("is null only when every primary entry is this jurisdiction's", () => {
    expect(primaryCaveat(resolve("ZZ", { ...BASELINE }), "ZZ")).toBeNull();
    // ...and that is not any real jurisdiction today, which is the finding, not a gap in the test.
    expect(primaryCaveat(WY, "WY")).toContain("IBC, IECC, A117.1");
  });

  it("uses the singular when one entry is baseline", () => {
    const one = resolve("ZZ", { IBC: 2021, IECC: 2021 });
    expect(primaryCaveat(one, "ZZ")).toContain("A117.1 is the national baseline");
  });
});

describe("seededHint — the refusal must be a seed gap, not a claim", () => {
  it("names the jurisdictions that do have specifics", () => {
    const h = seededHint(["CA", "FL", "IL", "NY", "TX", "WA"])!;
    expect(h).toContain("CA, FL, IL, NY, TX, WA");
    expect(h).toContain("gap in a dated seed, not a finding about your jurisdiction");
  });

  it("is null when the list is unavailable, so a failed request costs the hint not the section", () => {
    expect(seededHint(null)).toBeNull();
    expect(seededHint([])).toBeNull();
  });
});

/**
 * **The fixtures above are a claim about the server, so the server is read.**
 *
 * Every number in this file's header — six seeded jurisdictions, IL at 1 of 8, A117.1 seeded by
 * nobody — is a fact about `services/data/src/aec_data/codes.py`. A fixture hand-copied from a
 * measurement taken once is a measurement that stops being true without anything going red, which
 * is the drift this repository's own instructions keep paying for. These assertions fail when the
 * seed changes, and the message points at the fixtures.
 */
describe("the seed these fixtures describe", () => {
  const ENGINE = readFileSync("../../services/data/src/aec_data/codes.py", "utf8");
  const SEED = ENGINE.slice(ENGINE.indexOf("_ADOPTIONS: dict"), ENGINE.indexOf("_VERIFY ="));

  it("has 8 baseline families, so '1 of 8' and 'all 8' are the right denominators", () => {
    const block = ENGINE.slice(ENGINE.indexOf("BASELINE = {"), ENGINE.indexOf("# A small"));
    expect([...block.matchAll(/"([A-Za-z0-9.]+)":\s*\d{4}/g)]).toHaveLength(8);
  });

  it("seeds exactly the six jurisdictions `seededHint` is tested with", () => {
    const keys = [...SEED.matchAll(/^\s{4}"([A-Z]{2})":/gm)].map((m) => m[1]!);
    expect(keys.sort()).toEqual(["CA", "FL", "IL", "NY", "TX", "WA"]);
  });

  it("seeds ONE family for IL and four for CA — the mixed counts above", () => {
    const fams = (j: string) => {
      const line = SEED.split("\n").find((l) => l.includes(`"${j}": {`))!;
      // NO off-by-one correction: the jurisdiction key is followed by `{`, not a year, so it does
      // not match this pattern at all. The first draft subtracted one for it and read IL as ZERO —
      // and would have passed silently on any count where the two errors happened to agree.
      expect(line).toMatch(new RegExp(`"${j}":\\s*\\{`));
      return [...line.matchAll(/"([A-Za-z0-9.]+)":\s*\d{4}/g)].length;
    };
    expect(fams("IL")).toBe(1);
    expect(fams("CA")).toBe(4);
    expect(fams("NY")).toBe(3);
  });

  it("seeds A117.1 for NOBODY — the reason `primaryCaveat` is never null in practice", () => {
    expect(SEED).not.toContain('"A117.1"');
    expect(ENGINE).toContain('"A117.1": 2017');      // ...while the BASELINE does carry it
  });

  it("derives `source` PER FAMILY from the seed, which is what the rows rest on", () => {
    // The whole module is built on `source` distinguishing a seeded edition from a baseline one.
    // That expression is in another language, and a change making it unconditional leaves every
    // assertion above green because the fixtures compose their own responses — the same shape as
    // CLASH-TRUNC, where the guard was sound and its evidence was not.
    expect(ENGINE).toContain('"source": "seed" if seeded and fam in seeded else "baseline"');
  });

  it("still attaches `verify` to every answer, which this panel renders as visible text", () => {
    expect(ENGINE).toContain('"verify": _VERIFY,');
    expect(ENGINE).toContain("Authority Having Jurisdiction (AHJ)");
  });
});

/**
 * ---- the RENDER, through the real panel -------------------------------------------------------
 *
 * The decision functions above are pure and testable, and that is exactly what makes a renderer
 * that is never called invisible. MACRO-DARK found this by mutation hours earlier — thirteen
 * mutations red and the one that deleted the `append` alive — so the section is driven through
 * `renderJurisdiction` here rather than asserted at the seam.
 *
 * It also asserts the one behaviour no helper can carry: **with no jurisdiction the server is not
 * asked.** `/codes/adoptions` answers an empty jurisdiction with the full national baseline and a
 * `resolved: false` nobody is obliged to read, so a panel that asked anyway would put eight
 * editions on screen for a project that has no place at all.
 */
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

function panelCtx(jurisdiction: string | null, seed: Record<string, number> | null) {
  const api = {
    projectRequirements: vi.fn(async () => ({
      jurisdiction, packs: [], adopted: false, why: "no pack imported", explicit: false,
    })),
    jurisdictionCheck: vi.fn(async () => ({ packs: [], model_scored: false })),
    jurisdictionPacks: vi.fn(async () => ({ count: 0, packs: [] })),
    codeAdoptions: vi.fn(async (j: string) => resolve(j, seed)),
    codeSeeded: vi.fn(async () => ({ jurisdictions: ["CA", "FL", "IL", "NY", "TX", "WA"] })),
  };
  const c = {
    root: document.createElement("div"),
    host: { projectId: () => "p1", api, setStatus: () => undefined },
    mods: [], activeKey: "jurisdiction",
    bar: (t: string) => { const b = document.createElement("div"); b.textContent = t; return b; },
    buildNav: () => undefined, renderHome: async () => undefined,
    openModule: async () => undefined, navigate: () => undefined, hasDest: () => true,
  } as unknown as PanelContext;
  return { c, api };
}

describe("the governing-code section on the real panel", () => {
  it("renders the mixed scope, the per-row provenance and the AHJ note", async () => {
    const { c, api } = panelCtx("IL", { IBC: 2021 });
    await renderJurisdiction(c); await flush();
    const text = c.root.textContent ?? "";
    expect(api.codeAdoptions).toHaveBeenCalledWith("IL");
    expect(text).toContain("Governing code editions");
    expect(text).toContain("1 of 8 edition(s) are IL's");
    expect(text).toContain("adopted in IL");
    expect(text).toContain("national baseline, NOT IL's adoption");
    // The `primary` caveat, by a phrase ONLY it carries. Asserting "A117.1" was satisfied by the
    // row table, so deleting the caveat from the panel survived the mutation — the family name is
    // on screen twice and the assertion could not say which one it had found.
    expect(text).toContain("Of the three headline editions");
    expect(text).toContain("seeded for no jurisdiction at all");
    expect(text).toContain("Authority Having Jurisdiction (AHJ)");
  });

  it("asks the server NOTHING when the project has no jurisdiction", async () => {
    const { c, api } = panelCtx(null, null);
    await renderJurisdiction(c); await flush();
    expect(api.codeAdoptions).not.toHaveBeenCalled();
    const text = c.root.textContent ?? "";
    expect(text).toContain("No jurisdiction set");
    expect(text).not.toContain("IBC 2021");        // the baseline never reaches the screen
  });

  it("names the seeded jurisdictions when nothing is seeded for this one", async () => {
    const { c, api } = panelCtx("WY", null);
    await renderJurisdiction(c); await flush();
    const text = c.root.textContent ?? "";
    expect(text).toContain("No adoption is seeded for WY");
    expect(api.codeSeeded).toHaveBeenCalled();
    expect(text).toContain("CA, FL, IL, NY, TX, WA");
  });

  it("does not ask for the seeded list when the jurisdiction IS seeded", async () => {
    const { c, api } = panelCtx("CA", { IBC: 2021, IRC: 2021, IECC: 2021, IFC: 2021 });
    await renderJurisdiction(c); await flush();
    expect(api.codeSeeded).not.toHaveBeenCalled();
    expect(c.root.textContent).toContain("4 of 8 edition(s) are CA's");
  });

  it("loses the hint and keeps the section when the seeded list fails", async () => {
    const { c, api } = panelCtx("WY", null);
    api.codeSeeded.mockRejectedValueOnce(new Error("offline"));
    await renderJurisdiction(c); await flush();
    const text = c.root.textContent ?? "";
    expect(text).toContain("No adoption is seeded for WY");
    expect(text).toContain("Authority Having Jurisdiction (AHJ)");
    expect(text).not.toContain("gap in a dated seed");
  });

  it("reports a failed adoption read instead of rendering a silent gap", async () => {
    const { c, api } = panelCtx("IL", { IBC: 2021 });
    api.codeAdoptions.mockRejectedValueOnce(new Error("503"));
    await renderJurisdiction(c); await flush();
    expect(c.root.textContent).toContain("code adoptions failed: 503");
  });
});
