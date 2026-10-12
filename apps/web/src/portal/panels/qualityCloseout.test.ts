import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { QualityChain, QualityTurnover } from "./qualityCloseout";
import {
  certifyAcknowledgements, certifyConfirmBody, chainRowsHtml, qualityReading,
} from "./qualityCloseout";

/**
 * TURNOVER-UNGATED — the quality gate built for G704 certification was rendered as a caption.
 *
 * `quality_chain.turnover_readiness` exists as *"the seam `turnover.py` never had"* and is careful
 * about the one thing that matters: `ready` requires evidence to EXIST and be resolved, because
 * *"an element with no quality record counts against readiness rather than for it — otherwise a
 * project nobody inspected reads as perfectly clean, which is the failure this exists to prevent."*
 *
 * The Operations turnover tab read it, printed one line, and gated nothing. The architect-certify
 * button checked the PUNCH-list readiness from a different route and nothing else — and could not
 * have done otherwise, because the quality answer arrived in a detached `.then()` and was not in
 * scope where the decision is made.
 *
 * The three states this file exists to keep apart:
 *
 *  - **a failed read** is not "nothing to report" (the old `.catch(() => {})` made them identical);
 *  - **no evidence attached anywhere** printed as "0 outstanding · 0 never inspected · coverage 0%",
 *    which is what a clean fully-inspected project looks like at a glance, while `message` says
 *    which it is;
 *  - **elements nobody inspected** are not a pass.
 */

const qt = (o: Partial<QualityTurnover> = {}): QualityTurnover => ({
  ready: o.ready ?? true,
  outstanding_count: o.outstanding_count ?? 0,
  unrecorded_count: o.unrecorded_count ?? 0,
  coverage_pct: o.coverage_pct ?? 100,
  any_attached: o.any_attached ?? true,
  outstanding_elements: o.outstanding_elements ?? [],
  unrecorded_elements: o.unrecorded_elements ?? [],
  basis: o.basis ?? "`ready` requires evidence to EXIST and be resolved.",
  message: o.message ?? null,
  ...o,
});

describe("qualityReading — four states the old caption collapsed into one", () => {
  it("reports a FAILED READ as its own state, never as nothing to report", () => {
    const r = qualityReading(null);
    expect(r.kind).toBe("unread");
    expect(r.tone).not.toBe("ok");
    expect(r.detail).toContain("not a statement that there is nothing to report");
  });

  it("says what certifying over an unread answer means", () => {
    expect(qualityReading(null).detail).toContain("without having looked");
  });

  it("reports NO EVIDENCE ATTACHED as the absence of evidence, and carries the server's message", () => {
    const r = qualityReading(qt({
      ready: false, any_attached: false, coverage_pct: 0,
      message: "No quality record in this project is attached to an element (7 record(s) exist)",
    }));
    expect(r.kind).toBe("no-evidence");
    expect(r.tone).toBe("bad");
    expect(r.detail).toContain("7 record(s) exist");
    expect(r.detail).toContain("not evidence of conformance");
  });

  it("does NOT let zeros read as a clean project", () => {
    // The whole defect: outstanding_count 0, unrecorded_count 0, coverage 0% — identical numbers to
    // a project with no findings, and the old caption printed exactly those three.
    const r = qualityReading(qt({ ready: false, any_attached: false, coverage_pct: 0 }));
    expect(r.kind).not.toBe("ready");
    expect(r.headline).toContain("No quality record is attached to any element");
  });

  it("ranks OUTSTANDING above unrecorded, and still mentions the unrecorded", () => {
    const r = qualityReading(qt({ ready: false, outstanding_count: 3, unrecorded_count: 42,
                                  coverage_pct: 61 }));
    expect(r.kind).toBe("outstanding");
    expect(r.headline).toContain("3 element(s)");
    expect(r.headline, "a reader must not have to open a second card to learn about the 42")
      .toContain("42");
  });

  it("treats UNRECORDED alone as not-a-pass, and says why", () => {
    const r = qualityReading(qt({ ready: false, unrecorded_count: 42, coverage_pct: 11 }));
    expect(r.kind).toBe("unrecorded");
    expect(r.tone).toBe("warn");
    expect(r.detail).toContain("not the same as nothing being wrong");
    expect(r.detail).toContain("11");
  });

  it("reports a genuinely ready project as ready", () => {
    const r = qualityReading(qt());
    expect(r.kind).toBe("ready");
    expect(r.tone).toBe("ok");
  });

  it("carries the engine's `basis` rather than paraphrasing it", () => {
    expect(qualityReading(qt({ ready: false, unrecorded_count: 1, basis: "ENGINE SAYS SO" }))
      .detail).toContain("ENGINE SAYS SO");
  });
});

