import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { SpaceBenchmark } from "./spaceBenchmark";
import {
  benchmarkRows, benchmarkScope, exclusions, portfolioLine, reconciles,
} from "./spaceBenchmark";

/**
 * BENCH-DARK — the portfolio space benchmark, and the exclusion its own response did not carry.
 *
 * `spaceUtilBenchmarks` was frozen as callerless, so a firm could not see its portfolio's space
 * efficiency at all. **The engine fix is the finding, and it lived in a sentence.**
 * `benchmarking.space_utilization` said *"the projects skipped for the cap are counted, never
 * silently dropped"* — true of the cap, true of unreadable files, and false of the third exclusion:
 * a model that opens fine and models no `IfcSpace` hit `continue` and appeared in no count. It is
 * also the **common** one, so a portfolio of structural models answered `projects: 0,
 * skipped_over_cap: 0, unreadable_models: 0`, which reads as *no projects* when the truth is *no
 * project has spaces modelled* — and those have opposite remedies.
 *
 * The engine now returns `no_spaces` and `candidates`, so the counts **reconcile** and that is a
 * property a consumer can CHECK rather than a promise it must trust. `services/api/test_space_util.py`
 * asserts the identity server-side and was mutation-proved against the pre-fix engine.
 */

const bench = (over: Partial<SpaceBenchmark> = {}): SpaceBenchmark => {
  const rows = over.rows ?? [];
  const base: SpaceBenchmark = {
    area_per_person: 10, projects: rows.length, skipped_over_cap: 0, unreadable_models: 0,
    no_spaces: 0, candidates: rows.length, rows,
    portfolio: { total_area_m2: rows.reduce((n, r) => n + r.total_area_m2, 0),
                 total_capacity: rows.reduce((n, r) => n + r.capacity, 0),
                 median_m2_per_space: rows.length ? rows[0]!.m2_per_space : null },
    note: "Space capacity across the portfolio's modelled projects",
  };
  return { ...base, ...over };
};

const proj = (project: string, spaces: number, area: number) => ({
  project_id: project, project, space_count: spaces, total_area_m2: area,
  capacity: Math.floor(area / 10), m2_per_space: Math.round((area / spaces) * 10) / 10,
  top_type: "Office", top_type_area_m2: area,
});

describe("benchmarkScope — 'no spaces modelled' is not 'no projects'", () => {
  it("is the SHIPPED SHAPE: ten modelled projects, none with spaces", () => {
    // Before the engine fix this came back projects:0, skipped:0, unreadable:0 — indistinguishable
    // from an empty portfolio, and the two call for opposite actions.
    const b = bench({ projects: 0, rows: [], candidates: 10, no_spaces: 10 });
    const s = benchmarkScope(b);
    expect(s.kind).toBe("no-spaces");
    expect(s.tone).toBe("warn");
    expect(s.headline).toBe("None of 10 modelled project(s) is in the comparison");
    expect(s.detail).toContain("10 model no spaces (IfcSpace)");
    expect(s.detail).toContain("not an empty portfolio");
  });

  it("an actually empty portfolio says so instead", () => {
    const s = benchmarkScope(bench({ candidates: 0, projects: 0, rows: [] }));
    expect(s.kind).toBe("none");
    expect(s.tone).toBe("");
    expect(s.headline).toBe("No modelled projects");
    expect(s.detail).toContain("has a source IFC");
    expect(s.detail).not.toContain("space data");
  });

  it("names every exclusion when the comparison is partial", () => {
    const b = bench({ rows: [proj("A", 10, 1000)], projects: 1, candidates: 16,
                      no_spaces: 2, unreadable_models: 1, skipped_over_cap: 12 });
    const s = benchmarkScope(b);
    expect(s.kind).toBe("partial");
    expect(s.tone).toBe("warn");
    expect(s.headline).toBe("1 of 16 modelled project(s) compared");
    expect(s.detail).toContain("the median and the totals are over those 1");
    expect(s.detail).toContain("2 model no spaces");
    expect(s.detail).toContain("1 could not be read");
    expect(s.detail).toContain("12 were past this call's 12-model cap");
  });

  it("is `ok` only when every candidate is in the comparison", () => {
    const s = benchmarkScope(bench({ rows: [proj("A", 10, 1000), proj("B", 5, 400)] }));
    expect(s.kind).toBe("full");
    expect(s.tone).toBe("ok");
    expect(s.headline).toBe("All 2 modelled project(s) compared");
    expect(s.detail).not.toContain("excluded");
  });

  it("says so when the server's own counts do NOT add up", () => {
    // A coverage line computed from counts that do not reconcile is worse than none, so the
    // disagreement is surfaced rather than papered over with a confident fraction.
    const b = bench({ rows: [proj("A", 10, 1000)], projects: 1, candidates: 9, no_spaces: 1 });
    expect(reconciles(b)).toBe(false);
    expect(benchmarkScope(b).detail).toContain("do not add up");
  });

  it("reconciles when the four counts sum to the denominator", () => {
    expect(reconciles(bench({ rows: [proj("A", 2, 100)], projects: 1, candidates: 4,
                              no_spaces: 2, unreadable_models: 1 }))).toBe(true);
  });

  it("carries no markup — the panel escapes it", () => {
    for (const b of [bench(), bench({ candidates: 3, projects: 0, no_spaces: 3 }),
                     bench({ rows: [proj("A", 1, 10)], candidates: 2, no_spaces: 1 })]) {
      const s = benchmarkScope(b);
      expect(`${s.headline}${s.detail}`).not.toMatch(/[<>]/);
    }
  });
});

