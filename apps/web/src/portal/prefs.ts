/** Portal user preferences — localStorage-backed module favourites, recents, and collapsed nav
 *  stages. Extracted from portal.ts (T3) so everything reading them shares one source of truth
 *  instead of reaching into the PortalUI class.
 *
 *  Favourites are set from the pin control on each nav row (`portal.ts:moduleButton`) and read by
 *  `buildNav` and `shell/pinnedRail.ts`. That writer is the ONLY one — see `favourites.test.ts` for
 *  the two months it did not exist and what silently stopped working. */

// `SECTIONS_BY_PERSONA` lived here until v0.3.1084 and was deleted with the module catalog it served.
// Its own comment said "buildNav falls back to open-all when none match the active workspace" — but
// buildNav stopped grouping modules by section in v0.3.767, when the room spine made a second
// taxonomy in one rail a defect rather than a feature. So the table had been orphaned for longer
// than the catalog had, and its comment described a caller that no longer read it. **A constant's
// docstring is a claim about the rest of the tree, and nothing checks it.**

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

/**
 * Spine rooms need a **tri-state** memory, which is why they do not reuse the stage store.
 *
 * A stage defaults to open, so recording only what the user collapsed is enough. A room defaults to
 * *closed* unless it is the workspace's own room — every room expanded at once is
 * the same wall of options the spine exists to end. That means three distinct states: the user opened
 * it, the user closed it, and the user has said nothing yet. Collapsing that to a single set would
 * make "I have never touched this" indistinguishable from one of the two answers, and the rail would
 * either forget an explicit collapse or override an explicit expansion.
 */
export function readRoomOpen(key: string): boolean | null {
  try {
    const m = JSON.parse(localStorage.getItem("portal-room-open") || "{}") as Record<string, boolean>;
    return typeof m[key] === "boolean" ? m[key]! : null;
  } catch { return null; }
}

export function setRoomOpen(key: string, open: boolean): void {
  let m: Record<string, boolean>;
  try { m = JSON.parse(localStorage.getItem("portal-room-open") || "{}") as Record<string, boolean>; }
  catch { m = {}; }
  m[key] = open;
  localStorage.setItem("portal-room-open", JSON.stringify(m));
}

/** Command-center + register density. Three row heights, named, not two booleans:
 *  Field 56 px / Default 36 px / Compact 28 px. Dashboards still use `.dense` for compact only.
 *  Persisted globally (a personal viewing preference, not per project/persona). */
export const DENSITY_STEPS = ["field", "comfortable", "compact"] as const;
export type Density = (typeof DENSITY_STEPS)[number];
export const DENSITY_ROW_PX: Record<Density, number> = {
  field: 56,
  comfortable: 36,
  compact: 28,
};

export function readDensity(): Density {
  const raw = localStorage.getItem("portal-density");
  if (raw === "field" || raw === "compact" || raw === "comfortable") return raw;
  return "comfortable";
}

export function setDensity(d: Density): void {
  localStorage.setItem("portal-density", d);
}

/** Field → comfortable → compact → field. */
export function cycleDensity(): Density {
  const cur = readDensity();
  const next = DENSITY_STEPS[(DENSITY_STEPS.indexOf(cur) + 1) % DENSITY_STEPS.length]!;
  setDensity(next);
  return next;
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
