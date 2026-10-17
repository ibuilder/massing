/**
 * VERSION-VALUES — `versions.diff` has computed `FireRating: 1HR → 2HR` since VERSION-COMPARE
 * landed, and the compare card printed `FireRating`.
 *
 * The engine stores a bounded per-property VALUE snapshot at fingerprint position [7] for exactly
 * this: its own comment reads *"a per-property VALUE snapshot rides position [7] so a diff can show
 * `FireRating: 1HR -> 2HR`, not just 'FireRating changed'"*, bounded on three axes
 * (`_MAX_VALUE_ELEMENTS`, `_MAX_VALUE_PROPS`, `_MAX_VALUE_LEN`) so the version blob cannot balloon,
 * **and it says so when a cap bites** rather than pretending it has everything.
 *
 * The client type declared `changed_properties?: { property; status }[]` — no `from`, no `to` — so
 * the whole feature was unreachable from the one screen that compares two versions, and
 * `values_truncated` and `property_values_available` were undeclared beside it. *A snapshot the
 * server pays to store and bound, that no type names, is work nobody can spend.*
 *
 * Found through RESPKEY-DELEGATED's gap for this route. The gap listed the two coverage keys; the
 * undeclared `from`/`to` are NESTED inside `changed_properties` and that gate compares TOP-LEVEL
 * keys only, so it could not see them at all. *A key-set comparison at the root cannot see a shape
 * that is wrong one level down* — the second limit of that instrument found in a day, and the
 * reason its findings are a place to look rather than a list of what is wrong.
 *
 * Pure, returning plain text: `property`, the values and the element name are all model-derived
 * free text, and `kvTable` sets them with `textContent`, so nothing here may return markup.
 */

export interface PropertyChange {
  property: string;
  status: "added" | "removed" | "changed";
  /** The value in the EARLIER version (`from` = the `a` side), when the snapshot covered it. */
  from?: string | null;
  /** The value in the LATER version (`to` = the `b` side), when the snapshot covered it. */
  to?: string | null;
}

export interface DiffCoverage {
  modified_available: boolean;
  property_detail_available?: boolean;
  property_values_available?: boolean;
  values_truncated?: boolean;
}

/**
 * One property change, as a reader says it.
 *
 * The direction is pinned by a test, because getting it backwards is the one defect here that would
 * look completely plausible: `versions.diff` reads `before = fa.get(g)` for version `a` and assigns
 * `from` from `before`, so `from` is the `a` side — even though the locals holding them are spelled
 * `vb`/`va`, which reads the other way round.
 */
export function propertyChangeText(p: PropertyChange): string {
  const has = (v: string | null | undefined): v is string => v !== undefined && v !== null;
  if (p.status === "added") return has(p.to) ? `${p.property}: + ${p.to}` : `${p.property} (added)`;
  if (p.status === "removed") {
    return has(p.from) ? `${p.property}: − ${p.from}` : `${p.property} (removed)`;
  }
  // A CHANGED property with no values is the capped case, and it must not render as "x → x" or as
  // a bare name that looks like the no-snapshot case. It says the key changed, which is all the
  // hash comparison proved.
  if (!has(p.from) && !has(p.to)) return `${p.property} (changed, values not stored)`;
  return `${p.property}: ${has(p.from) ? p.from : "—"} → ${has(p.to) ? p.to : "—"}`;
}

/** The property clause for one modified row: up to `cap` changes, with a count of the rest. */
export function propertyClause(props: PropertyChange[] | undefined, cap = 6): string {
  const list = props ?? [];
  if (!list.length) return "";
  const shown = list.slice(0, cap).map(propertyChangeText).join(", ");
  // "…" SAID "THERE IS MORE" AND NOT HOW MUCH, which is the shape TRUNC-COUNTED is named for one
  // size down. The count is free here — the array is in hand.
  return list.length > cap ? `${shown} +${list.length - cap} more` : shown;
}

export type CoverageTone = "ok" | "warn" | "unknown";

/**
 * What this diff could and could not read, or `null` when there is nothing to qualify.
 *
 * Three distinct causes, kept distinct, because the actions differ: no fingerprints at all means
 * re-publish both versions; fingerprints without a value snapshot means one of them predates
 * VERSION-COMPARE and only the property NAMES can be shown; a snapshot that hit a cap means the
 * values are there for most of the model and absent past the bound. *Folding three causes into one
 * "unavailable" is what sends a reader to the wrong fix* — the lesson VERDICT-UNOWNED recorded.
 */
export function coverageNote(d: DiffCoverage): { text: string; tone: CoverageTone } | null {
  if (!d.modified_available) {
    return { text: "Modified elements cannot be detected between these two versions — one of them "
                   + "was published before element fingerprints were stored. Added and removed are "
                   + "still exact. Re-publish to compare properties.",
             tone: "unknown" };
  }
  if (!d.property_detail_available) {
    return { text: "Which properties changed is not available for this pair — the per-property "
                   + "hashes are missing from one version, so a modified element is reported "
                   + "without naming the property.",
             tone: "unknown" };
  }
  if (!d.property_values_available) {
    return { text: "Property NAMES only: one of these versions predates the per-property value "
                   + "snapshot, so a change shows which property moved but not from what to what.",
             tone: "unknown" };
  }
  if (d.values_truncated) {
    return { text: "⚠ Some property values were capped out of the version snapshot (it is bounded "
                   + "per element, per property and per value length so the stored blob cannot "
                   + "balloon). Those changes are real and show as \"values not stored\" — the "
                   + "property changed, the before/after was not kept.",
             tone: "warn" };
  }
  return null;              // full detail, nothing to qualify — no line rather than a reassurance
}

export const COVERAGE_CSS: Record<CoverageTone, string> = {
  ok: "var(--status-good)", warn: "var(--status-warn)", unknown: "var(--muted)",
};

/** The modified table is a PAGE. Says so with both numbers, or `""` when it is the whole list. */
export function modifiedPageNote(shown: number, total: number): string {
  return shown < total ? `Showing the first ${shown} of ${total} modified elements.` : "";
}
