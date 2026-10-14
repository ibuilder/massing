/** FLOW-CLEAR — the flowline card's subtitle promised the one thing it did not render.
 *
 *  The card is titled *"Flowline — line of balance"* and subtitled
 *
 *  > Where each crew is, and **whether anyone is in anyone's way.**
 *
 *  It rendered four tiles: duration, locations, trades, worst continuity cost. Nothing about
 *  anybody being in anybody's way. `interference_count` was declared and unread; `interferences`
 *  and `issues` were undeclared.
 *
 *  THE KEY IT COULD HAVE REACHED FOR IS THE ONE THAT WOULD HAVE MISLED IT
 *  ---------------------------------------------------------------------
 *  `interference_count` is **not** a count of collisions. `massingplan/core/locations.compute`
 *  appends an `Interference` for every consecutive pair of trade lines, unconditionally, recording
 *  where they come closest. Measured: two trades with ample clearance through three floors return
 *  `interference_count: 1`. *A careful consumer rendering it as a finding would have alarmed every
 *  reader of a perfectly coordinated schedule* — the opposite direction from the rest of this
 *  class, and the reason this module reads the per-pair records instead of the count.
 *
 *  WHAT ACTUALLY VARIES IS `converging`
 *  ------------------------------------
 *  `gap_days` is the clearance at the binding location, and `compute()` shifts each line until it
 *  is exactly tight there — so the clearance it leaves is the declared `buffer_days`, which the
 *  adapter never sets. Measured against the engine directly: buffer 0 → gap 0, +2 → +2, −3 → −3
 *  and a `LOB.OVERLAP` error. **So from this route `gap_days` is always 0** and the engine's
 *  overlap detection is unreachable (FLOW-BUFFER holds that gap: nobody can REQUEST a buffer).
 *
 *  `converging` does vary, and the engine says why it is the one to show: *"the successor is the
 *  faster trade and is catching up … a slip in the predecessor is felt immediately at the far end,
 *  and it is invisible on a bar chart."* That is the sentence a line-of-balance view exists for.
 */
import type { FlowlineResult, ScheduleIssue } from "../../api/schedule";

export type Tone = "" | "good" | "warn" | "crit";

export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** Does anybody get in anybody's way — the card's own promise, answered.
 *
 *  Three states and the order is severity. A negative clearance is trades sharing the space; a
 *  converging pair is the schedule degrading along the flow; otherwise the lines hold their
 *  clearance. Returns `null` when nothing was computed, so the caller shows `reason` instead. */
export function clearanceVerdict(r: FlowlineResult): { text: string; tone: Tone } | null {
  if (!r.available) return null;
  const pairs = r.interferences ?? [];
  if (pairs.length === 0) {
    // One trade, or an older server. Either way there is no handover to be in the way of.
    return r.trades.length < 2
      ? { tone: "", text: `Only ${r.trades.length} trade(s) carry a location, so there is no `
          + `handover to interfere with.` }
      : null;
  }
  const crossing = pairs.filter((p) => p.gap_days < 0);
  const converging = pairs.filter((p) => p.converging);
  if (crossing.length) {
    const worst = [...crossing].sort((a, b) => a.gap_days - b.gap_days)[0]!;
    return {
      tone: "crit",
      text: `${crossing.length} of ${pairs.length} handover(s) share the space: `
        + `${worst.successor_id} starts ${Math.abs(worst.gap_days)} day(s) before `
        + `${worst.predecessor_id} finishes in ${worst.location_id}.`,
    };
  }
  if (converging.length) {
    const p = converging[0]!;
    return {
      tone: "warn",
      text: `${converging.length} of ${pairs.length} handover(s) are CONVERGING — the clearance `
        + `shrinks along the flow, so a slip in the earlier trade is felt immediately at the far `
        + `end. Tightest: ${p.predecessor_id} → ${p.successor_id} at ${p.location_id}, `
        + `${p.gap_days} day(s) clear.`,
    };
  }
  return {
    tone: "good",
    text: `All ${pairs.length} handover(s) hold their clearance along the whole flow — no trade `
      + `catches the one in front of it.`,
  };
}

