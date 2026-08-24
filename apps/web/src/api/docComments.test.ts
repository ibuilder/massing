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
 * ## Why this is scoped to `api/` and not the whole tree
 *
 * The same scan was run over all of `apps/web/src` and found eight more. **Only one was safe to act
 * on.** The rest are two shapes this gate would get wrong outside this directory:
 *
 *   * a **module header placed after the imports** — `portal/panels/budget.ts` has one, and a blanket
 *     cleanup would have deleted the file's own documentation;
 *   * a **context block above a related declaration** — `viewer/app.ts` and `main.ts` both carry a
 *     RAIL-SPLIT narrative above the thing it motivates, which is deliberate prose, not residue.
 *
 * In `api/` neither shape occurs: headers sit at line 1 above imports, and the methods are a flat
 * list with one comment each. **A gate's scope is part of its claim** — widening this one would need
 * a rule that can tell a header and a narrative from a leftover, and that rule does not exist yet.
 * The one safe case outside `api/` was fixed by hand: `portal.ts` held the comment for `panelCtx()`,
 * which had none.
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

  /**
   * No doc comment sits directly above ANOTHER doc comment.
   *
   * That shape means the first one's declaration is gone — the same extraction that shifted comments
   * onto their neighbours also left comments behind entirely, and a stranded comment attaches itself
   * visually to whatever follows. **23 of these existed**, every one describing something other than
   * the declaration under it: `TOPIC-BOARD` above `modelConstraints`, `RISK-BOARD` above `devBudget`,
   * the R26 room spine above a `StripStatus` union.
   *
   * Deleting is the safe repair and moving is the better one, so both were used: two had a verifiable
   * owner (`setToken`, whose comment was separated from it when a getter was inserted between them,
   * and `riskBoard`, which had no comment of its own) and were moved; the rest described features with
   * no method here to own them and were removed. **A comment about a declaration that is not there is
   * not documentation — it is a false statement positioned where the next reader will trust it.**
   */
  it("no doc comment is stranded above another doc comment", () => {
    const stranded: string[] = [];
    for (const f of readdirSync(API).filter((n) => n.endsWith(".ts"))) {
      if (f.endsWith(".test.ts") || f === "schema.d.ts") continue;
      const lines = readFileSync(join(API, f), "utf8").split(String.fromCharCode(10));
      for (let i = 0; i < lines.length; i++) {
        const l = lines[i] ?? "";
        const closes = l.trimEnd().endsWith("*/") && (l.trim().startsWith("/**") || l.trim().startsWith("*"));
        if (closes && (lines[i + 1] ?? "").trim().startsWith("/**")) {
          let j = i;
          while (j > 0 && !(lines[j] ?? "").trim().startsWith("/**")) j--;
          stranded.push(`${f}:${j + 1} ${(lines[j] ?? "").trim().slice(0, 60)}…`);
        }
      }
    }
    expect(stranded,
      "a comment directly above another comment has lost its declaration. Move it to whatever it "
      + "describes, or delete it — left alone it will be read as documenting the next thing down.")
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
