import { readFileSync } from "node:fs";
import { readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { ApiClient } from "./client";

/**
 * Which API-client methods does the APPLICATION actually call?
 *
 * **The gap this closes.** `surface.test.ts` pins the client's method surface and asserts a floor on
 * its size. That answers "does the method exist", which is a different question from "can a user
 * reach it", and the two had already come apart. Its own comment introduces a list with *"the methods
 * the rest of the app actually calls … chosen because each has real call sites in the shell, the
 * viewer or the portal"* — and three of the names under that sentence (`proformaRenovation`,
 * `proformaRollover`, `proformaIncomeBasis`) have **no caller anywhere but that test**. They were
 * added to give server endpoints a client caller, which made the *endpoint* reachable and left the
 * *screen* exactly as absent as before. The prose claimed the stronger property; nothing checked it.
 *
 * That is the shape the backend already guards with a route-reachability ratchet, applied one layer
 * up: **a client method with no caller is a feature nobody can use**, and counting client methods
 * reports it as covered.
 *
 * **A ratchet, not a ban.** A client method may legitimately land before its screen — that is a
 * normal order of work, and this file's job is to stop the set growing silently, not to forbid the
 * first commit of a pair. The number below is a ceiling that only ever goes DOWN. Raising it is a
 * deliberate act that says "I am shipping another endpoint no user can reach yet", and it should be
 * argued for in the commit message.
 *
 * **The blind spot, and it was not hypothetical.** A first draft matched only static call text
 * (`.foo(`) and its docstring asserted "there is no computed dispatch in the app today". That was
 * wrong within one grep: `portal/portal.ts` fans out over
 * `["modelHealth", "costSummary", "scheduleVariance", …].map(call)`, dispatching by string name. The
 * draft therefore reported `costSummary` unreachable while the project home calls it on every load
 * — a confident false positive, produced by a checker whose comment asserted its own soundness.
 *
 * So a method counts as reached if the app either CALLS it (`.foo(`) or NAMES it as a string
 * literal. The second is deliberately loose: a bare `"foo"` might be a label rather than a
 * dispatch. That is the correct direction to fail for this particular gate — over-reporting
 * unreachability sends someone hunting a screen that already exists, while under-reporting merely
 * leaves the ceiling higher than it could be, and the ceiling is a ratchet that can be lowered
 * later.
 */

const SRC = resolve(process.cwd(), "src");

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

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) {
      if (e === "vendor" || e === "node_modules" || e === "demo") continue;
      walk(p, out);
    } else if (/\.(ts|tsx)$/.test(e)) {
      out.push(p);
    }
  }
  return out;
}

/**
 * Files that COUNT as an application caller.
 *
 * Excludes `src/api/**` itself — a client method calling another client method keeps the pair
 * alive in each other's eyes and tells a user nothing — and excludes every test, for the same
 * reason the three proforma methods slipped through: their only caller was a test asserting they
 * were callable.
 */
const appFiles = walk(SRC).filter((p) => {
  const rel = p.replace(/\\/g, "/");
  if (/\.(test|spec)\.tsx?$/.test(rel)) return false;
  return !rel.includes("/src/api/");
});

/**
 * Comments stripped before scanning — a source-grep gate must not read its own documentation.
 *
 * `budget.ts` gained a bid-tab card whose comment says the engine is *"not `procurementLevel`
 * (materials, compared on unit price)"*. The dispatch-by-name check below matches a name in
 * backticks, so that sentence registered as a call site and the ratchet reported `procurementLevel`
 * as newly wired. Nothing called it; a comment explaining what it is **not** was counted as
 * something calling it.
 *
 * That is the same shape this repo has hit before, and the fix is the scanner rather than the
 * wording: a comment that has to avoid naming its neighbour to keep a test green is a comment the
 * next person will rewrite back.
 *
 * **A scanner, not three regexes, and the first draft proves why.** The regex version opened a block
 * comment on the `/*` inside `photoIn.accept = "image/*"` and ate the next hundred lines, taking a
 * real `api.uploadVerificationPhoto(...)` call with it. The fix for one false positive had created a
 * false NEGATIVE — strictly worse, because an uncounted caller reads as dead code somebody may then
 * delete. It was caught only because this ratchet fails in **both** directions; a one-way "did
 * anything become unreachable" check would have accepted it silently.
 *
 * So this tracks string state. Regex literals are not tracked, and deliberately: a `/` opens a
 * comment here only when followed by `/` or `*`, neither of which can begin a valid regex, and a
 * slash inside a pattern is written `\/`.
 */