describe("certifyAcknowledgements — told, not blocked", () => {
  it("asks for nothing when the evidence supports closeout", () => {
    expect(certifyAcknowledgements(qt())).toEqual([]);
  });

  it("names an unread answer", () => {
    expect(certifyAcknowledgements(null).join(" ")).toContain("could not be read");
  });

  it("names a project with no quality evidence at all", () => {
    const a = certifyAcknowledgements(qt({ ready: false, any_attached: false, coverage_pct: 0 }));
    expect(a.join(" ")).toContain("ANY element");
    expect(a.join(" ")).toContain("coverage 0%");
  });

  it("names outstanding AND unrecorded separately, plus the coverage", () => {
    // Three facts, three lines. Collapsing them to the worst would hide what the architect is
    // certifying over.
    const a = certifyAcknowledgements(qt({ ready: false, outstanding_count: 3,
                                           unrecorded_count: 42, coverage_pct: 61 }));
    expect(a).toHaveLength(3);
    expect(a[0]).toContain("3 element(s)");
    expect(a[1]).toContain("42 element(s)");
    expect(a[2]).toContain("61%");
  });

  it("omits the line that does not apply", () => {
    const a = certifyAcknowledgements(qt({ ready: false, unrecorded_count: 42, coverage_pct: 11 }));
    expect(a).toHaveLength(2);
    expect(a.join(" ")).not.toContain("unresolved quality evidence");
  });

  it("names the hold point among the things `outstanding` can mean", () => {
    // An unverified hold or witness point is the specific thing an ITP exists to stop being
    // skipped, and "unresolved quality evidence" alone does not tell the signatory that.
    expect(certifyAcknowledgements(qt({ ready: false, outstanding_count: 1 })).join(" "))
      .toContain("hold point");
  });
});

describe("certifyConfirmBody — a judgement, and said to be one", () => {
  const body = certifyConfirmBody(["42 element(s) have no quality record at all."]);

  it("lists what is being certified over", () => {
    expect(body).toContain("42 element(s)");
  });

  it("says signing records that it was certified with this known", () => {
    expect(body).toContain("certified with this known");
  });

  it("says plainly that this is NOT a bar — G704 is certified with an open punch list", () => {
    // Asserting a veto here would assert a rule the engine deliberately declined to assert, and
    // would make the certificate unissuable on any project with one uninspected element.
    expect(body).toContain("judgement rather than a bar");
  });
});

