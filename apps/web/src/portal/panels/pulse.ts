/**
 * PROJECT PULSE — five numbers, each with a sentence naming what is actually at risk.
 *
 * Reconstructed from the R26 work-queue design. The list survived into `workQueue.ts`; the shell
 * around it did not, and neither did this. Its thesis is in the mockup's own subtitle: *you never
 * browse for work, work comes to you*. Pulse is the other half of that — you never assemble the
 * project's state from six dashboards, the state tells you what it is.
 *
 * **The number is not the point; the sentence is.** "Cost −0.7%" is a fact a chart already gives
 * you. "EAC under GMP. Three CORs unpriced could take that to +1.4%" tells you what to do before
 * lunch. So a card is *required* to say what would move the number, and when nothing would, it says
 * so plainly rather than padding with filler — `risk: null` renders as nothing, because a reassuring
 * sentence that means nothing teaches people to stop reading the card.
 *
 * This module is **pure**: engines in, cards out. Every input already exists (`modelHealth`,
 * `costSummary`/`evm`, `scheduleVariance`, `workQueue`, `proformaLive`) — Pulse invents no numbers of
 * its own, which is the rule that keeps it from becoming a sixth source of truth that disagrees with
 * the five panels it summarises.
 */

export type PulseTone = "good" | "watch" | "risk";

export interface PulseCard {
  key: "model" | "cost" | "schedule" | "work" | "deal";
  label: string;
  /** Pre-formatted for display — the caller must not re-format, or two screens will disagree. */
  value: string;
  tone: PulseTone;
  /** The state, in three or four words. */
  headline: string;
  /** What would change it, naming the specific thing. `null` when genuinely nothing is at risk. */
  risk: string | null;
}

/** What Pulse needs. Every field optional: a project mid-setup has no proforma and no schedule, and
 *  a card with no data must be **absent**, never shown as a confident zero. */
export interface PulseInput {
  model?: { score?: number | null; issues?: number | null; blocking?: string | null } | null;
  cost?: { variancePct?: number | null; unpricedChanges?: number | null; exposurePct?: number | null } | null;
  schedule?: { floatDays?: number | null; atRisk?: string | null } | null;
  work?: { open?: number | null; mine?: number | null; overdue?: string[] | null } | null;
  deal?: { irrPct?: number | null; band?: [number, number] | null; staleSince?: string | null } | null;
}

