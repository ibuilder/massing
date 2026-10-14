/**
 * MODELSYNC-DARK — `POST /projects/{pid}/dev-budget/sync-from-model` had no caller.
 *
 * Its own docstring: *"one click ties the underwriting to the real IFC quantities × unit rates
 * (priced through the project's pinned cost vintage), instead of a flat GFA×$/sf assumption … Closes
 * the model↔proforma disconnect."* That disconnect is the central claim of this product — IFC as the
 * source of truth, feasibility derived from it rather than from a spreadsheet guess — and the one
 * route that closes it was reachable from nothing. Its sibling `sync-gmp` has had a button in the
 * budget card since it shipped.
 *
 * Frozen in `services/api/test_route_reachability.py`'s `KNOWN_UNCALLED` since 2026-08-20 under the
 * entry that says *"a ratchet records 'this was looked at', never 'this is safe'"*. This is the
 * leaving.
 *
 * **The reading is not the click.** The route commits a number to the development budget, and three
 * facts decide what that number MEANS, none of which the GMP sync has to think about:
 *
 *   - **which basis won.** `estimate_from_takeoff` recommends the GFA benchmark over the element sum
 *     when the two diverge, and then the route writes ONE lump line instead of the per-discipline
 *     breakdown. The breakdown is still in the response and no longer adds up to the committed
 *     number. The server now says `basis` outright rather than leaving a caller to re-derive it from
 *     `sum(by_discipline)` against the server's own 2% tolerance — *a rule duplicated across the
 *     wire is a rule that will drift.*
 *   - **which cost vintage priced it**, and whether it was localized and escalated. A hard cost is a
 *     claim about a market and a year; `cost_vintage` and `cost_adjustment` are that claim.
 *   - **the two 409s are different refusals.** No accessible source IFC means load a model; a
 *     republication landing mid-takeoff means press it again. Flattening them to "sync failed"
 *     offers a retry that cannot work, or hides one that would.
 */

export interface ModelSyncResult {
  synced: boolean;
  hard_cost: number;
  by_discipline: Record<string, number>;
  /** `per_discipline`: the committed cost IS the sum below. `gfa_benchmark`: it is not. */
  basis?: "per_discipline" | "gfa_benchmark";
  discipline_total?: number;
  cost_vintage?: { name?: string; year?: number | null; region?: string | null } | null;
  cost_adjustment?: { combined_factor?: number; location_factor?: number;
                      escalation_factor?: number; note?: string } | null;
}

export type SyncTone = "ok" | "warn";

const TONE_CSS: Record<SyncTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)",
};

/** Discipline rows for the breakdown table, biggest first. */
export function disciplineRows(r: ModelSyncResult): { discipline: string; amount: number }[] {
  return Object.entries(r.by_discipline || {})
    .filter(([, v]) => v)
    .sort((a, b) => b[1] - a[1])
    .map(([discipline, amount]) => ({ discipline, amount }));
}

/**
 * What the committed number is, and what the breakdown beside it is NOT.
 *
 * On the benchmark branch the warning is the whole point: the table below the headline is the
 * element pricing, the headline is a GFA benchmark, and a reader who takes the table as a
 * decomposition of the headline is reading two different estimates as one. An ABSENT `basis` — an
 * older server — answers the same way as the benchmark branch would not: it says the basis is not
 * stated, rather than assuming the reassuring one.
 */
export function basisNote(r: ModelSyncResult): { text: string; tone: SyncTone } {
  if (r.basis === "per_discipline") {
    return { text: "The committed hard cost is the sum of the priced element lines below — each "
                   + "discipline is a line a GC could bid.",
             tone: "ok" };
  }
  if (r.basis === "gfa_benchmark") {
    const sum = r.discipline_total;
    const gap = sum === undefined ? "" : ` (elements priced at ${fmt(sum)})`;
    return { text: `⚠ The element pricing and the GFA benchmark diverged, so ONE benchmark line was `
                   + `written${gap}. The breakdown below is the element pricing and does NOT add up `
                   + `to the committed cost — refine the takeoff or the unit rates before treating `
                   + `either as the number.`,
             tone: "warn" };
  }
  return { text: "⚠ This server did not state which basis it committed — the breakdown below may be "
                 + "the element pricing rather than a decomposition of the hard cost.",
           tone: "warn" };
}

/** Which market and year priced it. `null` when no vintage is installed — the shipped rates applied. */
export function vintageNote(r: ModelSyncResult): string {
  const v = r.cost_vintage;
  if (!v) {
    return "No cost vintage is installed for this project, so the shipped benchmark unit rates "
      + "applied unchanged — not localized to a region and not escalated to a construction midpoint.";
  }
  const parts = [v.name || "installed vintage"];
  if (v.year) parts.push(String(v.year));
  if (v.region) parts.push(v.region);
  const a = r.cost_adjustment;
  // `combined_factor` of exactly 1 is a real answer (no localization, no escalation) and must not
  // read as an absent one, so it is tested against undefined rather than for truthiness.
  const f = a?.combined_factor;
  const adj = f === undefined ? ""
    : f === 1 ? " · no location or escalation adjustment applied"
    : ` · ×${f.toFixed(3)} for location + escalation`;
  return `Priced through ${parts.join(" · ")}${adj}.`;
}

/**
 * The two refusals, kept apart.
 *
 * Both are 409 and only the second is worth retrying immediately, so the message decides whether
 * the reader presses the button again or goes and loads a model. Matched on the server's own
 * sentence rather than on the status code, because the code cannot tell them apart.
 */
export function syncFailure(message: string): { text: string; retryable: boolean } {
  const m = message.toLowerCase();
  if (m.includes("republished while the takeoff ran")) {
    return { text: "The model was republished while the takeoff was running, so the sync was "
                   + "refused rather than committing a cost for a model this project no longer has. "
                   + "Press it again to price the current model.",
             retryable: true };
  }
  if (m.includes("source") && (m.includes("ifc") || m.includes("model"))) {
    return { text: "This project has no accessible source IFC, so there is nothing to take off. "
                   + "Upload or publish a model first.",
             retryable: false };
  }
  return { text: `Sync failed: ${message}`, retryable: false };
}

export const SYNC_CSS = TONE_CSS;

function fmt(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}
