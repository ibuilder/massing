import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import * as Charts from "./charts";
import {
  CHART_KINDS, NO_DATA_MARK,
  compact, money, chartColor, lineChart, groupedBar, stackedBar, waterfall,
  tornado, histogram, donut, progressBar, sparkline, signedBars, scatterQuadrant,
  Y_TICKS, usd, qty, SERIES_PALETTE, STATUS_GOOD, STATUS_WARN, STATUS_CRIT,
} from "./charts";

describe("number formatting", () => {
  it("compacts to k/M/B", () => {
    expect(compact(87)).toBe("87");
    expect(compact(1500)).toBe("2k");
    expect(compact(4_250_000)).toBe("4.3M");
    expect(compact(2_100_000_000)).toBe("2.1B");
    expect(compact(-3_400_000)).toBe("-3.4M");
  });
  it("money prefixes $ and keeps the sign", () => {
    expect(money(4_250_000)).toBe("$4.3M");
    expect(money(-1_200_000)).toBe("-$1.2M");
  });
  it("palette cycles", () => {
    expect(chartColor(0)).toBe(chartColor(7));   // 7 colors → wraps
    expect(chartColor(0)).toBe(SERIES_PALETTE[0]);
  });
});

describe("chart primitives produce valid svg", () => {
  it("lineChart draws a polyline per series with legend", () => {
    const svg = lineChart([
      { name: "PV", values: [0, 5, 12, 20] },
      { name: "EV", values: [0, 4, 10, 18] },
      { name: "AC", values: [0, 6, 13, 21] },
    ], { title: "EVM" });
    expect(svg.startsWith("<svg")).toBe(true);
    expect((svg.match(/<polyline/g) || []).length).toBe(3);
    expect(svg).toContain("PV"); expect(svg).toContain("AC");
    expect(svg).toContain("aria-label=\"EVM\"");
  });

  it("groupedBar renders a rect per bar with hover titles", () => {
    const svg = groupedBar([
      { label: "03", bars: [{ name: "Budget", value: 100 }, { name: "Actual", value: 80 }] },
      { label: "09", bars: [{ name: "Budget", value: 50 }, { name: "Actual", value: 70 }] },
    ], {});
    expect((svg.match(/<rect/g) || []).length).toBe(4);
    expect(svg).toContain("<title>03 · Budget: 100</title>");
  });

  it("stackedBar handles positive and negative segments", () => {
    const svg = stackedBar([
      { label: "Yr1", segments: [{ name: "Op", value: 50 }, { name: "Fin", value: -30 }] },
    ], {});
    expect(svg.match(/<rect/g)!.length).toBe(2);
  });

  it("waterfall accumulates and marks totals", () => {
    const svg = waterfall([
      { label: "Land", value: 4 }, { label: "Hard", value: 18 }, { label: "Total", value: 22, total: true },
    ], {});
    expect(svg.match(/<rect/g)!.length).toBe(3);
    expect(svg).toContain("Land: 4");
  });

  it("tornado centers bars on the base", () => {
    const svg = tornado([
      { label: "Exit cap", low: 8, high: 20 }, { label: "Rent", low: 11, high: 17 },
    ], { base: 14 });
    expect(svg.match(/<rect/g)!.length).toBe(2);
    expect(svg).toContain("Exit cap");
  });

  it("histogram bins values and draws P50 markers", () => {
    const vals = Array.from({ length: 200 }, (_, i) => i % 50);
    const svg = histogram(vals, { bins: 10, markers: [{ label: "P50", value: 25 }] });
    expect(svg.match(/<rect/g)!.length).toBe(10);
    expect(svg).toContain("P50");
    expect(histogram([], {})).toContain("no data");
  });

  it("donut emits a path per slice and a center label", () => {
    const svg = donut([{ label: "On track", value: 6 }, { label: "At risk", value: 2 }], { center: "8" });
    expect(svg.match(/<path/g)!.length).toBe(2);
    expect(svg).toContain(">8<");
  });

  it("progressBar clamps to 0..100% and labels", () => {
    expect(progressBar(150, 100, { label: "Spent" })).toContain("100%");
    expect(progressBar(25, 100, {})).toContain("25%");
    expect(progressBar(0, 0, {})).toContain("0%");      // no divide-by-zero
  });

  it("sparkline + signedBars render", () => {
    expect(sparkline([1, 2, 3, 2, 4])).toContain("<polyline");
    expect(sparkline([1])).toBe('<svg width="90" height="20"></svg>');   // too few points
    const sb = signedBars([-10, 5, -3, 8]);
    expect(sb.match(/<rect/g)!.length).toBe(4);
  });

  it("escapes labels (no raw injection)", () => {
    const svg = waterfall([{ label: "<x>", value: 1, total: true }], {});
    expect(svg).not.toContain("<x>");
    expect(svg).toContain("&lt;x&gt;");
  });

  it("scatterQuadrant plots a point per row + escapes labels", () => {
    const svg = scatterQuadrant([
      { label: "Project", x: 0.68, y: 0.95, kind: "project" },
      { label: "<cc>", x: 1.1, y: 0.9 },
    ]);
    expect(svg.match(/<circle/g)!.length).toBe(2);
    expect(svg).toContain("&lt;cc&gt;");            // label escaped in the <title>
    expect(svg).not.toContain("<cc>");
    expect(scatterQuadrant([])).toContain("<svg");   // empty is safe (no points)
  });
});