/** One row per handover, in the order the work flows. */
export function handoverRows(r: FlowlineResult): {
  pair: string; at: string; clearance: string; trend: string; tone: Tone;
}[] {
  return (r.interferences ?? []).map((p) => ({
    pair: `${p.predecessor_id} → ${p.successor_id}`,
    at: p.location_id,
    clearance: p.gap_days < 0 ? `${Math.abs(p.gap_days)}d OVERLAP` : `${p.gap_days}d`,
    trend: p.converging ? "catching up" : "holding",
    tone: p.gap_days < 0 ? "crit" : p.converging ? "warn" : "",
  }));
}

/** The population `interference_count` actually measures, said out loud.
 *
 *  Rendered only when the card would otherwise look like it is hiding something — i.e. whenever
 *  there are handovers to describe. The point is that the reader never sees the bare number. */
export function populationNote(r: FlowlineResult): string | null {
  const pairs = r.interferences ?? [];
  if (!r.available || pairs.length === 0) return null;
  return `${r.interference_count} handover(s) examined — one per adjacent pair of trade lines, not `
    + `a count of problems. Clearance is measured where each pair comes closest.`;
}

/** The zero-buffer caveat, which is why every clearance reads 0 when nothing was asked for.
 *
 *  Stated rather than left as a puzzle: a reader who sees `0d` on every row will otherwise conclude
 *  the schedule is pathologically tight.
 *
 *  **Its second sentence used to say a buffer "cannot be requested through this view yet", and
 *  FLOW-BUFFER made that false.** It now names the control instead — which is the difference
 *  between a caveat that explains a limit and one that has outlived it. A caveat nobody re-reads
 *  becomes folklore, and this file's own `*.test.ts` is what holds the sentence to the code. */
export function bufferNote(r: FlowlineResult): string | null {
  const pairs = r.interferences ?? [];
  if (pairs.length === 0 || pairs.some((p) => p.gap_days !== 0)) return null;
  const asked = Object.keys(r.buffer_days_requested ?? {}).length;
  if (asked) {
    // Every clearance is 0 AND a buffer was asked for: the request was zero, or it was for trades
    // whose lines were already tight. Either way the reader is not looking at an unasked question.
    return `Every clearance is 0 days — the buffer requested for ${asked} handover(s) produced no `
      + `spacing, so each line is still as tight as it can go.`;
  }
  return `Every clearance is 0 days because the flow is computed with no buffer between trades — `
    + `each line is placed as tight as it can go. Set a buffer above to space the handovers, or a `
    + `negative one for deliberate overlap.`;
}

/** What was ASKED for, beside what came out — null when nothing was asked.
 *
 *  **The request and the result are two different numbers**, and the engine reports only the second
 *  on each pair. The realised overlap saturates at the predecessor's per-location duration, because
 *  a successor cannot start before its predecessor did: measured against the engine at 2/4/6/10
 *  crew-days per location, a request of −5 returns −2/−4/−5/−5. *A planner who asked for five days
 *  of overlap and got two has been told nothing by a row that shows the two.* */
export function bufferRequestNote(r: FlowlineResult): string | null {
  const asked = r.buffer_days_requested ?? {};
  const names = Object.keys(asked);
  if (!names.length) return null;
  const vals = [...new Set(Object.values(asked))];
  const spec = vals.length === 1
    ? `${vals[0]}d at every one of ${names.length} handover(s)`
    : names.map((t) => `${t} ${asked[t]}d`).join(" · ");
  return `Buffer requested: ${spec}. A negative number is deliberate overlap.`;
}

