import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ClashPanelDeps } from "./clashPanel";
import { buildClashPanel } from "./clashPanel";

/**
 * CLASH-TRUNC — the coordination matrix must be built from the WHOLE run, never from the page.
 *
 * `/clash/federated` returns `count` (every clash) beside `clashes` (the first `limit` of them) and
 * a `truncated` flag. The panel built the discipline-pair matrix out of `clashes` while declaring
 * every pair tested, so `soft_clash.matrix` — whose entire reason for existing is that an untested
 * pair is never reported clean — was handed evidence that a pair had been tested and found nothing,
 * for pairs whose clashes all sat past the limit. On a run with more clashes than the limit that is
 * a `clean` cell for a pair holding hundreds of clashes, under a matrix reporting 100% coverage and
 * nothing untested — it states it examined pairs it never saw. (`coordinated` itself stays false:
 * it needs zero clashing cells and a truncated page always carries one. The first draft of this
 * comment claimed otherwise; `services/api/test_clash_trunc.py` measures the bound rather than
 * asserting a worse one.)
 *
 * *The engine refused the claim; its caller supplied a premise that made the refusal moot.*
 *
 * `truncated` was returned by the server and read by NOBODY — it is one of the fields
 * `deadFieldTyped.test.ts` reports with no reader, and the reason it could be unread for so long is
 * that the panel re-spelled the response shape inline instead of using the declared interface. Both
 * halves are fixed here: the shapes are declared in `apps/web/src/api/clash.ts` and used.
 */

type Json = Record<string, unknown>;

function harness(result: Json) {
  const matrixCalls: Json[] = [];
  const api = {
    enqueueJob: vi.fn(async () => ({ id: "j1", state: "queued" })),
    job: vi.fn(async () => ({ id: "j1", state: "done", result })),
    clashMatrix: vi.fn(async (_pid: string, body: Json) => {
      matrixCalls.push(body);
      return { disciplines: [], pair_count: 0, coverage_pct: 0, coordinated: false, note: "",
        counts: { clashes: 0, clean: 0, untested: 0 }, cells: [] };
    }),
  };
  const deps = {
    api: api as unknown as ClashPanelDeps["api"],
    projectId: () => "p1",
    selectByGuid: vi.fn(async () => undefined),
    setStatus: vi.fn(),
    refreshIssues: vi.fn(async () => undefined),
    reloadModelPins: vi.fn(async () => undefined),
  } satisfies ClashPanelDeps;
  return { deps, matrixCalls };
}

const hit = (a: string, b: string, i: number) => ({
  a_model: a, b_model: b, a_class: "IfcBeam", b_class: "IfcDuctSegment",
  a_guid: `A${i}`, b_guid: `B${i}`, volume: 0.5, method: "mesh" as const,
  point: { x: 0, y: 0, z: 0 },
});

/** 200 returned of 1,438 found. Every returned clash is STR×MEP; the pairs that only clash beyond
 *  the page are the ones the old code reported clean. */
const PAGE = Array.from({ length: 200 }, (_, i) => hit("STR", "MEP", i));
const TRUNCATED: Json = {
  disciplines: ["STR", "MEP", "ARC"],
  count: 1438,
  truncated: true,
  coordination: null,
  clashes: PAGE,
  pair_counts: [
    { discipline_a: "ARC", discipline_b: "MEP", count: 918 },
    { discipline_a: "MEP", discipline_b: "STR", count: 520 },
  ],
};

