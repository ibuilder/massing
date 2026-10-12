import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { ElementsFreshness } from "./indexCoverage";
import { indexReading, worthShowing } from "./indexCoverage";

/**
 * ELEMENTS-SILENT — the project browser was stale and truncated at once and reported neither.
 *
 * Two defects on one screen. `/projects/{pid}/elements/freshness` existed, said in its docstring
 * exactly what it was for, and had **no client method**; `/elements` returns a bare array that
 * breaks at `limit` with **no total anywhere**, so the panel could not have computed truncation
 * even if it had wanted to.
 *
 * What is asserted here, beyond the four states:
 *
 * - **Staleness is answered before truncation.** They are different questions and the stale one is
 *   worse, so a stale index must not be reported as a paging problem the user can filter away.
 * - **`stale: null` is not `false`.** The route is explicit that unknown and current are different
 *   claims; a consumer that folded them would report a snapshot of unknown age as current, which is
 *   the original defect wearing the fix's label.
 * - **The two reasons for `null` give different advice** — no reachable model versus an index that
 *   predates fingerprint stamping. One is fixed by finding the file, the other by republishing.
 * - **`indexed_elements` is the denominator for an UNFILTERED page only.** A filtered call showing
 *   fewer rows than the index holds is *correct*, and calling that truncation would put a warning on
 *   every filtered view — which is how a warning stops being read.
 */

const mk = (o: Partial<ElementsFreshness> = {}): ElementsFreshness => ({
  indexed_elements: o.indexed_elements ?? 1200,
  stale: o.stale === undefined ? false : o.stale,
  built_from_source: o.built_from_source ?? true,
  model_reachable: o.model_reachable ?? true,
  hint: o.hint ?? null,
});

describe("indexReading — stale is a different claim from truncated", () => {
  it("reports a stale index as stale, not as a capped page", () => {
    const r = indexReading(mk({ stale: true, indexed_elements: 900,
                                hint: "republish to rebuild the index from the current model" }),
                           900);
    expect(r.kind).toBe("stale");
    expect(r.tone).toBe("bad");
    expect(r.detail).toContain("900");
    expect(r.detail).toContain("republish");
  });

  it("answers STALENESS FIRST — a stale index that is also capped is still reported stale", () => {
    // The ordering is the assertion. 5,000 of 12,000 rows from an index that no longer matches the
    // model is both things at once, and "filter to see the rest" is advice about the wrong problem:
    // the rest is not there either. Reversing the two branches makes this read "truncated".
    const r = indexReading(mk({ stale: true, indexed_elements: 12000 }), 5000);
    expect(r.kind).toBe("stale");
    expect(r.headline).not.toContain("5000");
  });

  it("carries the engine's own hint when it has one, rather than restating it", () => {
    expect(indexReading(mk({ stale: true, hint: "source model replaced on 2026-10-02" }), 10).detail)
      .toContain("source model replaced on 2026-10-02");
  });

  it("still gives advice when the route sends no hint", () => {
    const r = indexReading(mk({ stale: true, hint: null }), 10);
    expect(r.kind).toBe("stale");
    expect(r.detail).toContain("republish");
  });
});

describe("indexReading — unknown is not current", () => {
  it("never reports an unknown-age index as complete", () => {
    const r = indexReading(mk({ stale: null, indexed_elements: 400 }), 400);
    expect(r.kind).toBe("unknown");
    expect(r.kind).not.toBe("complete");
    expect(r.tone).toBe("warn");
  });

  it("refuses to call an unknown index current even when the counts agree exactly", () => {
    // This is the trap: shown === indexed is exactly the shape of a complete answer, and it means
    // nothing here, because nobody checked the index against the model at all.
    const r = indexReading(mk({ stale: null, indexed_elements: 1200 }), 1200);
    expect(r.kind).toBe("unknown");
    expect(r.detail).toContain("not a claim that they are current");
  });

  it("names NO REACHABLE MODEL as the reason when that is the reason", () => {
    const r = indexReading(mk({ stale: null, model_reachable: false, built_from_source: true }), 7);
    expect(r.headline).toContain("no source model can be read");
    expect(r.headline).not.toContain("fingerprint");
  });

  it("names an UNSTAMPED INDEX as the reason when that is the reason — different advice", () => {
    const r = indexReading(mk({ stale: null, model_reachable: true, built_from_source: false }), 7);
    expect(r.headline).toContain("predates");
    expect(r.headline).not.toContain("no source model can be read");
  });

  it("prefers the unreachable-model reason when BOTH hold — nothing can be compared at all", () => {
    const r = indexReading(mk({ stale: null, model_reachable: false, built_from_source: false }), 7);
    expect(r.headline).toContain("no source model can be read");
  });
});

describe("indexReading — the denominator belongs to an unfiltered page", () => {
  it("reports a capped unfiltered page with BOTH numbers", () => {
    const r = indexReading(mk({ indexed_elements: 12000 }), 5000);
    expect(r.kind).toBe("truncated");
    expect(r.headline).toContain("5000");
    expect(r.headline).toContain("12000");
  });

  it("says the derived things are about the SUBSET, spatial selection included", () => {
    expect(indexReading(mk({ indexed_elements: 12000 }), 5000).detail)
      .toContain("spatial selection");
  });

  it("does NOT call a filtered page truncated — the two numbers are not comparable", () => {
    // Same counts as the case above, one flag apart. A filtered view showing 40 of 12,000 is a
    // correct answer to a narrower question, and warning about it would put a banner on every
    // filtered view in the app.
    const r = indexReading(mk({ indexed_elements: 12000 }), 40, true);
    expect(r.kind).toBe("complete");
    expect(r.detail).toContain("not expected to match");
  });

  it("reports a whole unfiltered page as complete, against a current index", () => {
    const r = indexReading(mk({ indexed_elements: 1200 }), 1200);
    expect(r.kind).toBe("complete");
    expect(r.tone).toBe("ok");
  });

  it("does not report truncation when the page is somehow LARGER than the index", () => {
    // Defensive, and the inequality direction is the assertion: `>` would make an index that is
    // merely behind by a few elements read as a capped page and tell the user to filter.
    expect(indexReading(mk({ indexed_elements: 10 }), 12).kind).toBe("complete");
  });
});

