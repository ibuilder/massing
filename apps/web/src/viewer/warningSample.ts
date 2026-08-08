// WARN-1 — pull the offender GUIDs out of a model-warning's sample.
//
// The feed's rows carry `sample: unknown[]`, and that is not laziness in the type: the producers
// genuinely disagree. Checked against `services/api/src/aec_api/model_qa.py` rather than guessed:
//
//   duplicate_guids        -> ["1a2b…", "3c4d…"]                    plain GUID strings
//   orphans / blank        -> [{ class, name, guid }]               objects carrying the guid
//   unenclosed / wrong_storey -> [{ name, guid, … }]                same
//   overlapping_duplicates -> [{ class, location, count }]          **no guid at all**
//
// The server's own `_qa_sample` already normalises across two different KEYS (`sample`, `groups`);
// this normalises across the element SHAPES underneath them.
//
// **The last row is the one that matters.** A group of stacked duplicates is identified by class and
// location, not by GUID, so there is nothing to select. A UI that offers every row a zoom affordance
// gives that row a click that does nothing — the silent-failure shape this codebase keeps finding.
// Returning an empty list is the honest answer, and the caller is expected to render accordingly.

/** An IFC GlobalId is 22 characters of the IFC base-64 alphabet. */
const GUID_RE = /^[0-9A-Za-z_$]{22}$/;

/** True for a string that is actually an IFC GlobalId, not just any string in the sample. */
export function isGuid(v: unknown): v is string {
  return typeof v === "string" && GUID_RE.test(v);
}

/**
 * Every GUID this sample can offer, de-duplicated and order-preserving.
 *
 * Order is preserved because the server sorts the punch list worst-first and the sample follows that
 * order; re-sorting here would silently disagree with the row the user clicked.
 */
export function guidsFromSample(sample: unknown): string[] {
  if (!Array.isArray(sample)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  const push = (g: unknown) => {
    if (isGuid(g) && !seen.has(g)) { seen.add(g); out.push(g); }
  };
  for (const entry of sample) {
    if (isGuid(entry)) { push(entry); continue; }
    if (entry && typeof entry === "object") {
      const o = entry as Record<string, unknown>;
      push(o.guid);
      // A few producers carry a list rather than a single offender.
      if (Array.isArray(o.guids)) for (const g of o.guids) push(g);
    }
    // Anything else — a group keyed by class+location, a bare count — contributes nothing, on purpose.
  }
  return out;
}
