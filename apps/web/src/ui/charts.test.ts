import { describe, expect, it } from "vitest";

import {
  compact, money, chartColor, lineChart, groupedBar, stackedBar, waterfall,
  tornado, histogram, donut, progressBar, sparkline, signedBars, scatterQuadrant,
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
