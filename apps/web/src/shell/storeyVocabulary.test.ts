import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

/**
 * R24-TERMS (diagnosis #17, "three vocabularies collide") — one storey, one word.
 *
 * **Measured before it was fixed, and the clearest instance was a single control disagreeing with
 * itself.** In `portal/panels/budget.ts` the button read "QTO by floor", its own tooltip two lines
 * below read "by storey", and its own table header read "Storey". One feature, three lines, two
 * words for one thing.
 *
 * **This is a consistency fix, not a naming decision**, which is the only reason it was safe to make
 * without asking. `storey` is already canonical everywhere that carries meaning: the API returns a
 * `storey` field per element, QUERY-DSL filters on `storey=L3`, and both rendered table headers say
 * Storey. Two chrome strings were the outliers. Picking a *new* canonical term would have been a
 * decision for the user — the sibling question, ROOM-NAMING, was settled with them on professional
 * terms, and this item deliberately did not follow that path because nothing needed settling.
 *
 * **What is banned is narrow, and the exceptions matter more than the rule.** "Floor" is correct
 * English in this domain and must stay: *gross floor area* is the standard term (and `operations.ts`
 * uses it correctly for EUI), and *floor plan* is what the drawing is called. Only the phrasings that
 * mean "per building storey" are refused — a blanket ban on the word would be a worse error than the
 * inconsistency it replaced, and would have flagged two correct strings.
 *
 * Test files are excluded from the scan. This file quotes the banned phrases in order to explain
 * them, and a gate that reads its own documentation is the shape this repo has now hit five separate
 * times.
 */
const SRC = resolve(__dirname, "..");

/** Phrases that mean "per building storey" and should say storey. */
const BANNED = [/\bby floor\b/i, /\beach floor\b/i, /\bper floor\b/i];

/** Correct uses of "floor" that must keep working — the reason this is not a word ban. */
const ALLOWED_EXAMPLES = ["gross floor area", "floor plan", "floor-to-floor height"];

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { sourceFiles(p, out); continue; }
    if (p.endsWith(".ts") && !p.endsWith(".test.ts") && !p.endsWith(".d.ts")) out.push(p);
  }
  return out;
}

/** Double-quoted string literals — the ones that reach a user. */
function renderedStrings(src: string): string[] {
  return [...src.matchAll(/"([^"\\\n]*(?:\\.[^"\\\n]*)*)"/g)].map((m) => m[1] ?? "");
}

describe("R24-TERMS — a building storey is called a storey", () => {
  const files = sourceFiles(SRC);

  it("scanned real source — otherwise the assertion below is vacuous", () => {
    expect(files.length, "no .ts files found").toBeGreaterThan(100);
    const total = files.reduce((n, f) => n + renderedStrings(readFileSync(f, "utf8")).length, 0);
    expect(total, "no string literals extracted — the matcher is broken").toBeGreaterThan(1000);
  });

  it("no rendered string uses 'floor' to mean a storey", () => {
    const hits: string[] = [];
    for (const f of files) {
      for (const s of renderedStrings(readFileSync(f, "utf8"))) {
        if (BANNED.some((re) => re.test(s))) {
          hits.push(`${f.replace(SRC, "src")}: ${JSON.stringify(s.slice(0, 70))}`);
        }
      }
    }
    expect(hits,
      "say 'storey'. The API returns a `storey` field, QUERY-DSL filters on `storey=`, and the table " +
      "headers already say Storey — these are the chrome strings that disagree with the data model " +
      "underneath them.")
      .toEqual([]);
  });

  it("...and the rule still permits the correct uses of 'floor'", () => {
    // The twin, and the one that keeps this honest. A rule that banned the word outright would
    // satisfy the assertion above and break "gross floor area", which is the standard term.
    for (const ok of ALLOWED_EXAMPLES) {
      expect(BANNED.some((re) => re.test(ok)), `"${ok}" must stay legal`).toBe(false);
    }
  });

  it("...and the rule can actually say no", () => {
    // Proves the matcher is not vacuously passing: the exact strings that were fixed must be caught.
    for (const bad of ["QTO by floor", "gridded over each floor", "cost per floor"]) {
      expect(BANNED.some((re) => re.test(bad)), `"${bad}" should be refused`).toBe(true);
    }
  });
});
