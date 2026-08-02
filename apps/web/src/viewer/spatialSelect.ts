/**
 * A29-SPATIAL-SELECT — click depth, not just objects.
 *
 * Pascal's selection walks Site → Building → Level → Zone → Item; ours holds the REAL hierarchy
 * (IfcBuildingStorey containment is on every element the client already loads), so re-clicking a
 * selected element widens the selection one spatial level instead of doing nothing:
 *
 *     click 1  →  the ITEM
 *     click 2  →  its LEVEL   (every element contained in the same storey)
 *     click 3  →  the MODEL   (everything)
 *     click 4  →  back to the item
 *
 * This is deliberately built on `ElementProps.storey` — data the model states, not a convention the
 * client invents. An element with NO storey (site work, unassigned proxies) skips the level step and
 * goes straight to model: inventing a "(no level)" pseudo-storey would select an accidental grab-bag
 * and present it as a spatial fact.
 *
 * Pure and unit-tested beside `inference.ts` / `placeValid.ts`; the widget layer only cycles scope
 * on a repeated click and resets it on any new element, deselect, or Escape.
 */

export type SpatialScope = "item" | "storey" | "model";

export interface SpatialElement { guid: string; storey: string | null }

/** The next scope after re-clicking the same element. `hasStorey=false` skips the level step. */
export function nextScope(current: SpatialScope, hasStorey: boolean): SpatialScope {
  if (current === "item") return hasStorey ? "storey" : "model";
  if (current === "storey") return "model";
  return "item";
}

/**
 * The selection a scope names, resolved against the loaded element list. Returns the guids and a
 * human label for the status line — the count is the honest part, because "Level 2" alone doesn't
 * say whether the widen actually grabbed anything.
 */
export function scopeSelection(guid: string, scope: SpatialScope, elements: readonly SpatialElement[],
): { guids: string[]; label: string } {
  if (scope === "item") return { guids: [guid], label: "element" };
  if (scope === "model") {
    const guids = elements.map((e) => e.guid);
    return { guids: guids.length ? guids : [guid], label: `whole model — ${guids.length || 1} elements` };
  }
  const me = elements.find((e) => e.guid === guid);
  const storey = me?.storey ?? null;
  if (storey === null) return { guids: [guid], label: "element (no level assigned)" };
  const guids = elements.filter((e) => e.storey === storey).map((e) => e.guid);
  return { guids, label: `${storey} — ${guids.length} element${guids.length === 1 ? "" : "s"}` };
}
