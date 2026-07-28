import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * The API client's public surface, pinned.
 *
 * `client.ts` is the file this codebase is least able to keep working on: measured 2026-07-28 at
 * 4,956 lines and 152 commits in a fortnight, it must be opened to add any endpoint, so every change
 * to it competes with every other change. Roadmap SCALE-SEAM splits it along the same domain seams
 * `routers/*.py` already uses server-side — the client simply never followed.
 *
 * A split like that is only safe if "I moved code" can be told apart from "I changed behaviour", and
 * a typecheck cannot tell you that: deleting a method and deleting its last caller both compile.
 * So this test captures the surface **before** any extraction and asserts it afterwards. Method
 * moves between modules freely; a method that *disappears* fails here, loudly, naming itself.
 *
 * Deliberately a count plus a spot-check of load-bearing names, not a 631-entry literal. A frozen
 * list of every method would have to be edited by hand on every legitimate new endpoint, and a
 * fixture that is edited on every commit stops being read — it would go stale exactly the way the
 * prose in CLAUDE.md did.
 */

/** Every callable on the instance and its prototype chain, excluding Object's own. */
function surfaceOf(obj: object): Set<string> {
  const names = new Set<string>();
  for (let o = obj; o && o !== Object.prototype; o = Object.getPrototypeOf(o)) {
    for (const k of Object.getOwnPropertyNames(o)) {
      if (k === "constructor" || k.startsWith("_")) continue;
      const d = Object.getOwnPropertyDescriptor(o, k);
      if (d && typeof d.value === "function") names.add(k);
    }
  }
  return names;
}

const api = new ApiClient("http://localhost:0");
const surface = surfaceOf(api);

describe("the API client's public surface", () => {
  it("has one — a client that exposes nothing means the constructor threw", () => {
    // Without this, every assertion below would pass vacuously against an empty set. That is the
    // exact can't-fail shape this repo has been bitten by repeatedly: a green test measuring nothing.
    expect(surface.size).toBeGreaterThan(400);
  });

  it("still carries the whole endpoint surface after the split", () => {
    // A floor, not an equality: new endpoints are normal and must not fail this. What must fail is
    // an extraction that drops methods on the floor — a mixin that is written but never composed
    // into the chain lands here as a sharp drop, with the count naming the damage.
    //
    // Set just under the real number (689 after the authoring extraction), NOT comfortably under.
    // The first draft said 620, which would have sat green through losing every one of the 15
    // methods that extraction moved — a threshold far below the truth is a test that cannot fail.
    // Raise this as the surface legitimately grows; that is what keeps it load-bearing.
    expect(surface.size, `only ${surface.size} methods reachable`).toBeGreaterThanOrEqual(685);
  });

  it("keeps the transport primitives the domain methods are built on", () => {
    // These live in HttpCore. If the mixin chain is composed wrong, the domain methods survive but
    // lose their base — and that failure would otherwise only surface at runtime, on a real request.
    for (const k of ["setToken", "url", "json", "health"]) {
      expect(surface.has(k), `HttpCore.${k} unreachable — the chain is composed wrong`).toBe(true);
    }
  });

  it("keeps the methods the rest of the app actually calls", () => {
    // Sampled across the domains the extraction touches, one per seam, chosen because each has real
    // call sites in the shell, the viewer or the portal. A regression here is a broken screen.
    for (const k of [
      "modules", "moduleRecords", "createModuleRecord", "updateModuleRecord",  // CRUD — used everywhere
      "topicsBoard", "createTopic", "viewpoints",                   // BCF coordination
      "elementEffectiveProps", "elementCosts", "costSummary",       // model + 5D
      "schedule4d", "scheduleCpm", "evm",                           // 4D + earned value
      "estimateFromModel", "qtoByFloor", "sovFromBudget",           // estimating
      "drawingMarkup", "promoteDrawingMarkup",                      // 2D markup -> RFI
      "editIfc", "publish", "createBlankModel", "placeFamily",      // authoring
      "notificationStream", "markupStream", "pullPlanStream",       // SSE subscriptions
    ]) {
      expect(surface.has(k), `${k}() vanished — a call site is now broken`).toBe(true);
    }
  });

  it("still carries the shared SSE helper the stream methods are built on", () => {
    // `liveStream` is declared `private` and the three stream methods above all call it. Reflection
    // sees it anyway — TS visibility is erased at compile time, so this set is the RUNTIME surface,
    // not the declared one. Worth being explicit about, because it is the limit of this technique:
    // it proves a method still exists, never that it is still callable from outside.
    //
    // The declared visibility is a real constraint on SCALE-SEAM regardless: a mixin cannot reach a
    // sibling mixin's `private` member, so `notificationStream`/`markupStream`/`pullPlanStream`
    // cannot move until `liveStream` moves down into HttpCore or becomes `protected` the way
    // `authToken` already is. That is an ordering fact worth having before the first extraction
    // rather than halfway through one.
    expect(surface.has("liveStream")).toBe(true);
  });

  it("does not leak transport internals as public API", () => {
    // `authToken` is protected precisely so cache keys can be identity-scoped without the token
    // becoming part of the surface. If a refactor promotes it, that is a real regression.
    expect(surface.has("authToken")).toBe(false);
  });
});
