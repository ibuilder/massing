import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = readFileSync(resolve(process.cwd(), "src/viewer/tools/authoringSection.ts"), "utf8");

/**
 * Does the Place button report publish progress, or sit on "converting…" for the whole convert?
 *
 * ### This gate could not fail for its own reason, and did not for its whole life
 *
 * It sliced the file from `indexOf("⊕ Place selected family")` — which finds the **docstring that
 * mentions the button** (offset 2076) hundreds of lines before the `toolBtn2(...)` that builds it
 * (offset 6312). The slice therefore opened above **Republish** and ran to the next button after
 * Place, so Republish's `onTick` satisfied an assertion whose name, comment and purpose were all
 * about Place. Removing Place's callback entirely left it green; so did removing Republish's.
 *
 * **An anchor that matches a MENTION of the subject instead of the subject is not a narrower
 * search, it is a different one** — and the failure is silent in the safe-looking direction,
 * because a passing test is what you get either way.
 *
 * Two changes, and the second is the one that matters: the slice is anchored on the button's
 * CONSTRUCTION (`toolBtn2("⊕ …`), which cannot collide with prose about it; and the slice is
 * asserted to exclude Republish, so a future edit that widens it back fails here rather than
 * quietly restoring the hole. The arity of the callback is deliberately NOT pinned — the previous
 * version pinned `(s)` and went red when `onTick` gained its elapsed-time argument and this very
 * call site opted in, reporting an improvement to the protected behaviour as a regression of it.
 */
function sliceForButton(label: string): string {
  const start = SRC.indexOf(`toolBtn2("${label}"`);
  expect(start, `no toolBtn2("${label}") in authoringSection.ts`).toBeGreaterThan(-1);
  const next = SRC.indexOf("toolBtn2(", start + 1);
  return next === -1 ? SRC.slice(start) : SRC.slice(start, next);
}

describe("Place reports the publish pipeline", () => {
  it("slices the Place button itself, not the docstring that names it", () => {
    // The defect above, asserted directly: the anchor must land on the construction, and the slice
    // must not reach back over Republish, whose callback used to be what made this pass.
    const place = sliceForButton("⊕ Place selected family");
    expect(place).toContain("⊕ Place selected family");
    expect(place).not.toContain("⟳ Republish");
    expect(place.length).toBeLessThan(SRC.length / 2);   // a slice, not "most of the file"
  });

  it("passes onTick into waitForPublish, the same path Republish already had", () => {
    // Without a callback the Place button sits on "converting…" for the whole convert.
    expect(sliceForButton("⊕ Place selected family")).toMatch(/waitForPublish\(pid,\s*\(/);
  });

  it("Republish keeps its own onTick — the call this gate used to be reading by mistake", () => {
    expect(sliceForButton("⟳ Republish (reconvert + reindex)")).toMatch(/waitForPublish\(pid,\s*\(/);
  });
});
