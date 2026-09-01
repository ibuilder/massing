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
    //
    // 2026-07-29 (SCALE-SEAM ③): raised 685 -> 696, the exact live count, because 685 had drifted
    // into 13 methods of slack and that slack was demonstrated, not theorised. During the /model
    // extraction I deleted `modelStream` outright and this file still reported **6 passed** — 695
    // clears a 685 floor, and `modelStream` is not one of the 28 spot-checked names. Only `tsc`
    // caught it, via its two real call sites. So the honest reading of this gate was: it catches a
    // catastrophic drop, or a named method, and nothing else.
    //
    // At the exact count it is a RATCHET, the same shape as `test_global_authz`'s BASELINE: losing
    // any single method now fails here by number, and a legitimate new endpoint fails too until
    // someone raises this line — one deliberate edit, and it only ever moves up.
    // (Set from what THIS reader counts, not from a probe I wrote: my own counter once said 698 while
    // the gate counted 696, and a threshold taken from a different reader is a threshold for a
    // different question.) That trade is
    // right for a file whose whole purpose is to prove nothing was dropped. **A gate whose threshold
    // sits below the truth is measuring the threshold, not the code.**
    //
    // 2026-07-30 (SCALE-SEAM ⑥): raised 696 -> 698, and the slack was DEMONSTRATED, not feared. During
    // the /procurement extraction I deleted `procurementGate` outright and this file reported **6
    // passed** — the surface had grown to 698 across #108-#111, so losing one method still cleared a
    // 696 floor. Unwiring the whole mixin (-9) failed correctly at 689; losing one did not. That is
    // the same drift that took it from 685 to 696 a day earlier, and it will happen again: **every
    // merge that adds an endpoint silently converts this ratchet back into a slack floor.** The
    // number must be re-read from this reader after any batch of merges, not only when extracting.
    //
    // 2026-08-06 (SCALE-SEAM ⑦): raised 698 -> 699, and the re-read is the point rather than the
    // extraction. The /auth move is surface-neutral by construction — this reader counted **699 both
    // before and after it**, which is the evidence that 20 methods changed file and none was lost.
    // The single method of slack was therefore NOT created by this change; it had accumulated from
    // merges since ⑥, exactly as the paragraph above predicted it would. That is worth stating
    // plainly: **an extraction is the occasion to re-read this number, never the cause of it moving.**
    // Anyone raising this line because their own change grew the surface should say so here; anyone
    // raising it to make a red test go green has inverted the gate.
    // 2026-08-06 (design/options extraction): raised 702 -> 703. The move of designOptionsGenerate
    // and designOptionsScore into designOptions.ts is invisible to this reader, which is the point;
    // the +1 is designOptionsRecord, a client caller for an endpoint that had none. The whole
    // stored-option family was server-only: /design/options/{compare,carbon,economics} have no
    // caller either and no panel touched the design_option register at all.
    // 2026-08-06 (SCALE-SEAM ⑧): raised 699 -> 702, and the +3 is NEW SURFACE, not a moved one.
    // The /proforma extraction moved 15 methods and this reader counted **699 both before and after
    // the move** — that is the evidence nothing was dropped. The three added methods
    // (proformaRenovation / proformaRollover / proformaIncomeBasis) are client callers for endpoints
    // that had none, which is why the floor legitimately rises.
    // 2026-08-07 (SCALE-SEAM ⑨): raised 703 -> 705, and the +1 over the measured baseline is NEW
    // SURFACE. Measured with THIS reader on both sides rather than reasoned about: at 85b73677,
    // pre-extraction, it counts **704**; with the six contract methods moved into contracts.ts and
    // `scopeExhibit` added, **705**. The move is invisible to it, which is the evidence nothing was
    // dropped; the +1 is `scopeExhibit`, a client caller for `/scope-library/exhibit`, an endpoint
    // that shipped with none at all.
    //
    // The floor was briefly written as 704 here, from a counter I wrote myself that said 706 — two
    // different numbers from two different instruments, neither of them this one. Take the number
    // from the reader that enforces it: raising the floor to force a high estimate green, or leaving
    // it slack under a hand-rolled one, both defeat the gate in the same direction.
    expect(surface.size, `only ${surface.size} methods reachable`).toBeGreaterThanOrEqual(751);
  });

  it("keeps the transport primitives the domain methods are built on", () => {
    // These live in HttpCore. If the mixin chain is composed wrong, the domain methods survive but
    // lose their base — and that failure would otherwise only surface at runtime, on a real request.
    for (const k of ["setToken", "url", "json", "health"]) {
      expect(surface.has(k), `HttpCore.${k} unreachable — the chain is composed wrong`).toBe(true);
    }
  });

  it("keeps the methods the rest of the app actually calls", () => {
    // Sampled across the domains the extraction touches, one per seam. A regression here is a
    // broken screen — for the ones that HAVE a screen.
    //
    // CORRECTED 2026-08-07. This said "chosen because each has real call sites in the shell, the
    // viewer or the portal", and that was false for the three ⑧ entries below: `proformaRenovation`,
    // `proformaRollover` and `proformaIncomeBasis` have no caller anywhere except this list. They
    // were added to give server endpoints a client caller, which made the ENDPOINT reachable and
    // left the SCREEN as absent as before — so the sentence claimed a property nothing checked, in
    // a file whose whole job is to check properties.
    //
    // The claim now has an owner: `clientCallers.test.ts` distinguishes "the method exists" from
    // "something outside src/api calls it", and holds the count of the second kind under a ratchet.
    // This list stays as it is — losing any of these names should still fail — but it no longer
    // asserts anything about reachability.
    for (const k of [
      "modules", "moduleRecords", "createModuleRecord", "updateModuleRecord",  // CRUD — used everywhere
      "topicsBoard", "createTopic", "viewpoints", "topicComments",  // BCF coordination
      "mepSummary", "mepConnectivity", "sprinklerCoverage", "mepModelExtract",
      "aiAsk", "riskSummary", "draftRfi",
      "estimateContinuity", "preconAlignment", "veLog",
      "elementEffectiveProps", "element", "elementLifecycle", "colorFacets", "elementCosts", "costSummary",       // model + 5D
      "modelHealth", "modelQa", "projectModels",
      "documentsTree", "uploadDocument", "documentDownloadUrl",
      "projectPulse",
      "solveProforma", "proformaLive", "portfolioCompare",           // ⑧ moved — spread over 4 regions
      // ⑧ new — added unreachable; `proformaRenovation` now has a screen (PULSE-FINDINGS, 2026-08-07)
      // and the other two still do not. Corrected here rather than left as "were unreachable", which
      // had already stopped being true for one of the three.
      "proformaRenovation", "proformaRollover", "proformaIncomeBasis",
      "appraisal", "listingAutofill", "shareListing", "syndicateListing",
      "schedule4d", "sequenceClash", "scheduleCpm", "evm",           // 4D + sequence clash + earned value
      "pullPlanBoard", "pullPlanMetrics", "leanPpc", "pullPlanStream",
      "clashMetrics", "clashClearanceRules", "clashMatrix",
      "chartOfAccounts", "namingConventions", "elementsByDiscipline", "pipelineFunnel",
      "twoSidedBudget", "mepPressureLoss", "mepTrayFill", "mepThermalLoads",
      "lienWaiver", "rfqStatus", "entitlementConditionChecks",
      "goldenThread", "k1Pack", "capTable", "waterfallScenario", "capitalCall", "ffeBom", "specLinks", "authoringMatrix",
      "equipmentBudgetLines", "lodCensus", "exportQa", "qualityTurnoverReadiness",
      "costDatasets", "costVintage", "unitRates", "costSummary", "gmpBudget", "payAppPdf", "elementCosts5d", "gaebX83Url",
      "codeAmendments", "agentPacks", "modelHistory", "fileModel", "spacePack",
      "compiledPdfUrl", "projectPackagePdfUrl",
      "bep", "cdeStatus", "infoRequirementsRegister", "cdeExchangeAcceptance",
      "drawingSchedulesCsvUrl", "permitsGeojsonUrl", "moduleLogPdfUrl", "viewTemplateGraphics",
      "estimateFromModel", "qtoByFloor", "sovFromBudget",           // estimating
      "drawingMarkup", "promoteDrawingMarkup",                      // 2D markup -> RFI
      "editIfc", "publish", "createBlankModel", "placeFamily",      // authoring
      "notificationStream", "markupStream", "pullPlanStream",       // SSE subscriptions
      // auth (SCALE-SEAM ⑦). Named here because the count alone was a weak guard for this group:
      // losing all 20 would have dropped the surface to 679 and failed loudly, but losing ONE — say
      // `login` — would have left 698 and cleared the floor that stood when they moved. Every one of
      // these has a real call site in `account/accountUI.ts`, and `stepUp` gates PDF sealing, so a
      // silent loss here locks people out rather than breaking a screen.
      "login", "logout", "me", "register", "changePassword",        // session lifecycle
      "mfaVerify", "mfaStatus", "mfaEnable",                        // MFA enrolment + challenge
      "stepUp",                                                     // per-action re-auth for seals
      "listUsers", "createUser", "updateUser", "resetWithToken",    // admin user management
      // ⑫ moved — one contiguous /connections run; a silent loss here is the admin connections screen
      "connections", "createConnection", "testConnection", "connectionTables",
      "syncProcore", "pushProcore", "syncSchedules",
      "drawingSet", "issueDrawingSet", "drawingIssuances", "drawingTransmittalUrl",
      "drawingMarkup", "promoteDrawingMarkup", "markupStream", "drawingSchedules",
    ]) {
      expect(surface.has(k), `${k}() vanished — a call site is now broken`).toBe(true);
    }
  });

  it("still carries the shared SSE helper the stream methods are built on", () => {
    // Reflection sees it regardless of visibility — TS access modifiers are erased at compile time,
    // so this set is the RUNTIME surface, not the declared one. Worth being explicit about, because
    // it is the limit of this technique: it proves a method still exists, never that it is still
    // callable from outside.
    //
    // **The ordering constraint this comment used to describe is now DISCHARGED.** It said the SSE
    // methods could not move until `liveStream` came down into HttpCore or became `protected`, since
    // a mixin is a BASE of ApiClient and cannot see ApiClient's `private` members. SCALE-SEAM ③ did
    // exactly that: `liveStream` is now `protected` on HttpCore, which is what let `modelStream`
    // travel with the `/model` group. `notificationStream` / `markupStream` / `pullPlanStream` are
    // unblocked for ④ — the prediction was right and the fix was the one it named.
    expect(surface.has("liveStream")).toBe(true);
  });

  it("does not leak transport internals as public API", () => {
    // `authToken` is protected precisely so cache keys can be identity-scoped without the token
    // becoming part of the surface. If a refactor promotes it, that is a real regression.
    expect(surface.has("authToken")).toBe(false);
  });
});