export function stripComments(src: string): string {
  let out = "";
  let i = 0;
  let quote: string | null = null;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (quote) {
      out += c;
      if (c === "\\") { out += next ?? ""; i += 2; continue; }
      if (c === quote) quote = null;
      i++;
      continue;
    }
    if (c === '"' || c === "'" || c === "`") { quote = c; out += c; i++; continue; }
    if (c === "/" && next === "/") {
      while (i < src.length && src[i] !== "\n") i++;
      continue;
    }
    if (c === "/" && next === "*") {
      i += 2;
      while (i < src.length && !(src[i] === "*" && src[i + 1] === "/")) i++;
      i += 2;
      out += " ";
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

const appText = appFiles.map((p) => stripComments(readFileSync(p, "utf8"))).join("\n");

const api = new ApiClient("http://localhost:0");
const surface = [...surfaceOf(api)].sort();

/** Transport plumbing and lifecycle helpers — not endpoints, and not expected to have screens. */
const NOT_ENDPOINTS = new Set([
  "setToken", "url", "json", "health", "token", "base", "headers", "fetch", "request",
]);

function reached(m: string): boolean {
  // A direct call: `api.foo(`, `this.api.foo(`, `client.foo(`. The leading `.` keeps
  // `proformaRenovation` from being matched inside `xproformaRenovation`.
  if (new RegExp(`\\.${m}\\s*\\(`).test(appText)) return true;
  // A dispatch by name: `["modelHealth", "costSummary", …].map(call)` in portal.ts. Quoted on both
  // sides so a substring of a longer identifier does not count.
  if (new RegExp(`["'\`]${m}["'\`]`).test(appText)) return true;
  return false;
}

/**
 * Methods that should NOT have a screen, with the condition under which that stops being true.
 *
 * This is deliberately not a suppression list for work nobody has got to yet — those belong in the
 * ceiling, where they stay visible and countable. An entry here is a positive argument that wiring
 * the method would be a mistake, and it carries the condition that would retire the entry, so it
 * cannot quietly become permanent.
 */
const KNOWN_UNCALLED: Record<string, string> = {
  // v0.3.1051: the dashboard risk card now calls `riskDigest`, which returns the SAME headline and
  // risks PLUS the drivers they were computed from — SPI, EAC, variance-at-completion, open
  // RFIs/submittals/CORs, incidents. `riskSummary` (`/ai/risk-summary`) returns the prose alone, and
  // a risk narrative an owner cannot check against anything is the same as no narrative.
  //
  // Kept rather than deleted: `/ai/risk-summary` is a smaller, cheaper call and a reasonable thing
  // for an external or embedded caller to want. It has no caller HERE, which is what this list is
  // for. EXPIRY: delete both method and route if nothing has wanted the prose-only form by 2026-Q4.
  riskSummary: "superseded on the dashboard by riskDigest, which carries the drivers too",

  // Deletes a captured schedule baseline. R40-EOT ② has just made the NAMED baseline the auditable
  // input to an extension-of-time figure that ends up in arbitration — slip is measured against it,
  // and the whole point of sourcing it from the record was that a typed date is unauditable. A
  // one-click destroy beside that is a footgun, and "it has no caller" is not a reason to give it
  // one. EXPIRY: wire it once baseline deletion is behind a confirm-and-audit step.
  clearBaseline: "until baseline deletion is behind a confirm-and-audit step",

  // v0.3.972: a deprecated alias for `scheduleMonteCarlo`, which is what the panel now calls. It has
  // no caller BY DESIGN and must not be given one. It exists because retiring the `/schedule/risk`
  // path is a user-facing removal the roadmap records as the user's call — the second SIMULATOR
  // behind it was deleted, the path was not. EXPIRY: delete both when that call is made.
  scheduleRisk: "a deprecated alias kept until the user decides whether /schedule/risk is retired",
};

const uncalled = surface.filter((m) => !NOT_ENDPOINTS.has(m) && !reached(m));
/** The countable set: deliberate exclusions are held separately so they cannot pad the ceiling. */
const uncalledCountable = uncalled.filter((m) => !(m in KNOWN_UNCALLED));

//: CEILING — only ever revised DOWN. The measured value on 2026-08-07, so the set cannot grow
//: quietly. Wiring a method to a screen lowers it; adding an unreachable endpoint raises it and has
//: to say so out loud in the commit message.
//:
//: 132 -> 131 when PULSE-FINDINGS wired `proformaRenovation` into the home pulse. It was expected to
//: drop by TWO, for `reserveStudy` as well — that was wrong, and the number is why it was caught:
//: `reserveStudy` already had a caller in `src/proforma/proforma.ts`, so it was never in this set.
//: Measured by probing rather than derived from what the wiring touched.
//: 129 -> 128 on 2026-08-07 (BOE-REACH): `estimateBoe` gained a caller — Basis of estimate on the
//: budget panel. Measured by re-running the scan, which reports exactly one fewer; nothing became
//: newly uncalled.
//:
//: 131 -> 129 on 2026-08-07 (UNCALLED-SWEEP, Lane C/G/I). The drop is TWO and was MEASURED by
//: re-running the reachability scan before and after, not derived from what was wired — the
//: `reserveStudy` note above is exactly why. `portfolioCompare` gained a caller (the returns spread
//: on the portfolio panel) and `clearBaseline` moved into KNOWN_UNCALLED, which the countable set
//: now excludes. Nothing became newly uncalled.
//:
//: HOW THIS NUMBER WAS OBTAINED, because it matters for trusting it: `vitest` is not installed in
//: `apps/web` and the shared clone's `src/api` differs from `origin/main` by ~795 deletions, so this
//: file could not be executed to produce it. The delta was measured with a static reproduction of
//: the same predicate against a clean `origin/main` worktree, which counts ~127 where this file
//: counts 131 — a different population, so its ABSOLUTE is not a valid ceiling input. The DELTA is
//: sound because both affected methods are present in both populations. If this run reports anything
//: other than 129, trust this file and not the reasoning above.
//:
//: 121 -> 117 on 2026-08-07 (LANE-REACH, re-derived at merge). This branch was measured at
//: 128 -> 123 against d0fbfadd and that was correct THEN. #271 then merged and reached
//: `estimateConfidence` too (register.ts, per-record), so only FOUR of this branch's five are
//: still new: wipModelProgress, dealAuthority, reviewContractClauses, aiEstimate.
//:
//: Landing the stale 123 on a main already at 121 would have RAISED the ceiling by two with
//: every gate green — line 181 is `toBeLessThanOrEqual` and has no floor. Two PRs measured
//: correctly against the same base go stale the instant either merges; the second one must
//: RE-MEASURE, not merely rebase.
//:
//: Set to 117 rather than to main's 121 on purpose. If the true count is 117 this is exact; if
//: it is higher the gate FAILS LOUDLY on the next run and gets corrected. 121 would have
//: passed either way and told nobody. Bias low: low fails, high hides.
//: 117 -> 101 (Lane A/B/E reach sweep, 2026-08-07). Seventeen capabilities that computed an answer
//: and could not show it to anyone — the qaSection readouts, the dimensional-locks panel, and four
//: recipes the node canvas simply did not list.
//:
//: **101 is what the GATE PRINTED on the merged tree, and the arithmetic would have been wrong.**
//: 117 minus the fourteen this branch wires is 103; the measured answer is 101, because reach is not
//: additive across lanes — three sweeps ran concurrently and touched overlapping method sets.
//:
//: The failure mode this avoids is not a small error. `toBeLessThanOrEqual` has NO FLOOR, so a stale
//: ceiling carried forward RAISES the number with every gate green: #273 measured 128 -> 123
//: correctly, #271 then landed and reached one of the same methods, and landing 123 on a main at 117
//: would have handed four points of slack to whoever added the next unreachable method.
//:
//: So: rebase, set this to 0, run, read the number the assertion prints, restore, land that. And
//: when two candidates are both defensible, take the smaller — a ceiling set too low fails loudly on
//: the next run and gets fixed; one set too high never fails at all.
//: ---------------------------------------------------------------------------------------------
//: RATCHET-SET (2026-08-07): the count above became a SET, and the history above is why.
//:
//: Every note in this block records the same class of near-miss: a literal measured correctly
//: against one base, gone stale the moment another PR merged, and passing anyway because
//: `toBeLessThanOrEqual` HAS NO FLOOR. A higher number always passes. On 2026-08-07 five PRs lowered
//: this one line from four different bases and two stale-high literals were caught BY HAND — #254
//: carried 129 onto a main at 128, #273 carried 123 onto a main at 117. Nothing would have failed.
//:
//: A set fixes the three problems the count could not:
//:   * TIGHT BY CONSTRUCTION — set equality has no loose direction, so there is no "too high".
//:   * MERGE-FRIENDLY — two PRs reaching different methods delete different lines instead of
//:     fighting over one number. Only two PRs reaching the SAME method conflict, which is a real
//:     conflict worth surfacing.
//:   * HONEST ABOUT POPULATION — a method moving into KNOWN_UNCALLED becomes a visible line move
//:     rather than an invisible change to what the number counts. That ambiguity is exactly what
//:     made 129 - 8 and 117 - 14 both wrong.
//:
//: WHAT IT STILL DOES NOT DO, so nobody mistakes this for the whole fix: a name leaving this list
//: proves a call site appeared, NOT that the feature works. `buyoutPackages` was wired to an
//: incompatible input and returned `packages: []` with every gate green; `aiEstimate` rendered
//: "0 line(s)" when the API key was simply unset. Both lowered the number. The complementary check
//: is to call the endpoint with the arguments the caller actually sends and look at the response.
//:
//: HOW TO CHANGE THIS LIST. Wire a method to a screen, then DELETE its line. If you delete the
//: wrong one the gate says so by name. Do not add a line without saying in the commit why another
//: unreachable endpoint is worth shipping.
const UNCALLED: readonly string[] = [
  // `job(pid, jobId)` — fetch ONE job. Uncalled all along; it read as reached only because
  // `shell/spine.ts` has a comment saying "`label` and `job` mirror `rooms.ROOMS`", and the
  // dispatch-by-name matcher counted a backticked word in prose as a call site. Stripping comments
  // uncovered it. The app polls `jobs(pid, limit)` and filters, which is correct for the runs inbox
  // and wasteful for tracking a job you just started; wiring it belongs with whoever owns
  // `main.ts` (Lane A), not with a session passing through.
  // `job` stays here even though `waitForJob.ts` polls it: that module lives under `src/api/`,
  // which this scanner excludes (a client helper is not an application screen). Tools enqueue
  // `clash_detect` / `clash_federated` rather than calling `runClash` / `clashFederated`; those
  // wrappers remain for scripts and the still-live POST routes.
  "job",
  "addBasePlate", "addCurtainWall", "addMepFitting", "addRebarCage",
  "addShearTab", "addTopicComment", "applyDetailingRules", "arrayElement",
  "assignMaterialSet", "assumptionsRegister", "attachDocument",
  "buyoutSchedule", "ciLatest", "citedQuery", "clashFederated", "clausePlaybook",
  "clientDecisions", "codeAdoptions", "codeCheck", "colorFacets",
  "competitiveSupply", "connectElements", "costSummary", "createAssembly", "createGroup",
  "createType", "decisionGate",
  "docGraph", "draftPost", "drawingSchedulesCalc", "drawingSetPlan",
  "drawingsSyncStatus", "ebcPathways", "editType", "elements5dMap",
  "energyExportUrl", "energyModel", "equipmentSpecCheck",
  "expandMacro", "feasibilityLotSupply", "feasibilitySellout", "holdSell",
  "importFamilyPack", "layoutVerify", "listMacros", "listingReso",
  "liveStream", "loanCovenants", "massingOptionRecipes", "mcpTools",
  "mep", "modelAdjacency", "moduleCalc", "myWork",
  "netEffectiveRent", "normalizeT12", "parcelAnalyze", "parcelsDataStatus",
  "pdfInfo", "permitsTimeline", "preconSnapshot", "procurementLevel",
  "procurementLevelQuotes", "proformaIncomeBasis", "proformaRenovation", "proformaRollover", "progressActuals",
  "progressCaptureDiff", "progressRollup", "raisePlan", "recordDistribution",
  "rentRollScrub", "residualLand", "reviewPost",
  "reviewScenario", "reviseDrawing", "runClash", "runMacro", "saveClausePlaybook",
  "saveDealAuthority", "saveMacros", "saveViewTemplates",
  "scanDeviation", "scopeRegister", "securitiesPackage", "sendDigest",
  "setLod", "setPhase", "sharedComment", "sharedDecision",
  "sharedDigestUrl", "spaceUtilBenchmarks", "speckleStatus", "tieredComps",
  "topicComments", "updateConnection", "veLog", "verificationDeviations",
  "wallJoins",
];

describe("client methods the application actually calls", () => {
  it("agrees with a hand-checked sample in BOTH directions", () => {
    // Self-testing the instrument. A reachability checker that only ever reports "uncalled" is
    // indistinguishable from a broken matcher, and the first draft of this file WAS one for
    // `costSummary` — it is dispatched by string name from the project home and read as unreachable.
    // Each name below was verified by hand with a plain grep; the pairing is the point, because a
    // one-sided sample cannot catch a matcher that is too loose OR too tight.
    for (const m of ["projectPulse", "modules", "publish"]) {
      expect(uncalled.includes(m), `${m} has app call sites but reads as uncalled`).toBe(false);
    }
    for (const m of ["colorFacets", "addBasePlate"]) {
      expect(uncalled.includes(m), `${m} has NO app call site but reads as reached`).toBe(true);
    }
  });

  it("counts an app caller, not merely a method definition", () => {
    // Guards the instrument before its verdict: if the scan found no callers at all it would report
    // every method uncalled and look like a catastrophic finding rather than a broken matcher.
    expect(appFiles.length, "no application files were scanned").toBeGreaterThan(50);
    expect(surface.length, "the client surface came back empty").toBeGreaterThan(600);
    expect(uncalled.length, "EVERY method reads as uncalled — the matcher is broken, not the app")
      .toBeLessThan(surface.length);
  });

  it("does not read a COMMENT as a call site — but still reads real code", () => {
    // Both directions, because stripComments is easy to make too eager. A version that stripped
    // everything would silence the whole gate and every method would read as uncalled — which the
    // test above catches — but a version that ate one line too many would just quietly lose callers.
    const src = [
      "/** not `procurementLevel` — this method is the other one. */",
      "// see `buyoutSchedule` for the time-phased version",
      "const url = \"https://example.test/a//b\";",
      // The one that broke the first draft: a `/*` inside a STRING is not a comment opener. The
      // regex version opened a block comment here and ate every line to the next `*/`, silently
      // deleting a real `api.uploadVerificationPhoto(...)` call a hundred lines down.
      "photoIn.accept = \"image/*\";",
      "await api.levelBids(pid);",
      "dispatch([\"scheduleCompare\"]);",
    ].join("\n");
    const out = stripComments(src);
    expect(out, "a backticked name in a comment counted as a call site — the exact false positive "
      + "that reported procurementLevel as newly wired").not.toContain("procurementLevel");
    expect(out, "a line comment naming a method still counted").not.toContain("buyoutSchedule");
    expect(out, "real calls must survive").toContain(".levelBids(");
    expect(out, "dispatch-by-name must survive").toContain("\"scheduleCompare\"");
    expect(out, "`//` inside a string truncated the line — a URL is not a comment")
      .toContain("example.test/a//b");
  });

  it("the set of unreachable client methods is exactly the committed one", () => {
    const measured = [...uncalledCountable].sort();
    const committed = [...UNCALLED].sort();

    // TWO ASSERTIONS, NOT ONE, because the two directions mean opposite things and a single
    // `toEqual` would report them as one indistinguishable diff.
    const appeared = measured.filter((m) => !committed.includes(m));
    const wired = committed.filter((m) => !measured.includes(m));

    expect(appeared,
      `${appeared.length} client method(s) became unreachable: ${appeared.join(", ")}\n` +
      `Wire each to a screen, or add it to UNCALLED and say in the commit why shipping another ` +
      `endpoint nobody can reach is worth it.`)
      .toEqual([]);

    // Down is NOT automatically fine here, unlike the innerHTML baseline. This list is the RECORD
    // of what cannot be reached; leaving a wired method in it makes the record lie, and the next
    // reader budgets against slack that is not there. The fix is one deletion and the gate names it.
    expect(wired,
      `${wired.length} method(s) in UNCALLED now HAVE a caller: ${wired.join(", ")}\n` +
      `Good - delete those line(s) from UNCALLED. The list must stay exact, because a stale entry ` +
      `is slack the next person spends without knowing.`)
      .toEqual([]);
  });

  it("names the three that prompted this check, so their status cannot drift silently", () => {
    // `surface.test.ts` lists these under "the methods the rest of the app actually calls".
    // That was false when written. This records which of them is still true, so wiring one up
    // fails here and forces the list to be corrected rather than left to rot.
    //
    // It did exactly that: PULSE-FINDINGS wired `proformaRenovation` into the home pulse and this
    // assertion went red on the same run, which is the whole reason it names them individually
    // instead of counting them.
    const trio = ["proformaRenovation", "proformaRollover", "proformaIncomeBasis"];
    const stillUncalled = trio.filter((m) => uncalled.includes(m));
    expect(stillUncalled.sort()).toEqual(
      ["proformaIncomeBasis", "proformaRenovation", "proformaRollover"]);
  });

  it("proformaRenovation is not POSTed from Pulse — a programme body is required", () => {
    // Pulse used to call this with no body (the route is POST). v0.3.991 maps Pulse on the
    // server and does not invent a renovation programme, so this method is uncalled again
    // until a screen that actually has unit types wires it.
    expect(uncalled.includes("proformaRenovation")).toBe(true);
  });
});
