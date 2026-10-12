import { HttpCore } from "./httpCore";
import type { DisciplineTree } from "./types";

type Ctor<T> = new (...args: any[]) => T;

/** The served classification reference: fetching it, and reading a code against it.
 *
 *  `GET /reference/disciplines` returns four payloads and the client kept one. `tree` drove the
 *  viewer's colours; `masterformat_divisions` (the division master — code, title, and the discipline
 *  each rolls up to) and `uniformat_crosswalk` (Uniformat II element → the MasterFormat divisions it
 *  procures through) were dropped at the `.then`, and they are the two that exist nowhere else in
 *  this shape: `tree.disciplines[].divisions` carries only the subset belonging to one discipline,
 *  and nothing else in the client knows that B2020 buys out of Division 08.
 *
 *  That mattered where someone types a code by hand. The Detailing panel asked for a MasterFormat
 *  section with the hint *"e.g. 08 51 00"* and had no way to say what 08 IS — so `80 51 00`, a
 *  transposition into a division that does not exist, was accepted in silence and became a
 *  classification on an IFC element.
 *
 *  Pure, so the reading is testable without a dialog. Nothing here REFUSES a code: MasterFormat
 *  reserves 48-49 and the 80s-90s for user-defined divisions, so an unknown division is a thing to
 *  say out loud, not a thing to block.
 */

/**
 * CLASSIFY-DARK — the three `/classify/*` routes, which had no client method at all.
 *
 * `classify_assist.py` exists because `classification.classify(ifc_class, system)` returns the
 * system's DEFAULT BUCKET for a class it has no entry for, and the return type cannot express the
 * difference — so an imported model full of `IfcBuildingElementProxy` prices every one of those
 * elements as *01 00 00 General Requirements* and reports a complete takeoff. The engine's answer is
 * three numbers that must be read TOGETHER: what the model `declared`, what is `proposable` from
 * evidence, and what is `unmapped`. Only the first raises `classified_pct`.
 *
 * **The declared shapes are here, not inline at the call site**, so a derivation over declarations
 * can see every field — the rule `apps/web/src/api/noRespelledShapes.test.ts` and CLASH-TRUNC paid
 * for: an inline cast is a field no audit over types can reach, which is how `truncated` went unread
 * for months on the clash panel.
 */

/** One element's classification, or the absence of one, with the evidence for it. */
export interface ProposalRow {
  guid: string;
  ifc_class: string | null;
  name: string | null;
  type_name: string | null;
  /** `declared` the model asserts it · `keyword` the element's own name determines it · `class_map`
   *  true of the CLASS and therefore identical for every element of it, right ones and wrong ones
   *  alike · `unmapped` no code at all. */
  basis: "declared" | "keyword" | "class_map" | "unmapped";
  code: string | null;
  title: string | null;
  confidence: "medium" | "low" | null;
  evidence: string;
}

/** The headline, and everything needed to know what it is a headline OF. */
export interface ClassifyCoverage {
  system: string;
  system_name: string;
  /** What `classification.classify` would return for an unmapped element — the thing an estimate
   *  silently prices them as. Named on screen because it is the whole reason this engine exists. */
  default_bucket: { code: string; title: string };
  /** False when the caller fed the property index instead of the file: the index carries no
   *  classification associations, so `classified_pct` is then a FLOOR, not a reading. */
  declared_supplied: boolean;
  total: number;
  declared: number;
  classified_pct: number | null;
  proposable: number;
  unmapped: number;
  by_basis: Record<string, number>;
  headline: string;
  counts_only_declared: string;
  unmapped_warning: string | null;
}

/** `rows` is a PAGE. `matching` is the total — the distinction TRUNC-COUNTED cost three screens. */
export interface ClassifyProposals extends ClassifyCoverage {
  rows: ProposalRow[];
  returned: number;
  matching: number;
  truncated: boolean;
  truncation_note: string | null;
}

/** A plan, not an application: `steps` are ordinary GUID-stable edit recipes for the caller to
 *  apply. `skipped` carries a REASON per GUID rather than being dropped, because a plan that
 *  silently covers 40 of the 60 elements somebody ticked is worse than one that refuses. */
export interface ClassifyPlan {
  system: string;
  steps: { recipe: string; params: Record<string, unknown> }[];
  count: number;
  skipped: { guid: string; reason: string }[];
  note: string;
}

/** One row of the division master. */
export interface MfDivision { code: string; title: string; discipline: string | null }
/** One Uniformat II element and the MasterFormat divisions it maps to. */
export interface UfCrosswalk { code: string; title: string; masterformat_divisions: string[] }
/** The flat discipline catalog — code → display name, for naming what a division rolls up to. */
export interface DisciplineRef { code: string; name: string }

export interface ClassificationRefs {
  disciplines: DisciplineRef[];
  masterformat_divisions: MfDivision[];
  uniformat_crosswalk: UfCrosswalk[];
}

/** The leading division of a MasterFormat section — "08 51 00" and "085100" both sit in `08`. */
export function divisionOf(code: string): string | null {
  const digits = code.replace(/[^0-9]/g, "");
  return digits.length >= 2 ? digits.slice(0, 2) : null;
}

/** The Uniformat entry a code belongs to: the LONGEST declared prefix, because the table holds both
 *  `B` and `B20` and the coarser one must not win over the finer. */