const pct = (n: number, dp = 1) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(dp)}%`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function modelCard(m: NonNullable<PulseInput["model"]>): PulseCard | null {
  if (m.score == null) return null;
  const issues = m.issues ?? 0;
  // "Integrity clean" is only sayable when it IS clean. Saying it beside a non-zero issue count is
  // the contradiction this repo already wrote a test to prevent elsewhere.
  return {
    key: "model", label: "Model health", value: String(Math.round(m.score)),
    tone: m.blocking ? "risk" : issues > 0 ? "watch" : "good",
    headline: issues === 0 ? "Integrity clean." : `${plural(issues, "open issue")}.`,
    risk: m.blocking ?? null,
  };
}

function costCard(c: NonNullable<PulseInput["cost"]>): PulseCard | null {
  if (c.variancePct == null) return null;
  const unpriced = c.unpricedChanges ?? 0;
  // The exposure sentence is the whole value of this card: a variance that is fine *today* and would
  // not be once the open changes are priced is the single most common way a job goes quietly wrong.
  const exposure = unpriced > 0 && c.exposurePct != null
    ? `${plural(unpriced, "change")} unpriced could take that to ${pct(c.exposurePct)}.`
    : null;
  return {
    key: "cost", label: "Cost", value: pct(c.variancePct),
    tone: c.variancePct > 0 ? "risk" : unpriced > 0 ? "watch" : "good",
    headline: c.variancePct <= 0 ? "Forecast under budget." : "Forecast over budget.",
    risk: exposure,
  };
}

function scheduleCard(s: NonNullable<PulseInput["schedule"]>): PulseCard | null {
  if (s.floatDays == null) return null;
  const f = Math.round(s.floatDays);
  return {
    key: "schedule", label: "Schedule",
    value: `${f > 0 ? "+" : f < 0 ? "−" : ""}${Math.abs(f)} d`,
    tone: f < 0 ? "risk" : s.atRisk ? "watch" : "good",
    headline: f >= 0 ? "Float positive." : "Behind on the critical path.",
    risk: s.atRisk ?? null,
  };
}

function workCard(w: NonNullable<PulseInput["work"]>): PulseCard | null {
  if (w.open == null) return null;
  const overdue = w.overdue ?? [];
  const mine = w.mine ?? 0;
  // Names, not counts. "2 are overdue" makes you go looking; "2 are overdue: RFI-118 and submittal
  // 08-4100" is already the answer, and it is the difference between a metric and a working tool.
  const parts: string[] = [];
  if (mine > 0) parts.push(`${mine} ${mine === 1 ? "is" : "are"} yours.`);
  if (overdue.length) {
    parts.push(`${overdue.length} ${overdue.length === 1 ? "is" : "are"} overdue: ${list(overdue)}.`);
  }
  return {
    key: "work", label: "Open items", value: String(w.open),
    tone: overdue.length ? "risk" : mine > 0 ? "watch" : "good",
    headline: w.open === 0 ? "Nothing outstanding." : `${plural(w.open, "open item")}.`,
    risk: parts.length ? parts.join(" ") : null,
  };
}

function dealCard(d: NonNullable<PulseInput["deal"]>): PulseCard | null {
  if (d.irrPct == null) return null;
  const inBand = d.band ? d.irrPct >= d.band[0] && d.irrPct <= d.band[1] : null;
  return {
    key: "deal", label: "Deal", value: `${d.irrPct.toFixed(1)}%`,
    tone: inBand === false ? "risk" : d.staleSince ? "watch" : "good",
    headline: inBand == null ? "IRR current." : inBand ? "IRR inside market band." : "IRR outside market band.",
    risk: d.staleSince ? `Re-forecast from ${d.staleSince} actuals.` : null,
  };
}

/** Join names the way a person would say them aloud. */
function list(xs: string[]): string {
  if (xs.length <= 1) return xs[0] ?? "";
  if (xs.length === 2) return `${xs[0]} and ${xs[1]}`;
  return `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
}

/**
 * Build the pulse. Cards with no data are **omitted**, never rendered as zero — a project without a
 * proforma has no deal position, and showing "0.0%" would be a claim nobody made.
 */
export function buildPulse(input: PulseInput): PulseCard[] {
  const cards = [
    input.model ? modelCard(input.model) : null,
    input.cost ? costCard(input.cost) : null,
    input.schedule ? scheduleCard(input.schedule) : null,
    input.work ? workCard(input.work) : null,
    input.deal ? dealCard(input.deal) : null,
  ];
  return cards.filter((c): c is PulseCard => c !== null);
}

/**
 * NEXT BEST ACTION — the single thing to do now.
 *
 * One, not a ranked list: the moment this returns three suggestions it becomes another queue to
 * triage, which is the problem the work queue already solves. Overdue beats due-today beats
 * blocking-something-else; ties break toward the item other work is waiting on.
 */
export interface ActionCandidate {
  ref: string; title: string; verb: string;
  overdueDays?: number | null; dueInDays?: number | null; blocks?: number | null;
}

export function nextBestAction(items: ActionCandidate[]): ActionCandidate | null {
  if (!items.length) return null;
  const score = (i: ActionCandidate) =>
    (i.overdueDays ?? 0) * 1000 +
    (i.dueInDays != null && i.dueInDays <= 0 ? 500 : 0) +
    (i.blocks ?? 0) * 10 -
    (i.dueInDays ?? 99);
  return [...items].sort((a, b) => score(b) - score(a))[0]!;
}
