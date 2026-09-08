import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * SKYLIGHT — a button that is BUILT is not a button a user can press.
 *
 * `R39-DECOMP-VIEWER` moved groups of viewer tools out of `app.ts` into section modules. Each
 * returns its buttons through a named interface, and `envelopeSection.ts`'s own comment says why:
 * *"named so re-ordering cannot silently re-map them"*. That protects the ORDER. Nothing protected
 * the last step — a caller has to take each button and then append it to a container, and a button
 * that is constructed, returned, destructured and never appended is invisible with every typecheck
 * green.
 *
 * That is not hypothetical here. `envelopeSection.ts`'s docstring records the annotation group
 * shipping exactly this way once: *"the same silent-inert failure `qaSection.ts` shipped"*. A tool
 * whose handler is perfect and whose element is in no DOM tree behaves identically to one that was
 * never written, and no existing check could tell them apart — `tsc` is satisfied by the
 * destructure, and the button's own unit test is satisfied by calling its handler.
 *
 * ## The gate was real and its SCOPE was the fiction (widened 2026-09-08, MODEL-SETUP)
 *
 * The first draft of this file claimed to be *"derived from the interfaces rather than from a
 * list"* one line after `for (const file of ["envelopeSection.ts", "fabricationSection.ts",
 * "mepSection.ts"])`. Three modules out of the whole `tools/` directory, hardcoded. And it read
 * appends out of **`app.ts` alone**, so the eight buttons appended in `qaSection.ts` — the two
 * `repairPanel.ts` controls, `sharedParamsPanel.ts`, `projectModelsPanel.ts`,
 * `modelReviewPanel.ts`, and the three `projectSetupPanel.ts` ones this note ships with — sat
 * entirely outside the check built for exactly their failure mode.
 *
 * Both halves are now derived: every non-test module under `tools/` is a candidate, and appends are
 * read from every non-test module under `viewer/`, not from one file. **Widening found no live
 * defect** — all eight were already appended — which is the outcome worth recording, because a
 * scope gap that happens to contain nothing today is indistinguishable from a check that works,
 * right up until it isn't.
 *
 * ## Two shapes, because a section module has two ways to hand a button over
 *
 * 1. **`export interface *Buttons`** — the section returns a record and the caller destructures it.
 *    Every declared field must be named by a caller AND passed to an `append`.
 * 2. **`export function <name>Button()`** — the panel modules export one builder per button, called
 *    inline inside an `appendChild(...)`. The first draft could not see this shape at all; it is
 *    now the larger of the two populations.
 *
 * A predicate that decides what to LOOK at is more dangerous than one that decides what to report,
 * so the derivation is proved rather than trusted: `finds the population` floors both counts, and
 * `detects a button that is built and never appended` mutates a synthetic source to check the
 * append-scan actually reports an unwired button instead of vacuously passing.
 */
const REPO = resolve(__dirname, "../../../../..");
const VIEWER = resolve(REPO, "apps/web/src/viewer");
const TOOLS = join(VIEWER, "tools");

/** Every non-test `.ts` under a directory, recursively. */
function sources(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...sources(p));
    else if (name.endsWith(".ts") && !name.endsWith(".test.ts") && !name.endsWith(".d.ts")) out.push(p);
  }
  return out;
}

/** Every `append(...)` / `appendChild(...)` argument list in a source, concatenated. */
function appendArgs(src: string): string {
  return [...src.matchAll(/\.append(?:Child)?\(([^;]*?)\)/g)].map((m) => m[1]!).join(",");
}

// The whole viewer tree is the consumer set. `app.ts` was the only file read before, which is why
// everything wired from `qaSection.ts` was invisible — the button and the append do not have to
// live in the file the section was extracted from.
//
// **A module is never its own consumer.** Widening the scan from `app.ts` to the whole tree would
// otherwise have WEAKENED the check it was meant to strengthen: every declared field name appears in
// its own module (that is where the record is built), and every builder name appears in its own
// `export function` line, so "somebody names it" would be satisfied by the definition itself. Each
// question is therefore asked against the tree MINUS the file that declares it — which is what
// "wired" meant when only `app.ts` was read, restated so it survives the widening.
const CONSUMERS = new Map(sources(VIEWER).map((p) => [p, readFileSync(p, "utf8")] as const));
const elsewhere = (declaredIn: string) =>
  [...CONSUMERS].filter(([p]) => p !== declaredIn).map(([, src]) => src);
const namedOutside = (declaredIn: string) => elsewhere(declaredIn).join("\n");
const appendedOutside = (declaredIn: string) => elsewhere(declaredIn).map(appendArgs).join(",");

const TOOL_MODULES = sources(TOOLS).map((p) => [p.slice(TOOLS.length + 1), p, readFileSync(p, "utf8")] as const);

/** `{ "<file> <Interface>" -> declared button field names }` for every module exporting one. */
function declaredButtonSets(): Map<string, { path: string; fields: string[] }> {
  const out = new Map<string, { path: string; fields: string[] }>();
  for (const [file, path, src] of TOOL_MODULES) {
    const m = src.match(/export interface (\w*Buttons) \{([\s\S]*?)\n\}/);
    if (!m) continue;
    out.set(`${file} ${m[1]}`, { path, fields: [...m[2]!.matchAll(/^\s*(\w+)\s*:/gm)].map((f) => f[1]!) });
  }
  return out;
}

/** `{ "<file>" -> exported `*Button()` builder names }` for every module exporting one. */
function exportedButtonBuilders(): Map<string, { path: string; names: string[] }> {
  const out = new Map<string, { path: string; names: string[] }>();
  for (const [file, path, src] of TOOL_MODULES) {
    const names = [...src.matchAll(/^export function (\w+Button)\(/gm)].map((m) => m[1]!);
    if (names.length) out.set(file, { path, names });
  }
  return out;
}

describe("every button a section module returns is wired into the app", () => {
  const sets = declaredButtonSets();
  const builders = exportedButtonBuilders();

  it("finds the population", () => {
    // A control on the derivation itself: if either regex stops matching, every assertion below
    // vacuously passes over an empty map. This is the same failure the file is about — a check
    // that has quietly stopped checking looks exactly like a check that has nothing to report.
    //
    // Floors rather than exact counts, deliberately: the failure guarded against is the derivation
    // COLLAPSING (a renamed convention, a moved directory, a regex that no longer matches), and a
    // floor catches a module disappearing just as well while letting a new button land without
    // editing its own gate. The first draft's hardcoded list is what this file is a correction of.
    expect(sets.size, "no *Buttons interfaces found — the derivation broke").toBeGreaterThanOrEqual(3);
    expect([...builders.values()].flatMap((b) => b.names).length,
      "no exported *Button() builders found — the derivation broke").toBeGreaterThanOrEqual(8);
    expect(TOOL_MODULES.length, "no tool modules found").toBeGreaterThanOrEqual(10);
    expect(CONSUMERS.size, "no consumer sources found").toBeGreaterThanOrEqual(20);
    for (const [name, { fields }] of sets) {
      expect(fields.length, `${name} parsed with no fields`).toBeGreaterThan(0);
    }
  });

  it("detects a button that is built and never appended", () => {
    // Deriving the population is half of it; the other half is proving the derivation REACHES a
    // defect. `appendArgs` is run against a source holding one wired and one unwired button, and
    // must separate them — otherwise every clean report above is a report about nothing.
    const synthetic = `
      const wired = someButton({ a: 1 });
      b.appendChild(wired);
      const orphan = otherButton({ a: 1 });
    `;
    const args = appendArgs(synthetic);
    expect(args, "the append scan did not see a button it was handed").toMatch(/\bwired\b/);
    expect(args, "the append scan reported a button that is in no append").not.toMatch(/\borphan\b/);
  });

  for (const [name, { path, fields }] of sets) {
    it(`${name}: every button is destructured and appended`, () => {
      const named = namedOutside(path), appended = appendedOutside(path);
      const notNamed = fields.filter((f) => !new RegExp(`\\b${f}\\b`).test(named));
      expect(notNamed, `${name} declares these, but no OTHER viewer source ever names them: `
        + `${notNamed.join(", ")}`).toEqual([]);

      const notAppended = fields.filter((f) => !new RegExp(`\\b${f}\\b`).test(appended));
      expect(notAppended, `${name} declares these and they are destructured, but they are `
        + `passed to no append() — built, returned, and in no DOM tree, which is indistinguishable `
        + `from not existing: ${notAppended.join(", ")}`).toEqual([]);
    });
  }

  for (const [file, { path, names }] of builders) {
    it(`${file}: every exported *Button() builder is called inside an append`, () => {
      const appended = appendedOutside(path);
      const notAppended = names.filter((n) => !new RegExp(`\\b${n}\\b`).test(appended));
      expect(notAppended, `${file} exports these builders, but their result reaches no append() — `
        + `a button nobody puts in a DOM tree is indistinguishable from one that was never `
        + `written: ${notAppended.join(", ")}`).toEqual([]);
    });
  }
});
