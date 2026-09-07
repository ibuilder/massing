/**
 * COL-PAIR — the two halves of an additive text+reference pair, resolved from a module's fields.
 *
 * MOD-SWEEP's additive pattern adds a reference BESIDE the free text it names rather than converting
 * it, so existing records keep whatever somebody typed while new ones point at a record. That is the
 * right call for the DATA and it leaves the REGISTER TABLE showing only one era: a column naming one
 * half is blank for every record that filled the other.
 *
 * Measured across all 139 registers before this was written: **19 registers list the text half while
 * its reference exists and is not a column**, and one (`subcontract`) lists the reference while the
 * text is not. Both directions are wrong in a register that has been in use across the change — and
 * the obvious repair, swapping which half is the column, only moves which era goes blank. So the
 * column renders the PAIR, not the field, and one column is right for both.
 *
 * The suffix list is the same one `services/api/test_module_fields.py::text_half` uses, and
 * `fieldPairs.test.ts` asserts the two agree by reading that file — two copies of one rule is exactly
 * what drifts, and a drift here is silent: the pair simply stops being detected and the column goes
 * back to showing one era with nothing to say so.
 */

/** A minimal field shape — the parts of `ModuleDef["fields"][number]` this rule needs. */
export interface PairField {
  name: string;
  type: string;
  module?: string | null;
}

/**
 * Suffixes a reference field carries over the text it was added beside.
 *
 * Keep in step with `REF_SUFFIXES` in `services/api/test_module_fields.py`.
 */
export const REF_SUFFIXES = [
  "_company", "_loc", "_spec", "_system", "_contact", "_package", "_ref", "_id",
] as const;

const isText = (f: PairField | undefined): boolean => f?.type === "text" || f?.type === "textarea";

/**
 * The free-text field `name` was added beside, or null if the reference stands alone.
 *
 * Two spellings, because the registers use both: `supplier` beside `supplier_company`, and
 * `assignee_name` beside `assignee_contact`. The `_name` form is the one the Python rule was blind to
 * until PARTY-REFS, so it is spelled out here rather than left to be rediscovered.
 */
export function textHalf(name: string, byName: Map<string, PairField>): string | null {
  const f = byName.get(name);
  if (!f || f.type !== "reference") return null;
  for (const suf of REF_SUFFIXES) {
    if (!name.endsWith(suf)) continue;
    const stem = name.slice(0, -suf.length);
    for (const cand of [stem, `${stem}_name`]) {
      if (isText(byName.get(cand))) return cand;
    }
  }
  return null;
}

/**
 * The reference field added beside the text field `name`, or null if nothing points at it.
 *
 * The inverse of `textHalf`, and NOT derived by string-building a candidate name: a text field can
 * only be half of a pair if some reference claims it, so this asks the references. Building
 * `name + "_company"` and testing for it would miss `assignee_name`/`assignee_contact` (whose stems
 * differ) and would invent pairs for any text field that happens to share a prefix with a reference.
 */
export function referenceHalf(name: string, byName: Map<string, PairField>): string | null {
  if (!isText(byName.get(name))) return null;
  for (const [other, f] of byName) {
    if (f.type !== "reference") continue;
    if (textHalf(other, byName) === name) return other;
  }
  return null;
}

/** Which field a pair-aware cell should actually render for a given column, and how. */
export interface PairedValue {
  /** The field to render. */
  field: PairField;
  /** How to render it: as a link into `field.module`, or as plain unlinked text. */
  as: "reference" | "text";
}

/**
 * Decide what a register column should show for one record.
 *
 * `col` is the column the register was configured with; `value(name)` reads that record's stored
 * value for a field. The rule, in both directions:
 *
 * - the column's own value is present → render it as its own type (nothing clever).
 * - the column is empty and its PAIR TWIN has a value → render the twin, as the twin's type.
 * - neither has a value → the column, empty, exactly as before.
 *
 * Returning the column itself when there is no twin is what keeps this safe to apply to every
 * column: a field that is not half of a pair takes the same path it always did.
 */
export function pairedValue(
  col: PairField,
  byName: Map<string, PairField>,
  value: (name: string) => unknown,
): PairedValue {
  const filled = (v: unknown) => v !== undefined && v !== null && v !== "";
  const own: PairedValue = { field: col, as: col.type === "reference" && col.module ? "reference" : "text" };
  if (filled(value(col.name))) return own;

  const twinName = col.type === "reference" ? textHalf(col.name, byName) : referenceHalf(col.name, byName);
  if (!twinName || !filled(value(twinName))) return own;

  const twin = byName.get(twinName)!;
  return { field: twin, as: twin.type === "reference" && twin.module ? "reference" : "text" };
}
