import type { ApiClient } from "../../api/client";

/**
 * CODE-ADOPT-DARK — which code editions govern here, and **which of them are actually this
 * jurisdiction's**.
 *
 * `/codes/adoptions` resolves a USPS state code to its adopted editions and had no client caller.
 * The engine (`services/data/src/aec_data/codes.py`) is scrupulous about what it knows: a top-level
 * `resolved`, an `as_of` year, a `verify` note on every answer, and — the field this module exists
 * for — a **per-family `source`** of `"seed"` or `"baseline"`. Its own docstring says the seed *"is
 * a starting point, never an authority"*.
 *
 * ## `resolved` is a verdict over a subset, in every case the seed can produce
 *
 * Measured against the shipped seed, not assumed: six jurisdictions are seeded and **all six are
 * MIXED** — CA 4 of 8 families, FL 4, NY 3, TX 3, WA 3, **IL 1 of 8**. There is no jurisdiction for
 * which `resolved: true` means every edition shown is that jurisdiction's, so a screen rendering
 * the flag alone would state the national baseline as Illinois law for seven of the eight families
 * — and the seed's own comment on that row reads *"no statewide building code; home-rule adopts"*.
 *
 * **And the shortcut is the worst offender.** The response hands a reader `primary: {IBC, IECC,
 * A117.1}`, which is the three a consumer naturally prints. **`A117.1` is seeded by nobody**, so
 * the accessibility edition in `primary` is the baseline for every jurisdiction including all six
 * seeded ones — and an unseeded state returns the identical `primary` to a project with no
 * jurisdiction at all. *A convenience field that collapses a provenance distinction is where the
 * distinction gets lost.*
 *
 * This is the master-builder rule as a defect class: *never let a jurisdiction-specific answer
 * masquerade as a universal one.* The panel this renders into already states the same principle for
 * data packs — *"requirements from the wrong authority are a different answer that looks exactly
 * like the right one"* — and resolves no pack at all without a jurisdiction. Code editions get the
 * same treatment: with no jurisdiction set the server is not asked, because it would answer with
 * the baseline.
 */
export type Adoptions = Awaited<ReturnType<ApiClient["codeAdoptions"]>>;

export interface AdoptionScope {
  /** `none` — no jurisdiction, nothing was asked. `unseeded` — every edition is the baseline.
   *  `mixed` — some are this jurisdiction's. `complete` — all of them are. */
  kind: "none" | "unseeded" | "mixed" | "complete";
  /** The answer in one phrase; the panel bolds it. */
  headline: string;
  /** What follows from it, and what to do. */
  detail: string;
  tone: "ok" | "warn" | "";
  /** Families whose edition came from this jurisdiction's seed. */
  seeded: number;
  total: number;
}

/**
 * The headline. `jurisdiction` is the PROJECT's, which is what decides whether to ask at all.
 *
 * **Returns PLAIN TEXT, split into a phrase and its detail, and that is not a style choice.** The
 * first draft returned one `html` string carrying `<b>` emphasis, and `apps/web/src/ui/innerHtmlGuard.test.ts`
 * refused it by name: the only interpolated value is the jurisdiction, which arrives from the
 * project record, so an `innerHTML` sink carrying it is a sink carrying stored input. Every sibling
 * in this panel already answers in plain text and is escaped at the call site — `adoptionLine`,
 * `packHeadline`, `checkSummary`. *A ratchet that rejects a shape the neighbours do not use is
 * telling you the shape is wrong, not that it needs an exemption.*
 */
export function adoptionScope(a: Adoptions | null, jurisdiction: string | null): AdoptionScope {
  if (!jurisdiction || !a) {
    return {
      kind: "none", seeded: 0, total: 0, tone: "",
      headline: "No jurisdiction set",
      detail: "so no governing code editions are resolved for this project. The server would "
        + "answer with the national baseline, which is not a fact about anywhere; set the "
        + "project's jurisdiction to get an adoption.",
    };
  }
  const j = jurisdiction.toUpperCase();
  const total = a.codes.length;
  const seeded = a.codes.filter((c) => c.source === "seed").length;
  const asOf = a.as_of ? ` as of ${a.as_of}` : "";
  if (!a.resolved || seeded === 0) {
    return {
      kind: "unseeded", seeded, total, tone: "warn",
      headline: `No adoption is seeded for ${j}`,
      detail: `all ${total} edition(s) below are the national baseline, not ${j}'s adoption. `
        + "Treat them as a starting point and confirm with the AHJ.",
    };
  }
  if (seeded < total) {
    return {
      kind: "mixed", seeded, total, tone: "warn",
      headline: `${seeded} of ${total} edition(s) are ${j}'s${asOf}`,
      detail: `the other ${total - seeded} are the national baseline, which is not a fact about `
        + `${j}. Each row below says which it is.`,
    };
  }
  return {
    kind: "complete", seeded, total, tone: "ok",
    headline: `All ${total} edition(s) are ${j}'s${asOf}`,
    detail: "every family below came from this jurisdiction's own adoption.",
  };
}

/** One row per code family, each carrying where its edition came from. */
export function adoptionRows(a: Adoptions, jurisdiction: string | null):
  { k: string; v: string; strong?: boolean }[] {
  const j = (jurisdiction || "").toUpperCase();
  return a.codes.map((c) => ({
    k: `${c.family} ${c.edition}`,
    v: c.source === "seed"
      ? `${c.name} — adopted in ${j || "this jurisdiction"}`
      : `${c.name} — national baseline, NOT ${j || "this jurisdiction"}'s adoption`,
    strong: c.source === "seed",
  }));
}

/**
 * The caveat on `primary`, named family by family.
 *
 * `primary` is the shortcut — three editions lifted out of the eight — and it carries no `source`,
 * so a reader who takes it gets the mixed answer with the provenance stripped. Returns `null` only
 * when every primary entry really is this jurisdiction's, which today never happens: `A117.1` is
 * seeded by no jurisdiction in the shipped reference seed.
 */
export function primaryCaveat(a: Adoptions, jurisdiction: string | null): string | null {
  const bySource = new Map(a.codes.map((c) => [c.family, c.source] as const));
  const baseline = Object.keys(a.primary).filter((f) => bySource.get(f) !== "seed");
  if (!baseline.length) return null;
  const j = (jurisdiction || "").toUpperCase() || "this jurisdiction";
  return `Of the three headline editions, ${baseline.join(", ")} `
    + `${baseline.length === 1 ? "is" : "are"} the national baseline rather than ${j}'s adoption`
    + (baseline.includes("A117.1")
        ? " — the accessibility edition is seeded for no jurisdiction at all, so it is always the "
          + "baseline"
        : "")
    + ".";
}

/**
 * What to say when nothing is seeded for this jurisdiction: name the ones that ARE.
 *
 * Without it the refusal is a dead end that reads as a claim about the jurisdiction. With it, it
 * reads as what it is — a gap in a dated reference seed. `null` when the list is unavailable, so a
 * failed second request costs the caveat and not the section.
 */
export function seededHint(seeded: readonly string[] | null): string | null {
  if (!seeded?.length) return null;
  return `The reference seed carries statewide specifics for ${seeded.join(", ")} only; `
    + "everywhere else resolves to the baseline. This is a gap in a dated seed, not a finding "
    + "about your jurisdiction.";
}