describe("chainRowsHtml — which elements, worst first", () => {
  const chain = (o: Partial<QualityChain> = {}): QualityChain => ({
    elements: o.elements ?? [],
    element_count: o.element_count ?? 0,
    counts: o.counts ?? {},
    any_attached: o.any_attached ?? true,
    coverage_pct: o.coverage_pct ?? 0,
    records_total: o.records_total ?? 0,
    records_without_element: o.records_without_element ?? {},
    message: o.message ?? null,
    ...o,
  });
  const elem = (guid: string, status: string, o: Partial<QualityChain["elements"][number]> = {}) => ({
    guid, status, status_note: o.status_note ?? `note for ${status}`,
    record_count: o.record_count ?? 1, open_count: o.open_count ?? 0,
    unverified_hold_points: o.unverified_hold_points ?? [],
  });

  it("puts UNRECORDED above clear, not below it", () => {
    // The ordering is the assertion: an element nobody inspected is not a pass, so it cannot sort
    // after the ones that are.
    const h = chainRowsHtml(chain({
      elements: [elem("A", "clear"), elem("B", "unrecorded"), elem("C", "outstanding")],
    }));
    expect(h.indexOf("C")).toBeLessThan(h.indexOf("B"));
    expect(h.indexOf("B")).toBeLessThan(h.indexOf("A"));
  });

  it("names unverified hold/witness points, which nothing else in the app showed", () => {
    const h = chainRowsHtml(chain({
      elements: [elem("A", "outstanding", { open_count: 2, unverified_hold_points: [
        { id: "1", ref: "ITP-3", point_type: "Hold", state: "active" }] })],
    }));
    expect(h).toContain("unverified hold/witness point");
  });

  it("carries the engine's status note per element", () => {
    expect(chainRowsHtml(chain({ elements: [elem("A", "unrecorded",
      { status_note: "the ABSENCE of evidence" })] }))).toContain("the ABSENCE of evidence");
  });

  it("renders the server's message when nothing names an element", () => {
    expect(chainRowsHtml(chain({ message: "No quality record is attached to an element" })))
      .toContain("No quality record is attached");
  });

  it("caps the list and SAYS it capped, rather than showing a short list", () => {
    const many = Array.from({ length: 250 }, (_, i) => elem(`g${i}`, "unrecorded"));
    const h = chainRowsHtml(chain({ elements: many }));
    expect(h).toContain("50 more");
  });

  it("escapes the GlobalId and the note", () => {
    const h = chainRowsHtml(chain({
      elements: [elem("<img src=x onerror=alert(1)>", "clear", { status_note: "<b>x</b>" })],
    }));
    expect(h).not.toContain("<img src=x");
    expect(h).toContain("&lt;img");
  });
});

/** The pins: the gate is consulted where the decision is, and the dark route has a door. */
const here = dirname(fileURLToPath(import.meta.url));
const ops = readFileSync(resolve(here, "operations.ts"), "utf8");
const client = readFileSync(resolve(here, "../../api/models.ts"), "utf8");

describe("the certify decision consults the quality gate", () => {
  it("awaits the quality answer in the same scope as the button", () => {
    // Previously it arrived in a detached `.then()`, so the decision could not have consulted it
    // even in principle. This is the structural half of the fix.
    expect(ops).toMatch(/const qt = await ctx\.host\.api\.qualityTurnoverReadiness\(pid\)/);
    expect(ops, "a detached then() puts the answer out of reach of the decision")
      .not.toMatch(/api\.qualityTurnoverReadiness\(pid\)\.then\(/);
  });

  it("consults it IN the certify handler, after the punch check", () => {
    const punchAt = ops.indexOf("if (!rd!.ready_for_substantial_completion)");
    const ackAt = ops.indexOf("const acks = certifyAcknowledgements(qt)");
    expect(punchAt).toBeGreaterThan(0);
    expect(ackAt).toBeGreaterThan(punchAt);
    expect(ops).toMatch(/if \(acks\.length && !await confirmModal\(/);
  });

  it("defaults the confirm to cancel, and marks it dangerous", () => {
    const block = ops.slice(ops.indexOf("const acks = certifyAcknowledgements(qt)"));
    expect(block.slice(0, 400)).toContain('"Certify anyway", true');
    expect(block.slice(0, 400), "a confirm that proceeds on dismissal is not a confirm")
      .toContain("return;");
  });

  it("does not swallow a failed quality read as an empty register", () => {
    expect(ops).toMatch(/qualityTurnoverReadiness\(pid\)\.catch\(\(\) => null\)/);
    expect(ops, "the old catch dropped the card, which reads as a project with no concerns")
      .not.toContain("/* quality registers may be empty */");
  });

  it("declares a client method for the per-element chain, and reads it", () => {
    expect(client).toMatch(/qualityChain\(pid: string, guids\?: string\[\]\)/);
    expect(client).toContain("/quality/chain");
    expect(ops).toMatch(/api\.qualityChain\(pid\)/);
    expect(ops).toMatch(/chainRowsHtml\(ch\)/);
  });

  it("surfaces records that name NO element — in no chain at all", () => {
    // The engine reports `records_without_element`: NCRs and inspections that exist but are
    // attached to nothing. They are invisible in a per-element view by construction.
    expect(ops).toContain("records_without_element");
    expect(ops).toContain("name no element");
  });
});