/** The requests the engine could not honour, each with both numbers. */
export function bufferUnmetRows(r: FlowlineResult): { k: string; v: string }[] {
  return (r.buffer_days_unmet ?? []).map((u) => ({
    k: u.trade,
    v: `asked ${u.requested}d, got ${u.realised}d`,
  }));
}

/** Why a request landed short, or null when every one landed exactly.
 *
 *  Separate from the rows because the REASON is one sentence about all of them and repeating it per
 *  row would bury it. */
export function bufferUnmetNote(r: FlowlineResult): string | null {
  const unmet = r.buffer_days_unmet ?? [];
  if (!unmet.length) return null;
  return `${unmet.length} request(s) could not be met in full: a trade cannot start before the one `
    + `it follows started, so the overlap saturates at that trade's work content per location. `
    + `Shorten the overlap, or give the predecessor more content per floor.`;
}

/** The requests that were DROPPED, and why — three different mistakes, kept apart.
 *
 *  A value on the first trade is a misunderstanding of the model (the engine spaces a trade from
 *  its PREDECESSOR, so the first has nothing to space from — and the field's own docstring in the
 *  vendored engine describes the other side, which is how a careful caller gets it wrong). An
 *  unknown name is a typo. A malformed pair never parsed at all. *Folding them into one "ignored"
 *  line would tell a reader there is a problem without saying which fix applies.* */
export function bufferDroppedNotes(r: FlowlineResult): string[] {
  const out: string[] = [];
  const first = r.buffer_days_ignored_first ?? [];
  if (first.length) {
    out.push(`No buffer was applied to ${first.join(", ")} — it is first in the flow, and a buffer `
      + `spaces a trade from the one BEFORE it. Set it on the following trade instead.`);
  }
  const unknown = r.buffer_days_ignored_unknown ?? [];
  if (unknown.length) {
    out.push(`${unknown.join(", ")} is not a trade on this project, so its buffer was ignored.`);
  }
  const bad = r.buffer_malformed ?? [];
  if (bad.length) {
    out.push(`Could not read ${bad.join(", ")} — a buffer is written as "<trade>:<days>".`);
  }
  const clamped = r.buffer_days_clamped ?? [];
  if (clamped.length) {
    out.push(`${clamped.join(", ")} asked for more than the ${r.max_buffer_days ?? 90}-day limit `
      + `and was reduced to it.`);
  }
  return out;
}

/** Pairs whose lines actually cross, as a sentence — null when none do.
 *
 *  `overlap_count` is a real measurement only since a buffer became requestable; before that it
 *  would have been a constant 0, which is why it was written and deleted before shipping. */
export function overlapNote(r: FlowlineResult): string | null {
  const n = r.overlap_count ?? 0;
  if (!n) return null;
  return `${n} handover(s) OVERLAP — the two trades share the space for part of the work. That is `
    + `a plan, not an error, but the engine logs it below so nobody ships it by accident.`;
}

const SEVERITY_RANK: Record<string, number> = { error: 0, warning: 1, info: 2 };

/** The engine's issue log, worst first. `LOB.OVERLAP` lands here when a buffer makes one. */
export function flowIssueRows(r: FlowlineResult): {
  code: string; text: string; tone: Tone;
}[] {
  const issues: ScheduleIssue[] = r.issues ?? [];
  return [...issues]
    .sort((a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3))
    .map((i) => ({
      code: i.code,
      text: `${i.message} — ${i.action}`,
      tone: i.severity === "error" ? "crit" : i.severity === "warning" ? "warn" : "",
    }));
}

/** The refusal's own diagnostic: what the engine DID find, when the locations would not arrange. */
export function flowUnavailableExtras(r: FlowlineResult): string | null {
  if (r.available) return null;
  const locs = r.locations ?? [];
  const trades = r.trades ?? [];
  const parts = [
    locs.length ? `Locations found: ${locs.map((l) => l.name || l.id).join(" · ")}.` : "",
    trades.length ? `Trades found: ${trades.join(" · ")}.` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : null;
}
