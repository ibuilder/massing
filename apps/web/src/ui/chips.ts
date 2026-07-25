/** UX-CHIPS — the one status/delta chip vocabulary (R19/UX-POLISH).
 *
 * Every list, money card, and lifecycle feed renders state through these three helpers instead of
 * hand-rolled spans, so "Sent → Viewed → Paid", "On track / Over budget", and "+12% · −$14K" look
 * and behave identically everywhere. Pure string builders over `esc()` — no DOM, trivially
 * unit-testable, safe for innerHTML composition.
 */
import { esc } from "./charts";

export type ChipTone = "ok" | "warn" | "bad" | "info" | "neutral";

// The platform's modules define ~112 distinct workflow states between them. The phrase patterns
// below only recognised 30 of those, so three quarters of every register rendered the same grey —
// the chip vocabulary looking uniform precisely where it exists to differentiate. These exact-match
// sets carry the real vocabulary; the patterns after them still catch multi-word phrases.
//
// The four meanings, kept deliberately distinct:
//   ok      — reached a good terminal state
//   info    — in flight, nothing wrong
//   warn    — still live, needs attention
//   bad     — refused, failed or missed
//   neutral — NO LONGER CURRENT (archived / superseded / void), or a word we don't recognise
const _OK = new Set(["accepted", "acknowledged", "adopted", "agreed", "approved", "awarded", "billed",
  "cleared", "closed", "committed", "complete", "completed", "confirmed", "corrected", "decided",
  "delivered", "done", "evidenced", "executed", "funded", "gc signed", "super signed", "installed",
  "issued", "leased", "mitigated", "paid", "passed", "published", "received", "reconciled", "recorded",
  "renewed", "resolved", "selected", "signed off", "sold", "tested", "under contract", "verified",
  "active", "answered", "sent"]);
const _INFO = new Set(["ae review", "agenda", "applied", "assessed", "assigned", "captured", "concept",
  "coming soon", "controlled", "dispositioned", "exported", "fieldwork", "gc review", "hearing",
  "identified", "in progress", "investigating", "logged", "made ready", "minutes", "ordered", "planned",
  "priced", "programmed", "proposed", "prospect", "quotes in", "ready", "reported", "requested",
  "reviewed", "returned", "rfq sent", "scheduled", "shared", "shortlisted", "sized", "wip"]);
const _WARN = new Set(["appealed", "deviated", "flagged", "holdover", "mitigating", "paused",
  "under revision"]);
const _BAD = new Set(["denied", "excluded", "failed", "missed", "not done", "rejected", "terminated",
  "withdrawn"]);
// deliberately neutral — these are not failures, they are records that have left the live set
const _RETIRED = new Set(["archived", "decommissioned", "demobilized", "exited", "inactive", "pulled",
  "retired", "superseded", "void", "voided"]);

/** Map a workflow-ish status word to a tone (shared vocabulary, override with `tone`). */
export function toneFor(status: string): ChipTone {
  const s = (status || "").toLowerCase().replace(/[_-]/g, " ").replace(/\s+/g, " ").trim();
  if (_RETIRED.has(s)) return "neutral";        // before the patterns: "void" must not read as bad
  if (_OK.has(s)) return "ok";
  if (_BAD.has(s)) return "bad";
  if (_WARN.has(s)) return "warn";
  if (_INFO.has(s)) return "info";
  // multi-word / free-text phrases the exact sets can't enumerate ("3 days overdue", "on track")
  if (/(over budget|overdue|rejected|failed|blocked|critical|error|declined|expired|red)/.test(s)) return "bad";
  if (/(at risk|warning|urgent|due soon|hold|yellow|behind)/.test(s)) return "warn";
  if (/(approved|paid|won|complete|closed|resolved|published|active|on track|passed|ok|green)/.test(s)) return "ok";
  if (/(pending|in review|in progress|submitted|sent|viewed|draft|open|rfq|upcoming|info)/.test(s)) return "info";
  return "neutral";
}

/** A timestamped status chip: `statusChip("Approved", { ts: "2026-07-24" })`. */
export function statusChip(label: string, opts: { tone?: ChipTone; ts?: string | null; title?: string } = {}): string {
  const tone = opts.tone ?? toneFor(label);
  const ts = opts.ts ? `<span class="chip2-ts">${esc(shortDate(opts.ts))}</span>` : "";
  const title = opts.title ?? (opts.ts ? `${label} — ${opts.ts}` : label);
  return `<span class="chip2 chip2-${tone}" title="${esc(title)}">${esc(label)}${ts}</span>`;
}

/** A metric delta chip: sign decides color (flip with `goodWhenNegative` for costs). */
export function deltaChip(value: number, opts: { pct?: boolean; currency?: boolean; goodWhenNegative?: boolean; digits?: number } = {}): string {
  if (!Number.isFinite(value)) return "";
  const digits = opts.digits ?? (opts.pct ? 1 : 0);
  const mag = Math.abs(value);
  const num = opts.currency ? fmtMoney(mag) : mag.toFixed(digits);
  const text = `${value > 0 ? "+" : value < 0 ? "−" : "±"}${num}${opts.pct ? "%" : ""}`;
  const goodPositive = !opts.goodWhenNegative;
  const tone: ChipTone = value === 0 ? "neutral" : (value > 0) === goodPositive ? "ok" : "bad";
  const arrow = value === 0 ? "" : value > 0 ? "▴" : "▾";
  return `<span class="chip2 chip2-${tone} chip2-delta">${arrow}${esc(text)}</span>`;
}

/** UX-KPI — a dashboard KPI header: metric tiles + a deterministic one-line narrative. */
export function kpiHeader(items: { label: string; value: string; delta?: number; deltaPct?: boolean;
                                   goodWhenNegative?: boolean }[],
                          narrative?: string): string {
  const tiles = items.map((k) =>
    `<div class="kpi-tile"><div class="kpi-value">${esc(k.value)}${k.delta !== undefined
      ? " " + deltaChip(k.delta, { pct: k.deltaPct, goodWhenNegative: k.goodWhenNegative }) : ""}</div>` +
    `<div class="kpi-label">${esc(k.label)}</div></div>`).join("");
  const line = narrative ? `<div class="kpi-narrative">${esc(narrative)}</div>` : "";
  return `<div class="kpi-header"><div class="kpi-row">${tiles}</div>${line}</div>`;
}

/** "3 jobs on track, 1 over budget" — a template-string narrative, never an LLM. */
export function countNarrative(pairs: [number, string][], zero = "Nothing needs attention"): string {
  const parts = pairs.filter(([n]) => n > 0).map(([n, label]) => `${n} ${label}`);
  return parts.length ? parts.join(", ") : zero;
}

function shortDate(ts: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ts);
  return m ? `${m[2]}/${m[3]}` : ts;
}

function fmtMoney(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}
