import { describe, expect, it } from "vitest";

import CASES from "./raciValidationCases.json";
import { orphanedRoles, validateMatrix } from "./raciValidation";
import type { ResponsibilityMatrix } from "../../api/client";

/**
 * RESP-ORPHAN — the rule, and the parity fixture the server has to agree with.
 *
 * `raciValidationCases.json` is shared ground: the same rule is implemented in
 * `services/api/src/aec_api/responsibility.py::_validate`, and the two had already drifted apart —
 * the client counted every assignment while the grid renders only the current columns, so a row
 * whose letters were all orphaned reported itself complete over a visibly blank line.
 *
 * The cases are read from the file rather than written inline **so that the file is load-bearing**.
 * A fixture nothing reads is a fixture that can rot; `runs every parity case` fails if the file
 * empties out, for the same reason the derivation checks elsewhere in this repo floor their
 * populations — a check that has quietly stopped checking looks exactly like one with nothing to
 * report.
 */

interface Case {
  name: string;
  roles: string[];
  doer: string;
  rows: { ref: string; activity: string; assignments: Record<string, string> }[];
  expect: {
    clean: boolean;
    missing: { ref: string; activity: string; count: number }[];
    noR: { ref: string; activity: string }[];
    unknown: string[];
    load: Record<string, number>;
  };
}

// TS infers a union of the literal shapes from the JSON, which does not widen to `Case` — the fixture is
// validated by the assertions below and by the Python side reading the same file, not by this cast.
const cases = (CASES as unknown as { cases: Case[] }).cases;

function matrix(c: Case): ResponsibilityMatrix {
  return {
    mode: c.doer === "D" ? "DACI" : "RACI",
    letters: c.doer === "D" ? ["D", "A", "C", "I"] : ["R", "A", "C", "I"],
    doer: c.doer,
    roles: c.roles,
    rows: c.rows.map((r) => ({
      id: r.ref, ref: r.ref, activity: r.activity,
      phase: null, category: null, milestone: null, reference: null,
      assignments: r.assignments,
    })),
    count: c.rows.length,
    validation: { missing_accountable: [], no_responsible: [], unknown_role: [],
      accountable_load: {}, clean: true },
    summary: { activities: c.rows.length, clean: true, issues: 0 },
  };
}

describe("the RACI rule is computed over the columns the user can see", () => {
  it("has parity cases to run", () => {
    // The fixture is the contract with the Python side; an empty one would let every assertion
    // below pass over nothing.
    expect(cases.length, "raciValidationCases.json has no cases").toBeGreaterThanOrEqual(5);
  });

  for (const c of cases) {
    it(`${c.name}`, () => {
      const v = validateMatrix(matrix(c));
      expect(v.clean).toBe(c.expect.clean);
      expect(v.missing).toEqual(c.expect.missing);
      expect(v.noR).toEqual(c.expect.noR);
      expect(orphanedRoles(v)).toEqual([...c.expect.unknown].sort());
      expect(v.load).toEqual(c.expect.load);
    });
  }

  it("an orphaned assignment is reported with the letter it still carries", () => {
    // `unknown` is not just a list of role names: the letter is what tells the user whether the
    // invisible cell was an Accountable they are about to lose or an Informed they will not miss.
    const v = validateMatrix(matrix({
      name: "x", roles: ["Owner"], doer: "R",
      rows: [{ ref: "R-9", activity: "Closeout", assignments: { Owner: "A", "Old Sub": "R" } }],
      expect: { clean: true, missing: [], noR: [], unknown: [], load: {} },
    }));
    expect(v.unknown).toEqual([{ ref: "R-9", activity: "Closeout", role: "Old Sub", letter: "R" }]);
  });

  it("survives a partial payload", () => {
    // The offline demo snapshot lacks this endpoint and the panel normalises around it; the
    // validator must not throw on the way through.
    const bare = { mode: "RACI", doer: "R" } as unknown as ResponsibilityMatrix;
    expect(validateMatrix(bare).clean).toBe(true);
  });
});
