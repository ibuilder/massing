import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * DEAD-FIELD — the SCOPE of the derivation, not the fields it returns.
 *
 * The roadmap's DEAD-FIELD axis is derived by matching every field of every `export interface` under
 * `apps/web/src/api/` against every reference in `apps/web/src`, minus the declaring file. That
 * derivation is **identifier-based, not type-aware**, and this file exists to keep that limitation a
 * measured fact rather than a footnote — because the entry's stated blocker ("read the remaining
 * ~35 detail fields, then gate") is the wrong one if the method cannot support a gate at all.
 *
 * ### The worked example, asserted below
 *
 * `SpatialNode.elevation` is referenced in dozens of files and by **none of them as a SpatialNode** —
 * they are storeys, drawing grids, GIS overlays, draft gizmos, all different types that happen to
 * name a field `elevation`. Nothing renders `SpatialNode.elevation`. The derivation calls it read.
 * Its companion `elevationUnit` — which the declaring comment says travels with the number precisely
 * because the unit varies per model — is correctly reported unread, so the pair lands in two
 * different buckets for no reason a reader could act on.
 *
 * ### Why this blocks a gate rather than delaying one
 *
 * A freeze-list built on this would inherit the blind spot, and it falls hardest on exactly the
 * fields most likely to be displayed: the common names. `name`, `key`, `id`, `title`, `status` and
 * `count` are each referenced in 200+ files, so any interface declaring one has that field marked
 * read no matter what the product does with it. `KNOWN_UNCALLED` recorded the cost of a freeze list
 * nobody had checked; this would be the same list with a mechanical reason to be wrong.
 *
 * Making it sound needs a **type-aware** pass (the TypeScript compiler API or language service,
 * resolving each property access to its declaring symbol). That is the unblocking step, and it is
 * not what the roadmap currently says it is.
 *
 * This test therefore pins the SHAPE of the measurement, not a defect list: the counts are a band so
 * ordinary work does not fail the build, and the collision case is asserted exactly, so a future
 * type-aware derivation makes this test fail and demand rewriting — which is the point.
 */

// process.cwd() is apps/web under vitest — the same convention `roadmapLanes.test.ts` records.
const API = resolve(process.cwd(), "src/api");
const WEB = resolve(process.cwd(), "src");

/** Every `.ts`/`.tsx` under `dir`, recursively — the file set both halves of the scan run over. */
function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith(".ts") || p.endsWith(".tsx")) out.push(p);
  }
  return out;
}

