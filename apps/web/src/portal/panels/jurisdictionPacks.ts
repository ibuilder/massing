/** R23-JURISDICTION-PACKS — the wording for a compliance answer that belongs to somebody.
 *
 *  Pure, so the rules can be tested without a DOM. The rules that matter here are all about
 *  ATTRIBUTION, because that is what this feature is for: a pack is a set of data requirements
 *  published by an authority, and the number it produces will be quoted at the party whose model
 *  failed. **A compliance figure detached from whose rules it measured is the thing the server's own
 *  docstring refuses to emit** — so nothing in this file renders one either.
 *
 *  The load-bearing case is the built-in `example` pack. It asserts nothing about any real place and
 *  is attributed to nobody, and it is the pack a first-time user will run, because it is the only
 *  one there before anything is imported. A result from it that reads like a compliance verdict is
 *  worse than no feature: it tells somebody their model passes rules that do not exist.
 */

/** One requirement's result inside a pack. */
export interface PackRuleResult {
  id: string;
  name?: string;
  severity?: string;
  matched?: number;
  violations?: number;
}

/** What one pack said about the model, with the authority that said it. */
export interface PackOutcome {
  id: string | null;
  name: string | null;
  authority: string | null;
  edition: string | null;
  is_example: boolean;
  total_rules: number;
  failing_rules: number;
  total_violations: number;
  rules?: PackRuleResult[];
}

/** A pack as the library lists it. */
export interface PackHeader {
  id: string;
  jurisdiction: string;
  authority: string;
  name: string;
  edition: string;
  source: string;
  is_example?: boolean;
  requirements?: { id: string }[];
}

/** Which packs apply to a project, and — when none do — why not. */
export interface Applicability {
  jurisdiction: string | null;
  packs: { id: string }[];
  adopted: boolean;
  why?: string | null;
  explicit?: boolean;
}

/** The check result. `model_scored` false means the figures are ABSENT, not zero. */
export interface CheckOutcome {
  model_scored: boolean;
  packs: PackOutcome[];
  total_requirements: number;
  failing_requirements?: number;
  total_violations?: number;
  satisfied?: boolean;
  note?: string;
}

/** `AUTHORITY · edition` — the line that makes a pack citable at a glance. */
export function packHeadline(p: PackHeader): string {
  const n = p.requirements?.length ?? 0;
  return `${p.name} — ${p.authority}, ${p.edition} · ${p.jurisdiction} · `
    + `${n} requirement${n === 1 ? "" : "s"}`;
}

/**
 * The caveat that must ride along with anything the example pack produced.
 *
 * Empty string for a real pack — a caveat printed on every result trains the reader to skip it, and
 * then it is not there when it matters.
 */
export function exampleCaveat(p: { is_example?: boolean }): string {
  return p.is_example
    ? "DEMONSTRATION PACK — attributed to nobody and asserting nothing about any real jurisdiction. "
      + "A result from it is not a compliance finding and must not be reported as one."
    : "";
}

/**
 * Whether this project has requirements at all, and the reason when it does not.
 *
 * A project with no jurisdiction gets the server's own reason rather than a default pack: a
 * requirement set from the wrong authority is not a conservative approximation of the right one, it
 * is a different answer that looks exactly the same.
 */
export function adoptionLine(a: Applicability): string {
  if (a.explicit) {
    return `Applying 1 pack by id — chosen explicitly, not resolved from this project's jurisdiction.`;
  }
  if (!a.jurisdiction) {
    return a.why || "This project has no jurisdiction set, so no data requirements can be resolved.";
  }
  if (!a.adopted) return a.why || `No pack has been imported for ${a.jurisdiction}.`;
  const n = a.packs.length;
  return `${n} pack${n === 1 ? "" : "s"} apply in ${a.jurisdiction}.`;
}

/**
 * Whether a check can be offered, and the reason when it cannot.
 *
 * Two refusals, and they are different: nothing applies (no jurisdiction, or no pack imported for
 * it), versus packs apply but no model is loaded to check them against. Collapsing them would tell
 * somebody to import a pack when what they need is to upload a model.
 */
export function checkGate(a: Applicability, modelLoaded: boolean): { can: boolean; why: string } {
  if (!a.adopted && !a.explicit) {
    return { can: false, why: adoptionLine(a) };
  }
  if (!modelLoaded) {
    return { can: false,
             why: "No model is loaded, and a data-requirement check needs a model to check." };
  }
  return { can: true, why: "" };
}

/**
 * What the check found — and never a bare number.
 *
 * `model_scored` false is reported as the absence it is. Every figure is followed by whose rules
 * produced it, and an example-pack run says so in the same breath rather than in a footnote.
 */
export function checkSummary(r: CheckOutcome): string {
  if (!r.model_scored) {
    return r.note || "No model was scored, so there is no result — this is not a pass.";
  }
  if (!r.packs.length || r.total_requirements === 0) {
    return "No requirements were evaluated, so there is nothing to report — this is not a pass.";
  }
  const failing = r.failing_requirements ?? 0;
  const verdict = failing === 0
    ? `Satisfied: ${r.total_requirements} requirement${r.total_requirements === 1 ? "" : "s"} met`
    : `${failing} of ${r.total_requirements} requirement${r.total_requirements === 1 ? "" : "s"} `
      + `failing (${r.total_violations ?? 0} violation${(r.total_violations ?? 0) === 1 ? "" : "s"})`;
  return `${verdict}, against ${attributionLine(r.packs)}.`;
}

/** Whose rules these were. Always plural-safe, and always names the example pack as an example. */
export function attributionLine(packs: PackOutcome[]): string {
  if (!packs.length) return "no pack";
  return packs
    .map((p) => `${p.authority || "an unattributed source"} ${p.edition || ""}`.trim()
      + (p.is_example ? " (demonstration pack — not a real requirement)" : ""))
    .join("; ");
}

/** One pack's row in the results table, worst first is the caller's job. */
export function outcomeLine(p: PackOutcome): string {
  const head = `${p.name || p.id || "pack"} — ${p.authority || "unattributed"} ${p.edition || ""}`.trim();
  if (p.total_rules === 0) return `${head}: no requirements`;
  const ok = p.total_rules - p.failing_rules;
  return `${head}: ${ok}/${p.total_rules} met, ${p.total_violations} violation`
    + `${p.total_violations === 1 ? "" : "s"}`;
}

/**
 * The confirmation before removing a pack from the shared library.
 *
 * Names the blast radius, because the library is global: deleting is not a per-project action and
 * every project resolving that jurisdiction loses the requirements.
 */
export function deleteConfirm(p: PackHeader): string {
  return `Delete the pack "${p.name}" (${p.authority}, ${p.edition})?\n\n`
    + `The pack library is SHARED — every project in ${p.jurisdiction} stops resolving these `
    + "requirements, not just this one. Imported packs can be re-imported from their source.";
}

/**
 * The import refusal, shown verbatim.
 *
 * The server's 422 `detail` names the missing citation field or the exact dotted property path that
 * would have made a requirement silently pass forever. **That text is the instruction**, so a
 * generic "import failed" throws away the only thing that tells the user what to fix — which is
 * also why `httpCore.json()` was taught to carry `detail` through in the first place.
 */
export function importRefusal(message: string): string {
  const m = (message || "").trim();
  return m
    ? `The pack was refused: ${m}`
    : "The pack was refused and the server gave no reason — nothing was stored.";
}
