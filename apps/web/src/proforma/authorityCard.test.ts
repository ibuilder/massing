import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { FACT_TYPES, day, entriesFromAssessment, renderAuthority } from "./authorityCard";

/**
 * CRE-AUTHORITY could be **read and never declared**.
 *
 * `portal/panels/design.ts` has rendered this gate on its go/no-go card all along — so the product
 * could tell you *"Source facts NOT current"* — and `saveDealAuthority()` had no caller anywhere, so
 * nothing in the product could make them current. A gate you can read and cannot satisfy looks like a
 * bug in the analysis rather than a missing surface.
 *
 * The load-bearing test here is the **tripwire**, not the rendering: `FACT_TYPES` is mirrored from
 * Python because the GET returns declared rows plus the *required* missing ones, so an optional fact
 * type nobody has declared yet appears in neither and a card built from the response alone could never
 * offer to add one. Two tables encoding one fact drift — this repo has the scars — and the `required`
 * flag is the one that matters: if it drifts, this card shows a fact type as optional while the gate
 * blocks on it. Same technique as `ui/reportMoments.test.ts` against `reports.py`.
 */

const DEAL_AUTHORITY_PY = resolve(
  __dirname, "../../../../services/api/src/aec_api/deal_authority.py");

type Assessment = Awaited<ReturnType<ApiClient["dealAuthority"]>>;

const ROW = (over: Partial<Assessment["table"][number]> = {}) => ({
  fact_type: "rent_roll", label: "Rent roll", document: "RR 2026-08.xlsx", as_of: "2026-09-01",
  age_days: 24, freshness_days: 45, fresh: true, reviewer: null, required: true,
  supersedes: [], ...over,
});

const ASSESS = (over: Partial<Assessment> = {}): Assessment => ({
  as_of: "2026-09-25", table: [ROW()], missing: [], stale: [], superseded_still_active: [],
  gate: { passes: true, blocking: [], advisory: [] },
  counts: { declared: 1, missing: 0, stale: 0, blocking: 0, advisory: 0 },
  note: "Authority is declared per fact type, not per file.",
  ...over,
} as Assessment);

const mount = () => {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
};

describe("the mirrored fact-type table", () => {
  /** `FACT_TYPES: dict[str, tuple[label, days, required]]` as the Python declares it, in file order. */
  function pythonFactTypes(): [string, string, number, boolean][] {
    const src = readFileSync(DEAL_AUTHORITY_PY, "utf-8");
    const block = /FACT_TYPES: dict\[str, tuple\[str, int, bool\]\] = \{([\s\S]*?)\n\}/.exec(src);
    expect(block, "FACT_TYPES not found in deal_authority.py — the mirror below cannot be checked, "
      + "which is exactly the state this test exists to prevent").toBeTruthy();
    const out: [string, string, number, boolean][] = [];
    for (const m of block![1]!.matchAll(/"(\w+)":\s*\("([^"]+)",\s*(\d+),\s*(True|False)\)/g)) {
      out.push([m[1]!, m[2]!, Number(m[3]), m[4] === "True"]);
    }
    return out;
  }

  it("parsed the Python at all — a short list would make every assertion below vacuous", () => {
    expect(pythonFactTypes().length).toBeGreaterThanOrEqual(8);
  });

  it("matches key, label, default freshness and required flag, in order", () => {
    // `required` is the load-bearing column: a drift there shows a fact type as optional on this card
    // while `assess()` blocks on it, which is worse than not showing the fact type at all.
    expect(FACT_TYPES.map((f) => [...f])).toEqual(pythonFactTypes().map((f) => [...f]));
  });

  it("agrees with the engine about which types are required", () => {
    expect(FACT_TYPES.filter(([, , , r]) => r).map(([k]) => k))
      .toEqual(["rent_roll", "operating_statement", "tax"]);
  });
});

describe("dates", () => {
  it("formats from a fixed table, not the host's ICU", () => expect(day("2026-09-01")).toBe("1 Sep 2026"));
  it("returns an unparsable value unchanged", () => expect(day("whenever")).toBe("whenever"));
  it("renders an absent date as a dash", () => expect(day(null)).toBe("—"));
});

