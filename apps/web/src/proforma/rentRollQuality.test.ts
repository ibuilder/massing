import { describe, expect, it } from "vitest";

import type { ApiClient } from "../api/client";
import { renderNetEffective, renderRentScrub } from "./rentRollQuality";

/**
 * Two R20 engines — CRE-NER and CRE-RRSCRUB — shipped complete, tested, and with no screen. Both are
 * built around a REFUSAL, and what these tests pin is that the cards keep it.
 *
 * `rent_scrub.py`: *"a check that cannot run says so … A scrub that reports 'no findings' because half
 * its inputs were missing is worse than no scrub — it launders absent data into apparent confidence."*
 * And `clean` is `bool(ran) and not failed`, so ONE check running and passing with six unable to run
 * is `clean: true`. Rendering a green tick off that flag would be the exact defect the engine exists
 * to prevent, committed by its own consumer.
 *
 * `net_effective.py`: every total is summed over the COMPUTABLE leases only, so with any
 * `skipped_count > 0` the Face GPR in this card is a different population from the "Base rent / yr" in
 * the rent-roll card directly above it — and the two sit on one screen inviting a subtraction. The
 * `skipped` list is additionally capped at 50 while `skipped_count` is not.
 */

type Ner = Awaited<ReturnType<ApiClient["netEffectiveRent"]>>;
type Scrub = Awaited<ReturnType<ApiClient["rentRollScrub"]>>;

const NER = (over: Partial<Ner> = {}): Ner => ({
  lease_count: 12, skipped_count: 0, excluded_not_active: 0,
  face_gpr_annual: 3_600_000, ner_gpr_annual_discounted: 3_150_000,
  ner_gpr_annual_straight_line: 3_240_000, concession_total_term: 1_800_000,
  concession_load_pct: 9.4, face_to_ner_delta_annual: 450_000, face_to_ner_delta_pct: 12.5,
  lc_included: true, discount_rate: 0.08, skipped: [],
  leases: [{ tenant: "Northline Health", suite: "400", face_rent_annual: 480_000,
             ner_annual_discounted: 402_000, ner_psf_discounted: 28.4, concession_load_pct: 16.2 }],
  note: "Concessions are deducted before effective income.",
  ...over,
} as Ner);

const CHECK = (over: Partial<Scrub["checks"][number]>): Scrub["checks"][number] => ({
  check: "scheduled_vs_gpr", applicable: true, passed: true, severity: "info",
  finding: "scheduled rent is within tolerance of gross potential rent", ...over,
});

const SCRUB = (over: Partial<Scrub> = {}): Scrub => ({
  lease_count: 12, excluded_not_active: 0, clean: true,
  counts: { total: 7, ran: 7, not_applicable: 0, passed: 7, failed: 0 },
  checks: [CHECK({})], findings: [],
  coverage_note: "7 of 7 checks could run; 0 lacked inputs and are reported as not-run, never as passing.",
  ...over,
} as Scrub);

function mount() {
  const host = document.createElement("div");
  document.body.replaceChildren(host);
  return host;
}