/**
 * R24-CHARTS-GRAMMAR — the first shared rule, enforced.
 *
 * "Empty is safe" was the old bar, and every chart cleared it: none of them emitted `NaN`. But safe
 * is not the same as honest. Twelve of thirteen rendered their axes, gridlines and legend with
 * nothing plotted, which is indistinguishable from a chart whose data failed to load — and it
 * appears exactly where a user cannot tell the difference, on a project that has not got there yet.
 *
 * The reason these assertions are written as a loop over `CHART_KINDS`, rather than one `it()` per
 * chart, is drift: a fourteenth chart is added by writing a function, and nothing about writing a
 * function reminds anyone that empty input has a house style. The second test closes that by
 * checking the *list itself* against the module's exports.
 */
describe("every chart says 'no data' rather than drawing an empty frame", () => {
  /** Minimal empty input per chart — all of them take an array first. */
  const EMPTY: Record<string, unknown[]> = Object.fromEntries(CHART_KINDS.map((k) => [k, [[]]]));

  for (const kind of CHART_KINDS) {
    it(`${kind} renders the shared no-data state`, () => {
      const fn = (Charts as unknown as Record<string, (...a: unknown[]) => string>)[kind]!;
      const out = fn(...EMPTY[kind]!);
      expect(out).toContain(NO_DATA_MARK);
      expect(out).toContain("<svg");            // still a valid, sized box — the layout must not jump
      expect(out).not.toMatch(/NaN|Infinity/);
    });
  }

  it("CHART_KINDS lists every chart the module exports — so a new one cannot skip the rule", () => {
    // Helpers go in this list; CHARTS do not. Anything exported and not named here must be a chart
    // that honours the whole grammar — which is why adding a helper is a deliberate edit here rather
    // than something that silently widens what the gate ignores.
    const HELPERS = ["esc", "compact", "money", "usd", "qty", "chartColor", "noData",
                     "fmtFor", "yGrid", "legendRow"];
    const exported = Object.entries(Charts as unknown as Record<string, unknown>)
      .filter(([name, v]) => typeof v === "function" && !HELPERS.includes(name))
      .map(([name]) => name);
    // progressBar returns a <div> and sparkline a bare inline <svg>; neither draws a frame that could
    // be mistaken for data, and both are documented as deliberate omissions in charts.ts.
    const framed = exported.filter((n) => !["progressBar", "sparkline"].includes(n));
    expect([...framed].sort()).toEqual([...CHART_KINDS].sort());
  });
});

