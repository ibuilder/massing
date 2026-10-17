import type { ApiClient } from "../../api/client";
import type { DetailRefEdge, DetailRefGraph } from "../../api/types";
import { escapeHtml, withLoading } from "../../ui/feedback";
import { kvTable, resultNote, showResult } from "../../ui/result";

/**
 * DETAIL-REFS-DARK — can a reader follow the callouts in this set, and what breaks if not?
 *
 * `services/api/src/aec_api/detail_refs.py` builds the section↔detail cross-reference graph of an
 * issued drawing set and had no client method at all. It was frozen in
 * `test_route_reachability.UNREACHABLE_ROUTES`, and it was also one of the verdicts
 * `test_verdict_coverage`'s unowned bucket counted — a bucket that held three *nested* verdicts and
 * one *operator* surface beside it, so a single floor let "nobody built the screen" sit
 * indistinguishable from "no screen should ever own this".
 *
 * ## The engine was already careful, and that is what made this wireable
 *
 * NEGATED-VERDICT had to fix `navigable` before any screen could honestly show it: it was
 * `not dangling and not orphans and not unparseable`, **unconditionally True on a register with no
 * references at all**, and `test_detail_refs.py` asserted exactly that with the word *"vacuously"*
 * in the comment beside it. *The empty case was considered, named as vacuous, and then returned as
 * the same boolean a cross-referenced set returns* — and no consumer can read a word in a test
 * comment. So `assessed` leads the verdict now, `unassessed_reason` says why in the engine's own
 * sentence, and this card renders **three** states rather than two. A card written a month ago
 * would have shipped "navigable ✓" to somebody whose set had never been checked.
 *
 * ## What the card does that a bare list would not
 *
 * **It keeps the engine's split by reason, in words.** `sheet_not_in_set` and
 * `detail_not_on_sheet` are one count to a reader and two different afternoons: the first is a typo
 * or a sheet nobody issued, the second is a renumber that was not propagated — and for that one the
 * engine hands over `available`, the detail numbers that ARE on the target sheet, which is the
 * shortest route to the right number. Collapsing them into "N dangling references" throws away the
 * only field that says what to do next.
 *
 * **`reference_count` is not `edges.length`.** The engine counts resolved + dangling; `edges` is the
 * resolved half. Printing the array's length beside the word "references" is TRUNC-COUNTED at field
 * level, so the ratio is rendered from the engine's own two numbers.
 */
export interface DetailRefsDeps {
  api: ApiClient;
  pid: string;
}

/**
 * The verdict, in three states, with its coverage on every one of them.
 *
 * `assessed` is the declared coverage of `navigable` (`# COVERAGE: assessed` at the engine), and
 * `services/api/test_verdict_coverage.py` reports a consumer that renders the verdict without it.
 * Rendering it is not box-ticking here: the unassessed state is the one a reader most needs told,
 * because the correct response to an unchecked set is to record the callouts, not to go hunting for
 * defects whose absence the missing references guarantee.
 */
export function verdictNote(g: DetailRefGraph): { html: string; kind: "ok" | "warn" | "bad" | "" } {
  if (!g.assessed) {
    return { html: `<b>UNCHECKED — not clean</b><br>${escapeHtml(g.unassessed_reason
      || "nothing in this set records a detail or a callout, so there is nothing to cross-reference")}`,
             kind: "warn" };
  }
  const scale = `${g.sheet_count} sheet(s), ${g.detail_count} detail(s), `
    + `${g.resolved} of ${g.reference_count} callout(s) resolve`;
  if (g.navigable) {
    return { html: `<b>Navigable</b> — every callout resolves and every detail is pointed at. ${scale}.`,
             kind: "ok" };
  }
  const bits: string[] = [];
  if (g.dangling.length) bits.push(`${g.dangling.length} dangling callout(s)`);
  if (g.orphans.length) bits.push(`${g.orphans.length} orphan detail(s)`);
  if (g.unparseable.length) bits.push(`${g.unparseable.length} unreadable callout(s)`);
  return { html: `<b>NOT navigable</b> — ${bits.join(", ")}. ${scale}.`, kind: "bad" };
}

/** The two dangling reasons, in the words that say what to do about them. */
export const DANGLING_REASON: Record<string, string> = {
  sheet_not_in_set: "the sheet is not in the set — a typo in the callout, or a sheet nobody issued",
  detail_not_on_sheet: "the sheet is there and carries no such detail — almost always a renumber "
    + "that was not propagated",
};