describe("worthShowing — the ordinary case stays silent", () => {
  it("shows the three states that mean something", () => {
    expect(worthShowing(indexReading(mk({ stale: true }), 1200))).toBe(true);
    expect(worthShowing(indexReading(mk({ stale: null }), 1200))).toBe(true);
    expect(worthShowing(indexReading(mk({ indexed_elements: 99 }), 5))).toBe(true);
  });

  it("stays quiet on a complete unfiltered page, and on a filtered one", () => {
    expect(worthShowing(indexReading(mk({ indexed_elements: 99 }), 99))).toBe(false);
    expect(worthShowing(indexReading(mk({ indexed_elements: 99 }), 5, true))).toBe(false);
  });
});

/** The source pins. A pure reading nobody calls is the defect this item is about. */
const here = dirname(fileURLToPath(import.meta.url));
const panel = readFileSync(resolve(here, "projectPanel.ts"), "utf8");
const client = readFileSync(resolve(here, "../../api/elements.ts"), "utf8");

describe("the project browser actually asks, and actually renders", () => {
  it("declares a client method for the freshness route", () => {
    expect(client).toMatch(/elementsFreshness\(pid: string\)/);
    expect(client).toContain("/elements/freshness");
  });

  it("calls it from the panel and renders the reading", () => {
    expect(panel).toMatch(/api\.elementsFreshness\(projectId\)/);
    expect(panel).toMatch(/renderIndexNote\(fresh, elements\.length\)/);
    expect(panel).toMatch(/treePanel\.appendChild\(note\)/);
  });

  it("passes NO filtered flag, because that call site is the unfiltered one", () => {
    // `renderIndexNote(fresh, n, true)` here would suppress the truncation note on the one call
    // that can legitimately raise it — the panel's own `limit: 5000`.
    expect(panel).not.toMatch(/renderIndexNote\([^)]*,\s*true\)/);
    expect(panel).toContain("limit: 5000");
  });

  it("reaches the module through a DYNAMIC import — the shell is at its budget", () => {
    // `viewer/tools/*` is the eager `app-*` chunk. A static import of this module put the shell at
    // 224.5 KB against a 224 KB budget and `npm run budget` refused the build. The note's DOM is
    // built inside the lazy module for the same reason: the previous item on this branch was
    // refused a second time with the reading deferred and the card-building still eager.
    expect(panel).toMatch(/await import\("\.\/indexCoverage"\)/);
    expect(panel, "a static import of the reading module puts it back in the shell")
      .not.toMatch(/^import .*from "\.\/indexCoverage"/m);
  });

  it("renders the note with textContent, not innerHTML — `hint` is server text", () => {
    const mod = readFileSync(resolve(here, "indexCoverage.ts"), "utf8");
    const block = mod.slice(mod.indexOf("export function renderIndexNote"));
    expect(block).toContain("textContent");
    expect(block).not.toContain("innerHTML");
  });

  it("puts the note ABOVE the empty state, which can only say the other sentence", () => {
    // "This model published with no elements" and "this index predates the model" are different
    // claims, and an index of 0 built from an older model is both. Ordering is the assertion.
    // The needle is the string LITERAL, quotes included: the prose a few lines above the note
    // mentions the same words, and the first draft of this pin matched that comment instead and
    // reported the block in the wrong place. A pin keyed on words matches every mention of them.
    const emptyState = panel.indexOf('"This model published with no elements."');
    expect(emptyState).toBeGreaterThan(0);
    expect(panel.indexOf("renderIndexNote(fresh, elements.length)")).toBeGreaterThan(0);
    expect(panel.indexOf("renderIndexNote(fresh, elements.length)")).toBeLessThan(emptyState);
  });

  it("does not let a missing freshness answer remove the tree", () => {
    // Two properties, and the behavioural half is in `projectPanel.test.ts`. The `.catch` absorbs a
    // rejection; the `Promise.resolve().then(...)` wrapper absorbs a SYNCHRONOUS throw, which a
    // bare `api.elementsFreshness(projectId).catch(...)` does not. The shipped first draft had the
    // catch and not the wrapper, and a client missing the method rendered "no model in this
    // project" over a model that was there.
    expect(panel).toMatch(/Promise\.resolve\(\)\s*\n?\s*\.then\(\(\) => api\.elementsFreshness\(projectId\)\)/);
    expect(panel).toMatch(/\.catch\(\(\) => null\)/);
  });

  it("starts that fetch OUTSIDE the try that decides noModel", () => {
    // The ordering is the assertion: `freshP` declared before the `try`, so nothing it throws can
    // reach the catch that means "this project has no model". **Both needles are floored first**:
    // `indexOf` returns -1 for an absent one, and -1 is less than everything — so moving the fetch
    // back inside the `try` under a different name would have passed this check by deleting its
    // subject. A pin that is satisfied by the absence of what it looks for is not a pin.
    const at = panel.indexOf("const freshP = Promise.resolve()");
    const fetchAt = panel.indexOf("elements = await api.elements(projectId");
    expect(at).toBeGreaterThan(0);
    expect(fetchAt).toBeGreaterThan(0);
    expect(at).toBeLessThan(fetchAt);
    expect(panel).toMatch(/\} catch \{\s*\n\s*noModel = true;/);
  });
});
