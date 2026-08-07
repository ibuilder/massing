// R38-SOLVER-LOCKS — turn a solved constraint system into element edits.
//
// `POST /projects/{pid}/constraints/solve` is pure computation: it takes a flat dict of named scalars
// and returns new values, and it "neither reads nor writes the model" in its own words. So the solver
// was never the missing piece — this mapping is. Something has to decide that `thickness` on a wall
// writes through `set_wall_thickness(guid, …)` while `depth` on a column writes through
// `set_extrusion_depth(guid, …)`, and nothing did.
//
// **Every write below is an existing guid-keyed recipe from `services/data/src/aec_data/edit.py`.**
// No new recipe is needed, which was not obvious: the recipes that are the WRONG granularity are the
// ones with guessable names (`edit_type_params` is type-level, `set_pset_on_class` is class-level),
// while the single-element writes live in a dispatch table keyed by `p["guid"]`. A grep for setter
// names finds the wrong four and stops.
//
// **A variable with no recipe is REFUSED BY NAME, and the rest still apply.** A partial apply that
// says which locks it could not write is honest; one that silently drops them produces a model that
// looks like it satisfies the locks and does not — the same failure as a reserve suggestion printed
// without its verification flag, in a new place.

/** One solver variable, bound to the element and parameter it came from. */
export interface LockVariable {
  /** The name used in the solver's flat dict — must match the key in its `values` result. */
  name: string;
  /** Value as read from the model, before solving. Needed for deltas — see `move_element`. */
  current: number;
  guid: string;
  ifcClass: string;
  /** The parameter this variable represents: `thickness`, `depth`, `x`, `y`, `z`, … */
  param: string;
}

export interface Write {
  /** An `editIfc` recipe name, from the RECIPES table. */
  op: string;
  params: Record<string, unknown>;
  /** Which variable produced this write, so a failure can be attributed. */
  variable: string;
  /** What changed, for the confirmation the user reads before applying. */
  from: number;
  to: number;
}

export interface Refusal {
  variable: string;
  reason: string;
}

export interface ApplyPlan {
  writes: Write[];
  refused: Refusal[];
}

/** Below this, a "change" is solver noise rather than an edit anyone asked for. Millimetre scale. */
export const EPSILON_M = 1e-6;

/**
 * `move_element` takes **deltas**, not absolutes — `move_element(guid, dx, dy, dz)`.
 *
 * That is the one place this mapping can silently produce a wrong model rather than refuse: passing a
 * solved absolute coordinate as `dx` moves the element to `current + target` instead of `target`, and
 * the result is plausible geometry in the wrong place. The delta is computed here, from the variable's
 * own `current`, which is why `LockVariable` carries it.
 */
const AXIS: Record<string, "dx" | "dy" | "dz"> = { x: "dx", y: "dy", z: "dz" };

function writeFor(v: LockVariable, target: number): Write | Refusal {
  const base = { variable: v.name, from: v.current, to: target };
  const cls = v.ifcClass.toLowerCase();

  if (v.param === "thickness") {
    if (!cls.includes("wall")) {
      return { variable: v.name, reason: `set_wall_thickness only applies to walls, not ${v.ifcClass}` };
    }
    return { ...base, op: "set_wall_thickness", params: { guid: v.guid, thickness: target } };
  }
  if (v.param === "depth") {
    return { ...base, op: "set_extrusion_depth", params: { guid: v.guid, depth: target } };
  }
  const axis = AXIS[v.param];
  if (axis) {
    return { ...base, op: "move_element", params: { guid: v.guid, [axis]: target - v.current } };
  }
  return {
    variable: v.name,
    reason: `no edit recipe writes '${v.param}' on ${v.ifcClass}`,
  };
}

const isRefusal = (w: Write | Refusal): w is Refusal => "reason" in w;

/**
 * Plan the edits for a solved system.
 *
 * Unchanged variables produce no write — applying a no-op edit still versions the model, and a
 * publish nobody asked for is how "I only moved one wall" turns into a reload banner for everyone.
 */
export function planApply(
  variables: LockVariable[], solved: Record<string, number>,
): ApplyPlan {
  const writes: Write[] = [];
  const refused: Refusal[] = [];
  for (const v of variables) {
    const target = solved[v.name];
    if (typeof target !== "number" || !Number.isFinite(target)) {
      // The solver did not return this variable. Silence here would look like "nothing to change".
      refused.push({ variable: v.name, reason: "the solver returned no value for this variable" });
      continue;
    }
    if (Math.abs(target - v.current) < EPSILON_M) continue;   // unchanged — not an edit
    const w = writeFor(v, target);
    if (isRefusal(w)) refused.push(w); else writes.push(w);
  }
  return { writes, refused };
}

/** A one-line summary for the confirmation step. Names the refusals — that is the whole point. */
export function describePlan(plan: ApplyPlan): string {
  const n = plan.writes.length;
  const head = n === 0 ? "Nothing to apply" : `Apply ${n} change${n === 1 ? "" : "s"}`;
  if (!plan.refused.length) return `${head}.`;
  return `${head} — ${plan.refused.length} cannot be written: `
    + plan.refused.map((r) => r.variable).join(", ");
}
