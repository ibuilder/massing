import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { unmetRequires } from "./requiresGate";

/**
 * The `|` alternation in a transition's `requires`, and the cross-language agreement it depends on.
 *
 * CodeRabbit found the defect on PR #449: adding `entitlement.agency_company` gave the user a control
 * whose help text says to pick a company INSTEAD of typing the agency name, while `submit` still
 * required the typed `agency`. A linked-only entitlement could never be submitted. The sweep across
 * all 139 modules found a second instance already on main — `compliance_evidence.sign_off` requires
 * `responsible`, which has a `responsible_contact` beside it — so this is the additive pattern's
 * general collision with the workflow gate, not one bad manifest.
 */
describe("unmetRequires", () => {
  it("a plain entry behaves exactly as before", () => {
    expect(unmetRequires(["answer"], {})).toEqual(["answer"]);
    expect(unmetRequires(["answer"], { answer: "" })).toEqual(["answer"]);
    expect(unmetRequires(["answer"], { answer: "yes" })).toEqual([]);
  });

  it("either side of an alternation satisfies it", () => {
    const e = ["agency|agency_company"];
    expect(unmetRequires(e, { agency: "City of Example" })).toEqual([]);
    expect(unmetRequires(e, { agency_company: "0d1c…" })).toEqual([]);
    expect(unmetRequires(e, { agency: "", agency_company: "0d1c…" })).toEqual([]);
  });

  it("neither side filled is still blocked — the gate is loosened, not removed", () => {
    expect(unmetRequires(["agency|agency_company"], {})).toEqual(["agency|agency_company"]);
    expect(unmetRequires(["agency|agency_company"], { agency: "", agency_company: null }))
      .toEqual(["agency|agency_company"]);
  });

  it("unrelated fields never satisfy an entry", () => {
    expect(unmetRequires(["agency|agency_company"], { subject: "CUP" }))
      .toEqual(["agency|agency_company"]);
  });
});

/**
 * The reason this file reaches across the repo: the SAME rule is enforced in Python, and a rule
 * implemented twice diverges. Asserting the server splits on `|` too means the UI cannot grey out a
 * transition the server would accept — the exact failure this change exists to remove, in mirror.
 */
describe("the server enforces the same alternation", () => {
  const MODULES_PY = resolve(__dirname, "../../../../../services/api/src/aec_api/modules.py");

  it("splits a requires entry on `|` and accepts any filled alternative", () => {
    const src = readFileSync(MODULES_PY, "utf8");
    const i = src.indexOf('required = tr.get("requires")');
    expect(i, "the requires gate moved — re-point this test at it").toBeGreaterThan(-1);
    const block = src.slice(i, i + 900);
    expect(block, "the server must split a requires entry on `|`").toContain('r.split("|")');
    expect(block, "…and be satisfied when ANY alternative is filled").toContain("any(");
  });
});
