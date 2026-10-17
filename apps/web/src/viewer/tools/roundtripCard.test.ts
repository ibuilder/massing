import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { RoundtripReport } from "./roundtripCard";
import { SELECT_CAP, roundtripGroups, roundtripReading } from "./roundtripCard";

/**
 * NEGATED-VERDICT, the round-trip screen half.
 *
 * The engine half is `services/api/test_negated_verdict.py`, which derives every all-negated verdict
 * and demands a guard or a declaration. This file asserts the consumer: that "nothing was compared"
 * is a state of its own rather than a pass, and that the STATUS LINE — the one place the verdict
 * appeared with no count beside it — says so.
 */

const mk = (o: Partial<RoundtripReport> = {}): RoundtripReport => ({
  fidelity_ok: true, nothing_compared: false, element_count: 10,
  missing: [], added: [], changed: [],
  counts: { missing: 0, added: 0, changed: 0 },
  ...o,
} as RoundtripReport);

describe("roundtripReading — three states, because an unrun check is not a clean one", () => {
  it("ranks UNRUN first and tones it as neither a pass nor a finding", () => {
    const r = roundtripReading(mk({ nothing_compared: true, fidelity_ok: false, element_count: 0 }));
    expect(r.kind).toBe("unrun");
    expect(r.tone).toBe("");
    expect(r.html).toContain("not a lossless result; it is an unrun one");
  });

  it("THE STATUS LINE is where this mattered — it carries no count at all", () => {
    // The card rendered `element_count` in its own sentence, so "all 0 elements survived" was at
    // least self-refuting. This line printed the bare verdict, and "round-trip clean" was the whole
    // of the answer for a model with no products.
    expect(roundtripReading(mk({ nothing_compared: true, fidelity_ok: false, element_count: 0 })).status)
      .toBe("nothing to round-trip");
    expect(roundtripReading(mk()).status).toBe("round-trip clean");
    expect(roundtripReading(mk({ fidelity_ok: false,
      counts: { missing: 2, added: 1, changed: 4 } })).status).toBe("7 discrepancy(ies)");
  });

  it("does not let `nothing_compared` be overridden by a stale `fidelity_ok`", () => {
    // A server that still sends the unguarded flag beside the new field must not read as lossless —
    // the same second-refusal shape as the ledger's reconcile line.
    const r = roundtripReading(mk({ nothing_compared: true, fidelity_ok: true, element_count: 0 }));
    expect(r.kind).toBe("unrun");
  });

  it("is lossless only with elements behind it, and says how many", () => {
    const r = roundtripReading(mk({ element_count: 4_210 }));
    expect(r.kind).toBe("lossless");
    expect(r.tone).toBe("ok");
    expect(r.html).toContain("all 4210 elements survived");
  });

  it("reports a lossy round-trip against the population, never as a bare count", () => {
    const r = roundtripReading(mk({ fidelity_ok: false, element_count: 900,
      counts: { missing: 3, added: 0, changed: 1 } }));
    expect(r.kind).toBe("lossy");
    expect(r.tone).toBe("bad");
    expect(r.html).toContain("of 900 elements");
  });
});

describe("roundtripGroups", () => {
  it("leads with MISSING — an element that does not survive our own export is data loss", () => {
    const g = roundtripGroups(mk({ missing: ["a"], added: ["b", "c"] }));
    expect(g.map((x) => x.label)).toEqual(["Missing after round-trip", "Appeared after round-trip"]);
    expect(g[0]!.guids).toEqual(["a"]);
  });

  it("drops an empty group rather than rendering a row that says zero", () => {
    expect(roundtripGroups(mk({ missing: [], added: ["b"] })).map((x) => x.label))
      .toEqual(["Appeared after round-trip"]);
    expect(roundtripGroups(mk())).toEqual([]);
  });
});

describe("the panel is WIRED, and the extraction is what paid for the fix", () => {
  const HERE = dirname(fileURLToPath(import.meta.url));
  const SRC = readFileSync(resolve(HERE, "qaSection.ts"), "utf-8");

  it("reads the status line from the module, not from a ternary chain inline", () => {
    expect(SRC).toContain("out.textContent = m.roundtripReading(r).status;");
    expect(SRC).not.toContain("round-trip clean");
    expect(SRC).not.toContain("nothing_compared");
  });

  it("keeps the card BODY out of the eager chunk — `viewer/tools/*` is the first load", () => {
    // The size ratchet in `services/api/test_file_sizes.py` refused the ten lines the third state
    // cost, which is what made this a module instead of an inline fix.
    expect(SRC).toContain('await import("./roundtripCard")');
    expect(SRC).not.toContain("roundtripGroups(");
  });

  it("the client DECLARES `nothing_compared`, or no derivation over declarations sees it", () => {
    const api = readFileSync(resolve(HERE, "../../api/model.ts"), "utf-8");
    expect(api).toContain("nothing_compared: boolean");
  });

  it("caps the GUID run handed to a selection call", () => {
    expect(SELECT_CAP).toBe(200);
  });
});
