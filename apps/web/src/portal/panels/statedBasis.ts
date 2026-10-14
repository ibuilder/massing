/** BASIS-UNREAD — two verdicts whose own engine says what they are worth, printed without it.
 *
 *  ## The envelope card: `4/4 assemblies compliant (100.0%)` over 4 of 40
 *
 *  `envelope.audit` counts an assembly as `checked` only once it can RULE on it — a readable IECC
 *  climate zone AND a readable R-value or U-factor. `total` is every assembly registered, and
 *  `compliance_pct` is over `checked`. The card read `compliant`, `checked` and `compliance_pct`,
 *  and **never `total`**, so the two populations could diverge arbitrarily without a mark on the
 *  screen. Measured against a live server on a 40-row register where 4 rows are dimensioned:
 *
 *  | registered | checked | headline as shipped |
 *  |---|---|---|
 *  | 40 | 4 | `4/4 assemblies compliant (100.0%)` |
 *  | 40 | 0 | `no envelope assemblies registered` |
 *
 *  **The second row is the worse one and it is the quieter one.** `checked` is falsy, so the card
 *  took its empty-state branch and reported *no assemblies registered* over forty of them — not a
 *  number with a missing qualifier but a flat denial that the register exists. A reader acts on
 *  "nothing is registered" by registering something; the forty rows are already there, waiting for
 *  a climate zone. *An empty-state branch keyed on the EVALUABLE count reports the wrong absence.*
 *
 *  And `climate_zone` and `element_type` are both OPTIONAL fields on the module, so registering an
 *  assembly before dimensioning it is not misuse — it is the normal order of work.
 *
 *  ## The basis, which nobody could read even deliberately
 *
 *  `note` was undeclared on the client type, so no TypeScript could reach it:
 *
 *  > Opaque assemblies vs IECC 2021 minimum R; fenestration vs maximum U, by climate zone.
 *  > **Representative prescriptive values — a first-pass screen, not a stamped energy model.**
 *
 *  That sentence is the difference between a screen and a submittal, and an unqualified
 *  `100% compliant` on an envelope tab is exactly the thing somebody forwards to a plan reviewer.
 *
 *  ## The per-assembly numbers that make a FAIL actionable
 *
 *  `required_min_r` / `provided_r` (opaque), `required_max_u` / `provided_u` (fenestration) and
 *  `margin` were all computed and all undeclared, so the table could only render `PASS`/`FAIL`/`—`.
 *  *A FAIL with no requirement beside it tells a designer there is a problem and not what to
 *  change.* `margin` is signed as headroom in both directions, which is why one column can carry
 *  both families.
 *
 *  ## And the 20-row cap kept the wrong rows
 *
 *  `results.slice(0, 20)` is register order, and in the measured fixture 16 of the first 20 rows
 *  were the ones with no verdict. The cap stays — a 500-row table is its own defect — but the page
 *  is ordered FAIL, then unevaluable, then PASS, and says so. *A cap that hides the findings is the
 *  same mistake as a total that hides the exclusions.*
 *
 *  ## The commissioning dossier: a substring match rendered as an assignment
 *
 *  `cx.dossier` says so itself — *"Punch mentions are a substring match on description/location
 *  (the punchlist module has no system field)."* `note` was already declared on `cxDossier` and
 *  simply unread, while `open_punch_mentions` rendered in `var(--status-warn)` with no caveat. A
 *  count of punch items whose TEXT mentions a system is not a count of punch items against that
 *  system, and the warn colour asserts the second.
 */
import type { EnvelopeAudit, EnvelopeAssemblyCheck } from "../../api/model";

export type Tone = "" | "good" | "warn" | "crit";

/** Literal, not `var(--status-${tone})`: a custom property assembled at runtime cannot be resolved
 *  and is dropped in silence (`apps/web/src/ui/cssVars.test.ts` holds that line). */
export const TONE_CSS: Record<Tone, string> = {
  "": "",
  good: "var(--status-good)",
  warn: "var(--status-warn)",
  crit: "var(--status-crit)",
};

/** The default page size, matching the cap the card already applied. */
export const ASSEMBLY_PAGE = 20;

function unevaluable(r: EnvelopeAssemblyCheck): boolean {
  return r.compliant == null;
}

/** The compliance headline, with the population it is over.
 *
 *  Four states, and the two that did not exist before are the ones that matter: a register with
 *  rows and nothing evaluable is NOT an empty register, and a percentage over a subset says which
 *  subset. Tone is the worse of the two concerns — a real IECC failure outranks a coverage gap. */
export function envelopeHeadline(a: EnvelopeAudit): { text: string; tone: Tone } {
  if (a.total === 0) {
    return { tone: "", text: "No envelope assemblies registered yet." };
  }
  if (a.checked === 0) {
    return {
      tone: "warn",
      text: `${a.total} assembly(ies) registered and NONE could be checked — this envelope has no `
        + `compliance verdict at all.`,
    };
  }
  const missing = a.total - a.checked;
  const failing = a.checked - a.compliant;
  const pct = a.compliance_pct == null ? "" : ` (${a.compliance_pct}%)`;
  const scope = missing
    ? `, over ${a.checked} of ${a.total} registered assembly(ies) — the other ${missing} could not `
      + `be checked`
    : `, over all ${a.total} registered assembly(ies)`;
  return {
    tone: failing ? "crit" : missing ? "warn" : "good",
    text: `${a.compliant}/${a.checked} compliant${pct}${scope}.`,
  };
}

