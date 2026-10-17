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

/** What defines this kit's scope right now, said in words.
 *
 *  Takes `modelLoaded` because **the selector branch otherwise states a number it cannot know**.
 *  With no index `resolve()` matches nothing, so the sentence read *"matching 0 elements right
 *  now"* — a measurement, on a screen whose own caveat says no measurement is possible. Found by
 *  review, and it is the exact defect `modelCaveat` exists to prevent, one function over:
 *  **writing the guard is not the same as applying it everywhere it belongs.** */
export function scopeNote(kit: PrefabKit, modelLoaded: boolean): string {
  if (kit.scope_source === "frozen") {
    return `Scope is the frozen list: ${kit.frozen_count} GlobalId${kit.frozen_count === 1 ? "" : "s"}, `
      + "written when the kit was released. The selector is only the record of how it was arrived at.";
  }
  if (!modelLoaded) {
    return "Scope is the selector, and with no model loaded there is no way to say what it matches. "
      + "Nothing is written down yet — releasing without writing it hands the shop a query rather "
      + "than a list.";
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

/** What the write actually did, and whether it matched what was confirmed.
 *
 *  `expected` is the count the confirmation named. **This started as a DETECTION control and is now
 *  an INVARIANT CHECK, and the message had to change with it.** It shipped saying *"the model
 *  changed between confirming and writing"*, which was the right sentence while the write had no
 *  precondition: the server re-resolved the selector and the divergence was the expected,
 *  unpreventable outcome of a race (PREFAB-FREEZE-RACE, raised in review on PR #524).
 *
 *  `if_scope_version` now makes that case a **409 rather than a 200** — the server refuses the
 *  write when either half of the scope moved — so reaching here with a mismatch no longer means the
 *  model changed. It means the token did NOT cover something that changed the resolution, which is
 *  a different and worse statement, and the old sentence would have sent the reader to check a
 *  model that is innocent.
 *
 *  **Kept rather than deleted, and the reason is a measurement about somebody else's module.** The
 *  mismatch is unreachable only because the index cache has exactly one content writer
 *  (`POST /projects/{pid}/properties/index`) and that route bumps the model version — a fact in
 *  `routers/properties.py`, not here, which a future change could break without touching this
 *  file. A backstop whose reachability rests on another module's behaviour is worth keeping; a
 *  backstop whose MESSAGE describes the case it no longer catches is not. */
export function freezeSummary(r: PrefabFreezeResult, expected?: number): string {
  const head = `${r.ref || "Kit"}: ${r.frozen} element${r.frozen === 1 ? "" : "s"} written `
    + `(selector matched ${r.matched}). ${r.note}`;
  if (expected != null && expected !== r.frozen) {
    return `${head} — NOTE: you confirmed ${expected}, and the server accepted the scope version you `
      + "were shown, so this difference should not have been possible. Treat the written scope as "
      + "unverified and check it before releasing.";
  }
  return head;
}

/** What to say when the server refused the write because the scope moved — the 409 recovery.
 *
 *  `before` is the kit the reader confirmed against; `after` is the re-read. It names WHAT moved,
 *  because "try again" with no reason is the message that teaches people to click twice and stop
 *  reading.
 *
 *  **The third branch is the one worth writing down.** The two halves of the token are the model
 *  version and the record's `modified_at`, and neither is a count — so a model republished with a
 *  different set of elements that happens to match the same NUMBER moves the token while every
 *  figure on the card stays identical. Reporting that as "nothing changed, try again" would be the
 *  empty-versus-absent confusion wearing a third costume: the scope genuinely moved, and the only
 *  honest thing to say is that the numbers agreeing is not evidence the elements do. */
export function staleScopeNote(before: PrefabKit, after: PrefabKit): string {
  const head = `${before.ref || "This kit"}: not written — its scope moved while the confirmation `
    + "was open, so the server refused rather than record a list you have not seen. ";
  if (before.selector.selector !== after.selector.selector) {
    return `${head}The selector itself was edited (now “${after.selector.selector}”, `
      + `matching ${after.selector.matched}). The numbers below are the new ones.`;
  }
  if (before.selector.matched !== after.selector.matched) {
    return `${head}It matched ${before.selector.matched} when you confirmed and matches `
      + `${after.selector.matched} now. Check the new scope below before writing it.`;
  }
  return `${head}The model was republished. It still matches ${after.selector.matched} element`
    + `${after.selector.matched === 1 ? "" : "s"} — but the same count is not the same elements, so `
    + "the scope below has to be confirmed again rather than assumed unchanged.";
}
