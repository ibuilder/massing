import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * An accessor threaded through a seam must not be collapsed to a value on arrival.
 *
 * R39-DECOMP-VIEWER moves code out of `app.ts` by handing it explicit parameters. Mutable state
 * (`selectedGuid`, `lastPoint`) crosses as a **function**, because `app.ts` holds it as a `let` and a
 * value copy would freeze whatever it held when the panel was built. `tsc` cannot see the difference
 * — that is written down in `qaSection.ts` and in `projectPanel.test.ts`.
 *
 * **It happened anyway, and the accessor was not the part that failed.** `qaSection.ts` opened with
 * `const selectedGuid = d.selectedGuid();` — one call, at panel-build time — directly beneath a
 * docstring explaining why that class of bug is impossible by construction. The panel is built at app
 * init, before anything is selected, so the captured value was `null` for the life of the session:
 *
 *   - "🕸 Related elements (model graph)" answered *"select an element in 3D first"* no matter what
 *     was selected.
 *   - the layer-stack "＋ override (selected element)" button did the same.
 *
 * Two dead tools on main, under a comment saying they could not be. Threading the accessor correctly
 * across the seam is only half the contract; the other half is not undoing it on the first line.
 *
 * So the check is on the SHAPE, not on one name: `const x = d.x()` at any point in a tools module is
 * the collapse, whatever `x` is called. A genuine one-shot read is still available as `d.x()` inline
 * at the point of use, which is what the fix does.
 */

const DIR = resolve(process.cwd(), "src/viewer/tools");

/** `const foo = d.foo();` / `const foo = deps.foo();` — the accessor-collapse shape. */
const COLLAPSE = /\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*(?:d|deps)\.\1\s*\(\s*\)\s*;/g;

const files = readdirSync(DIR).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"));

/**
 * Strip comments before matching. Without this the gate reads its own subject matter: a module that
 * *documents* the collapse — quoting the `qaSection.ts` line that caused it — is flagged for the bug
 * it is warning against. `modelStatePanels.ts` tripped exactly that on its first run, and the fix is
 * not to reword the comment; a check that punishes explaining a defect teaches people to stop
 * explaining defects.
 *
 * This is the second gate in this repo to need it (`test_lock_advisories.py` reads a workflow step
 * whose comment says "do not add continue-on-error"). The general rule: **a gate that greps source
 * must strip comments, or its own documentation becomes a finding.**
 */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
}

describe("tools sections do not collapse an accessor dependency", () => {
  it("found the tools modules — else this passes by measuring nothing", () => {
    // The vacuity guard. An empty file list reports zero collapses and looks like total compliance.
    expect(files.length, "no tools modules found — the path is wrong, not the code").toBeGreaterThan(3);
  });

  it("never assigns d.x() to a const named x", () => {
    const hits: string[] = [];
    for (const f of files) {
      const src = code(readFileSync(resolve(DIR, f), "utf8"));
      for (const m of src.matchAll(COLLAPSE)) hits.push(`${f}: const ${m[1]} = d.${m[1]}()`);
    }
    expect(hits,
      "an accessor was collapsed to a value at build time — it will freeze at whatever it held then, "
      + "which for a selection is null. Call it at the point of use instead.")
      .toEqual([]);
  });

  it("still recognises the pattern it is looking for — the matcher is not dead", () => {
    // The paired control. A regex that matches nothing passes the assertion above against any code
    // at all, which is indistinguishable from the rule being followed.
    const sample = "  const selectedGuid = d.selectedGuid();\n  const other = d.other();";
    expect([...sample.matchAll(COLLAPSE)].map((m) => m[1])).toEqual(["selectedGuid", "other"]);
  });

  it("does not flag the collapse when it appears in a COMMENT", () => {
    // The paired control for `code()`. Documenting the defect must stay possible — and the strip
    // must not be so eager that it also removes real code on the same line.
    const commented = "/** was `const selectedGuid = d.selectedGuid();` */\n"
      + "// const lastPoint = d.lastPoint();\n"
      + "const real = d.real();   // this one is code and must still be caught";
    expect([...code(commented).matchAll(COLLAPSE)].map((m) => m[1])).toEqual(["real"]);
  });

  it("does not flag a legitimate inline read", () => {
    // `const guid = selectedGuid();` inside a handler is the CORRECT shape and must not trip this.
    const ok = "const guid = selectedGuid();\nconst p = d.lastPoint();\nconst renamed = d.selectedGuid();";
    expect([...ok.matchAll(COLLAPSE)].map((m) => m[1])).toEqual([]);
  });
});
