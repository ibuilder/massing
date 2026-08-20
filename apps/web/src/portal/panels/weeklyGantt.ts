/**
 * UX-GANTT — a week you can actually work, not a month-scale bar chart.
 *
 * The server Gantt (`schedule_viz.gantt_svg`) already paints percent-complete. What it does not
 * do is *this week*: seven day columns, crew/trade colour that is not a traffic light, and a
 * metric strip you can read without hovering. This file is that view. It consumes lookahead
 * rows (already on the API) so the Schedule panel does not grow a second fetch shape.
 *
 * Colour is `SERIES_PALETTE` — a trade is a series, not a status.
 */
import { SERIES_PALETTE, chartColor } from "../../ui/charts";

export type WeekActivity = {
  name: string;
  trade?: string;
  start?: string;
  finish?: string;
  percent: number;
  crew_size?: number;
};

const DAY_MS = 86_400_000;

export function parseDay(s: string | undefined): Date | null {
  if (!s) return null;
  const d = new Date(`${s.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Monday 00:00 UTC of the week containing `d` (ISO week, Mon–Sun). */
export function mondayUtc(d: Date): Date {
  const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
  const day = x.getUTCDay();
  x.setUTCDate(x.getUTCDate() + (day === 0 ? -6 : 1 - day));
  return x;
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * DAY_MS);
}

export function dayIndex(weekStart: Date, d: Date): number {
  return Math.round((d.getTime() - weekStart.getTime()) / DAY_MS);
}

/** Inclusive start/finish clipped to [weekStart, weekStart+7). */
export function barInWeek(
  act: WeekActivity,
  weekStart: Date,
): { leftPct: number; widthPct: number } | null {
  const s = parseDay(act.start);
  const f = parseDay(act.finish);
  if (!s || !f || f < s) return null;
  const weekEnd = addDays(weekStart, 7);
  const a0 = s < weekStart ? weekStart : s;
  const a1 = addDays(f, 1); // finish date is inclusive
  const b1 = a1 < weekEnd ? a1 : weekEnd;
  if (b1 <= a0) return null;
  const left = dayIndex(weekStart, a0);
  const width = dayIndex(weekStart, b1) - left;
  if (width <= 0) return null;
  return { leftPct: (left / 7) * 100, widthPct: (width / 7) * 100 };
}

export function tradeColor(trade: string | undefined): string {
  const t = (trade || "").trim();
  if (!t) return chartColor(SERIES_PALETTE.length - 1);
  let h = 0;
  for (let i = 0; i < t.length; i++) h = (h + t.charCodeAt(i) * (i + 1)) % 997;
  return chartColor(h % SERIES_PALETTE.length);
}

export function weekMetrics(acts: readonly WeekActivity[], weekStart: Date): {
  count: number; avgPct: number; trades: number;
} {
  const inWeek = acts.filter((a) => barInWeek(a, weekStart));
  const trades = new Set(inWeek.map((a) => (a.trade || "").trim()).filter(Boolean));
  const avg = inWeek.length
    ? inWeek.reduce((n, a) => n + (Number(a.percent) || 0), 0) / inWeek.length
    : 0;
  return { count: inWeek.length, avgPct: avg, trades: trades.size };
}

export function flattenLookahead(
  weeks: { activities: WeekActivity[] }[] | undefined,
): WeekActivity[] {
  const out: WeekActivity[] = [];
  for (const w of weeks ?? []) out.push(...w.activities);
  return out;
}

export function renderWeeklyGantt(
  acts: readonly WeekActivity[],
  weekStart: Date,
): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "dash-card";
  wrap.dataset.weeklyGantt = "1";
  wrap.style.marginBottom = "10px";

  const title = document.createElement("div");
  title.className = "section-title";
  title.textContent = "This week";

  const m = weekMetrics(acts, weekStart);
  const strip = document.createElement("div");
  strip.className = "meta";
  strip.dataset.metrics = "1";
  const mon = weekStart.toISOString().slice(0, 10);
  if (!m.count) {
    strip.textContent = `Week of ${mon} — no activities in this interval.`;
    wrap.append(title, strip);
    return wrap;
  }
  strip.textContent =
    `Week of ${mon} · ${m.count} activit${m.count === 1 ? "y" : "ies"}`
    + ` · avg ${Math.round(m.avgPct)}%`
    + ` · ${m.trades} trade${m.trades === 1 ? "" : "s"}`;

  const days = document.createElement("div");
  days.style.cssText = "display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin:6px 0 4px;font-size:10px;color:var(--muted)";
  const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  for (const lab of labels) {
    const c = document.createElement("div");
    c.textContent = lab;
    c.style.textAlign = "center";
    days.appendChild(c);
  }

  const rows = document.createElement("div");
  for (const a of acts) {
    const bar = barInWeek(a, weekStart);
    if (!bar) continue;
    const row = document.createElement("div");
    row.style.cssText = "position:relative;height:22px;margin:2px 0;background:var(--panel2)";
    const fill = document.createElement("div");
    fill.style.cssText =
      `position:absolute;top:2px;bottom:2px;left:${bar.leftPct}%;width:${bar.widthPct}%;`
      + `background:${tradeColor(a.trade)};border-radius:3px;min-width:4px`;
    const lab = document.createElement("span");
    lab.style.cssText = "position:relative;z-index:1;padding:0 6px;font-size:11px;line-height:22px;white-space:nowrap";
    const crew = a.crew_size != null ? ` · crew ${a.crew_size}` : "";
    lab.textContent = `${a.name} · ${Math.round(a.percent)}%${a.trade ? ` · ${a.trade}` : ""}${crew}`;
    row.append(fill, lab);
    rows.appendChild(row);
  }

  wrap.append(title, strip, days, rows);
  return wrap;
}
