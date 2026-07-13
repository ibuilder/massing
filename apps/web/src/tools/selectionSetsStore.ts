import type { ElementProps } from "../api/client";

/**
 * Named selection sets (Navisworks / Bluebeam "Search Set" pattern). A set is a saved query
 * plus the GUIDs it resolved to at save time; applying a set isolates those elements. Sets are
 * persisted per-project in localStorage — they're a personal view aid, not model data, so they
 * don't touch the IFC.
 */
export interface SelSet {
  name: string;
  /** The search term this set was built from (kept so the set can be re-resolved / shown). */
  q: string;
  /** GUIDs resolved from `q` at save time (the stable key; survives re-conversion). */
  guids: string[];
}

const keyFor = (pid: string) => `massing.selsets.${pid}`;

export function loadSelSets(pid: string): SelSet[] {
  try {
    const raw = localStorage.getItem(keyFor(pid));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((s): s is SelSet =>
      !!s && typeof s === "object"
      && typeof (s as SelSet).name === "string"
      && Array.isArray((s as SelSet).guids));
  } catch {
    return [];
  }
}

export function saveSelSets(pid: string, sets: SelSet[]): void {
  try {
    localStorage.setItem(keyFor(pid), JSON.stringify(sets));
  } catch { /* storage full / disabled — sets are a convenience, fail quietly */ }
}

/** GUIDs of every element matching `q` (name / class / type / discipline / storey, substring). */
export function resolveGuids(elements: ElementProps[], q: string): string[] {
  const t = q.trim().toLowerCase();
  if (!t) return [];
  return elements.filter((el) =>
    (el.name ?? "").toLowerCase().includes(t)
    || el.ifc_class.toLowerCase().includes(t)
    || (el.type_name ?? "").toLowerCase().includes(t)
    || (el.discipline ?? "").toLowerCase().includes(t)
    || (el.storey ?? "").toLowerCase().includes(t),
  ).map((el) => el.guid);
}