describe("exclusions — only the non-zero ones, in the order a reader can act on", () => {
  it("omits the zeros so a clean portfolio carries no permanent warning", () => {
    expect(exclusions(bench())).toEqual([]);
  });

  it("puts the actionable reason first", () => {
    const e = exclusions(bench({ no_spaces: 1, unreadable_models: 2, skipped_over_cap: 3 }));
    expect(e.map((x) => x.n)).toEqual([1, 2, 3]);
    expect(e[0]!.reason).toContain("no spaces");
  });
});

describe("benchmarkRows and portfolioLine", () => {
  it("compares each project against the portfolio median", () => {
    const b = bench({ rows: [proj("Tower", 10, 1000), proj("Annex", 10, 500)],
                      portfolio: { total_area_m2: 1500, total_capacity: 150,
                                   median_m2_per_space: 50 } });
    const [tower, annex] = benchmarkRows(b);
    expect(tower!.perSpace).toBe("100 m²");
    expect(tower!.vsMedian).toBe("+100%");
    expect(annex!.vsMedian).toBe("0%");
  });

  it("refuses the comparison when there is ONE project — a median of one is itself", () => {
    const b = bench({ rows: [proj("Only", 10, 1000)] });
    expect(benchmarkRows(b)[0]!.vsMedian).toBe("—");
    expect(portfolioLine(b)).toContain("one project, so the median is itself");
  });

  it("shows a dash rather than a number when the median is absent", () => {
    const b = bench({ rows: [proj("A", 1, 10), proj("B", 1, 20)],
                      portfolio: { total_area_m2: 30, total_capacity: 3,
                                   median_m2_per_space: null } });
    expect(benchmarkRows(b).every((r) => r.vsMedian === "—")).toBe(true);
    expect(portfolioLine(b)).toContain("median — per space");
  });

  it("states the standard the capacity was computed at", () => {
    expect(portfolioLine(bench({ area_per_person: 14, rows: [proj("A", 2, 100)] })))
      .toContain("at 14 m²/person");
  });

  it("shows a dash for a project with no dominant space type", () => {
    const b = bench({ rows: [{ ...proj("A", 1, 10), top_type: null, top_type_area_m2: null }] });
    expect(benchmarkRows(b)[0]!.top).toBe("—");
  });
});

/** **The engine side**, read rather than assumed: the counts this module states must exist and the
 *  `continue` that used to be silent must still be counted. */
describe("the engine these readings are about", () => {
  const SRC = readFileSync("../../services/api/src/aec_api/benchmarking.py", "utf8");

  it("counts the readable-but-spaceless model instead of dropping it", () => {
    expect(SRC).toContain("no_spaces += 1");
    expect(SRC).toContain('"no_spaces": no_spaces,');
  });

  it("returns the denominator, so coverage is stated rather than inferred", () => {
    expect(SRC).toContain('"candidates": len(rows),');
  });

  it("still counts the other two exclusions", () => {
    expect(SRC).toContain('"skipped_over_cap": skipped_cap, "unreadable_models": unreadable,');
  });
});

/** The render, pinned at the source: a reading nothing calls is the MACRO-DARK mutation. */
describe("the reading reaches the portfolio panel", () => {
  const PF = readFileSync("src/portal/panels/portfolio.ts", "utf8");

  it("calls the benchmark and renders its scope, both halves", () => {
    expect(PF).toContain("ctx.host.api.spaceUtilBenchmarks()");
    expect(PF).toContain("const scope = benchmarkScope(sb)");
    expect(PF).toContain("esc(scope.headline)");
    expect(PF).toContain("why.textContent = scope.detail");
  });

  it("renders the table and the portfolio line only when something was compared", () => {
    expect(PF).toContain("if (sb.projects) {");
    expect(PF).toContain("portfolioLine(sb)");
    expect(PF).toContain("benchmarkRows(sb)");
  });

  it("escapes every cell — a project name is user text in innerHTML", () => {
    expect(PF).toContain("<td>${esc(r.project)}</td>");
    expect(PF).toContain("${esc(r.vsMedian)}");
  });

  it("APPENDS the card — a section built and never rendered is the recurring mutation", () => {
    // Found by mutation: `ctx.root.appendChild(card)` -> `void card` left every assertion above
    // green, because they prove the reading is COMPUTED and nothing proved it is on screen. The
    // anchor is the section's own closing sequence rather than the bare append, since `card` is a
    // local name several sections in this file share and a loose pin would pass on any of them.
    expect(PF).toContain("      note.textContent = sb.note;\n"
      + "      card.appendChild(note);\n"
      + "      ctx.root.appendChild(card);");
    // The limit, stated rather than left to be discovered: this is a SOURCE pin, so it cannot see a
    // render wrapped in a condition that is never true. The DOM complement is not built here
    // because this section sits inside `executivePortfolio().then(…)`, so reaching it needs that
    // response's full KPI shape plus six more stubs — the same bargain `reportCenter`'s pins make.
    expect(PF).toContain("void ctx.host.api.spaceUtilBenchmarks().then((sb) => {");
  });
});
