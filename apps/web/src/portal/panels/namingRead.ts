/** NAMING-UNREAD — a compliance audit that names every offending file, printed as two percentages.
 *
 *  ## What the card showed, and what the engine had computed
 *
 *  `naming.audit` validates every CDE container filename against the ISO 19650 pattern
 *  `Type_Discipline_Description_Revision_Date` and every drawing number against the NCS sheet-ID
 *  grammar, and returns a bounded list of **up to 200 offending rows per register, each with the
 *  exact reason it failed**. The Naming compliance card rendered a two-row table —
 *  `Containers | 5 | 1 | 20.0%` — and discarded the list on every call. *The actionable half of a
 *  compliance audit was computed and thrown away*: a reader was told that 80% of their containers
 *  are misnamed and not which ones, nor why, nor what the right name would have been.
 *
 *  ## The percentage was also wrong, and in the direction that makes work
 *
 *  `container_id` — the ISO 19650 name — is an OPTIONAL field on `information_container`; only
 *  `title` is required. The audit fell back to the title and validated *that* against a filename
 *  convention. Measured on a five-row register holding exactly one misnamed file:
 *
 *  | | as shipped | now |
 *  |---|---|---|
 *  | headline | `20.0%` of 5 | `50.0%` of the 2 named |
 *  | violations | 4 | 1 |
 *  | unnamed | — | 3 |
 *
 *  Three of those four violations read *expected Type_Discipline_Description_Revision_Date (>=5
 *  '_'-separated fields), got 1* against the titles **Ground floor plan**, **Structural calcs** and
 *  **Fire strategy** — character-for-character the issue reported for `New file (2).pdf`, the one
 *  file that is genuinely misnamed. *One sentence for two different pieces of work*: three rows need
 *  an ID recorded, one needs the file renamed. `unnamed` is a third state now, never folded into
 *  either percentage — the same split `envelope.audit` makes between `total` and `checked`, and the
 *  reason BASIS-UNREAD's lesson applies here too: an empty-state branch keyed on the EVALUABLE
 *  count reports the wrong absence.
 *
 *  ## The basis was fetched from a second route the card could lose
 *
 *  `audit()` returns `conventions()` — the identical object the standalone `/naming/conventions`
 *  route serves, verified byte-for-byte — and the card fetched it from that route anyway, in a
 *  `Promise.all` with `.catch(() => null)`. So a failed second request printed the percentages with
 *  no convention beside them: **the basis was optional and the verdict was not**. It travels with
 *  the verdict now and the second client method is gone, under the rule
 *  `services/api/test_route_reachability.py` already states — *a route whose payload is a strict
 *  subset of another route's is not a second capability.*
 *
 *  ## And there was no way to check a name before using it
 *
 *  `/naming/validate` had no client method at all and sat frozen in `UNREACHABLE_ROUTES`. The
 *  product could tell a reader their filename was wrong and could not tell them whether the one
 *  they were about to use instead is right — so the violations table had no fix loop. It does now,
 *  and the parse is shown rather than a bare valid/invalid, because *the fields the parser READ are
 *  what teach the convention.*
 */
import type { NamingAudit, NamingCheck, NamingRegisterAudit } from "../../api/types";

export type { Tone } from "./statedBasis";
import type { Tone } from "./statedBasis";

/** The compliance headline for one register, with the population it is over.
 *
 *  Four states. The two that did not exist before are the ones that matter: a register with rows
 *  and nothing NAMED is not an empty register, and a percentage over a subset says which subset.
 *  Tone is the worse of the two concerns — a real naming failure outranks a recording gap, because
 *  a wrong name is already on a file somebody else has downloaded. */
export function namingHeadline(reg: NamingRegisterAudit, noun: string): { text: string; tone: Tone } {
  if (reg.total === 0) return { tone: "", text: `No ${noun}s registered yet.` };
  if (reg.named === 0) {
    return {
      tone: "warn",
      text: `${reg.total} ${noun}(s) registered and NONE carries a recorded name — this register has `
        + `no compliance verdict at all.`,
    };
  }
  const pct = reg.compliance_pct == null ? "" : ` (${reg.compliance_pct}%)`;
  const unnamed = reg.total - reg.named;
  const scope = unnamed
    ? `, over the ${reg.named} of ${reg.total} ${noun}(s) that carry a name — the other ${unnamed} `
      + `have none recorded`
    : `, over all ${reg.total} ${noun}(s)`;
  const failing = reg.named - reg.compliant;
  return {
    tone: failing ? "crit" : unnamed ? "warn" : "good",
    text: `${reg.compliant}/${reg.named} compliant${pct}${scope}.`,
  };
}

