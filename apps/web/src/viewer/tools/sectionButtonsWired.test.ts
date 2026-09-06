import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * SKYLIGHT — a button that is BUILT is not a button a user can press.
 *
 * `R39-DECOMP-VIEWER` moved groups of viewer tools out of `app.ts` into section modules. Each
 * returns its buttons through a named interface, and `envelopeSection.ts`'s own comment says why:
 * *"named so re-ordering cannot silently re-map them"*. That protects the ORDER. Nothing protected
 * the last step — `app.ts` has to destructure each button and then append it to a container, and a
 * button that is constructed, returned, destructured and never appended is invisible with every
 * typecheck green.
 *
 * That is not hypothetical here. `envelopeSection.ts`'s docstring records the annotation group
 * shipping exactly this way once: *"the same silent-inert failure `qaSection.ts` shipped"*. A tool
 * whose handler is perfect and whose element is in no DOM tree behaves identically to one that was
 * never written, and no existing check could tell them apart — `tsc` is satisfied by the
 * destructure, and the button's own unit test is satisfied by calling its handler.
 *
 * So: for every `*Buttons` interface a section module exports, every member must be **destructured
 * from the builder call** and **passed to an `append`** in `app.ts`. Derived from the interfaces
 * rather than from a list, so a button added to a section is covered the day it is added — the
 * failure mode is precisely that somebody adds one and forgets the second half.
 */
const REPO = resolve(__dirname, "../../../../..");
const APP = readFileSync(resolve(REPO, "apps/web/src/viewer/app.ts"), "utf8");
const TOOLS = resolve(REPO, "apps/web/src/viewer/tools");

/** `{ Interface name -> declared button field names }` for every section module that exports one. */
function declaredButtonSets(): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const file of ["envelopeSection.ts", "fabricationSection.ts", "mepSection.ts"]) {
    const src = readFileSync(resolve(TOOLS, file), "utf8");
    const m = src.match(/export interface (\w*Buttons) \{([\s\S]*?)\n\}/);
    if (!m) continue;
    const fields = [...m[2]!.matchAll(/^\s*(\w+)\s*:/gm)].map((f) => f[1]!);
    out.set(`${file} ${m[1]}`, fields);
  }
  return out;
}

/** Every `append(...)` / `appendChild(...)` argument list in `app.ts`, concatenated. */
const APPENDED = [...APP.matchAll(/\.append(?:Child)?\(([^;]*?)\)/g)].map((m) => m[1]!).join(",");

describe("every button a section module returns is wired into app.ts", () => {
  const sets = declaredButtonSets();

  it("finds the section button interfaces to check", () => {
    // A control on the derivation itself: if the regex stops matching, every assertion below
    // vacuously passes over an empty map. This is the same failure the file is about — a check
    // that has quietly stopped checking looks exactly like a check that has nothing to report.
    expect([...sets.keys()].length, "no *Buttons interfaces found — the derivation broke").toBe(3);
    for (const [name, fields] of sets) {
      expect(fields.length, `${name} parsed with no fields`).toBeGreaterThan(0);
    }
  });

  for (const [name, fields] of sets) {
    it(`${name}: every button is destructured and appended`, () => {
      const notDestructured = fields.filter((f) => !new RegExp(`\\b${f}\\b`).test(APP));
      expect(notDestructured, `${name} declares these, but app.ts never names them: `
        + `${notDestructured.join(", ")}`).toEqual([]);

      const notAppended = fields.filter((f) => !new RegExp(`\\b${f}\\b`).test(APPENDED));
      expect(notAppended, `${name} declares these and app.ts destructures them, but they are `
        + `passed to no append() — built, returned, and in no DOM tree, which is indistinguishable `
        + `from not existing: ${notAppended.join(", ")}`).toEqual([]);
    });
  }
});