/** One row per dangling callout: where it is written, what it points at, and why that fails. */
export function danglingRows(dangling: readonly DetailRefEdge[]): { k: string; v: string }[] {
  return dangling.map((e) => ({
    k: `${e.from_sheet} → ${e.label}`,
    v: (DANGLING_REASON[e.reason ?? ""] ?? `unrecognised reason ${e.reason ?? "(none)"}`)
      + (e.available?.length ? ` · on ${e.to_sheet}: ${e.available.join(", ")}` : ""),
  }));
}

/** One row per orphan detail. The title and scale are what identifies it on the sheet. */
export function orphanRows(g: DetailRefGraph): { k: string; v: string }[] {
  return g.orphans.map((o) => ({
    k: `${o.detail}/${o.sheet}`,
    v: [o.title || "(untitled)", o.scale || "(no scale)"].join(" · ") + " — nothing points at it",
  }));
}

/** One row per callout that could not be parsed. The raw text IS the finding. */
export function unparseableRows(g: DetailRefGraph): { k: string; v: string }[] {
  return g.unparseable.map((u) => ({ k: u.from_sheet, v: `could not be read as a reference: ${u.text}` }));
}

/** The card, rendered into a host the caller owns. */
export function renderDetailRefs(host: HTMLElement, g: DetailRefGraph): void {
  host.innerHTML = "";
  const note = verdictNote(g);
  host.appendChild(resultNote(note.html, note.kind));
  // NO early return on `!g.assessed`, and the deleted one is worth a note. It read
  // `if (!g.assessed) return;  // nothing below would have a row` — which is the reason it was
  // REDUNDANT, written as if it were the reason it was needed: the engine defines
  // `assessed = bool(targets or edges or dangling or unparseable)`, so an unassessed graph has no
  // findings by construction and each `if (length)` below already renders nothing. A mutation
  // deleting the guard passed every test in this file, because no fixture could put findings on an
  // unassessed graph without contradicting the engine. *A branch no input can reach is a branch
  // nobody has run*, so it is gone and the invariant it assumed is asserted where it lives, in
  // `services/api/test_detail_refs.py`.
  if (g.dangling.length) {
    host.appendChild(resultNote("<b>Dangling callouts</b> — a reader follows these and finds nothing.", "bad"));
    host.appendChild(kvTable(danglingRows(g.dangling)));
  }
  if (g.orphans.length) {
    host.appendChild(resultNote("<b>Orphan details</b> — drawn, and nothing points at them.", "warn"));
    host.appendChild(kvTable(orphanRows(g)));
  }
  if (g.unparseable.length) {
    host.appendChild(resultNote("<b>Unreadable callouts</b> — the text is not a reference this "
      + "parser recognises, so it was neither resolved nor counted as dangling.", "warn"));
    host.appendChild(kvTable(unparseableRows(g)));
  }
}

/** Fetch and render into a host the caller owns. */
export async function openDetailRefs(host: HTMLElement, d: DetailRefsDeps): Promise<void> {
  const g = await d.api.detailReferences(d.pid);
  renderDetailRefs(host, g);
}

/**
 * The whole click, overlay included — and the overlay lives HERE for a measured reason.
 *
 * The first version kept `withLoading` + `showResult` in `drawingsSection.ts`, which is the eager
 * app-shell chunk, and took the shell to **225.1 KB against a 225 KB cap**: the closure, the two
 * title strings and the overlay call were ~200 bytes more than the shell had left. Caught by
 * `npm run budget` BEFORE the commit this time, which is the one thing the previous budget failure
 * was about. So the eager half is now a label, an `await import()` and one call, and everything that
 * can be deferred is. `withLoading` and `showResult` are already in the shell for this section's
 * other buttons, so naming them here costs nothing new.
 *
 * The fetch is inside `withLoading` and the overlay opens only after it resolves: a 404 or a 500 is
 * a toast, not an empty card — the shape `recipeLogTool.ts` settled on for the same reason.
 */
export async function openDetailRefsCard(d: DetailRefsDeps & {
  container: HTMLElement;
  notify: (msg: string, kind?: "info" | "success" | "error") => void;
}): Promise<void> {
  await withLoading(d.container, "Reading the cross-reference graph", async () => {
    let g: DetailRefGraph;
    try { g = await d.api.detailReferences(d.pid); }
    catch (e) { d.notify(`cross-references unavailable: ${(e as Error).message}`, "error"); return; }
    showResult("Detail references", (body) => { renderDetailRefs(body, g); });
  });
}