const flush = () => new Promise((r) => setTimeout(r, 0));
const btn = (text: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!;

async function run(result: Json) {
  document.body.replaceChildren();
  const panel = document.createElement("div");
  panel.id = "panel-clash";
  document.body.appendChild(panel);
  const h = harness(result);
  await buildClashPanel(h.deps);
  btn("Run clash — all disciplines").click();
  await flush(); await flush(); await flush();
  return { ...h, panel };
}

describe("CLASH-TRUNC: a truncated clash run", () => {
  beforeEach(() => { document.body.replaceChildren(); });

  it("builds the matrix from the per-pair tally over the whole run, not from the page", async () => {
    const { panel, matrixCalls } = await run(TRUNCATED);
    btn("Discipline-pair matrix").click();
    await flush();
    expect(matrixCalls, "the matrix button did not reach the client").toHaveLength(1);
    const body = matrixCalls[0] as { findings: { discipline_a: string; count?: number }[];
      tested_pairs: [string, string][] };

    // THE DEFECT: every clash on the page is STR×MEP, so a matrix built from the page has no
    // evidence at all for ARC×MEP — and with ARC declared tested, that cell reads `clean`.
    expect(new Set(PAGE.map((c) => `${c.a_model}|${c.b_model}`)), "the fixture no longer exercises "
      + "the defect — the page must name FEWER pairs than the run").toEqual(new Set(["STR|MEP"]));
    expect(body.findings.map((f) => f.discipline_a).sort()).toEqual(["ARC", "MEP"]);
    expect(body.findings.find((f) => f.discipline_a === "ARC")?.count,
      "the tally's real count must travel — a finding weighing 1 understates the cell").toBe(918);

    // The pairs ARE declared tested here, because the tally covers every clash.
    expect(body.tested_pairs.length).toBeGreaterThan(0);
    void panel;
  });

  it("never declares the intra-model DIAGONAL tested — a federated run cannot examine it", async () => {
    // `clash.detect_federated` skips any pair whose two elements carry the same model tag
    // (`if tags[i] == tags[j]: continue`), because an intra-model overlap is a beam-column joint,
    // not a coordination finding. So STR×STR is never tested by this run — and declaring it tested,
    // with no findings for it, makes `soft_clash.matrix` report it `clean`. That is this item's own
    // defect one level down: a premise the caller supplies that the run cannot support.
    const { matrixCalls } = await run(TRUNCATED);
    btn("Discipline-pair matrix").click();
    await flush();
    const body = matrixCalls[0] as { tested_pairs: [string, string][] };
    expect(body.tested_pairs.length, "no pair is declared tested at all — the check below would "
      + "then pass by vacuity").toBeGreaterThan(0);
    expect(body.tested_pairs.filter(([a, b]) => a === b),
      "a same-model pair is declared tested; the federated run excluded it by construction")
      .toEqual([]);
    // …and the cross pairs ARE still declared, so the filter has not thrown the coverage away.
    // Order-independent: the panel sends the pair in the disciplines' own order and the server's
    // `pair_key` is what normalises it, so asserting a direction here would pin the wrong thing.
    expect(body.tested_pairs.map((pr) => [...pr].sort().join("|")).sort())
      .toEqual(["ARC|MEP", "ARC|STR", "MEP|STR"]);
  });

  it("declares NOTHING tested when the run is truncated and no tally came back", async () => {
    // An older server truncates and sends no `pair_counts`. Falling back to the page would resume
    // the defect silently, so the honest degradation is the engine's third state: a pair with no
    // evidence is UNTESTED, not clean.
    const { matrixCalls } = await run({ ...TRUNCATED, pair_counts: undefined });
    btn("Discipline-pair matrix").click();
    await flush();
    const body = matrixCalls[0] as { tested_pairs: [string, string][] };
    expect(body.tested_pairs, "a truncated run with no tally may not declare a pair tested")
      .toEqual([]);
  });

  it("still declares the pairs tested on a run that was NOT truncated", async () => {
    // The mirror of the check above: without it, "declare nothing" would pass by never declaring
    // anything, and every complete run would report a fully untested matrix.
    const { matrixCalls } = await run({
      ...TRUNCATED, truncated: false, count: PAGE.length, pair_counts: undefined });
    btn("Discipline-pair matrix").click();
    await flush();
    const body = matrixCalls[0] as { tested_pairs: [string, string][];
      findings: { discipline_a: string }[] };
    expect(body.tested_pairs.length).toBeGreaterThan(0);
    expect(body.findings.length, "with no tally and nothing truncated, the page IS the run")
      .toBe(PAGE.length);
  });

  it("says how many of the run the list shows — the two numbers used to disagree silently",
    async () => {
      const { panel } = await run(TRUNCATED);
      const header = [...panel.querySelectorAll(".section-title")]
        .map((e) => e.textContent ?? "").find((t) => t.includes("click to inspect")) ?? "";
      expect(panel.textContent, "the summary states the whole run").toContain("1438 clashes");
      expect(header, "the list header must name both numbers, not just its own")
        .toContain("200 of 1438 clashes");
      expect(header).toContain("list capped");
    });

  it("names one number when nothing is hidden", async () => {
    const { panel } = await run({ ...TRUNCATED, truncated: false, count: PAGE.length });
    const header = [...panel.querySelectorAll(".section-title")]
      .map((e) => e.textContent ?? "").find((t) => t.includes("click to inspect")) ?? "";
    expect(header).toContain("200 clashes");
    expect(header, "nothing is hidden, so there is no cap to disclose").not.toContain("of");
  });
});
