/** Portal user preferences — localStorage-backed module favorites, recents, and the per-persona
 *  "which nav sections open first" map. Extracted from portal.ts (T3) so the nav rail and the module
 *  catalog share one source of truth instead of each reaching into the PortalUI class for it. */

// Which module sections open first, per persona. Section names must match the workspace a role lives
// in (a developer sees the *Developer* sections, not construction ones). buildNav falls back to
// "open all" when none match the active workspace, so a role browsing another workspace never sees
// everything collapsed.
export const SECTIONS_BY_PERSONA: Record<string, string[]> = {
  gc: ["Field", "Cost", "Change Management", "Contracts"],
  // the super works the field (daily reports, manpower, safety, quality, schedule);
  // the PM works the office (RFIs/submittals, cost, change, contracts, preconstruction).
  superintendent: ["Field", "Safety", "Quality", "Schedule"],
  project_manager: ["Engineering", "Cost", "Change Management", "Contracts", "Preconstruction"],
  // the real-estate developer lives in the Developer workspace — feasibility, market/sales, capital, ops.
  developer: ["Feasibility", "Market & Sales", "Capital", "Operations"],
  // architect/engineer live in the Design workspace — programming, phases, model authoring, and
  // the ISO 19650 information-management registers open first.
  architect: ["Programming", "Design Phases", "Engineering", "BIM", "Information Management"],
  engineer: ["Engineering", "BIM", "Information Management", "Design Phases"],
  subcontractor: ["Field", "Safety", "Quality"],
};

export function readFavs(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem("portal-favs") || "[]") as string[]); }
  catch { return new Set(); }
}

/** Nav stage groups the user has collapsed, keyed "workspace:stage" — so a folded stage stays folded
 *  next time they're in that workspace (the rail stays scannable as destinations grow). */
export function readCollapsedStages(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem("portal-collapsed-stages") || "[]") as string[]); }
  catch { return new Set(); }
}

/** Persist a stage's collapsed flag (keyed "workspace:stage"). */
export function setStageCollapsed(key: string, collapsed: boolean): void {
  const s = readCollapsedStages();
  if (collapsed) s.add(key); else s.delete(key);
  localStorage.setItem("portal-collapsed-stages", JSON.stringify([...s]));
}

/** Toggle a module's favorite flag; returns the updated set (already persisted). */
export function toggleFav(key: string): Set<string> {
  const f = readFavs();
  if (f.has(key)) f.delete(key); else f.add(key);
  localStorage.setItem("portal-favs", JSON.stringify([...f]));
  return f;
}

/** Last-opened module keys, newest first — auto-populated so the nav works with zero setup. */
export function readRecents(): string[] {
  try { return JSON.parse(localStorage.getItem("portal-recents") || "[]") as string[]; }
  catch { return []; }
}

export function pushRecent(key: string): void {
  const r = [key, ...readRecents().filter((k) => k !== key)].slice(0, 5);
  localStorage.setItem("portal-recents", JSON.stringify(r));
}
