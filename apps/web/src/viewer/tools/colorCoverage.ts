import type { ApiClient } from "../../api/client";

/**
 * COLOR-UNSET — colouring the model by a property is a DATA-COVERAGE tool, and the legend left out
 * the coverage.
 *
 * `/elements/color-by` returns `total`, **`colored`**, **`unset`** and the buckets. The portal's own
 * description of the feature is *"Shade the model by any attribute to spot missing / inconsistent
 * data visually"* — so the elements that carry no value are the point, and a legend that lists only
 * the buckets reports the opposite of what the tool is for.
 *
 * **Live where it already shipped.** `modelStatePanels.ts`'s "Isolate a phase in 3D" calls
 * `colorBy(pid, "Massing_Phasing.Status", 6)` and renders `r.buckets` alone — so a model with 40
 * phased elements out of 4,000 shows four tidy phase buttons and nothing says that 99% is unphased.
 * For a phasing tool, the unphased set is the finding.
 *
 * ## And the picker offers two of the properties the engine enumerates
 *
 * `/elements/facets-list` exists *"to drive the viewer's 'Color by…' picker"* — every top-level
 * attribute and every pset/qto property present, each with its distinct-value count. `colorFacets`
 * was frozen in `apps/web/src/api/clientCallers.test.ts` as called by nothing, and the picker in
 * `projectPanel.ts` is two hardcoded options, IFC class and Discipline. The engine, the painter
 * (`colorBy` takes any `prop`) and the product copy all say "any attribute"; the control says two.
 *
 * **The picker is NOT built here, and the blocker is named rather than worked around.** A new panel
 * needs an entry point in `apps/web/src/viewer/app.ts`, which sits at its exact size pin in
 * `services/api/test_file_sizes.py`; and the existing control is a client-side swatch mode (class ↔
 * discipline) rather than a `colorBy` caller, so converting it is a product change about how
 * colour-by should work, not a wiring job. `colorFacets` therefore stays frozen as callerless with
 * that reason recorded beside it.
 *
 * **Two helpers were written for that picker and then DELETED.** A module that exports a decision
 * nothing calls is the very class this item is about — *writing them was the cheap part; shipping
 * them would have put another instance of it in the file documenting it.* (No count here on purpose:
 * `apps/web/src/api/clientCallers.test.ts` is the authority on what is callerless, and a narrative
 * copy of a number that has a gate is what drifts.)
 */
export type ColorBy = Awaited<ReturnType<ApiClient["colorBy"]>>;

export interface CoverageReading {
  /** `none` — nothing carries the property. `partial` — some do. `full` — every element does. */
  kind: "none" | "partial" | "full";
  text: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * How much of the model the colouring actually covers.
 *
 * Plain text; the caller escapes it. `unset` is taken from the response rather than derived as
 * `total - colored`, because they are the engine's two numbers and a consumer that recomputes one
 * from the other stops reporting the engine's answer the day they diverge.
 */
export function coverageReading(r: ColorBy): CoverageReading {
  if (!r.total) {
    return { kind: "none", tone: "",
             text: "No elements in the index to colour — load a model first." };
  }
  if (!r.colored) {
    return {
      kind: "none", tone: "bad",
      text: `NOTHING carries ${r.prop} — all ${r.total} element(s) are unset, so colouring by it `
        + "paints nothing. That absence is the finding.",
    };
  }
  if (r.unset) {
    const pct = Math.round((r.colored / r.total) * 100);
    return {
      kind: "partial", tone: "warn",
      text: `${r.colored} of ${r.total} element(s) carry ${r.prop} (${pct}%) — the other ${r.unset} `
        + "are in no bucket below and keep their existing colour. The uncoloured set is the gap this "
        + "view exists to show.",
    };
  }
  return {
    kind: "full", tone: "ok",
    text: `All ${r.total} element(s) carry ${r.prop}.`,
  };
}

/**
 * The buckets **in the engine's own order**, with the share of the COLOURED set each represents.
 *
 * It does NOT re-sort, and the first draft did — largest first, which looked like an improvement and
 * was wrong for half the responses. The engine's order is already meaningful and is meaningful
 * *differently* per `kind`: a categorical response comes back `most_common` with `Other` appended
 * last, so sorting by count is redundant and moves `Other` into the middle; a numeric response comes
 * back as ascending RANGES, so sorting by count scrambles the very axis the bins divide up. *A sort
 * that is redundant on one branch and destructive on the other is not a presentation choice.*
 *
 * Found by mutation: deleting the sort changed no test, because the categorical fixture was already
 * descending. **A reorder is invisible to a fixture that is already in that order** — hence
 * `NUMERIC_BINS` in the test beside this, whose engine order and count order are different lists.
 *
 * The share is of `colored`, not `total`: a bucket is a slice of what carries the property, and the
 * part that does not is `coverageReading`'s sentence rather than a share of anything.
 */
export function bucketRows(r: ColorBy): { k: string; v: string; guids: string[] }[] {
  return r.buckets.map((b) => ({
    k: b.label,
    v: `${b.count}`
      + (r.colored ? ` · ${Math.round((b.count / r.colored) * 100)}% of the coloured` : ""),
    guids: b.guids,
  }));
}
