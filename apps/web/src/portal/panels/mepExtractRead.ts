/** MEP-DISCIPLINE-DARK — MEP counted in a modeller's vocabulary, paged without saying so.
 *
 *  `mep.extract_from_model` returns the element counts two ways: `by_class` (`IfcDuctSegment`,
 *  `IfcPipeFitting`, …) and **`by_discipline`** — Mechanical / Plumbing / Electrical, which is the
 *  division a contractor actually buys MEP by and the one a GC's eye goes to first. `by_discipline`
 *  was undeclared on the client type, so the card could only render IFC classes. *A count is only
 *  useful in the vocabulary of whoever has to act on it.*
 *
 *  The class table was also `by_class.slice(0, 15)` with no note, over a list that runs to 25 —
 *  TRUNC-COUNTED, in a card whose header is a total. `class_count` is the server's own count of
 *  distinct classes, so the page can be stated against it.
 *
 *  **And a clean negative worth keeping.** The discipline came from
 *  `discipline_name(discipline_of_ifc_class(cl)) or "Mechanical"` — a fallback that picks a real
 *  answer rather than admitting it has none, and one that would land a mis-attributed plumbing
 *  element straight in a procurement breakdown. Measured: **all 25 of `_MEP_CLASSES` resolve**, so
 *  the branch was unreachable and nothing was ever mis-attributed. It is written up as a negative
 *  rather than a fix; what keeps it that way is `services/api/test_mep.py` asserting every key
 *  resolves, plus the fallback now reading `Unattributed` and `unattributed` being declared here so
 *  a screen can say the columns are short rather than a reader assuming they are exhaustive.
 */
import type { MepModelExtract } from "../../api/model";

export type { Tone } from "./statedBasis";
import type { Tone } from "./statedBasis";

/** The headline: the total, and the disciplines it splits into. */
export function mepHeadline(a: MepModelExtract): { text: string; tone: Tone } {
  if (!a.model_scored) {
    return { tone: "", text: "Load a model to count MEP elements off it." };
  }
  if (a.mep_elements === 0) {
    return {
      tone: "warn",
      text: "A model is loaded and it contains no MEP elements of any class this reads — ducts, "
        + "pipes, terminals, equipment or electrical.",
    };
  }
  const discs = a.by_discipline.map((d) => `${d.discipline} ${d.count.toLocaleString()}`).join(" · ");
  return {
    tone: a.unattributed ? "warn" : "",
    text: `${a.mep_elements.toLocaleString()} MEP element(s) in ${a.class_count} IFC class(es)`
      + (discs ? ` — ${discs}` : ""),
  };
}

/** Discipline rows with their share, which is what makes two columns comparable at a glance. */
export function disciplineRows(a: MepModelExtract): {
  discipline: string; count: string; share: string;
}[] {
  const total = a.mep_elements || 0;
  return a.by_discipline.map((d) => ({
    discipline: d.discipline,
    count: d.count.toLocaleString(),
    share: total ? `${Math.round((1000 * d.count) / total) / 10}%` : "—",
  }));
}

/** How the disciplines were decided, verbatim from the engine. The client does not paraphrase a
 *  basis — and here the basis matters, because a discipline derived from the IFC CLASS is a
 *  different claim from one read off the model's own discipline metadata. */
export function mepBasis(a: MepModelExtract): string {
  return a.note;
}

/** Elements the classifier could not place. Absent on a clean extract, because the measured answer
 *  is zero and a permanent `0 unattributed` row is a decoration. */
export function unattributedNote(a: MepModelExtract): string | null {
  if (!a.unattributed) return null;
  return `${a.unattributed.toLocaleString()} element(s) could not be attributed to a discipline and `
    + "are counted under Unattributed — the discipline columns above are short by that much.";
}

export const CLASS_PAGE = 15;

export function classRows(a: MepModelExtract, limit = CLASS_PAGE): {
  ifcClass: string; label: string; count: string;
}[] {
  return a.by_class.slice(0, limit).map((x) => ({
    ifcClass: x.ifc_class, label: x.label, count: x.count.toLocaleString(),
  }));
}

/** `showing N of M` against the SERVER's count of distinct classes, not the length of what shipped. */
export function classPageNote(a: MepModelExtract, limit = CLASS_PAGE): string | null {
  if (a.class_count <= limit) return null;
  return `Showing the ${limit} largest of ${a.class_count} IFC class(es) present. The discipline `
    + "totals above are over all of them.";
}
