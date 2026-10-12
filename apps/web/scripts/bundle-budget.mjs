#!/usr/bin/env node
// Fail the build if the eager app *shell* grows past its budget. The shell is what every user
// downloads before anything is interactive; the heavy viewer libs (three/@thatopen), Studio, and the
// Finance/Drawings panels are code-split and lazy-loaded, so they're deliberately NOT counted here.
// We measure Brotli-compressed bytes — that's what a modern static server actually ships over the wire.
import { brotliCompressSync } from "node:zlib";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const DIST_ROOT = join(process.cwd(), "dist");
const DIST = join(DIST_ROOT, "assets");
// Budget in KB (Brotli). Set generously above the current shell so it catches regressions, not noise.
// Bump this deliberately (with a note) when the shell legitimately grows.
//
// 220 -> 224 on 2026-10-12, and the measurement is the point. The shell hit **220.4 KB** and the
// budget had never moved since it was written, so "generously above the current shell" had quietly
// become a ceiling the shell was touching — the next change to land anywhere eager was going to pay
// for everyone's growth. CODE-READY-DARK tipped it: `Web typecheck + test + build` was green through
// b57490e7 and red on the next push, whose only bundle-affecting commit was that one.
//
// WHAT IT COST, measured per feature rather than assumed, by grepping the built chunks for a string
// only each module emits:
//
//   viewer/tools/*            -> app-*.js        EAGER SHELL   (macroTool, codeReadiness, mepSection)
//   portal/panels/*           -> jurisdictionPanel-*.js  lazy
//   reportCenter + its helpers-> reportCenter-*.js        lazy
//
// So of four features shipped that day, two cost shell bytes and two cost none, and nothing told
// anybody which — a tool added to the viewer rail is downloaded by every first-time visitor before
// anything is interactive, while the same amount of code in a portal panel is not. **That asymmetry
// is the useful finding here, not the number.** The honest alternative to this bump is to lazy-load
// a tool's body behind its click, which is the right shape and is a pattern no tool in that
// directory uses today (measured: zero `await import(` under `viewer/tools/`); applying it to two
// of some forty tools would buy 0.4 KB and leave an inconsistency for the next reader to explain.
//
// **That last measurement went out of date the same day, and in the direction that flatters the
// bump.** Re-measured 2026-10-12: FOUR files under `viewer/tools/` reach a module through
// `await import(` in code — `analyseSection`, `modelReviewPanel`, `projectPanel`, `qaSection`, five
// call sites between them — every one of them added by this gate refusing a build, not chosen. The
// last one was refused TWICE: deferring only the rendering left the shell **five bytes** over, so
// the fetch, the toast, the status line and the `showResult` call went behind the click as well.
// So the alternative this paragraph declined on grounds of inconsistency is now what the newest
// tools do, and the next legitimate growth should pay for itself the same way before this number
// moves again.
//
// *A number that decays toward the conclusion it supports is the hardest kind to notice, because
// nothing it predicts ever looks wrong.* Re-derive it, never read it — and count CODE, not
// comments, because two of the six files that match the string only discuss it:
//   grep -c "await import(" apps/web/src/viewer/tools/*.ts
//
// **224 -> 225 on 2026-10-12, later the same day, and the measurement is again the point.**
// FIRM-RULES-OPTIONAL slice (2) wired four routes that had no client method between them --
// `GET`/`PUT /projects/{pid}/rules` and `GET`/`PUT /firm/rules` -- so the parametric rule library
// every check in the product evaluates could finally be AUTHORED from the product. Measured: the
// shell went 223.8 -> **224.03 KB, which is 229,407 brotli bytes against a 229,376 limit: 31 over**
// -- and all of it is the four client methods. The figure is given in BYTES because the display
// rounds to one decimal and "224.0 KB" is what both a pass and a 31-byte failure look like; this
// file's own history is a chain of numbers that rotted, so the one that decides a build is written
// in the unit the decision is made in. The editor itself,
// `portal/panels/ruleStandards.ts` at 310 lines, cost ZERO shell bytes, because `portal/panels/*`
// is lazily imported by construction. That is the same asymmetry the paragraph above measures,
// seen from the other side: the UI was free and the four fetch wrappers were not.
//
// **What was tried before bumping, and why it was rejected.** The `ApiClient` mixins are composed
// eagerly, so a method on one is shell bytes by construction; the only way to defer these four
// would be to expose a generic request helper for a lazy panel to build its own URLs on -- which
// is more eager bytes, and it would put URL construction outside the one place
// `services/api/test_route_reachability.py` and `apps/web/src/api/clientCallers.test.ts` both look
// for it. *Contorting the API surface to fit a byte budget costs more than the byte budget is
// worth*, and a client method per route is the shape two gates depend on.
//
// **The bump is 1 KB, not a round-up to a comfortable number.** 220 -> 224 was four, and what that
// bought was four releases of nobody deciding anything; this leaves ~0.9 KB, which is roughly one
// more feature's worth of client methods. The next thing to land eager should pay for itself by
// deferring, the way the three tools above now do.
const BUDGET_KB = Number(process.env.BUNDLE_BUDGET_KB || 225);

