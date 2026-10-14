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

/** The zero-buffer caveat, which is why every clearance above reads 0.
 *
 *  Stated rather than left as a puzzle: a reader who sees `0d` on every row will otherwise conclude
 *  the schedule is pathologically tight, when in fact nobody has been able to ask for a buffer. */
export function bufferNote(r: FlowlineResult): string | null {
  const pairs = r.interferences ?? [];
  if (pairs.length === 0 || pairs.some((p) => p.gap_days !== 0)) return null;
  return `Every clearance is 0 days because the flow is computed with no buffer between trades — `
    + `each line is placed as tight as it can go. A deliberate buffer ("two days between drywall `
    + `and paint") cannot be requested through this view yet.`;
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