/**
 * R24-CHARTS-GRAMMAR ② — one tick style, one legend position, one currency format.
 *
 * The rules are enforced two ways on purpose, because either alone is weak. The **behavioural**
 * assertions below check what a chart renders; the **source scan** checks that no chart hand-rolls
 * what the shared helper exists to provide. A behavioural check alone passes a copy-pasted loop that
 * happens to agree today, which is exactly the state this item found: three copies of the same
 * gridline loop, already diverged in what they labelled, and a fourth chart with no gridlines at all.
 */
describe("R24-CHARTS-GRAMMAR ② — the grammar is shared, not agreed-upon", () => {
  const SRC = readFileSync(resolve(__dirname, "charts.ts"), "utf8");

  /** Source with block comments and line comments stripped — a gate must not read its own prose. */
  const CODE = SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("the scan sees real code — otherwise every assertion below is vacuous", () => {
    expect(CODE.length).toBeGreaterThan(4000);
    expect(CODE).toContain("export function lineChart");
    expect(CODE).not.toContain("R24-CHARTS-GRAMMAR");     // the header comment really is stripped
  });

  it("no chart hand-rolls a gridline loop — yGrid is the only one", () => {
    // The exact shape that existed three times over. Matching the loop rather than the output is
    // what makes this a structural rule instead of a coincidence check.
    const loops = [...CODE.matchAll(/for\s*\(\s*let\s+k\s*=\s*0\s*;\s*k\s*<=\s*4/g)];
    expect(loops.map((m) => CODE.slice(m.index, m.index! + 40)),
      "gridlines belong to yGrid; a local loop is how the three copies diverged").toEqual([]);
  });

  it("no chart hand-rolls a legend <text> — legendRow is the only one", () => {
    const inline = [...CODE.matchAll(/<text x="\$\{L\}" y="9"/g)];
    expect(inline).toHaveLength(0);
    expect(CODE).toContain("export function legendRow");
  });

  it("every framed chart with a y-axis draws exactly Y_TICKS + 1 gridlines", () => {
    const grid = (svg: string) => (svg.match(/stroke="var\(--line\)" stroke-width="0\.4"/g) ?? []).length;
    const series = [{ name: "PV", values: [1, 5, 9] }, { name: "EV", values: [1, 4, 7] }];
    const groups = [{ label: "2026", bars: [{ name: "budget", value: 10 }, { name: "actual", value: 8 }] }];
    const stacks = [{ label: "2026", segments: [{ name: "op", value: 10 }, { name: "inv", value: -4 }] }];
    const steps = [{ label: "equity", value: 10 }, { label: "debt", value: 30 }];
    for (const [name, svg] of Object.entries({
      lineChart: Charts.lineChart(series),
      groupedBar: Charts.groupedBar(groups),
      stackedBar: Charts.stackedBar(stacks),
      waterfall: Charts.waterfall(steps),
    })) {
      expect(grid(svg), `${name} must draw ${Y_TICKS + 1} gridlines`).toBe(Y_TICKS + 1);
    }
  });

  it("...and stackedBar is the one that had NONE — the reason this rule exists", () => {
    // Guard against the fix being quietly reverted: a cash-flow chart beside a budget chart was
    // being read against different furniture. It also keeps its zero rule, which a signed chart needs.
    const svg = Charts.stackedBar([{ label: "2026", segments: [{ name: "op", value: 10 }, { name: "inv", value: -4 }] }]);
    expect((svg.match(/stroke="var\(--line\)" stroke-width="0\.4"/g) ?? []).length).toBe(Y_TICKS + 1);
    expect(svg).toContain(`stroke="var(--muted)" stroke-width="0.5"`);
  });

  describe("one currency format — `unit` says what the numbers ARE", () => {
    it("unit: money puts a $ on every axis label without the caller remembering a formatter", () => {
      const svg = Charts.waterfall([{ label: "equity", value: 4_000_000 }], { unit: "money" });
      expect(svg).toContain("$4M");
      expect(svg).not.toMatch(/>4M</);            // never the bare number it used to print
    });

    it("...and without it, the same chart prints no currency at all", () => {
      // The twin. Without this the assertion above would pass on an implementation that stuck a `$`
      // on everything, which would be a different bug in a percentage chart.
      const svg = Charts.waterfall([{ label: "equity", value: 4_000_000 }]);
      expect(svg).not.toContain("$4M");
      expect(svg).toContain("4M");
    });

    it("percent and count each get their own reading", () => {
      expect(Charts.fmtFor({ unit: "percent" })(12)).toBe("12%");
      expect(Charts.fmtFor({ unit: "percent" })(12.34)).toBe("12.3%");
      expect(Charts.fmtFor({ unit: "count" })(1500)).toBe("2k");
      expect(Charts.fmtFor({ unit: "money" })(-1500)).toBe("-$2k");
    });

    it("an explicit fmt still wins — the grammar is a default, not a cage", () => {
      expect(Charts.fmtFor({ unit: "money", fmt: (n) => `${n} EUR` })(5)).toBe("5 EUR");
      expect(Charts.fmtFor({})(1500)).toBe("2k");
    });
  });

  it("legendRow renders nothing for no series, rather than an empty <text>", () => {
    expect(Charts.legendRow([], 34)).toBe("");
    expect(Charts.legendRow([{ name: "PV" }], 34)).toContain("PV");
  });

  it("legendRow escapes a hostile series name", () => {
    expect(Charts.legendRow([{ name: '<script>x</script>' }], 34)).not.toContain("<script>");
  });
});

/**
 * R24-CHARTS-GRAMMAR ② — one currency format, enforced across the app rather than inside this module.
 *
 * The measurement that produced this rule: `const usd = …` was declared **eighteen times** across
 * `apps/web/src`, in five different behaviours. Ten of them wrote
 * `` `$${Math.round(n).toLocaleString()}` ``, which renders a negative as **`$-1,000`** — the sign on
 * the wrong side of the currency mark. Three had already fixed it locally, so the same panel set
 * disagreed with itself about how a loss looks, and which spelling you got depended on which file
 * you were reading.
 *
 * One of the eighteen was not a money formatter at all: the stormwater card's `usd` emitted no `$`
 * because it formats cubic feet. Converting it would have put a currency mark on a detention volume.
 * That is why `qty` exists, and why the rule below bans *declaring* a formatter rather than banning
 * the name — the name was the defect there, and a rule that only chased the name would have made the
 * output wrong to make the label right.
 */
describe("R24-CHARTS-GRAMMAR ② — one currency format for the whole app", () => {
  const SRC_DIR = resolve(__dirname, "..");

  function walk(dir: string, out: string[] = []): string[] {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) { walk(p, out); continue; }
      if (p.endsWith(".ts") && !p.endsWith(".test.ts") && !p.endsWith(".d.ts")) out.push(p);
    }
    return out;
  }

  const files = walk(SRC_DIR);

  it("scanned real source — otherwise the ban below is vacuous", () => {
    expect(files.length).toBeGreaterThan(100);
    expect(files.some((f) => f.endsWith("charts.ts"))).toBe(true);
  });

  it("no file declares its own currency formatter — `usd` is imported, not rewritten", () => {
    // Matches a DECLARATION, not a call: `const usd = ` / `const cmoney = ` / `const money = `.
    // Comments are stripped first, so this rule cannot flag the prose above that explains it — the
    // failure mode this repo has hit five separate times.
    const DECL = /(?:const|let|function)\s+(usd|cmoney|money2?|dollars)\s*[=(]/g;
    const hits: string[] = [];
    for (const f of files) {
      if (f.endsWith("charts.ts")) continue;             // the one place allowed to define them
      const code = readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      for (const m of code.matchAll(DECL)) hits.push(`${f.replace(SRC_DIR, "src")}: ${m[0]}`);
    }
    expect(hits, "import { usd } from ui/charts — eighteen local copies disagreed about how a "
      + "negative renders, and ten of them put the $ on the wrong side of the minus").toEqual([]);
  });

  it("...and the scan can actually say no", () => {
    // Vacuity twin: the regex must catch the exact declaration that was removed from ten files.
    const DECL = /(?:const|let|function)\s+(usd|cmoney|money2?|dollars)\s*[=(]/;
    expect(DECL.test('  const usd = (n: number) => `$${Math.round(n).toLocaleString()}`;')).toBe(true);
    expect(DECL.test('  const usd = (n: number) => cmoney(n);')).toBe(true);
    expect(DECL.test("  out.textContent = usd(total);")).toBe(false);   // a CALL is fine
  });

  describe("usd", () => {
    it("puts the currency mark outside the minus", () => {
      expect(usd(-1000)).toBe("−$1,000");
      expect(usd(-1000)).not.toBe("$-1,000");            // the spelling ten files had
      expect(usd(4_250_000)).toBe("$4,250,000");
      expect(usd(0)).toBe("$0");
    });

    it("renders absent money as an em-dash, never as $0", () => {
      // Absent money and no money are different facts, and the one that reads as a plausible zero is
      // the dangerous one.
      expect(usd(null)).toBe("—");
      expect(usd(undefined)).toBe("—");
      expect(usd(0)).not.toBe("—");
    });
  });

  describe("qty", () => {
    it("groups without a currency mark — it formats cubic feet, not dollars", () => {
      expect(qty(12_500)).toBe("12,500");
      expect(qty(12_500)).not.toContain("$");
      expect(qty(null)).toBe("—");
    });
  });
});

/**
 * R24-CHARTS-GRAMMAR ③ — series identity is not status.
 *
 * Slot 0 used to be `--accent` and slot 1 the same green as "passing". An S-curve then read as
 * "PV is the thing you can act on, EV is fine". Status hues stay for signed magnitude and the
 * quadrant; `chartColor` is a categorical ramp that does not include them.
 */
describe("R24-CHARTS-GRAMMAR ③ — series colour is not a traffic light", () => {
  const SRC = readFileSync(resolve(__dirname, "charts.ts"), "utf8");
  const CODE = SRC.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const STATUS = [STATUS_GOOD, STATUS_WARN, STATUS_CRIT] as const;

  it("the categorical ramp has seven slots and none of them is a status hue or --accent", () => {
    expect(SERIES_PALETTE).toHaveLength(7);
    for (const c of SERIES_PALETTE) {
      expect(STATUS, c).not.toContain(c);
      expect(c).not.toMatch(/accent|status-/);
    }
  });

  it("chartColor never returns a status hue", () => {
    for (let i = 0; i < 21; i++) {
      expect(STATUS, `slot ${i}`).not.toContain(chartColor(i));
    }
  });

  it("a multi-series line is categorical, not good/warn/crit", () => {
    const svg = lineChart([
      { name: "PV", values: [0, 5, 12] },
      { name: "EV", values: [0, 4, 10] },
      { name: "AC", values: [0, 6, 13] },
    ]);
    expect(svg).toContain(SERIES_PALETTE[0]);
    expect(svg).toContain(SERIES_PALETTE[1]);
    expect(svg).not.toContain(STATUS_GOOD);
    expect(svg).not.toContain(STATUS_CRIT);
    expect(svg).not.toContain("var(--accent)");
  });

  it("signed magnitude still uses the status hues — that is what they are for", () => {
    const sb = signedBars([-10, 5]);
    expect(sb).toContain(STATUS_CRIT);
    expect(sb).toContain(STATUS_GOOD);
    const wf = waterfall([{ label: "in", value: 4 }, { label: "out", value: -2 }]);
    expect(wf).toContain(STATUS_GOOD);
    expect(wf).toContain(STATUS_CRIT);
  });

  it("a progress bar's complete / low states are status; mid-flight is series 0", () => {
    expect(progressBar(100, 100, {})).toContain(STATUS_GOOD);
    expect(progressBar(10, 100, {})).toContain(STATUS_WARN);
    expect(progressBar(60, 100, {})).toContain(SERIES_PALETTE[0]);
  });

  it("each status hex is declared once — copies are how EV became 'passing'", () => {
    for (const hex of STATUS) {
      const hits = [...CODE.matchAll(new RegExp(hex.replace(/[.#]/g, "\\$&"), "g"))];
      expect(hits, hex).toHaveLength(1);
    }
  });
});
