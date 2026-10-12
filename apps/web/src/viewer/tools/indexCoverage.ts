import type { ElementsFreshness } from "../../api/elements";

/**
 * ELEMENTS-SILENT — the project browser can be STALE and TRUNCATED at once, and reported neither.
 *
 * Two defects on one screen, each a class this branch has corrected repeatedly, compounding:
 *
 * **① The freshness check was dark, so the defect it exists to prevent is live.**
 * `/projects/{pid}/elements/freshness` says in its own docstring that *"Authoring edits move the IFC
 * and leave the snapshot behind until the next publish, so `/elements` can return a fraction of what
 * the takeoff sees — and used to do it in complete silence… What it must do is **say so**, so a
 * browser can show '5 elements added since this list was built — republish to see them' instead of
 * quietly looking like a smaller building."* It had no client method at all, and neither
 * `/elements` caller asked anything like it.
 *
 * **② `/elements` has no total to read even if a consumer wanted one.** The route breaks at
 * `len(out) >= limit` and returns a bare array. `projectPanel.ts` asks for `limit: 5000` unfiltered,
 * so a 12,000-element model returns exactly 5,000 rows and the response carries no field that could
 * say otherwise. TRUNC-COUNTED's class in its worst form: *there is no number to misread, because
 * there is no number.* And the same list feeds A29-SPATIAL-SELECT, so spatial selection silently
 * operates on a subset too.
 *
 * `indexed_elements` closes ② without a breaking change, because it is the index's full size — the
 * right denominator for an UNFILTERED page and the wrong one for a filtered page, which this module
 * refuses to guess about.
 *
 * ## Three freshness states, not two
 *
 * `stale` is `true | false | null`, and the route is explicit that *"Unknown and current are
 * different claims and this endpoint refuses to conflate them."* A consumer that treated `null` as
 * "fine" would report a snapshot of unknown age as current, which is the whole defect one level up.
 */
export type { ElementsFreshness };

export interface IndexReading {
  /** `stale` — the model moved since the snapshot. `unknown` — cannot tell, and why.
   *  `truncated` — the page is a subset of a current index. `complete` — all of a current index. */
  kind: "stale" | "unknown" | "truncated" | "complete";
  headline: string;
  detail: string;
  tone: "ok" | "warn" | "bad" | "";
}

/**
 * What the element list in front of the user actually is.
 *
 * `shown` is the number of rows the caller received; `filtered` says whether it asked for a subset
 * of the index. **Staleness is answered before truncation** because they are not the same question
 * and the stale one is worse: a truncated page of a current index is a paging problem the user can
 * solve by narrowing, while a stale index is a different building.
 */
export function indexReading(f: ElementsFreshness, shown: number,
                             filtered = false): IndexReading {
  if (f.stale === true) {
    return {
      kind: "stale", tone: "bad",
      headline: "This list was built from an older version of the model.",
      detail: `The index holds ${f.indexed_elements} element(s) from a previous publish; the model `
        + "on disk has moved since. Elements added or changed by authoring are not here — "
        + (f.hint || "republish to rebuild the index from the current model") + ".",
    };
  }
  if (f.stale === null) {
    // TWO REASONS, and they are different advice. Not conflated with `false`, which the route is
    // explicit about, and not conflated with each other either.
    const why = !f.model_reachable
      ? "no source model can be read, so there is nothing to compare the index against"
      : "this index predates publish fingerprinting, so there is no stamp to compare";
    return {
      kind: "unknown", tone: "warn",
      headline: `Cannot tell whether this list matches the model — ${why}.`,
      detail: `${f.indexed_elements} element(s) are indexed. This is not a claim that they are `
        + "current: republish to stamp the index, after which this check becomes meaningful.",
    };
  }
  // Current index. Now, and only now, is a count comparison meaningful.
  if (!filtered && shown < f.indexed_elements) {
    return {
      kind: "truncated", tone: "warn",
      headline: `Showing ${shown} of ${f.indexed_elements} element(s) — the list is capped.`,
      detail: "The remaining elements are in the index but not on this page, so anything derived "
        + "from this list — counts, spatial selection, the tree — is about the subset. Filter by "
        + "class or storey to see the rest.",
    };
  }
  return {
    kind: "complete", tone: "ok",
    headline: filtered
      ? `Showing ${shown} element(s) from a current index of ${f.indexed_elements}.`
      : `All ${f.indexed_elements} indexed element(s) are shown, from a current index.`,
    detail: filtered
      ? "This is a filtered view, so the two numbers are not expected to match."
      : "The index matches the model on disk.",
  };
}

/**
 * Whether the reading is worth putting on screen at all.
 *
 * `complete` and unfiltered is the ordinary case and says nothing a user needs — rendering a banner
 * for it would train them to ignore the banner, which is how the three states that DO matter stop
 * being read. The other three always render.
 */
export function worthShowing(r: IndexReading): boolean {
  return r.kind !== "complete";
}

/**
 * The note itself, built HERE rather than in the panel — and that is a budget constraint, not a
 * preference.
 *
 * `viewer/tools/*` lands in the eager `app-*` chunk, and this module is reached through an
 * `await import()` from `projectPanel.ts` so its text and branching sit in a lazy chunk instead.
 * **Deferring only the READING is not enough**: the previous item on this branch was refused by
 * `npm run budget` twice, the second time because the card-BUILDING was still eager at exactly the
 * limit. So the DOM construction lives beside the reading, and the panel's eager cost is one
 * dynamic import and one `appendChild`.
 *
 * Returns `null` for the ordinary case, so the caller does not need to know the rule.
 *
 * `textContent` throughout, never `innerHTML`: `hint` is server text.
 */
export function renderIndexNote(f: ElementsFreshness, shown: number,
                                filtered = false): HTMLElement | null {
  const r = indexReading(f, shown, filtered);
  if (!worthShowing(r)) return null;
  const note = document.createElement("div");
  note.className = `result-note ${r.tone}`.trim();
  note.style.cssText = "margin:0 6px 7px;font-size:11px;line-height:1.5";
  const head = document.createElement("b");
  head.textContent = r.headline;
  const detail = document.createElement("div");
  detail.textContent = r.detail;
  detail.style.marginTop = "3px";
  note.append(head, detail);
  return note;
}
