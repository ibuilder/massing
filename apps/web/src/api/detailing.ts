/** Detailing carriers: the informational attachments an element carries — classification codes
 *  (keynote / spec / element) and associated documents (details, installation instructions) — the
 *  rule engine that writes them in bulk, and the QA that audits what is missing.
 *
 *  **SCALE-SEAM (98).** *What informational carriers are attached to this element, write them, and
 *  which are missing?* Five methods: `elementDetailing` (the inspector), `classify` and
 *  `attachDocument` (the two writers), `applyDetailingRules` (the rule engine that writes both in
 *  bulk) and `validateDetailing` (the gap audit).
 *
 *  **The witness is a 1:1 AND TOTAL field-to-writer map**, the shape (96) established. The reader's
 *  response has exactly two carrier arrays, and `services/data/src/aec_data/detailing.py` holds
 *  exactly two writers, one per array:
 *
 *    `classifications[]`  <-  `classify`         (writes `IfcRelAssociatesClassification`)
 *    `documents[]`        <-  `attachDocument`   (writes `IfcRelAssociatesDocument`)
 *
 *  `element_detailing` walks `HasAssociations` and branches on precisely those two relationship
 *  types — nothing else contributes a field — so the map is derived from the reader's own body, not
 *  inferred from names. The other two methods are the same two writes under automation:
 *  `applyDetailingRules` runs the condition-to-content rule set and writes BOTH carrier kinds, and
 *  `validateDetailing` reports elements a rule applies to that lack the required code.
 *
 *  **What this does NOT claim, and it is the same limit (96) recorded.** `attachOmDocument` —
 *  moved to `model.ts` in (96) — is a purpose-tagged wrapper of the SAME
 *  `detailing.attach_document`, so it also writes `IfcRelAssociatesDocument` and its output appears
 *  in `documents[]`. *"These are all the writers of this reader's fields"* is therefore **false**.
 *  The map is 1:1 and total over `detailing.py`, which is the claim the evidence supports; one
 *  method answering the turnover question reaches the same carrier from another file, and that
 *  overlap was named when it moved rather than discovered here.
 *
 *  *Two weaker witnesses, labelled as such rather than promoted.* `viewer/tools/detailingSection.ts`
 *  calls only the two READERS, so it corroborates them and bounds nothing; and these five were
 *  CONTIGUOUS in `client.ts` (119-145), which means — unlike (95), where non-contiguity was the
 *  whole argument — a positional split would have found this set too. **Adjacency agreeing with the
 *  answer is not evidence for it**; it is worth stating precisely because it looks like support.
 *
 *  *`api.classify()` has no call site.* `viewer/tools/detailingSection.ts` drives the recipe through
 *  the generic `authorAndReload("classify", ...)` path, so the typed method is bypassed.
 *  `api/clientCallers.test.ts` counts it as reached because it matches bare string literals too — a
 *  looseness that file's own docstring declares deliberate, preferring a higher ceiling to a false
 *  unreachability report. Recorded here because the next reader of this file will otherwise assume
 *  the method is live.
 */
import type { NeedsEditIfc } from "./types";

type Ctor<T> = new (...args: any[]) => T;

export function withDetailing<TBase extends Ctor<NeedsEditIfc>>(Base: TBase) {
  return class Detailing extends Base {
  /** W11 Track D: one element's attached carriers — classification codes + documents (details/instructions). */
  elementDetailing(pid: string, guid: string) {
    return this.json<{ guid: string; name: string; ifc_class: string;
      classifications: { system: string | null; code: string | null; title: string | null }[];
      documents: { identification: string | null; name: string | null; location: string | null; description: string | null }[] }>(
      `/projects/${pid}/detailing/${encodeURIComponent(guid)}`);
  }
  /** W11 Track D: classify elements with a keynote/spec/element code (UniFormat/MasterFormat/OmniClass). */
  classify(pid: string, guids: string[], system: string, code: string, name?: string, edition?: string, publish = true) {
    return this.editIfc(pid, "classify", { guids, system, code, name, edition }, publish);
  }
  /** W11 D3: auto-detail — run the condition→content rule set (e.g. exterior window → IBC flashing
   *  detail + 08 51 00), writing code/detail bundles to every matching element. */
  applyDetailingRules(pid: string, publish = true) {
    return this.editIfc(pid, "apply_detailing_rules", {}, publish);
  }
  /** W11 D3: IDS-style QA — elements that a rule applies to but are missing their required keynote/spec code. */
  validateDetailing(pid: string) {
    return this.json<{ rules_evaluated: number; gaps: number;
      elements: { rule: string; guid: string; name: string; missing: string }[] }>(
      `/projects/${pid}/detailing/rules/validate`);
  }
  /** W11 Track D: attach a document (detail drawing / installation instruction) to elements. */
  attachDocument(pid: string, guids: string[], name: string,
                 opts: { location?: string; identification?: string; description?: string; purpose?: string } = {}, publish = true) {
    return this.editIfc(pid, "attach_document", { guids, name, ...opts }, publish);
  }
  };
}
