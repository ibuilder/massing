import type { CoordStale } from "../../api/model";

/**
 * COORD-UNANCHORED, the screen half — reading clash freshness, coverage first.
 *
 * `GET /projects/{pid}/coordination/stale?a=&b=` answers *"which open coordination issues touch an
 * element that moved between these two published versions"*, and `/recheck` flags them for
 * re-verification. Neither had a client method: the capability was frozen in
 * `services/api/test_route_reachability.py` as a route no screen reaches.
 *
 * **The engine had to be fixed first** (`services/api/test_coord_unanchored.py`). Its whole test is
 * `topic.element_guids ∩ changed`, so a topic carrying no element GlobalIds can never be stale by
 * construction — and it was counted among the open issues that did NOT go stale. A coordinator
 * reading *"2 of 40 open issues are stale"* concludes the other 38 are still valid; for an
 * unanchored one the truth is *"this check cannot say"*.
 *
 * So the reading answers, in order: can this comparison be made at all → what it could not rule on
 * → what it found. The order is the point, not the wording: `clean` is reachable only when
 * `comparable` is true AND nothing is unanchored, which is the one state that genuinely means
 * "still valid".
 */
export type { CoordStale };

export interface FreshnessReading {
  /** `incomparable` — the diff found nothing, or no topic could be assessed. `partial` — some
   *  topics have no anchors. `stale` — findings. `clean` — assessed everything, nothing stale. */
  kind: "incomparable" | "partial" | "stale" | "clean";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

export function freshnessReading(r: CoordStale): FreshnessReading {
  const span = `v${r.from} → v${r.to}`;
  if (!r.comparable) {
    // TWO REASONS, and they are different advice. Nothing changed → compare different versions.
    // Nothing assessable → go and anchor the topics. Collapsing them would send the reader at the
    // wrong one, which is the whole cost of an undifferentiated empty state.
    const why = r.changed_elements === 0
      ? `no element changed between ${span}, so nothing here is evidence about any issue`
      : `none of the ${r.open_coordination_issues} open issue(s) carries an element GlobalId, so`
        + " this check ruled on nothing";
    return {
      kind: "incomparable", tone: "",
      headline: `No comparison could be made — ${why}.`,
      detail: r.changed_elements === 0
        ? "Pick two versions that differ. A freshness check over an unchanged model reports 0 stale"
          + " for every issue, which says nothing about any of them."
        : "Anchor these issues to the elements they are about (open each topic and attach its"
          + " GlobalIds) and this check starts applying to them. Until then it is not a statement"
          + " that they are still valid.",
    };
  }
  const base = `${r.assessable} of ${r.open_coordination_issues} open issue(s) could be assessed`
    + `; ${r.changed_elements} element(s) changed ${span}.`;
  if (r.stale_count) {
    return {
      kind: "stale", tone: "bad",
      headline: `${r.stale_count} open issue(s) touch an element that changed.`,
      detail: `${base} A changed element does not prove the clash is gone — it can be worse — so`
        + " these are flagged for re-verification, never closed automatically."
        + (r.unanchored ? ` ${r.unanchored} further issue(s) have no anchors and are not`
          + " included either way." : ""),
    };
  }
  if (r.unanchored) {
    return {
      kind: "partial", tone: "warn",
      headline: `Nothing stale among the ${r.assessable} issue(s) that could be assessed`
        + ` — and ${r.unanchored} could not be.`,
      detail: `${base} An issue with no element GlobalIds is outside this check entirely: it is not`
        + " reported as still valid, because nothing was measured about it.",
    };
  }
  return {
    kind: "clean", tone: "ok",
    headline: `All ${r.assessable} open issue(s) still refer to unchanged elements.`,
    detail: base,
  };
}

/** The counts, with both sides of the population so neither can hide. */
export function freshnessRows(r: CoordStale): { k: string; v: string }[] {
  return [
    { k: "Versions compared", v: `v${r.from} → v${r.to}` },
    { k: "Elements changed", v: String(r.changed_elements) },
    { k: "Open coordination issues", v: String(r.open_coordination_issues) },
    { k: "…assessable (anchored)", v: String(r.assessable) },
    { k: "…unanchored (not ruled on)", v: String(r.unanchored) },
    { k: "Stale (element changed)", v: String(r.stale_count) },
    { k: "Already flagged", v: String(r.stale.filter((s) => s.already_flagged).length) },
  ];
}

/**
 * What the re-check button should say before it is pressed.
 *
 * Returns null when there is nothing to flag, so the caller renders no button rather than a disabled
 * one — and the count is of what is NOT already flagged, because the route is idempotent and a
 * button promising to flag 6 that would flag 0 is the same lie as a progress bar at 100%.
 */
export function recheckPrompt(r: CoordStale): { label: string; confirm: string; count: number } | null {
  const fresh = r.stale.filter((s) => !s.already_flagged);
  if (!fresh.length) return null;
  return {
    count: fresh.length,
    label: `⚑ Flag ${fresh.length} for re-verification`,
    confirm: `Add a "model-changed" label and a re-verify comment to ${fresh.length} open`
      + ` coordination issue(s).\n\nThis never closes an issue — a changed element can mean the`
      + " clash is resolved or that it is worse, so the coordinator decides. Running it again"
      + " changes nothing.",
  };
}