/** (interface, field) -> declaring file, for hand-written api/ interfaces. */
function declaredFields(): Map<string, string> {
  const out = new Map<string, string>();
  for (const f of walk(API)) {
    // schema.d.ts is GENERATED from OpenAPI and deliberately not regenerated (doing so churned
    // 38,231 lines). Its `components` blob declares more fields than the rest of api/ combined —
    // including it reports 730 "unread" and buries the axis entirely.
    if (f.endsWith(".test.ts") || f.endsWith("schema.d.ts")) continue;
    const src = readFileSync(f, "utf-8");
    for (const m of src.matchAll(/export interface (\w+)\s*\{/g)) {
      let i = m.index! + m[0].length - 1;
      let depth = 0;
      for (; i < src.length; i++) {
        if (src[i] === "{") depth++;
        else if (src[i] === "}" && --depth === 0) break;
      }
      const body = src.slice(m.index! + m[0].length, i);
      // ANY indent, not just the top level: a derivation anchored on two spaces cannot see a NESTED
      // field, and this axis's one load-bearing defect (`ResponsibilityMatrix.validation.*`) was
      // nested. A predicate that decides what to LOOK at hides its own misses.
      for (const fm of body.matchAll(/^[ \t]+(?:readonly\s+)?([A-Za-z_]\w*)\??\s*:/gm)) {
        const k = `${m[1]}.${fm[1]}`;
        if (!out.has(k)) out.set(k, f);
      }
    }
  }
  return out;
}

// THIS FILE IS NOT PART OF THE CORPUS, and leaving it in was a live defect caught in review.
// The scan matches a bare identifier in raw text — comments and strings included — so the prose
// below naming `elevation`, `elevationUnit` and `SpatialNode` counted as *readers* of those fields.
// Measured: unread was 31 with this file in the corpus and 32 without, and the single field it
// moved was `SpatialNode.elevationUnit` — precisely the one the roadmap holds up as the correctly
// reported-unread half of the pair. **The file falsified its own worked example by existing**, and
// the reported population would then drift with documentation edits rather than with product usage.
// A measurement whose corpus contains the measurement is the same shape as the flaw it records.
const AUDIT = resolve(API, "deadFieldScope.test.ts");
const files = walk(WEB).filter((f) => f !== AUDIT);
const tokens = new Map<string, Set<string>>();
for (const f of files) {
  tokens.set(f, new Set(readFileSync(f, "utf-8").match(/[A-Za-z_]\w*/g) ?? []));
}
const decls = declaredFields();

/** Files mentioning `field` as a bare identifier, excluding the one that declares it.
 *  This is the derivation's whole notion of "read", and the reason it cannot be trusted: the match
 *  is on the NAME, so a file handling an unrelated type with a same-named field counts as a reader. */
function readersOf(field: string, declaring: string): string[] {
  return files.filter((f) => f !== declaring && tokens.get(f)!.has(field));
}

describe("DEAD-FIELD: what the derivation can and cannot see", () => {
  it("derives a population of the expected order — the roadmap's number is not read, it is re-run", () => {
    // A band, not a pin: this must not fail because someone added an interface. It fails if the
    // derivation itself breaks (regex stops matching, directory moves), which is the real risk —
    // a silently-empty population would report a clean axis.
    expect(decls.size).toBeGreaterThan(600);
    const unread = [...decls].filter(([k, f]) => readersOf(k.split(".")[1]!, f).length === 0);
    expect(unread.length).toBeGreaterThan(10);
    expect(unread.length).toBeLessThan(80);
  });

  it("SpatialNode.elevation has readers by NAME and none by TYPE — the collision, exactly", () => {
    // The whole argument in one case. If this ever fails because the derivation became type-aware,
    // rewrite this file rather than relaxing the assertion: the limitation would be gone.
    const decl = decls.get("SpatialNode.elevation");
    expect(decl, "SpatialNode.elevation is no longer declared — re-derive before trusting this")
      .toBeTruthy();
    const readers = readersOf("elevation", decl!);
    expect(readers.length,
      "the identifier is referenced widely, which is what makes the field look read")
      .toBeGreaterThan(10);
    // ...and not one of those files names the interface, i.e. none of them is handling a SpatialNode.
    const typed = readers.filter((f) => tokens.get(f)!.has("SpatialNode") && !f.endsWith(".test.ts"));
    expect(typed,
      "a production file now handles SpatialNode — check whether it renders `elevation`, and "
      + "whether it renders `elevationUnit` beside it (the unit varies per model, often mm)")
      .toEqual([]);
  });

  it("this file's own prose is not a reader — the exclusion above, asserted", () => {
    // Pins the fix rather than trusting it: `elevationUnit` is named several times in the comments
    // here, so it is unread ONLY while this file is out of the corpus. Delete the filter and this
    // fails, which is the point — the roadmap's 32 and the number this test computes must agree.
    const decl = decls.get("SpatialNode.elevationUnit");
    expect(decl, "SpatialNode.elevationUnit is no longer declared — re-derive before trusting this")
      .toBeTruthy();
    expect(readersOf("elevationUnit", decl!),
      "something now reads elevationUnit — if it is this audit file, the corpus filter has been "
      + "removed and the population is drifting with prose rather than with product usage")
      .toEqual([]);
  });

  it("the common field names are unusable as evidence, and that is the blocker", () => {
    // Not a defect list — a statement about the METHOD. Each of these is referenced so widely that
    // declaring one guarantees a "read" verdict regardless of what the product does with it.
    for (const name of ["name", "key", "id", "title", "status", "count"]) {
      const n = files.filter((f) => tokens.get(f)!.has(name)).length;
      expect(n, `'${name}' should be referenced in enough files to be evidence-free`)
        .toBeGreaterThan(100);
    }
  });
});