/** The rows outside every percentage above, and the field that would bring them in.
 *
 *  Separate from the violations because the FIX is different, which is the whole finding: these
 *  rows need a name recorded, not a file renamed. */
export function unnamedNote(reg: NamingRegisterAudit, noun: string, field: string): string | null {
  if (!reg.unnamed_count) return null;
  const shown = reg.unnamed.length < reg.unnamed_count
    ? ` (listing the first ${reg.unnamed.length})`
    : "";
  return `${reg.unnamed_count} of ${reg.total} ${noun}(s) have no ${field} recorded and are outside `
    + `every percentage above${shown} — record the name and they become checkable.`;
}

/** The convention the audit ruled against, returned verbatim from the audit's OWN response.
 *
 *  The client does not get to paraphrase a basis, and it no longer gets to lose one: this is a key
 *  on the verdict rather than a second request. */
export function conventionNote(a: NamingAudit): string {
  const c = a.conventions;
  return `Containers: ${c.container.pattern} (separator "${c.container.separator}") — ${c.container.note} `
    + `· Sheets: ${c.sheet.pattern} — ${c.sheet.note}`;
}

/** One row per offending name: the register reference, the human title, the string that was ruled
 *  on, and every reason. `ref` first because it is what makes the row findable. */
export function violationRows(reg: NamingRegisterAudit): {
  ref: string; title: string; name: string; why: string;
}[] {
  return reg.violations.map((v) => ({
    ref: v.ref || "—",
    title: v.title || "—",
    name: v.name,
    why: v.issues.join("; ") || "no reason given",
  }));
}

export function unnamedRows(reg: NamingRegisterAudit): { ref: string; title: string }[] {
  return reg.unnamed.map((u) => ({ ref: u.ref || "—", title: u.title || "(untitled)" }));
}

/** `showing N of M` for a bounded list, with the cap named from the SERVER's own number.
 *
 *  `violations.length` is the page and `violations_count` is the total; TRUNC-COUNTED is three
 *  screens that printed the first as the second. The cap is `max_violations` rather than a literal
 *  200, so the client cannot come to disagree with the server about the bound it is subject to. */
export function pageNote(shown: number, count: number, max: number, noun: string): string | null {
  if (shown >= count) return null;
  return `Showing ${shown} of ${count} ${noun} — the server caps each list at ${max}. Fix these and `
    + `re-run to see the rest.`;
}

export function violationPageNote(reg: NamingRegisterAudit, max: number): string | null {
  return pageNote(reg.violations.length, reg.violations_count, max, "violation(s)");
}

export function unnamedPageNote(reg: NamingRegisterAudit, max: number): string | null {
  return pageNote(reg.unnamed.length, reg.unnamed_count, max, "unnamed row(s)");
}

/** The on-demand check's verdict. `valid` is a plain boolean over one name the caller supplied, so
 *  there is no coverage question here — the subject is the whole population. */
export function checkHeadline(c: NamingCheck): { text: string; tone: Tone } {
  if (c.valid) return { tone: "good", text: `"${c.name}" satisfies the ${c.kind} convention.` };
  return {
    tone: "crit",
    text: `"${c.name}" does not satisfy the ${c.kind} convention: ${c.issues.join("; ") || "no reason given"}`,
  };
}

/** What the parser actually READ, which is what teaches the convention — a bare FAIL tells somebody
 *  there is a problem and not which field to change. Empty on a name the parser could not split at
 *  all, where there is nothing to show and the issues carry the whole answer. */
export function checkFieldRows(c: NamingCheck): { field: string; value: string }[] {
  return Object.entries(c.fields || {})
    .filter(([, v]) => v !== "" && v != null)
    .map(([k, v]) => ({ field: k.replace(/_/g, " "), value: String(v) }));
}