export function crosswalkFor(code: string, crosswalk: UfCrosswalk[]): UfCrosswalk | null {
  const want = code.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
  if (!want) return null;
  let best: UfCrosswalk | null = null;
  for (const x of crosswalk) {
    const c = x.code.toUpperCase();
    if (want.startsWith(c) && (!best || c.length > best.code.length)) best = x;
  }
  return best;
}

/**
 * What to tell the person about the code they just typed, or `null` when this system has no
 * reference to read it against (OmniClass and Uniclass are not served here, and saying nothing is
 * correct — an annotation that appears for two systems and not the others is information, whereas a
 * fabricated one is not).
 *
 * `known: false` is the one worth acting on: it means the code names a division the master does not
 * carry, which is either a user-defined division or a typo, and the caller says so without refusing.
 */
export function codeAnnotation(system: string, code: string, refs: ClassificationRefs):
    { text: string; known: boolean } | null {
  const sys = system.toLowerCase();
  if (sys === "masterformat") {
    const div = divisionOf(code);
    if (!div) return null;
    const row = refs.masterformat_divisions.find((d) => d.code === div);
    if (!row) return { text: `Division ${div} is not in the MasterFormat division master`, known: false };
    const disc = refs.disciplines.find((d) => d.code === row.discipline);
    return { text: `Division ${row.code} · ${row.title}${disc ? ` (${disc.name})` : ""}`, known: true };
  }
  if (sys === "uniformat") {
    const row = crosswalkFor(code, refs.uniformat_crosswalk);
    if (!row) return { text: `${code} is not under any Uniformat II element in the crosswalk`, known: false };
    const divs = row.masterformat_divisions;
    return { text: `${row.code} · ${row.title}${divs.length ? ` → MasterFormat ${divs.join(", ")}` : ""}`,
             known: true };
  }
  return null;
}

/** Everything `GET /reference/disciplines` sends — and the declared type used to be `{ tree }`
 *  alone, which is not what the route sends: the other three payloads arrived on every call and
 *  were dropped at the `.then`. One alias, so the two cached call sites below cannot drift apart. */
type ClassificationReference = { tree: DisciplineTree } & ClassificationRefs;

/** A mixin, not two more methods on `client.ts`: the size ratchet in
 *  `services/api/test_file_sizes.py` refused the growth, which is the pin working exactly as its
 *  comment says it should. `disciplineTree` came across with the new accessor rather than being
 *  left behind — they are one question (*what does the served vocabulary say?*) answered from one
 *  cached request, and splitting them would put the cache in a different file from its readers. */
export function withClassification<TBase extends Ctor<HttpCore>>(Base: TBase) {
  return class Classification extends Base {
    private _classRef?: Promise<ClassificationReference>;
    /** The unified discipline tree (colors + IFC-class→discipline map) — the viewer, model browser,
     *  and any legend share one served vocabulary. */
    disciplineTree(): Promise<DisciplineTree> {
      return (this._classRef ??= this.json<ClassificationReference>("/reference/disciplines")).then((r) => r.tree);
    }
    /** The division master + Uniformat crosswalk + flat discipline catalog, for reading back a code
     *  the user typed. Shares the cached request above rather than issuing a second one.
     *
     *  The `??=` is repeated rather than factored into a private helper on purpose:
     *  `apps/web/src/api/clientCallers.test.ts` asks which CLIENT METHODS no screen can reach, and
     *  it reads the application outside `api/`, so a helper called only from in here reads as an
     *  endpoint nobody wired. Two explicit call sites keep that gate measuring what it means to. */
    classificationRefs(): Promise<ClassificationRefs> {
      return (this._classRef ??= this.json<ClassificationReference>("/reference/disciplines")).then(
        ({ disciplines, masterformat_divisions, uniformat_crosswalk }) =>
          ({ disciplines, masterformat_divisions, uniformat_crosswalk }));
    }

    /** CLASSIFY-DARK: how much of the model carries a cost code, and what the rest would need.
     *
     *  Counts only what the model DECLARES. Derived codes are proposals and never raise the figure —
     *  a percentage that included our own guesses would measure the guessing, not the model. */
    classifyCoverage(pid: string, system = "masterformat") {
      return this.json<ClassifyCoverage>(
        `/projects/${pid}/classify/coverage?system=${encodeURIComponent(system)}`);
    }
    /** One row per element with its basis and evidence. `basis` filters to one kind of claim;
     *  `class_map` rows are worth reviewing as a group because they are identical for every element
     *  of that class. The response's `matching` is the total and `rows` is a page of it. */
    classifyProposals(pid: string, system = "masterformat",
                      opts: { basis?: ProposalRow["basis"]; limit?: number } = {}) {
      const q = new URLSearchParams({ system });
      if (opts.basis) q.set("basis", opts.basis);
      if (opts.limit != null) q.set("limit", String(opts.limit));
      return this.json<ClassifyProposals>(`/projects/${pid}/classify/proposals?${q}`);
    }
    /** Turn an explicit list of accepted GUIDs into `set_classification` recipe steps. Returns the
     *  plan; applying it is a separate, authored act through `editBatch`. */
    classifyPlan(pid: string, accept: string[], system = "masterformat", edition?: string) {
      return this.json<ClassifyPlan>(`/projects/${pid}/classify/plan`, {
        method: "POST",
        body: JSON.stringify(edition ? { accept, system, edition } : { accept, system }) });
    }
  };
}