// The eager shell = exactly what index.html loads up front: the entry chunk + its CSS, plus the split
// first-party `app-*` chunk the entry statically imports. Everything else is a lazy chunk that doesn't
// block first interaction.
//
// We parse the entry/CSS out of index.html rather than filename-matching `index-*.js`: a lazy *vendor*
// chunk whose source module is `index.js` (e.g. pdfjs-dist, ~160 KB, loaded only when a PDF is opened)
// also gets an `index-<hash>.js` name from Rollup, and must NOT be miscounted as shell (that false
// positive is exactly what used to blow the budget). The LAZY libs (three/@thatopen/…) are separate
// chunks and never part of this set.
const APP = /^app-.*\.js$/;
const LAZY = /^(three|thatopen|studio|panel|viewer|charts|proforma)-/;

let files;
try {
  files = readdirSync(DIST);
} catch {
  console.error(`bundle-budget: ${DIST} not found — run \`vite build\` first.`);
  process.exit(2);
}

let html;
try {
  html = readFileSync(join(DIST_ROOT, "index.html"), "utf8");
} catch {
  console.error(`bundle-budget: ${join(DIST_ROOT, "index.html")} not found — run \`vite build\` first.`);
  process.exit(2);
}
// only the entry assets index.html actually references (under <base>assets/), not registerSW.js etc.
//
// The `[^"]*` before `/assets/` is load-bearing and was not there originally: `vite.config.ts` sets
// `base: process.env.VITE_BASE || "/"`, and the Pages build (`pages.yml`) sets `VITE_BASE=/app/`, so
// Vite emits `src="/app/assets/…"` there and `src="/assets/…"` by default. Anchoring the match at
// `/assets/` meant this script found no entry on a Pages build and exited 2 — which reads as "the
// build output changed", not as "this configuration is unmeasured". It never surfaced because
// `npm run budget` was not in `pages.yml` at all. Matching the segment rather than the prefix is
// what lets one script measure both builds.
const htmlEntry = (re) => [...html.matchAll(re)].map((m) => m[1]);
const entryJs = htmlEntry(/<script[^>]+src="[^"]*\/assets\/([^"/]+\.js)"/g);
const entryCss = htmlEntry(/<link[^>]+href="[^"]*\/assets\/([^"/]+\.css)"/g);
const shellNames = new Set([...entryJs, ...entryCss, ...files.filter((f) => APP.test(f))]);
const shellFiles = files.filter((f) => shellNames.has(f));
if (!entryJs.length) {
  console.error("bundle-budget: no entry <script> found in dist/index.html — did the build output change?");
  process.exit(2);
}

let total = 0;
const rows = [];
for (const f of shellFiles) {
  const br = brotliCompressSync(readFileSync(join(DIST, f)));
  total += br.length;
  rows.push([f, br.length]);
}

const kb = (n) => (n / 1024).toFixed(1);
console.log("App shell (Brotli):");
for (const [f, n] of rows.sort((a, b) => b[1] - a[1])) console.log(`  ${kb(n).padStart(7)} KB  ${f}`);
console.log(`  ${"-".repeat(28)}`);
console.log(`  ${kb(total).padStart(7)} KB  total  (budget ${BUDGET_KB} KB)`);

// Sanity: confirm the heavy libs really are separate lazy chunks, not folded into the shell.
const lazy = files.filter((f) => LAZY.test(f) && /\.js$/.test(f));
console.log(`Lazy chunks kept out of the shell: ${lazy.length}`);

// ...and ASSERT it, because printing a number is not a check.
//
// `vite.config.ts` says of the vendor split: "A vendor split that silently stops splitting is the
// worst kind of build regression: the bundle still works, so nothing fails" — and then "Verify by
// grepping the OUTPUT, never by reading the config and believing it." Nobody was verifying the
// output. The line above computed `lazy` and printed it, and a build with the split gone printed
// a smaller number and exited 0.
//
// It is not hypothetical. Measured 2026-08-06, same commit, same command, two checkouts:
//
//     main clone   exit 0   three-*.js + thatopen-*.js present   app shell    334 KB
//     git worktree exit 1   NEITHER chunk emitted                app shell  6,581 KB   (19.7x)
//
// In a worktree the hoisted `node_modules` sits outside the workspace root, the deps fall back to
// CommonJS interop (a `_commonjsHelpers` chunk appears; 638 modules transformed vs 585), and the
// `advancedChunks` rules never match — so three.js and the That Open stack are folded into the
// eager shell. The only thing that turned that into a visible failure was the PWA precache size
// limit, which is absent from `VITE_PAGES=1` builds. Without this assertion, that configuration
// ships a 20x shell in silence.
const VENDOR_CHUNKS = [
  ["three", /^three-.*\.js$/],
  ["thatopen", /^thatopen-.*\.js$/],
];
const missingVendor = VENDOR_CHUNKS.filter(([, re]) => !files.some((f) => re.test(f))).map(([n]) => n);
if (missingVendor.length) {
  console.error(
    `\nbundle-budget: FAIL — vendor chunk(s) not emitted: ${missingVendor.join(", ")}.\n` +
    "The advancedChunks split did not match, so these libs are inside the eager shell and are no\n" +
    "longer separately cacheable. Chunking has regressed, or a build ran a Vite that ignores\n" +
    "rolldownOptions.advancedChunks. npm run build must go through scripts/run-vite.mjs.",
  );
  process.exit(1);
}

if (total / 1024 > BUDGET_KB) {
  console.error(`\nbundle-budget: FAIL — shell ${kb(total)} KB exceeds ${BUDGET_KB} KB.`);
  console.error("Trim the eager path (lazy-load it) or bump BUNDLE_BUDGET_KB deliberately with a note.");
  process.exit(1);
}
console.log(`\nbundle-budget: OK — shell within ${BUDGET_KB} KB.`);