describe("the gate", () => {
  it("leads with the block and the engine's own reason for each fact type", () => {
    const el = renderAuthority(mount(), ASSESS({
      gate: { passes: false, advisory: [], blocking: [
        { fact_type: "operating_statement",
          why: "authoritative document is 87 day(s) past its 60-day freshness limit" },
        { fact_type: "tax", why: "no authoritative document declared" }] },
    }));
    expect(el.textContent).toContain("Blocked — 2 required fact type(s)");
    // Scoped to the blocking TABLE. Asserting the label against the whole card passes on the
    // "Not declared" line, which is rendered straight from FACT_TYPES and not through `label()` —
    // so the raw-key mutation satisfied it via a path the test is not about.
    const blockRows = [...el.querySelectorAll("table")][0]!.querySelectorAll("tr");
    const cells = [...blockRows].slice(1).map((tr) => [...tr.querySelectorAll("td")].map((td) => td.textContent));
    expect(cells).toEqual([
      ["Operating statement (T-12)", "authoritative document is 87 day(s) past its 60-day freshness limit"],
      ["Property tax bill", "no authoritative document declared"],
    ]);
  });

  it("says plainly when it passes", () => {
    expect(renderAuthority(mount(), ASSESS()).textContent)
      .toContain("Authority is sufficient to underwrite");
  });

  // A stale offering package is not a stale tax bill. One list would make the required ones look
  // negotiable and the optional ones look alarming.
  it("keeps advisory apart from blocking", () => {
    const t = renderAuthority(mount(), ASSESS({
      gate: { passes: true, blocking: [],
              advisory: [{ fact_type: "offering", why: "stale (not required)" }] },
    })).textContent ?? "";
    expect(t).toContain("Advisory — stale, not required");
    expect(t).toContain("Offering package");
    expect(t).not.toContain("Blocked");
  });

  it("renders the case nobody looks for: superseded and still relied on", () => {
    const t = renderAuthority(mount(), ASSESS({
      superseded_still_active: [{ fact_type: "tax", document: "Tax bill 2024.pdf",
                                  issue: "superseded by Tax bill 2025.pdf and still authoritative" }],
    })).textContent ?? "";
    expect(t).toContain("Superseded, still active");
    expect(t).toContain("Tax bill 2024.pdf");
    expect(t).toContain("how a stale number reaches a committee");
  });
});

describe("the declared table", () => {
  // A tax bill and an offering package go stale on different clocks, so "stale" alone is not
  // checkable — the age against its own limit is.
  it("shows age against the fact type's own freshness limit", () => {
    const t = renderAuthority(mount(), ASSESS({
      table: [ROW({ age_days: 147, freshness_days: 60, fresh: false })],
    })).textContent ?? "";
    expect(t).toContain("147 / 60d");
  });

  it("names what has not been declared, required ones marked", () => {
    const t = renderAuthority(mount(), ASSESS()).textContent ?? "";
    expect(t).toContain("Not declared:");
    expect(t).toContain("Operating statement (T-12) (required)");
    expect(t).toContain("Property tax bill (required)");
    expect(t).not.toContain("Rent roll (required)");        // it IS declared
  });

  it("marks a required row as required", () => {
    expect(renderAuthority(mount(), ASSESS()).textContent).toContain("required");
  });
});

describe("round-tripping into the editor", () => {
  it("opens on what is already declared rather than a blank form", () => {
    expect(entriesFromAssessment(ASSESS())).toEqual([{
      fact_type: "rent_roll", document: "RR 2026-08.xlsx", as_of: "2026-09-01",
      freshness_days: 45, authoritative: true, supersedes: [],
    }]);
  });

  it("carries a supersedes chain through", () => {
    const [e] = entriesFromAssessment(ASSESS({
      table: [ROW({ supersedes: ["RR 2026-06.xlsx"] })] }));
    expect(e!.supersedes).toEqual(["RR 2026-06.xlsx"]);
  });
});