/** What is outside every percentage above, counted and grouped by the engine's own reason.
 *
 *  Grouped rather than listed: the reasons are a closed set of three and the register is not, so
 *  `30 × no valid climate zone (1–8)` is the actionable form.
 *
 *  **The COUNT comes from the rollup and the REASONS from the rows**, which are two different
 *  populations if the server ever pages `results`. It does not today — `envelope.audit` returns
 *  every row — but TRUNC-COUNTED is three screens that printed the length of a page as a total, so
 *  the two are derived separately and a shortfall is declared rather than quietly rescaling the
 *  denominator. */
export function envelopeCoverageNote(a: EnvelopeAudit): string | null {
  const unruled = a.total - a.checked;
  if (unruled <= 0) return null;
  const out = a.results.filter(unevaluable);
  const by = new Map<string, number>();
  for (const r of out) {
    const why = r.issue || "no reason given";
    by.set(why, (by.get(why) ?? 0) + 1);
  }
  const parts = [...by.entries()]
    .sort((x, y) => y[1] - x[1] || x[0].localeCompare(y[0]))
    .map(([why, n]) => `${n} × ${why}`);
  const reasons = parts.length ? `: ${parts.join(" · ")}` : "";
  const partial = out.length < unruled
    ? ` (reasons cover the ${out.length} returned in this response)`
    : "";
  return `${unruled} of ${a.total} assembly(ies) carry no verdict and are outside every `
    + `percentage above${reasons}${partial}.`;
}

/** The engine's statement of what the check IS. Suppressed on an empty register, where there is no
 *  number for it to qualify. Returned verbatim — the client does not get to paraphrase the basis. */
export function envelopeBasisNote(a: EnvelopeAudit): string | null {
  return a.total > 0 && a.note ? a.note : null;
}

/** `required / provided`, in whichever family's units the engine ruled in.
 *
 *  Either half can be absent and they are absent for different reasons, so neither is allowed to
 *  stand in for the other. An unreadable climate zone returns from `check_assembly` BEFORE a
 *  requirement is looked up, so a row can carry a perfectly good R-value and no requirement —
 *  measured on "Party wall", R-19 with no zone. Showing the R-19 is what tells the reader this is
 *  a one-field fix rather than a missing submittal. */
function reqProvided(r: EnvelopeAssemblyCheck): string {
  if (r.required_min_r != null) {
    return `R-${r.required_min_r} min / ${r.provided_r == null ? "—" : `R-${r.provided_r}`}`;
  }
  if (r.required_max_u != null) {
    return `U-${r.required_max_u} max / ${r.provided_u == null ? "—" : `U-${r.provided_u}`}`;
  }
  if (r.r_value != null) return `— / R-${r.r_value}`;
  if (r.u_factor != null) return `— / U-${r.u_factor}`;
  return "—";
}

function verdict(r: EnvelopeAssemblyCheck): { result: string; tone: Tone } {
  if (unevaluable(r)) return { result: r.issue || "not checked", tone: "warn" };
  const unit = r.required_max_u != null ? "U" : "R";
  const m = r.margin;
  if (m == null) return { result: r.compliant ? "PASS" : "FAIL", tone: r.compliant ? "good" : "crit" };
  return r.compliant
    ? { result: `PASS — ${m} ${unit} to spare`, tone: "good" }
    : { result: `FAIL — short ${Math.abs(m)} ${unit}`, tone: "crit" };
}

/** Rank for the page order: findings first, then the rows nobody could rule on, then the passes. */
function rank(r: EnvelopeAssemblyCheck): number {
  if (r.compliant === false) return 0;
  if (unevaluable(r)) return 1;
  return 2;
}

/** One row per assembly, FAILs first, carrying the requirement the verdict was measured against.
 *
 *  Sorted, not filtered: every assembly is still reachable, but the page the cap keeps is the page
 *  with the findings on it. Ties hold register order (`Array.prototype.sort` is stable). */
export function assemblyRows(a: EnvelopeAudit, cap = ASSEMBLY_PAGE): {
  name: string; type: string; zone: string; requirement: string; result: string; tone: Tone;
}[] {
  return [...a.results]
    .sort((x, y) => rank(x) - rank(y))
    .slice(0, cap)
    .map((r) => ({
      name: r.name || "(unnamed)",
      type: r.element_type || "—",
      zone: r.climate_zone == null ? "—" : String(r.climate_zone),
      requirement: reqProvided(r),
      ...verdict(r),
    }));
}

/** The cap, and the fact that the page is not register order. Both or neither: a re-ordered page
 *  presented as the first N rows is a second silent claim on top of the truncation.
 *
 *  Counted against `total` rather than `results.length`, so if the server ever pages `results` the
 *  table is named as a page OF a page instead of claiming the shorter number is everything. */
export function assemblyPageNote(a: EnvelopeAudit, cap = ASSEMBLY_PAGE): string | null {
  const shown = Math.min(a.results.length, cap);
  const ordered = a.results.some((r) => rank(r) !== 2);
  if (shown >= a.total) {
    return ordered ? "Ordered worst first — failures, then assemblies with no verdict." : null;
  }
  return `Showing ${shown} of ${a.total} assembly(ies), ordered worst first — failures, then `
    + `assemblies with no verdict, then passes.`;
}

/** The commissioning dossier's punch count, with the engine's own account of how it was derived.
 *
 *  Takes the three values rather than the response shape: the dossier type is declared once in
 *  `apps/web/src/api/documents.ts` and re-spelling it here is the defect
 *  `apps/web/src/api/noRespelledShapes.test.ts` exists to refuse. `note` is passed through rather
 *  than paraphrased; the second sentence is derived from the count and the system name, which is
 *  the part a reader cannot work out from the colour. */
export function punchMentionNote(system: string, openMentions: number, note?: string): string | null {
  if (!openMentions) return null;
  const name = system.trim() || "this system";
  return `${note ? `${note} ` : ""}So this is ${openMentions} open punch item(s) whose text `
    + `mentions "${name}" — not ${openMentions} assigned to it.`;
}
