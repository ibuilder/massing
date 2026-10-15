/** DOCHEALTH-VACUOUS — `naming 100%` over names the server wrote itself, and every list behind the
 *  other percentages thrown away.
 *
 *  ## The naming percentage measured this product, not the project
 *
 *  `docmanager.upload` builds every filed name with `_standard_name`, and `health` validates
 *  `f["name"]` — the generated one. So the percentage answers *did the auto-namer produce a
 *  standard name*, and it is 100% by construction. Measured: a document uploaded as
 *  **"Final final v2.pdf"** is filed as `DOC_G_FinalFinalV2_P01_2026-10-15.pdf` and the strip read
 *  **naming 100%**. True, and nothing a reader can act on.
 *
 *  `orig_name` is already stored on every entry, so `named_at_source_pct` costs nothing and is the
 *  number that is about the project: how many documents arrived already conforming. On the same
 *  two-file fixture it reads **50%**, with the one renamed file named and both spellings shown.
 *  *Two questions, and only the second can be acted on by anyone but a developer.*
 *
 *  ## And a long title filed a document with no revision in its name
 *
 *  `_safe` truncates at 120 characters and used to be handed the whole assembled name, so a
 *  300-character title pushed the revision and the date off the end: `DOC_G_Aaaa…`, **three fields**,
 *  which the validator reports as *"expected Type_Discipline_Description_Revision_Date (>=5
 *  '_'-separated fields), got 3"*. In a revision-controlled CDE the revision in the filename is the
 *  one thing the standard exists to guarantee. `_standard_name` bounds the DESCRIPTION now, so the
 *  fields that must survive do. *Found by probing the auto-namer with hostile titles — every title
 *  in the suite was short.*
 *
 *  ## The lists
 *
 *  `required_missing` and `by_cde_state` were DECLARED and rendered nowhere, so a strip printing
 *  `required coverage 18.2%` had the missing nine folders in hand and discarded them — the
 *  LOD-UNREAD shape exactly. `orphans` was undeclared AND unactionable: a list of bare file ids,
 *  which is a list a reader resolves one lookup at a time. It carries name and folder now.
 */
import type { DocOrphan, DocRenamed, DocumentsHealth } from "../../api/types";

export type { Tone } from "./statedBasis";
import type { Tone } from "./statedBasis";

function pct(v: number | null): string {
  return v == null ? "—" : `${v}%`;
}

/** The one-line strip: the count, and the one naming number that is about the project.
 *
 *  **Neither `naming_compliance_pct` nor `revision_control_pct` is in the headline**, and that is
 *  the finding rather than a layout choice: `upload` generates every filed name AND assigns every
 *  revision, so both are 100% by construction. The strip used to lead with the first and print the
 *  second beside it — two of its three percentages could not vary. The basis note carries them. */
export function healthHeadline(h: DocumentsHealth): { text: string; tone: Tone } {
  if (h.total_files === 0) {
    return { tone: "", text: "No documents on file yet." };
  }
  const kept = h.superseded_kept ? ` · ${h.superseded_kept} superseded revision(s) kept` : "";
  return {
    tone: h.named_at_source_pct != null && h.named_at_source_pct < 50 ? "warn" : "",
    text: `${h.total_files} document(s) on file · ${pct(h.named_at_source_pct)} named to the standard `
      + `at source${kept}`,
  };
}

/** The two naming numbers, said apart. The engine's own basis follows verbatim. */
export function namingNote(h: DocumentsHealth): string | null {
  if (!h.total_files) return null;
  const re = h.renamed_on_intake
    ? ` ${h.renamed_on_intake} document(s) were renamed on intake.`
    : " Every document arrived already conforming.";
  return `Filed names ${pct(h.naming_compliance_pct)} conform and revision control is `
    + `${pct(h.revision_control_pct)} — the server writes both, so these check this module rather `
    + `than the document set.${re}`;
}

export function namingBasis(h: DocumentsHealth): string {
  return h.naming_basis;
}

/** `orig_name → name`, so a reader can see what their people actually typed. */
export function renamedRows(h: DocumentsHealth): DocRenamed[] {
  return h.renamed;
}

export function renamedPageNote(h: DocumentsHealth): string | null {
  if (!h.renamed_truncated) return null;
  return `Showing ${h.renamed.length} of ${h.renamed_on_intake} renamed document(s).`;
}

/** Required-folder coverage with the denominator and the MISSING folders, which were declared and
 *  rendered nowhere. A percentage whose complement a reader cannot see cannot be acted on. */
export function coverageNote(h: DocumentsHealth): { text: string; tone: Tone } | null {
  if (!h.required_total) return null;
  const have = h.required_total - h.required_missing.length;
  if (!h.required_missing.length) {
    return { tone: "good", text: `All ${h.required_total} required folders have at least one document.` };
  }
  return {
    tone: have ? "warn" : "crit",
    text: `${have} of ${h.required_total} required folders have a document (${pct(h.required_coverage_pct)}) `
      + `— nothing filed in: ${h.required_missing.join(", ")}`,
  };
}

/** The CDE-state spread, declared and unread. Ordered by the ISO 19650 progression rather than by
 *  count, because the shape of the spread is the point: everything still WIP reads differently from
 *  everything published, at the same total. */
const STATE_ORDER = ["wip", "shared", "published", "archived"];

export function stateRows(h: DocumentsHealth): { state: string; count: number }[] {
  const seen = Object.entries(h.by_cde_state);
  const rank = (s: string) => {
    const i = STATE_ORDER.indexOf(s);
    return i < 0 ? STATE_ORDER.length : i;
  };
  return seen
    .sort((a, b) => rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]))
    .map(([state, count]) => ({ state, count }));
}

/** Documents filed outside the standard taxonomy. Absent rather than zero on a clean set, because
 *  the engine's own basis says the list is normally empty by construction. */
export function orphanNote(h: DocumentsHealth): string | null {
  if (!h.orphan_count) return null;
  const shown = h.orphans.length < h.orphan_count ? ` (showing ${h.orphans.length})` : "";
  return `${h.orphan_count} document(s) sit outside the standard folder taxonomy${shown} — the `
    + "upload and move routes both refuse a non-standard folder, so these were filed before a folder "
    + "left the standard tree.";
}

export function orphanRows(h: DocumentsHealth): DocOrphan[] {
  return h.orphans;
}

export function orphanBasis(h: DocumentsHealth): string | null {
  return h.orphan_count ? h.orphan_basis : null;
}
