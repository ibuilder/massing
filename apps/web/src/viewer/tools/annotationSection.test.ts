import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { buildAnnotationSection, type AnnotationDeps } from "./annotationSection";

/**
 * R39-DECOMP-VIEWER ⑭ — the guide tracker installs ONCE, across panel rebuilds.
 *
 * WHAT THIS GUARDS. `annotGuide` and `guideWired` were `let`s in `app.ts`, declared immediately
 * before `buildToolsPanel` — outside it, deliberately, because `buildToolsPanel()` re-runs on every
 * `aec:persona` event. The obvious extraction scopes them inside the builder, and two things break
 * that nothing else in this repo would have caught:
 *
 *   1. the `pointermove` tracker installs again on every rebuild, each copy running
 *      `screenToGround` on every mouse move for the life of the session;
 *   2. the tracker installed by the FIRST build closes over the FIRST `annotGuide`, so after a
 *      rebuild the rubber band silently stops following the cursor.
 *
 * NEITHER IS VISIBLE TO tsc, AND 619 VIEWER TESTS PASSED WITH BOTH IN PLACE. What found it was
 * `no-useless-assignment` flagging `guideWired = true` as dead — dead *within one call*, which is
 * precisely the symptom of state that was never meant to be per-call. A lint rule caught a leak; it
 * should not be the only thing that would catch it again, hence this file.
 *
 * The assertion is behavioural, not structural: build the section twice, drive the real path that
 * arms the guide, and count listeners. A gate that grepped for `let guideWired` at module scope
 * would pass on a module that had moved the flag and still wired twice.
 */
function harness() {
  const container = document.createElement("div");
  const add = vi.spyOn(container, "addEventListener");
  const handlers: Record<string, () => unknown> = {};

  const deps: AnnotationDeps = {
    toolBtn2: (label, onClick) => {
      handlers[label] = onClick;
      const b = document.createElement("button");
      b.textContent = label;
      return b;
    },
    api: {} as AnnotationDeps["api"],
    projectId: "p1",
    container,
    notify: () => {},
    viewer: { world: { scene: { three: new THREE.Scene() } } },
    screenToGround: () => new THREE.Vector3(1, 0, 1),
    reloadModelPins: async () => {},
    loadProjectModel: async () => true,
    waitForPublish: async () => "done",
    // The point that has been clicked in 3D — an accessor, as it is across the seam.
    lastPoint: () => new THREE.Vector3(2, 0, 3),
    selectedGuid: () => "0GUID000000000000000001",
  };
  return { deps, container, add, handlers };
}

/**
 * Arm the rubber band the way a user does: start a dimension, which sets the first point.
 *
 * Throws rather than optional-calling. Under `noUncheckedIndexedAccess` the lookup is
 * `(() => unknown) | undefined`, and `handlers[...]?.()` would compile — then silently arm nothing
 * if the label ever changed, leaving a test that passes because it did nothing at all.
 */
function armGuide(handlers: Record<string, () => unknown>) {
  const label = "📐 Dimension (2 points)";
  const h = handlers[label];
  if (!h) throw new Error(`no handler registered for ${label} — the button label changed`);
  return h();
}

describe("R39-DECOMP-VIEWER ⑭ — annotation guide wiring survives a panel rebuild", () => {
  it("installs the pointermove tracker exactly once across TWO builds on one container", async () => {
    const h = harness();

    buildAnnotationSection(h.deps);
    await armGuide(h.handlers);
    const afterFirst = h.add.mock.calls.filter(([t]) => t === "pointermove").length;

    // The persona switch: `buildToolsPanel()` runs again against the SAME container.
    buildAnnotationSection(h.deps);
    await armGuide(h.handlers);
    const afterSecond = h.add.mock.calls.filter(([t]) => t === "pointermove").length;

    expect(afterFirst, "the first build must arm the tracker at all — else this test is vacuous")
      .toBe(1);
    expect(afterSecond,
      "a rebuild re-armed the tracker: `guideWired` is per-call again, so every persona switch "
      + "stacks another pointermove listener on the container")
      .toBe(1);
  });

  it("returns the four annotation tools, in rail order", () => {
    const h = harness();
    const out = buildAnnotationSection(h.deps);
    expect(Object.keys(out)).toEqual(["annotBtn", "dimBtn", "cloudBtn", "tagBtn"]);
    expect(out.annotBtn.textContent).toContain("Add note");
    expect(out.dimBtn.textContent).toContain("Dimension");
    expect(out.cloudBtn.textContent).toContain("Revision cloud");
    expect(out.tagBtn.textContent).toContain("Tag selected");
  });
});
