/** The prefab-kit register's presentation rules — pure, so they can be tested without a DOM.
 *
 *  R23-PREFAB-KIT shipped its whole server side and **no client at all**: three routes, zero callers
 *  in `apps/web/src` until 2026-09-11. Two of them could not even be reported dark, because their
 *  last static segment is five characters and the reachability gate does not assess a leaf that
 *  short; the third was hidden behind an English sentence about the wet season.
 *
 *  The distinction this file exists to make visible is `scope_source`. A kit's scope is a *selector*
 *  before release and a *frozen GlobalId list* after it. A released kit still sourced from its
 *  selector is a live query the shop is fabricating against — it looks identical to a correct one on
 *  every screen, which is the failure `services/api/src/aec_api/prefab_kit.py` says the mechanism
 *  exists to prevent. So it is stated in words on every row, not inferred from a badge.
 */
import type { PrefabKit, PrefabRegister, PrefabFreezeResult } from "../../api/prefab";

/** The server's blocker codes, in its own severity order, with what a person does about each. */
const BLOCKER_LABELS: Record<string, string> = {
  released_without_freezing: "released with no frozen scope — the shop is building against a live query",
  scope_drift: "the model no longer matches what was frozen",
  unresolved_elements: "frozen GlobalIds are missing from the current model",
  selector_error: "the scope selector does not parse",
  need_by_passed: "the on-site date has passed",
  delivery_late: "the delivery it depends on is late",
  no_delivery_date: "no delivery date to check against",
  task_constrained: "the installing task still has open constraints",
  empty_scope: "the scope matches no elements",
  no_pull_task: "not linked to a pull-plan task",
  no_model: "no model loaded — nothing about this scope can be checked",
};

/** A human sentence for a blocker code, falling back to the code itself for one we do not know.
 *
 *  The fallback is deliberate and is the reason this returns the raw code rather than "unknown": the
 *  server owns this list, and a code added there must still reach the screen legibly on the day it
 *  ships rather than the day someone remembers to edit this map. */
export function blockerLabel(code: string): string {
  return BLOCKER_LABELS[code] ?? code;
}

/** The register's one-line state. */
export function registerHeadline(reg: PrefabRegister): string {
  if (!reg.total) return "No prefab kits on this project yet.";
  return `${reg.total} kit${reg.total === 1 ? "" : "s"} — ${reg.ready} ready, ${reg.blocked} blocked.`;
}

/** The caveat that outranks every figure on the screen, or null when a model is loaded.
 *
 *  Without a model index every scope count is *unverifiable*, not zero — and a register that renders
 *  `0 elements` for every kit while quietly meaning "cannot tell" is the wrong-answer-shaped-like-a-
 *  right-answer this codebase keeps finding. */
export function modelCaveat(reg: PrefabRegister): string | null {
  return reg.model_loaded ? null
    : "No model is loaded for this project, so no kit's scope, bill of materials or drift can be "
      + "checked. The counts below are what the records say, not what the model contains.";
}

/** What defines this kit's scope right now, said in words. */
export function scopeNote(kit: PrefabKit): string {
  if (kit.scope_source === "frozen") {
    return `Scope is the frozen list: ${kit.frozen_count} GlobalId${kit.frozen_count === 1 ? "" : "s"}, `
      + "written when the kit was released. The selector is only the record of how it was arrived at.";
  }
  return `Scope is the selector, matching ${kit.selector.matched} element`
    + `${kit.selector.matched === 1 ? "" : "s"} right now. Nothing is written down yet — releasing `
    + "without writing it hands the shop a query rather than a list.";
}

/** The drift sentence, or null when there is nothing to say. */
export function driftLine(kit: PrefabKit): string | null {
  const d = kit.drift;
  if (!d || !d.drifted) return null;
  return `${d.added.length} added, ${d.removed.length} removed since the scope was written. ${d.means}`;
}

/** Whether this kit's scope can be written now, and — when it cannot — the reason to show instead.
 *
 *  Mirrors `prefab_kit.freeze_blocker` so the button is absent rather than offered-and-refused. It is
 *  deliberately NOT the authority: the server re-checks and answers with its own constants, because a
 *  client-side gate is a convenience and a server-side one is the rule. */
export function freezeGate(kit: PrefabKit, modelLoaded: boolean): { can: boolean; why: string } {
  if (!modelLoaded) return { can: false, why: "needs a loaded model to resolve the selector" };
  if (kit.selector.error) return { can: false, why: kit.selector.error };
  if (!kit.selector.matched) return { can: false, why: "the selector matches no elements" };
  if (kit.selector.truncated) return { can: false, why: "the selector result was truncated — narrow it first" };
  return { can: true, why: "" };
}

/** The confirmation shown before writing a kit's scope.
 *
 *  Names the blast radius in the two cases that differ: writing a scope for the first time, and
 *  REPLACING one the shop may already be building from. The second is not a louder version of the
 *  first — it can change what is being fabricated, so it says so. */
export function freezeConfirm(kit: PrefabKit): string {
  const n = kit.selector.matched;
  const head = `Write ${n} element${n === 1 ? "" : "s"} onto ${kit.ref || "this kit"} as its scope?`;
  if (kit.frozen_count) {
    return `${head}\n\nThis REPLACES the ${kit.frozen_count} GlobalId${kit.frozen_count === 1 ? "" : "s"} `
      + "already written. If the kit is released, the shop is building against that list and this "
      + "changes it.";
  }
  return `${head}\n\nFrom here the shop builds this list. The selector becomes the record of how it `
    + "was arrived at, and any later divergence is reported rather than applied.";
}

/** What the write actually did. */
export function freezeSummary(r: PrefabFreezeResult): string {
  return `${r.ref || "Kit"}: ${r.frozen} element${r.frozen === 1 ? "" : "s"} written `
    + `(selector matched ${r.matched}). ${r.note}`;
}
