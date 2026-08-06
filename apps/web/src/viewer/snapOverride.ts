import { nearestSnaps, perpendicularSnaps, type SnapCandidate, type SnapKind, type Vec2 } from "./snapEngine";

/** AUTH-SNAP-OVERRIDE — a one-shot object-snap override: "**this one pick**, take a perpendicular".
 *
 *  ## What was actually missing (premise-checked 2026-08-06, and the roadmap entry was understated)
 *
 *  The entry said "today a snap preference is modal, and needing this one pick to take a perpendicular
 *  means changing a mode and changing it back". There is **no such mode to change**. The only snap
 *  setting in the app is `getSettings().snap`, a *grid increment* (a number). Object-snap in the
 *  viewer is entirely automatic with a fixed precedence — typed constraint > Shift ortho > geometry
 *  snap > axis inference > polar > grid — and no part of it can be aimed. So the gap is not "the mode
 *  is inconvenient to flip"; it is that a drafter **cannot ask for a snap kind at all, ever**.
 *
 *  Second premise correction, same check: `resolveSnap` and `segmentSnaps` in `snapEngine.ts` — the
 *  priority-ordered resolver, the half that knows what a snap *kind* is — had **no callers**. Only
 *  `polarConstrain` and `applyDynamicInput` were wired. `perpendicular` has been a member of
 *  `SnapKind` all along with nothing anywhere able to produce one.
 *
 *  ## The chord
 *
 *  The roadmap suggested Shift+right-click (Shift is taken here by ortho lock, so it flagged the need
 *  to pick something else). This uses the app's **own existing grammar instead of a new chord**: the
 *  two-letter buffer that arms draw tools (`WA` wall, `CL` column …) also accepts an override code
 *  while a tool is armed. `EN` `MI` `CE` `PE` `NE` `NO`. Nothing to learn beyond the codes, no
 *  modifier to fight the browser over, and the two code sets are asserted **disjoint** by
 *  `snapOverride.test.ts` — so an ambiguous code fails a build rather than arming the wrong thing.
 *
 *  ## Only kinds that can actually be produced
 *
 *  `SnapKind` also contains `intersection` and `grid`, and there is **no override code for either**.
 *  Nothing in the pipeline emits an intersection candidate, so an `IN` override could never resolve —
 *  it would be a control that is always "no intersection here", which reads as a broken feature
 *  rather than an absent one. `ALL_OVERRIDE_KINDS` is asserted to be exactly what
 *  `overrideCandidates` can emit, so adding a code without a producer fails the same build.
 */

export type OverrideKind = "endpoint" | "midpoint" | "center" | "perpendicular" | "nearest" | "none";

/** Two-letter codes, typed into the same buffer as the draw-tool shortcuts. Disjoint from
 *  `KEY_SHORTCUTS` by test, not by inspection. */
export const OVERRIDE_CODES: Record<string, OverrideKind> = {
  EN: "endpoint",
  MI: "midpoint",
  CE: "center",
  PE: "perpendicular",
  NE: "nearest",
  NO: "none",        // suppress every snap for one pick — the raw cursor, untouched
};

export const OVERRIDE_LABEL: Record<OverrideKind, string> = {
  endpoint: "endpoint", midpoint: "midpoint", center: "centre",
  perpendicular: "perpendicular", nearest: "nearest on edge", none: "no snap",
};

/** Every kind an override can name. Kept beside the producer so the two cannot drift. */
export const ALL_OVERRIDE_KINDS: OverrideKind[] =
  ["endpoint", "midpoint", "center", "perpendicular", "nearest", "none"];

/** A plan-projected bounding footprint (world x / z), which is what the viewer can cheaply get for a
 *  picked element without re-reading its mesh. */
export type PlanBox = { minX: number; maxX: number; minZ: number; maxZ: number };

/** The footprint as a closed 4-point ring, in a fixed winding so tests can name an edge. */
function ring(b: PlanBox): Vec2[] {
  return [
    { x: b.minX, z: b.minZ }, { x: b.maxX, z: b.minZ },
    { x: b.maxX, z: b.maxZ }, { x: b.minX, z: b.maxZ },
  ];
}

/**
 * Candidates of **one kind only** for a picked element's footprint.
 *
 * Deliberately narrow: an override asks for one kind, so building the other five would only create
 * opportunities for the resolver to return something the drafter did not ask for. `none` yields no
 * candidates at all — its meaning is "do not snap", which the caller honours by keeping the raw
 * point, not by searching for one.
 *
 * `from` is the previous point of the run; `perpendicular` returns nothing without it (there is no
 * perpendicular to something from nowhere), and that is a refusal rather than a fallback.
 */
export function overrideCandidates(
  kind: OverrideKind, box: PlanBox, cursor: Vec2, from: Vec2 | null,
): SnapCandidate[] {
  const r = ring(box);
  const midX = (box.minX + box.maxX) / 2, midZ = (box.minZ + box.maxZ) / 2;
  switch (kind) {
    case "none":
      return [];
    case "endpoint":
      return r.map((p) => ({ x: p.x, z: p.z, kind: "endpoint" as SnapKind }));
    case "midpoint":
      return [
        { x: midX, z: box.minZ, kind: "midpoint" }, { x: box.maxX, z: midZ, kind: "midpoint" },
        { x: midX, z: box.maxZ, kind: "midpoint" }, { x: box.minX, z: midZ, kind: "midpoint" },
      ];
    case "center":
      return [{ x: midX, z: midZ, kind: "center" }];
    case "perpendicular":
      return from ? perpendicularSnaps(r, from, true) : [];
    case "nearest":
      return nearestSnaps(r, cursor, true);
  }
}

export interface SnapOverrideHandle {
  /** Arm from a two-letter code. Returns the kind armed, or null if the code is not an override. */
  arm(code: string): OverrideKind | null;
  /** What is armed, without consuming it (for the HUD). */
  peek(): OverrideKind | null;
  /** Take the armed override and clear it — a one-shot is spent by the pick that reads it, whether
   *  or not that pick found anything of the kind. Otherwise a failed override would silently apply
   *  to the *next* click too. */
  consume(): OverrideKind | null;
  clear(): void;
  /** Watch the armed kind. The key layer draws the HUD from this rather than polling, so the HUD
   *  cannot outlive the override it describes — a stale "next pick: perpendicular" is a lie about
   *  what the next click will do. */
  subscribe(fn: (k: OverrideKind | null) => void): void;
}

export function createSnapOverride(): SnapOverrideHandle {
  let armedKind: OverrideKind | null = null;
  const subs: ((k: OverrideKind | null) => void)[] = [];
  const set = (k: OverrideKind | null) => { armedKind = k; for (const fn of subs) fn(k); };
  return {
    arm(code) {
      const k = OVERRIDE_CODES[code.toUpperCase()];
      if (!k) return null;
      set(k);
      return k;
    },
    peek: () => armedKind,
    consume() {
      const k = armedKind;
      if (k) set(null);
      return k;
    },
    clear: () => { if (armedKind) set(null); },
    subscribe: (fn) => { subs.push(fn); },
  };
}
