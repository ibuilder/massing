import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Does each API-client method's doc comment describe THAT method?
 *
 * ## The defect this was written from
 *
 * SCALE-SEAM moved route groups out of `client.ts` one at a time, and along the way the pairing
 * between a comment and its method came apart. Not once — **thirteen methods** were documented as
 * something they were not, in a rotation:
 *
 *     proformaLive   carried importXer's comment    ("Import a Primavera P6 export…")
 *     importXer      carried modulesGraph's         ("The module-relations graph…")
 *     scheduleCpm    carried proformaLive's         ("PROFORMA-LIVE: takeoff-priced cost…")
 *     evm            carried resourceLoading's      ("Cost-loaded resource histogram…")
 *     permitCities   carried a schedule alert's     ("Predictive schedule alerts…")
 *
 * Every one of those reads as authoritative. **A wrong docstring is worse than none**: it is the
 * thing a caller trusts instead of reading the route, and these are the methods every screen calls.
 * `carbonComplianceReport` claimed to run a Monte Carlo over the CPM network.
 *
 * ## How it checks, and what that costs
 *
 * A comment should share at least one substantial word with the method it sits above — its name, or
 * the route and types in its first few lines. That is a crude rule and deliberately so: anything
 * cleverer would need to understand the prose, and this only has to catch a comment that belongs to
 * a *different* method, which shares nothing with this one by construction.
 *
 * **It has exactly two false positives, and they are frozen below rather than silenced.** Both are
 * comments that describe their method correctly using a compound identifier the rule cannot see
 * through. The set may only ever shrink: a new entry means someone is adding a comment this check
 * cannot read, which is worth a moment's thought even when the comment is fine.
 */

const API = resolve(process.cwd(), "src/api");

/**
 * Comments that ARE correct and that the rule cannot see. Frozen, may only shrink.
 *
 * `addCurtainWall` — "author an IfcCurtainWall (mullions + transoms + glazing panels)". Correct; the
 * shared noun is inside `IfcCurtainWall`, one token to this rule.
 * `queryElements` — "power selection via the IfcOpenShell selector DSL". Correct; it describes the
 * selector grammar rather than repeating the route word.
 */
const KNOWN_UNREADABLE = new Set(["addCurtainWall", "queryElements"]);

const STOP = new Set(
  ("the a an and or of to for by with per from into on in is are be as it its this that one two each"
    + " every all any not no non vs at over under after before").split(" "),
);

interface Doc { file: string; line: number; method: string; comment: string }

/** Every `/** … *\/` that sits directly above a method, with the method it documents. */
function docs(): Doc[] {
  const out: Doc[] = [];
  for (const f of readdirSync(API).filter((n) => n.endsWith(".ts"))) {
    if (f.endsWith(".test.ts") || f === "schema.d.ts") continue;
    const lines = readFileSync(join(API, f), "utf8").split("\n");
    for (let i = 0; i < lines.length; i++) {
      const m = /^\s*\/\*\* (.+?)(?:\*\/)?\s*$/.exec(lines[i] ?? "");
      if (!m?.[1]) continue;
      let j = i + 1;
      while (j < lines.length && (lines[j] ?? "").trim().startsWith("*")) j++;
      const sig = /^\s*(?:async )?([a-zA-Z_][A-Za-z0-9_]*)\s*\(/.exec(lines[j] ?? "");
      if (!sig?.[1]) continue;
      out.push({ file: f, line: i + 1, method: sig[1], comment: m[1] });
    }
  }
  return out;
}

/** The method's own text: its name plus the first few lines of its body (route + types). */
function context(d: Doc): string {
  const lines = readFileSync(join(API, d.file), "utf8").split("\n");
  return `${d.method}\n${lines.slice(d.line, d.line + 14).join("\n")}`.toLowerCase();
}

const DOCS = docs();

describe("API client doc comments describe the method they sit above", () => {
  it("found a plausible number of documented methods — else this is vacuous", () => {
    expect(DOCS.length, `only ${DOCS.length} doc/method pairs parsed`).toBeGreaterThan(200);
  });

  it("every comment shares a substantial word with its method", () => {
    const wrong: string[] = [];
    for (const d of DOCS) {
      if (KNOWN_UNREADABLE.has(d.method)) continue;
      const words = (d.comment.toLowerCase().match(/[a-z]{4,}/g) ?? []).filter((w) => !STOP.has(w));
      if (!words.length) continue;
      const ctx = context(d);
      if (!words.some((w) => ctx.includes(w.slice(0, 6)))) {
        wrong.push(`${d.file}:${d.line} ${d.method}() is documented as "${d.comment.slice(0, 64)}…"`);
      }
    }
    expect(wrong,
      "a doc comment that shares nothing with its method is usually a NEIGHBOUR's comment, left "
      + "behind when the method moved. Thirteen of these existed at once; a wrong docstring is worse "
      + "than no docstring, because it is what a caller trusts instead of reading the route.")
      .toEqual([]);
  });

  // The exemptions are a ratchet, not a dustbin: each names a comment that is CORRECT and merely
  // unreadable to the rule. Growing the set is how a real defect would get waved through.
  it("the frozen exemptions still exist, and there are still only two", () => {
    expect(KNOWN_UNREADABLE.size).toBeLessThanOrEqual(2);
    const names = new Set(DOCS.map((d) => d.method));
    for (const k of KNOWN_UNREADABLE) {
      expect(names.has(k), `${k} no longer has a doc comment — drop it from the exemption set`).toBe(true);
    }
  });
});
