/**
 * The keep-list in `client.ts` must agree with the file it describes.
 *
 * WHY THIS EXISTS
 *     SCALE-SEAM (83) replaced a banner that named nothing with a map of the methods still
 *     unfiled, grouped by what each answers. That map is prose: a declared count and a list of
 *     names, with nothing checking either against the file underneath it.
 *
 *     It was wrong within one slice. (83) counted the banner's methods with
 *
 *         /^  ([a-zA-Z_]\w*)\(/
 *
 *     which does not match `async` methods, so it silently skipped five — `importRvt`,
 *     `loanDrawRequestPdf`, `raisePlan`, `takeoffDxf`, `uploadSourceIfc` — and reported 44 where
 *     the true figure was 49. The roadmap had said 49; (83) "corrected" the right number to a
 *     wrong one and shipped that into the changelog, the roadmap and its own merge commit.
 *
 *     The failure is not carelessness with a number. It is the class this whole sequence exists
 *     to find: A CHECK WHOSE OUTPUT DOES NOT MEASURE WHAT IT CLAIMS TO. A regex that silently
 *     drops a syntactic variant returns a smaller number, not an error, and a smaller number
 *     looks exactly like a correct one. The same shape produced the inverted count #396 pinned,
 *     the two changelog totals #399 fixed, and a `&&` chained off `head` that printed
 *     "TYPECHECK CLEAN" over a failing `tsc`.
 *
 *     So the map is not proofread here, it is DERIVED. If a slice moves a method and forgets the
 *     map, or writes a count from a hand-run query, this fails and names the difference.
 */
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const CLIENT = join(__dirname, "client.ts");
//: Was `--- UNFILED — N methods` until SCALE-SEAM (87). The CX-1 residue is placed, and the four
//: methods left below it are DECIDED to stay, not pending — so calling them unfiled was the very
//: thing this file exists to stop: a label that does not describe what is under it.
const BANNER = /^\s*\/\/ --- STAYING — (\d+) client-level methods/;

/** Method declarations in `client.ts`, which indents its class body by two. `async` included —
 *  that is the variant (83) missed, and the reason its count was five short. */
const METHOD = /^ {2}(?:async )?([a-zA-Z_]\w*)\(/;

/** The same, across `api/` — where the indent is NOT uniform. `authoring.ts` (37 methods),
 *  `assetRights.ts`, `docqa.ts` and `library.ts` indent by four, and a handful of files mix both.
 *  (85) found this file matching only two, so ~47 names — every method on `withAuthoring` among
 *  them — were missing from the vocabulary, and a map entry naming one of them could never be
 *  reported stale. **That is the async bug again, in the test written to prevent it**: a pattern
 *  whose scope silently excludes part of its population returns a smaller set, not an error. */
const METHOD_ANY_INDENT = /^ {2,4}(?:async )?([a-zA-Z_]\w*)\(/;

function readMap() {
  const lines = readFileSync(CLIENT, "utf8").split("\n");
  const start = lines.findIndex((l) => BANNER.test(l));
  expect(start, "the STAYING banner is gone from client.ts — if the keep-list was deliberately "
    + "retired, delete this test in the same commit rather than leaving it asserting nothing")
    .toBeGreaterThan(-1);

  const declared = Number(BANNER.exec(lines[start] ?? "")?.[1] ?? NaN);
  expect(declared, "the UNFILED banner no longer states a method count").not.toBeNaN();

  // The map's own comment block ends at the first line that is not a `//` comment.
  let bodyAt = start + 1;
  while (bodyAt < lines.length && /^\s*\/\//.test(lines[bodyAt] ?? "")) bodyAt++;

  // Which tokens in the map are METHOD NAMES is derived, not guessed: a word counts only if some
  // file in `api/` declares a method by that name. Matching camelCase or a hand-kept word list
  // would either miss `property` and `templates` (no capital) or swallow prose like "check" and
  // "stay" — and a name check that quietly drops or invents entries is the exact defect this
  // file exists to prevent.
  const vocabulary = new Set<string>();
  for (const f of readdirSync(__dirname)) {
    if (!f.endsWith(".ts") || f.endsWith(".test.ts") || f === "schema.d.ts") continue;
    const body = readFileSync(join(__dirname, f), "utf8");
    let found = 0;
    for (const l of body.split("\n")) {
      const m = METHOD_ANY_INDENT.exec(l);
      if (m?.[1]) { vocabulary.add(m[1]); found++; }
    }
    // A mixin that contributes NOTHING means its indentation fell outside the pattern, which is
    // exactly how authoring.ts's 37 methods went missing. Fail loudly rather than shrink quietly.
    if (body.includes("return class ")) {
      expect(found, `${f} declares a mixin class but contributed no method names to the `
        + `vocabulary — its indentation is outside METHOD_ANY_INDENT, so every name it declares `
        + `is invisible to the stale check below`).toBeGreaterThan(0);
    }
  }
  expect(vocabulary.size, "no method declarations found anywhere in api/ — the vocabulary is "
    + "empty, so the name checks below would pass vacuously").toBeGreaterThan(100);

  // Only the cluster list carries names. The prose above it discusses methods that have already
  // MOVED (that is the point of the note), so scanning the whole block would flag them as stale.
  const listAt = lines.findIndex((l, i) => i > start && i < bodyAt
    && (l ?? "").includes("the four that stay"));
  expect(listAt, "the keep-list no longer has its 'the four that stay' marker — this test "
    + "locates the name list by it, and without it the name checks would scan the prose instead")
    .toBeGreaterThan(-1);

  // Within a list line, a name is whatever follows the question. Question text sits in the left
  // column and can itself contain a method name ("how is the portfolio doing?" — `portfolio` is
  // a method on `withProforma`), so everything up to the last `?` on the line is discarded.
  const named = new Set<string>();
  for (const l of lines.slice(listAt, bodyAt)) {
    const tail = l.includes("?") ? l.slice(l.lastIndexOf("?") + 1) : l;
    for (const m of tail.matchAll(/\b([a-zA-Z_]\w*)\b/g)) {
      if (m[1] && vocabulary.has(m[1])) named.add(m[1]);
    }
  }

  const actual: string[] = [];
  for (const l of lines.slice(bodyAt)) {
    const m = METHOD.exec(l);
    if (m?.[1]) actual.push(m[1]);
  }
  return { declared, actual, named };
}

describe("the keep-list in client.ts", () => {
  it("declares the number of methods that are actually below it", () => {
    const { declared, actual } = readMap();
    expect(actual.length, `the STAYING banner says ${declared} methods but ${actual.length} `
      + `follow it. Count from the file, never from a hand-run query — the count this replaces `
      + `was produced by a regex that skipped every 'async' method. Methods found: `
      + actual.join(", "))
      .toBe(declared);
  });

  it("names every method it covers, so none is unfiled-and-unmentioned", () => {
    const { actual, named } = readMap();
    const missing = actual.filter((m) => !named.has(m));
    expect(missing, `these methods sit under the STAYING banner but the keep-list does not name them: `
      + `${missing.join(", ")}. A map that omits a method is how a method gets left behind — `
      + `add it to the cluster whose question it answers, or give it its own line.`)
      .toEqual([]);
  });

  it("does not name a method that has already been extracted", () => {
    const { actual, named } = readMap();
    const stale = [...named].filter((n) => !actual.includes(n));
    expect(stale, `the map names these, but they are no longer under the banner: `
      + `${stale.join(", ")}. A slice moved them and did not update the map.`)
      .toEqual([]);
  });
});
