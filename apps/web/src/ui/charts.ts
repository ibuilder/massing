/**
 * charts.ts — a tiny, dependency-free SVG chart kit, themed via CSS variables.
 *
 * Every function returns a self-contained `<svg>` string (width:100%, responsive viewBox) so charts
 * drop straight into innerHTML alongside the app's hand-rolled tables — no library, fully offline,
 * works on the dark and light themes. Bars/points carry `<title>` tooltips for hover detail.
 *
 * Construction/RE best-practice set: multi-series line (EVM S-curve), grouped + stacked bars,
 * waterfall (JV / sources-uses), tornado (sensitivity), histogram (Monte Carlo), donut, progress.
 */

const PALETTE = ["var(--accent)", "#33d17a", "#e6a700", "#9b7cff", "#4ac6e2", "#e2554a", "#e07b39"];
const POS = "#33d17a";
const NEG = "#e2554a";
const GRID = "var(--line)";
const AXIS = "var(--muted)";

export function chartColor(i: number): string { return PALETTE[i % PALETTE.length] ?? PALETTE[0]!; } // safe: PALETTE is a non-empty literal

export function esc(s: unknown): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Compact number: 1.2B / 3.4M / 450k / 87. */
export function compact(n: number): string {
  if (!isFinite(n)) return "—";
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  if (a >= 1e9) return s + (a / 1e9).toFixed(a >= 1e10 ? 0 : 1).replace(/\.0$/, "") + "B";
  if (a >= 1e6) return s + (a / 1e6).toFixed(a >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (a >= 1e3) return s + Math.round(a / 1e3) + "k";
  return s + Math.round(a);
}
export const money = (n: number): string => (n < 0 ? "-$" : "$") + compact(Math.abs(n));

/**
 * R24-CHARTS-GRAMMAR ② — **one** full-precision currency format, for tables and inline figures.
 *
 * `money()` is the compact form for axis labels (`$4.3M`); this is the grouped form for a number a
 * reader is expected to check (`$4,250,000`). Both existed in spirit and neither was shared: a
 * `const usd = …` was redefined **eighteen times** across the panels, in five different behaviours.
 *
 * Ten of those eighteen were written `` `$${Math.round(n).toLocaleString()}` ``, which renders a
 * negative as **`$-1,000`** — the currency sign on the wrong side of the minus. Three sites had
 * already noticed and written `(n < 0 ? "−$" : "$")`, so the same panel set disagreed with itself
 * about how a loss looks. This is that spelling, promoted.
 *
 * `null` renders as an em-dash, not `$0`. Absent money and no money are different facts, and the one
 * that reads as a plausible zero is the dangerous one — the same rule the vitals strip and the run
 * diff both follow.
 */
export const usd = (n: number | null | undefined): string =>
  n == null ? "—" : (n < 0 ? "−$" : "$") + Math.round(Math.abs(n)).toLocaleString();

/**
 * A grouped count — thousands separators, no currency.
 *
 * Exists because one of the eighteen (`operations.ts`, the stormwater card) was a `const usd` that
 * emitted **no dollar sign at all**, and it was right not to: it formats cubic feet and square feet.
 * The name was the defect, not the output, and swapping it for the currency helper would have put a
 * `$` in front of a detention volume. Worth stating, because "18 copies of a money formatter" was
 * the obvious reading and it was wrong about one of them.
 */
export const qty = (n: number | null | undefined): string =>
  n == null ? "—" : Math.round(n).toLocaleString();

type Fmt = (n: number) => string;

/**
 * R24-CHARTS-GRAMMAR — one no-data state, for every chart.
 *
 * The audit's finding 15: this is a dependency-free SVG kit that "has not been given a grammar", and
 * without shared rules the charts drift apart as the surfaces multiply. The first rule is the one
 * that was actually costing something: **only `histogram` handled empty input.** The other twelve
 * rendered their frame — axes, four gridlines, a legend — with nothing in it.
 *
 * Nothing was broken (no `NaN` reached any path), which is exactly why it survived: an empty axis
 * frame does not look like a defect, it looks like a chart. It is indistinguishable from one whose
 * data failed to load, and it appears at the moment a user is least able to tell the difference — on
 * a project that has not got there yet. That is the same failure `noProjectHtml` exists to prevent
 * one layer up, and the same rule the vitals strip follows: an absent number renders as an em-dash
 * with its reason, never as a plausible zero.
 *
 * `CHART_KINDS` below is the enforced part. `charts.test.ts` asserts every name in it returns this
 * state for empty input, **and** that every exported function returning an `<svg>` is in the list —
 * so a fourteenth chart added without an empty state fails the build rather than shipping a frame.
 */
export const NO_DATA_MARK = "no data";

export function noData(title: string, height: number, vb = 150): string {
  return wrap(vb, txt(150, vb / 2, NO_DATA_MARK, { anchor: "middle" }), title, height);
}

/**
 * Every chart function, by name. The list a test walks — not documentation.
 *
 * `progressBar` and `sparkline` are deliberately absent: neither renders a frame (one is a div, the
 * other a 90×20 inline squiggle), so there is no empty grid to mistake for data. `sparkline` already
 * returns a blank `<svg>` under two points, which is the right answer for something that sits inside
 * a table cell.
 */
export const CHART_KINDS = [
  "lineChart", "scatterQuadrant", "groupedBar", "stackedBar",
  "waterfall", "tornado", "histogram", "donut", "signedBars",
] as const;

/**
 * R24-CHARTS-GRAMMAR ② — one tick style, one legend position, one currency format.
 *
 * The no-data rule shipped first because it was costing something. These three are the rest of the
 * audit's finding 15, and they were **not** cosmetic drift — measured before touching anything:
 *
 * * **Ticks.** Three charts hand-rolled the same `for (k = 0; k <= 4)` gridline loop, and the copies
 *   had already diverged: `lineChart` labelled `max − (k/4)(max − min)` while `groupedBar` and
 *   `waterfall` labelled `max − (k/4)·max`, which is a different axis whenever the minimum is not
 *   zero. Meanwhile **`stackedBar` drew no gridlines at all** — just a zero rule — so a cash-flow
 *   chart and a budget chart sitting in the same panel were read against different furniture.
 * * **Legend.** Four hand-rolled copies of `x=L y=9 font-size=8`. Consistent today by coincidence,
 *   and a fifth chart would have been consistent only if whoever wrote it copied the right neighbour.
 * * **Currency.** `money()` existed and nothing made a chart *use* it. A caller had to remember to
 *   pass `fmt: money`, so a sources-and-uses waterfall printed `1.2M` with no `$` whenever they
 *   forgot — and a bare number in a finance panel is read as whatever unit the reader assumes.
 *
 * `unit` is the fix for the third, and it is a different kind of option on purpose: it says what the
 * numbers **are**, not how to print them. `fmt` still wins when given, because a caller with a real
 * formatting need should not have to fight the grammar — but nobody has to remember `money` again.
 */
export type Unit = "money" | "percent" | "count";

const UNIT_FMT: Record<Unit, Fmt> = {
  money: (n) => money(n),
  percent: (n) => `${n.toFixed(n === Math.round(n) ? 0 : 1)}%`,
  count: (n) => compact(n),
};

/** The one place a chart decides how to print a number: explicit `fmt`, else the unit, else compact. */
export function fmtFor(opts: { fmt?: Fmt; unit?: Unit }): Fmt {
  return opts.fmt ?? (opts.unit ? UNIT_FMT[opts.unit] : compact);
}

/** Gridline count — five lines, four intervals, everywhere. Exported so the gate counts against it. */
export const Y_TICKS = 4;

/**
 * The y-axis: `Y_TICKS + 1` gridlines with a label on each, from `max` down to `min`.
 *
 * `min` defaults to 0 rather than being required, because that is the case three of the four callers
 * had inlined — but it is a parameter, because `lineChart` genuinely needs a non-zero floor and
 * silently clamping it to 0 is how the copies diverged in the first place.
 */
export function yGrid(box: { L: number; R: number; T: number; B: number; W: number; H: number },
                      max: number, min: number, fmt: Fmt): string {
  let g = "";
  for (let k = 0; k <= Y_TICKS; k++) {
    const gy = box.T + (k / Y_TICKS) * (box.H - box.T - box.B);
    const gv = max - (k / Y_TICKS) * (max - min);
    g += `<line x1="${box.L}" y1="${gy.toFixed(1)}" x2="${box.W - box.R}" y2="${gy.toFixed(1)}" stroke="${GRID}" stroke-width="0.4"/>`;
    g += txt(box.L - 2, gy + 2, fmt(gv), { anchor: "end" });
  }
  return g;
}

/** The one legend: swatch + name, top-left above the plot, at the one size every chart shares. */
export function legendRow(items: readonly { name: string; color?: string }[], x: number, y = 9): string {
  if (!items.length) return "";
  const spans = items.map((it, i) =>
    `<tspan fill="${it.color ?? chartColor(i)}">■</tspan><tspan fill="${AXIS}"> ${esc(it.name)}  </tspan>`).join("");
  return `<text x="${x}" y="${y}" font-family="system-ui,sans-serif" font-size="8">${spans}</text>`;
}

const wrap = (vb: number, inner: string, title: string, h = 150): string =>
  `<svg viewBox="0 0 300 ${vb}" role="img" aria-label="${esc(title)}" preserveAspectRatio="none" `
  + `style="width:100%;height:${h}px;display:block;background:var(--panel2);border:1px solid var(--line);border-radius:6px">`
  + `<title>${esc(title)}</title>${inner}</svg>`;

const txt = (x: number, y: number, s: string, opts: { anchor?: string; size?: number; fill?: string; weight?: number } = {}): string =>
  `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-family="system-ui,sans-serif" font-size="${opts.size ?? 8}" `
  + `fill="${opts.fill ?? AXIS}" text-anchor="${opts.anchor ?? "start"}"${opts.weight ? ` font-weight="${opts.weight}"` : ""}>${esc(s)}</text>`;

// --- multi-series line (EVM S-curve: PV / EV / AC) ---------------------------
export function lineChart(series: { name: string; values: number[]; color?: string }[],
                          opts: { title?: string; fmt?: Fmt; unit?: Unit; xlabels?: string[]; height?: number } = {}): string {
  const fmt = fmtFor(opts);
  const W = 300, H = 150, L = 34, R = 8, T = 12, B = 18;
  if (!series.length || !series.some((s) => s.values.length)) return noData(opts.title ?? "chart", opts.height ?? 170);
  const n = Math.max(1, ...series.map((s) => s.values.length));
  const all = series.flatMap((s) => s.values);
  const max = Math.max(1, ...all), min = Math.min(0, ...all);
  const x = (i: number) => L + (i / Math.max(1, n - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const g = yGrid({ L, R, T, B, W, H }, max, min, fmt);
  const lines = series.map((s, si) => {
    const col = s.color ?? chartColor(si);
    const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const dots = s.values.map((v, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="1.3" fill="${col}"><title>${esc(s.name)} ${fmt(v)}</title></circle>`).join("");
    return `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.4"/>${dots}`;
  }).join("");
  const xl = (opts.xlabels ?? []).map((l, i) => i % Math.ceil((opts.xlabels!.length) / 6 || 1) === 0
    ? txt(x(i), H - 6, l, { anchor: "middle" }) : "").join("");
  return wrap(H, `${g}${lines}${xl}${legendRow(series, L)}`, opts.title ?? "line chart", opts.height ?? 160);
}

// --- CPI–SPI quadrant scatter (the EVM "bullseye") ---------------------------
export function scatterQuadrant(points: { label: string; x: number; y: number; kind?: string }[],
                                opts: { title?: string; center?: number; xLabel?: string; yLabel?: string; height?: number } = {}): string {
  const W = 300, H = 220, L = 30, R = 10, T = 12, B = 24;
  if (!points.length) return noData(opts.title ?? "CPI–SPI quadrant", opts.height ?? 230, H);
  const c = opts.center ?? 1.0;
  const span = Math.max(0.25, 0.5, ...points.flatMap((p) => [Math.abs(p.x - c), Math.abs(p.y - c)]));
  const lo = c - span * 1.15, hi = c + span * 1.15;
  const sx = (v: number) => L + ((v - lo) / (hi - lo)) * (W - L - R);
  const sy = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  const cx = sx(c), cy = sy(c), x0 = sx(lo), x1 = sx(hi), y0 = sy(lo), y1 = sy(hi);
  const tint = (ax: number, ay: number, bx: number, by: number, fill: string): string =>
    `<rect x="${Math.min(ax, bx).toFixed(1)}" y="${Math.min(ay, by).toFixed(1)}" width="${Math.abs(bx - ax).toFixed(1)}" height="${Math.abs(by - ay).toFixed(1)}" fill="${fill}" opacity="0.1"/>`;
  let g = tint(cx, cy, x1, y1, POS) + tint(x0, cy, cx, y1, "#e6a700")
        + tint(cx, cy, x1, y0, "#e6a700") + tint(x0, cy, cx, y0, NEG);
  g += `<line x1="${cx.toFixed(1)}" y1="${T}" x2="${cx.toFixed(1)}" y2="${(H - B).toFixed(1)}" stroke="${AXIS}" stroke-width="0.6" stroke-dasharray="2 2"/>`;
  g += `<line x1="${L}" y1="${cy.toFixed(1)}" x2="${(W - R).toFixed(1)}" y2="${cy.toFixed(1)}" stroke="${AXIS}" stroke-width="0.6" stroke-dasharray="2 2"/>`;
  for (const v of [lo, c, hi]) {
    g += txt(sx(v), H - 9, v.toFixed(2), { anchor: "middle" });
    g += txt(L - 2, sy(v) + 2, v.toFixed(2), { anchor: "end" });
  }
  g += points.map((p) => {
    const proj = p.kind === "project";
    const col = proj ? "var(--accent)" : (p.x >= c && p.y >= c ? POS : (p.x < c && p.y < c ? NEG : "#e6a700"));
    return `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="${proj ? 3.2 : 2}" fill="${col}" stroke="var(--panel2)" stroke-width="0.6"><title>${esc(p.label)} — SPI ${p.x.toFixed(2)} / CPI ${p.y.toFixed(2)}</title></circle>`;
  }).join("");
  g += txt(W / 2, H - 1, opts.xLabel ?? "SPI (schedule) →", { anchor: "middle", size: 7 });
  g += `<text transform="translate(8,${(T + (H - T - B) / 2).toFixed(1)}) rotate(-90)" font-family="system-ui,sans-serif" font-size="7" fill="${AXIS}" text-anchor="middle">${esc(opts.yLabel ?? "CPI (cost) →")}</text>`;
  return wrap(H, g, opts.title ?? "CPI–SPI quadrant", opts.height ?? 230);
}

// --- grouped bars (budget vs committed vs actual vs EAC) ---------------------
export function groupedBar(groups: { label: string; bars: { name: string; value: number; color?: string }[] }[],
                           opts: { title?: string; fmt?: Fmt; unit?: Unit; height?: number } = {}): string {
  const fmt = fmtFor(opts);
  const W = 300, H = 150, L = 34, R = 6, T = 14, B = 26;
  if (!groups.length) return noData(opts.title ?? "grouped bar", opts.height ?? 170);
  const max = Math.max(1, ...groups.flatMap((g) => g.bars.map((b) => b.value)));
  const gw = (W - L - R) / Math.max(1, groups.length);
  const names = groups[0]?.bars.map((b) => b.name) ?? [];
  let g = yGrid({ L, R, T, B, W, H }, max, 0, fmt);
  groups.forEach((grp, gi) => {
    const x0 = L + gi * gw, bw = (gw - 4) / Math.max(1, grp.bars.length);
    grp.bars.forEach((b, bi) => {
      const bh = (b.value / max) * (H - T - B), x = x0 + 2 + bi * bw, yb = (H - B) - bh;
      g += `<rect x="${x.toFixed(1)}" y="${yb.toFixed(1)}" width="${Math.max(bw - 1, 1).toFixed(1)}" height="${Math.max(bh, 0).toFixed(1)}" fill="${b.color ?? chartColor(bi)}"><title>${esc(grp.label)} · ${esc(b.name)}: ${fmt(b.value)}</title></rect>`;
    });
    g += txt(x0 + gw / 2, H - 14, grp.label, { anchor: "middle" });
  });
  return wrap(H, `${g}${legendRow(names.map((name) => ({ name })), L)}`,
    opts.title ?? "grouped bar", opts.height ?? 170);
}

// --- stacked bars (cash flow by year: operating / investing / financing) ----
export function stackedBar(groups: { label: string; segments: { name: string; value: number; color?: string }[] }[],
                           opts: { title?: string; fmt?: Fmt; unit?: Unit; height?: number } = {}): string {
  const fmt = fmtFor(opts);
  const W = 300, H = 150, L = 34, R = 6, T = 14, B = 22;
  if (!groups.length) return noData(opts.title ?? "stacked bar", opts.height ?? 170);
  const totals = groups.map((g) => g.segments.reduce((a, s) => a + Math.max(0, s.value), 0));
  const negs = groups.map((g) => g.segments.reduce((a, s) => a + Math.min(0, s.value), 0));
  const max = Math.max(1, ...totals), min = Math.min(0, ...negs);
  const y = (v: number) => T + (1 - (v - min) / (max - min || 1)) * (H - T - B);
  const gw = (W - L - R) / Math.max(1, groups.length);
  // The gridlines this chart never had. A cash-flow chart beside a budget chart was being read
  // against different furniture; the zero rule stays on top of them because a signed chart needs it.
  let g = yGrid({ L, R, T, B, W, H }, max, min, fmt)
    + `<line x1="${L}" y1="${y(0).toFixed(1)}" x2="${W - R}" y2="${y(0).toFixed(1)}" stroke="${AXIS}" stroke-width="0.5"/>`;
  groups.forEach((grp, gi) => {
    const x = L + gi * gw + 3, bw = gw - 6;
    let up = 0, dn = 0;
    grp.segments.forEach((s, si) => {
      if (s.value >= 0) { const y1 = y(up + s.value), h = y(up) - y1; up += s.value;
        g += `<rect x="${x.toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h, 0).toFixed(1)}" fill="${s.color ?? chartColor(si)}"><title>${esc(grp.label)} · ${esc(s.name)}: ${fmt(s.value)}</title></rect>`;
      } else { const y0 = y(dn), h = y(dn + s.value) - y0; dn += s.value;
        g += `<rect x="${x.toFixed(1)}" y="${y0.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(h, 0).toFixed(1)}" fill="${s.color ?? chartColor(si)}"><title>${esc(grp.label)} · ${esc(s.name)}: ${fmt(s.value)}</title></rect>`;
      }
    });
    g += txt(L + gi * gw + gw / 2, H - 10, grp.label, { anchor: "middle" });
  });
  const names = groups[0]?.segments.map((s) => s.name) ?? [];
  return wrap(H, `${g}${legendRow(names.map((name) => ({ name })), L)}`,
    opts.title ?? "stacked bar", opts.height ?? 170);
}

// --- waterfall (sources & uses / JV distribution) ---------------------------
export function waterfall(steps: { label: string; value: number; total?: boolean }[],
                          opts: { title?: string; fmt?: Fmt; unit?: Unit; height?: number } = {}): string {
  const fmt = fmtFor(opts);
  const W = 300, H = 150, L = 34, R = 6, T = 12, B = 26;
  if (!steps.length) return noData(opts.title ?? "waterfall", opts.height ?? 170);
  let run = 0; const tops: number[] = []; const bots: number[] = [];
  let peak = 0;
  for (const s of steps) {
    if (s.total) { bots.push(0); tops.push(s.value); peak = Math.max(peak, s.value); }
    else { const start = run; run += s.value; bots.push(Math.min(start, run)); tops.push(Math.max(start, run)); peak = Math.max(peak, Math.abs(start), Math.abs(run)); }
  }
  const max = Math.max(1, peak);
  const y = (v: number) => T + (1 - v / max) * (H - T - B);
  const bw = (W - L - R) / Math.max(1, steps.length) - 4;
  let g = yGrid({ L, R, T, B, W, H }, max, 0, fmt);
  steps.forEach((s, i) => {
    const x = L + i * ((W - L - R) / steps.length) + 2;
    const yt = y(tops[i] ?? 0), h = Math.max(y(bots[i] ?? 0) - yt, 1);
    const col = s.total ? "var(--accent)" : s.value >= 0 ? POS : NEG;
    g += `<rect x="${x.toFixed(1)}" y="${yt.toFixed(1)}" width="${Math.max(bw, 1).toFixed(1)}" height="${h.toFixed(1)}" fill="${col}"><title>${esc(s.label)}: ${fmt(s.value)}</title></rect>`;
    g += txt(x + bw / 2, H - 14, s.label.length > 8 ? s.label.slice(0, 8) + "…" : s.label, { anchor: "middle", size: 7 });
  });
  return wrap(H, g, opts.title ?? "waterfall", opts.height ?? 170);
}

// --- tornado (one-way sensitivity) ------------------------------------------
export function tornado(rows: { label: string; low: number; high: number }[],
                        opts: { title?: string; base?: number; fmt?: Fmt; height?: number } = {}): string {
  const fmt = opts.fmt ?? ((n: number) => n.toFixed(1) + "%");
  const W = 300, H = Math.max(60, 18 * rows.length + 24), L = 96, R = 8, T = 6;
  if (!rows.length) return noData(opts.title ?? "tornado", opts.height ?? 70, 60);
  const base = opts.base ?? 0;
  const span = Math.max(0.01, ...rows.flatMap((r) => [Math.abs(r.low - base), Math.abs(r.high - base)]));
  const x = (v: number) => (L + W) / 2 + ((v - base) / span) * ((W - L - R) / 2);
  const mid = (L + W) / 2;
  let g = `<line x1="${mid}" y1="${T}" x2="${mid}" y2="${H - 14}" stroke="${AXIS}" stroke-width="0.5"/>`
    + txt(mid, H - 4, `base ${fmt(base)}`, { anchor: "middle", size: 7 });
  rows.forEach((r, i) => {
    const yb = T + i * 18, h = 12;
    const xl = x(Math.min(r.low, r.high)), xh = x(Math.max(r.low, r.high));
    g += `<rect x="${xl.toFixed(1)}" y="${yb.toFixed(1)}" width="${Math.max(xh - xl, 1).toFixed(1)}" height="${h}" fill="var(--accent)" opacity="0.85"><title>${esc(r.label)}: ${fmt(r.low)} … ${fmt(r.high)}</title></rect>`;
    g += txt(L - 4, yb + 9, r.label, { anchor: "end", size: 7.5 });
  });
  return wrap(H, g, opts.title ?? "tornado", opts.height ?? Math.max(70, 20 * rows.length + 26));
}

// --- histogram (Monte Carlo distribution) -----------------------------------
export function histogram(values: number[], opts: { title?: string; bins?: number; fmt?: Fmt; markers?: { label: string; value: number }[]; height?: number } = {}): string {
  const fmt = opts.fmt ?? compact;
  const W = 300, H = 150, L = 8, R = 8, T = 10, B = 18;
  if (!values.length) return noData(opts.title ?? "histogram", opts.height ?? 160);
  const bins = opts.bins ?? 24;
  const lo = Math.min(...values), hi = Math.max(...values), w = (hi - lo) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const v of values) counts[Math.min(bins - 1, Math.floor((v - lo) / w))]++;
  const cmax = Math.max(1, ...counts);
  const bw = (W - L - R) / bins;
  let g = counts.map((c, i) => {
    const bh = (c / cmax) * (H - T - B), x = L + i * bw, y = (H - B) - bh;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw - 0.4, 0.6).toFixed(1)}" height="${bh.toFixed(1)}" fill="var(--accent)" opacity="0.8"><title>${fmt(lo + i * w)}–${fmt(lo + (i + 1) * w)}: ${c}</title></rect>`;
  }).join("");
  const mx = (v: number) => L + ((v - lo) / (hi - lo || 1)) * (W - L - R);
  for (const m of opts.markers ?? []) {
    const x = mx(m.value);
    g += `<line x1="${x.toFixed(1)}" y1="${T}" x2="${x.toFixed(1)}" y2="${H - B}" stroke="${POS}" stroke-width="0.8" stroke-dasharray="2 2"/>`
      + txt(x, T + 6, m.label, { anchor: "middle", size: 7, fill: POS });
  }
  g += txt(L, H - 6, fmt(lo)) + txt(W - R, H - 6, fmt(hi), { anchor: "end" });
  return wrap(H, g, opts.title ?? "histogram", opts.height ?? 160);
}

// --- donut (status / mix) ---------------------------------------------------
export function donut(slices: { label: string; value: number; color?: string }[],
                      opts: { title?: string; center?: string; height?: number } = {}): string {
  const total = slices.reduce((a, s) => a + Math.max(0, s.value), 0) || 1;
  const cx = 75, cy = 75, r = 55, ri = 34;
  if (!slices.length) return noData(opts.title ?? "donut", opts.height ?? 160);
  let a0 = -Math.PI / 2, g = "";
  slices.forEach((s, i) => {
    const frac = Math.max(0, s.value) / total, a1 = a0 + frac * 2 * Math.PI;
    const large = frac > 0.5 ? 1 : 0;
    const p = (ang: number, rad: number) => `${(cx + rad * Math.cos(ang)).toFixed(2)} ${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    g += `<path d="M ${p(a0, r)} A ${r} ${r} 0 ${large} 1 ${p(a1, r)} L ${p(a1, ri)} A ${ri} ${ri} 0 ${large} 0 ${p(a0, ri)} Z" fill="${s.color ?? chartColor(i)}"><title>${esc(s.label)}: ${s.value} (${Math.round(frac * 100)}%)</title></path>`;
    a0 = a1;
  });
  if (opts.center) g += txt(cx, cy + 4, opts.center, { anchor: "middle", size: 13, fill: "var(--text)", weight: 700 });
  // The donut's legend sits under the ring rather than above a plot it does not have -- the one
  // legitimate position difference, and it still goes through `legendRow` so the swatch, the size and
  // the spacing cannot drift from the other eight.
  const legend = legendRow(slices.map((sl, i) => ({ name: sl.label, color: sl.color ?? chartColor(i) })), 150, 78);
  return `<svg viewBox="0 0 300 150" role="img" aria-label="${esc(opts.title ?? "donut")}" style="width:100%;height:${opts.height ?? 160}px;display:block;background:var(--panel2);border:1px solid var(--line);border-radius:6px">`
    + `<title>${esc(opts.title ?? "donut")}</title>${g}${legend}</svg>`;
}

// --- progress bar / gauge ---------------------------------------------------
export function progressBar(value: number, max: number, opts: { label?: string; color?: string; suffix?: string } = {}): string {
  const pct = max ? Math.max(0, Math.min(1, value / max)) : 0;
  const col = opts.color ?? (pct >= 1 ? POS : pct >= 0.5 ? "var(--accent)" : "#e6a700");
  return `<div style="margin:3px 0"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted)">`
    + `<span>${esc(opts.label ?? "")}</span><span>${Math.round(pct * 100)}%${opts.suffix ? " " + esc(opts.suffix) : ""}</span></div>`
    + `<div style="height:7px;background:var(--bg);border:1px solid var(--line);border-radius:4px;overflow:hidden">`
    + `<div style="width:${(pct * 100).toFixed(1)}%;height:100%;background:${col}"></div></div></div>`;
}

// --- sparkline --------------------------------------------------------------
export function sparkline(values: number[], opts: { color?: string; width?: number; height?: number } = {}): string {
  const w = opts.width ?? 90, h = opts.height ?? 20;
  if (values.length < 2) return `<svg width="${w}" height="${h}"></svg>`;
  const max = Math.max(...values), min = Math.min(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1) * w).toFixed(1)},${(h - (v - min) / (max - min || 1) * h).toFixed(1)}`).join(" ");
  return `<svg width="${w}" height="${h}" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="${opts.color ?? "var(--accent)"}" stroke-width="1.2"/></svg>`;
}

// --- signed bars (equity cash flow) -----------------------------------------
export function signedBars(values: number[], opts: { title?: string; fmt?: Fmt; height?: number } = {}): string {
  const fmt = opts.fmt ?? compact;
  const W = 300, H = 90, pad = 6, mid = H / 2;
  if (!values.length) return noData(opts.title ?? "cash flow", opts.height ?? 90, H);
  const max = Math.max(1, ...values.map((v) => Math.abs(v)));
  const bw = (W - 2 * pad) / Math.max(1, values.length);
  const bars = values.map((v, i) => {
    const bh = (Math.abs(v) / max) * (mid - pad), x = pad + i * bw, y = v >= 0 ? mid - bh : mid;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(bw - 0.5, 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${v >= 0 ? POS : NEG}"><title>${fmt(v)}</title></rect>`;
  }).join("");
  return wrap(H, `<line x1="${pad}" y1="${mid}" x2="${W - pad}" y2="${mid}" stroke="${AXIS}" stroke-width="0.5"/>${bars}`,
    opts.title ?? "cash flow", opts.height ?? 90);
}