describe("net effective rent card", () => {
  it("renders face, both NER forms and the concession load", () => {
    const t = renderNetEffective(mount(), NER()).textContent ?? "";
    expect(t).toContain("$3,600,000");
    expect(t).toContain("$3,150,000");
    expect(t).toContain("$3,240,000");
    expect(t).toContain("9.4%");
    expect(t).toContain("12.5%");
  });

  it("names which NER form underwriting uses, so two numbers are a choice and not a puzzle", () => {
    expect(renderNetEffective(mount(), NER()).textContent).toContain("discounted");
  });

  // The engine never invents a leasing-commission rate. Without it landlord costs are understated,
  // so BOTH NERs are the optimistic case — the card has to say so or the absence reads as complete.
  it("says both NERs are the optimistic case when leasing commission was not supplied", () => {
    const t = renderNetEffective(mount(), NER({ lc_included: false })).textContent ?? "";
    expect(t).toContain("Leasing commission is not included");
    expect(t).toContain("optimistic");
  });

  it("…and says nothing of the sort when it WAS supplied", () => {
    expect(renderNetEffective(mount(), NER({ lc_included: true })).textContent)
      .not.toContain("optimistic");
  });

  // THE POPULATION CAVEAT. Every total is over the computable leases; the rent-roll card above shows
  // all of them. Two figures for "the rent roll", one screen, different sets.
  it("warns that the totals cover a smaller population than the rent roll above", () => {
    const t = renderNetEffective(mount(), NER({
      lease_count: 9, skipped_count: 3,
      skipped: [{ tenant: "Vale Dental", suite: "210", reason: "no end date" },
                { tenant: "Kerr & Co", suite: "115", reason: "no base rent" },
                { tenant: "Unit 6", suite: "6", reason: "end date before start" }],
    })).textContent ?? "";
    expect(t).toContain("9 lease(s) valued");
    expect(t).toContain("3 skipped");
    expect(t).toContain("not meant to reconcile");
    expect(t).toContain("no end date");             // the reasons, so the gap is actionable
  });

  it("…and stays quiet about reconciling when nothing was skipped", () => {
    expect(renderNetEffective(mount(), NER()).textContent).not.toContain("not meant to reconcile");
  });

  // `skipped` is capped at 50 server-side while `skipped_count` is not — a page presented as the
  // whole set is how a screen reports over a partial view and calls it complete (CLASH-TRUNC).
  it("says when the skipped list is a page of a larger set", () => {
    const t = renderNetEffective(mount(), NER({
      lease_count: 40, skipped_count: 120,
      skipped: Array.from({ length: 50 }, (_, i) => ({ tenant: `T${i}`, suite: "", reason: "no end date" })),
    })).textContent ?? "";
    expect(t).toContain("Showing 50 of 120 skipped leases");
  });

  it("…and does not claim truncation when the list is complete", () => {
    const t = renderNetEffective(mount(), NER({
      lease_count: 10, skipped_count: 2,
      skipped: [{ tenant: "A", suite: "", reason: "no base rent" },
                { tenant: "B", suite: "", reason: "no end date" }],
    })).textContent ?? "";
    expect(t).not.toContain("Showing");
  });

  // Zero computable leases: every total would be 0, and rendering those renders an absence as a
  // measurement — "$0 of net effective rent" is a different claim from "this cannot be stated".
  it("refuses to render zeros as a valuation when nothing could be computed", () => {
    const t = renderNetEffective(mount(), NER({
      lease_count: 0, skipped_count: 4, face_gpr_annual: 0, ner_gpr_annual_discounted: 0,
      concession_load_pct: 0, face_to_ner_delta_annual: 0, face_to_ner_delta_pct: 0, leases: [],
    })).textContent ?? "";
    expect(t).toContain("cannot be stated");
    expect(t).not.toMatch(/\$0/);
  });
});

describe("rent-roll scrub card", () => {
  // THE ONE THIS CARD EXISTS FOR. `clean` is true whenever at least one check ran and none failed.
  it("never renders `clean` as a clean rent roll when checks could not run", () => {
    const t = renderRentScrub(mount(), SCRUB({
      clean: true,
      counts: { total: 7, ran: 1, not_applicable: 6, passed: 1, failed: 0 },
      checks: [CHECK({}),
               CHECK({ check: "occupied_no_lease", applicable: false, passed: undefined,
                       finding: "not run", needs: "a unit inventory with {unit, occupied}" })],
      coverage_note: "1 of 7 checks could run; 6 lacked inputs and are reported as not-run, never as passing.",
    })).textContent ?? "";
    expect(t).toContain("1 of 7 checks could run");
    expect(t).toContain("not the same as a clean");
    expect(t).toContain("6 check(s) had no inputs");
  });

  it("…and does not hedge when every check ran and passed", () => {
    const t = renderRentScrub(mount(), SCRUB()).textContent ?? "";
    expect(t).toContain("7 of 7 checks could run");
    expect(t).not.toContain("not the same as a clean");
  });

  // The actionable half: what to go and get. Without it the gap is only an absence of green ticks.
  it("names what each check that could not run would need", () => {
    const t = renderRentScrub(mount(), SCRUB({
      counts: { total: 7, ran: 5, not_applicable: 2, passed: 5, failed: 0 },
      checks: [CHECK({ check: "occupied_no_lease", applicable: false, passed: undefined,
                       finding: "not run", needs: "a unit inventory with {unit, occupied}" }),
               CHECK({ check: "bad_debt_vs_occupancy", applicable: false, passed: undefined,
                       finding: "not run", needs: "income.bad_debt + prior_bad_debt" })],
    })).textContent ?? "";
    expect(t).toContain("a unit inventory with {unit, occupied}");
    expect(t).toContain("income.bad_debt + prior_bad_debt");
  });

  it("renders findings with their severity", () => {
    const t = renderRentScrub(mount(), SCRUB({
      clean: false,
      counts: { total: 7, ran: 7, not_applicable: 0, passed: 5, failed: 2 },
      findings: [{ check: "scheduled_vs_gpr", severity: "high",
                   finding: "scheduled rent is 11.4% above gross potential rent" },
                 { check: "expired_active", severity: "medium",
                   finding: "3 active leases are past their end date" }],
    })).textContent ?? "";
    expect(t).toContain("11.4% above gross potential rent");
    expect(t).toContain("high");
    expect(t).toContain("2 finding(s)");
  });

  it("reports the population it scrubbed, and what it left out", () => {
    const t = renderRentScrub(mount(), SCRUB({ lease_count: 12, excluded_not_active: 4 })).textContent ?? "";
    expect(t).toContain("12 active lease(s) scrubbed");
    expect(t).toContain("4 excluded as not active");
  });
});
