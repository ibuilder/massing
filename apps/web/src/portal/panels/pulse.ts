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
 * This module is **pure**: engines in, cards out. Every input already exists
 * (`GET /projects/{id}/pulse` maps `modelHealth`, cost summary, schedule variance,
 * work queue, and the latest IRR). Pulse invents no numbers of its own.
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
  deal?: {
    irrPct?: number | null; band?: [number, number] | null; staleSince?: string | null;
    /**
     * `reserve.suggestion_clears_horizon === false` — the suggested level contribution was solved,
     * re-run against the schedule, and does NOT clear it. The number is still displayed elsewhere,
     * which is the hazard: an unverified suggestion looks exactly like a verified one.
     */
    reserveSuggestionFails?: boolean | null;
    /** `renovation.nothing_renovated_why` — carried verbatim; the server phrases it with the pace. */
    nothingRenovated?: string | null;
  } | null;
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

/**
 * Two findings ride this card rather than getting panels of their own, and the reason is that they
 * are **booleans**. Neither has a chart to sit in: "the pace you chose renovates nothing across the
 * entire hold" is a sentence, not a metric. Pulse's contract is that a card says what would move the
 * number, which is exactly the shape of both.
 *
 * They are also both **silent-wrong-answer** findings, which is why they are risk lines rather than
 * anything softer. A reserve suggestion that does not clear the horizon renders identically to one
 * that does; a renovation programme that completes no unit returns a perfectly well-formed schedule.
 * The failure mode in each case is a plausible number, not a missing one.
 *
 * KNOWN LIMIT, stated rather than discovered later: both ride the deal card, so they are invisible on
 * a project with no IRR. That follows the panel's existing rule — no proforma means no deal position,
 * and a card with no number cannot be rendered — but it does mean a reserve finding on a project that
 * never had a proforma has nowhere to appear. Asserted below so it is a decision, not a surprise.
 */
function dealCard(d: NonNullable<PulseInput["deal"]>): PulseCard | null {
  if (d.irrPct == null) return null;
  const inBand = d.band ? d.irrPct >= d.band[0] && d.irrPct <= d.band[1] : null;
  // Ordered worst-first: a suggestion that does not clear invalidates the funding plan outright,
  // where a stale forecast only ages it.
  const risks = [
    d.reserveSuggestionFails ? "Suggested reserve contribution does not clear the horizon." : null,
    d.nothingRenovated ? `Renovation renovates nothing — ${d.nothingRenovated}.` : null,
    d.staleSince ? `Re-forecast from ${d.staleSince} actuals.` : null,
  ].filter((x): x is string => x !== null);
  return {
    key: "deal", label: "Deal", value: `${d.irrPct.toFixed(1)}%`,
    tone: inBand === false || d.reserveSuggestionFails || d.nothingRenovated ? "risk"
      : d.staleSince ? "watch" : "good",
    headline: inBand == null ? "IRR current." : inBand ? "IRR inside market band." : "IRR outside market band.",
    risk: risks.length ? risks.join(" ") : null,
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

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

import { escapeHtml as esc } from "../../ui/feedback";

/** Card -> DOM. Kept beside the logic deliberately: the rule "a card may say nothing" is only
 *  honoured if the renderer also declines to draw an empty line, and splitting the two is how a
 *  `null` risk turns back into a blank row that looks like a loading state. */
export function pulseCardEl(c: PulseCard): HTMLElement {
  const el = document.createElement("article");
  // `pulse-tone-`, not `pulse-`: the tones are good/watch/risk, and `pulse-risk` was ALSO the
  // class on the risk sentence below — one selector matching both the card and a paragraph
  // inside it. Nothing depended on the ambiguity because nothing styled either, which is how it
  // survived from v0.3.749 to v0.3.1087.
  el.className = `pulse-card pulse-tone-${c.tone}`;
  el.setAttribute("data-pulse", c.key);
  const risk = c.risk ? `<p class="pulse-risk">${esc(c.risk)}</p>` : "";
  el.innerHTML =
    `<header class="pulse-head"><span class="pulse-dot" aria-hidden="true"></span>` +
    `<h4>${esc(c.label)}</h4><span class="pulse-value">${esc(c.value)}</span></header>` +
    `<p class="pulse-headline">${esc(c.headline)}</p>${risk}`;
  return el;
}

/** The whole rail. Returns null when there is nothing to show, so a caller can omit the column
 *  rather than render an empty panel captioned "Project Pulse". */
export function pulseRailEl(cards: PulseCard[]): HTMLElement | null {
  if (!cards.length) return null;
  const wrap = document.createElement("aside");
  wrap.className = "pulse-rail";
  wrap.setAttribute("aria-label", "Project pulse");
  const h = document.createElement("h3");
  h.className = "pulse-title";
  h.textContent = "PROJECT PULSE";
  wrap.appendChild(h);
  for (const c of cards) wrap.appendChild(pulseCardEl(c));
  return wrap;
}
