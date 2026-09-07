/**
 * CSS-VAR-VOID — does every `var(--x)` name a custom property something defines?
 *
 * The sibling of `gridAreas.ts`, and the same defect class: CSS naming something that does not
 * exist, silently. Found by running that gate's own scanner over the palette and asking the
 * question in the other direction.
 *
 * **A `var()` that resolves to nothing is not "the property is skipped".** It makes the declaration
 * *invalid at computed-value time*, which means the property takes its **unset** value — inherited
 * for an inherited property, initial for everything else. So the damage depends on the PROPERTY,
 * not on the token, and that is the whole reason this needs a list rather than a rename:
 *
 * | property                    | unset value        | measured effect of a void var           |
 * |-----------------------------|--------------------|------------------------------------------|
 * | `border: 1px solid var(…)`  | initial            | `border-style: none; width: 0px` — GONE  |
 * | `background: var(…)`        | initial            | `rgba(0,0,0,0)` — no background          |
 * | `stroke="var(…)"` (SVG)     | inherited          | `none` — the shape is INVISIBLE          |
 * | `color: var(…)`             | inherited          | the ancestor's colour — often harmless   |
 *
 * The last row is why this gate reports rather than assumes: three `var(--fg)` colour sites landed
 * on exactly the value they wanted, by inheritance, while a fourth — `--fg` as an SVG `stroke` on a
 * `fill="none"` rect — made a chart's baseline marker disappear entirely. **Same token, opposite
 * severity, decided by the property.**
 *
 * **A fallback is not reported, and that is a statement about THIS GATE, not about CSS.**
 * `var(--x, #ccc)` carries a fallback, so the token's absence is not what breaks it and the gate
 * stays quiet. It does **not** follow that the declaration is valid: if the substituted value is
 * wrong for the property, the declaration is still invalid at computed-value time. Measured —
 * `border: 1px solid var(--nope, #3a3f47)` computes `solid 1px`, while
 * `border: 1px solid var(--nope, notacolor)` computes `none 0px`. Checking that a fallback is
 * *usable by its property* needs a browser, and this gate does not do it. (Seven tokens here exist
 * only in fallback form.)
 *
 * **Scope is CSS *and* TypeScript, and that is load-bearing.** A CSS-only sweep is a predicate
 * deciding what to look at: `--err` is defined in `style.css` and referenced only from
 * `accountUI.ts`, so a CSS-only "unused token" pass would have called it dead and invited deleting
 * a live one — while 13 of the 22 void sites found here live in `.ts` files, invisible to it.
 */
import { scanDeclarations } from "./gridAreas";

/**
 * Drop the lines that are documentation, so a doc example is not read as a usage.
 *
 * **This gate failed CI by flagging its own docstring** — the table above writes
 * `color: var(--fg)` as prose, and a scan of raw text counts it as a reference to a token nothing
 * defines. It passed *locally* first, which is the more interesting half: `git ls-files` lists only
 * TRACKED files, and when the test first ran these two files were not yet `git add`ed, **so the
 * population excluded the one file that would have failed it.**
 *
 * **The first fix was a character-level comment stripper, and it was worse.** It tracked `'`/`"`
 * strings, and the regex literal `SET_VIA_JS` below contains the character class `["']` — so the
 * lone `'` opened a "string" that ran on until the next apostrophe, several lines away, hiding a
 * real `//` comment inside it. A naive tokenizer over 582 TypeScript files can mis-classify in
 * *either* direction, and the fail-open one — swallowing a live reference — is silent.
 *
 * So: no tokenizer. A line whose first non-space characters are `//` or `*` is documentation; every
 * other line is scanned exactly as written. Nothing that ships is written on such a line.
 */
export function withoutCommentLines(text: string): string {
  return text
    .split("\n")
    .map((line) => (/^\s*(\/\/|\*|\/\*)/.test(line) ? "" : line))
    .join("\n");
}

/** A test file's fixtures are not shipped styles — see `varRefs`. */
const isTest = (file: string) => /\.test\.[cm]?tsx?$/.test(file);

/** Source as the scanners should see it: TypeScript with its comments removed. */
const readable = (s: { file: string; text: string }) =>
  s.file.endsWith(".ts") ? withoutCommentLines(s.text) : s.text;

/** A `var()` reference that supplies no fallback, so the token must exist. */
export interface VarUse {
  name: string;
  file: string;
}

/** `var(--name` optionally followed by a comma — the comma means a fallback, so the token's
 *  absence cannot be what breaks it. Whether the fallback SUITS the property is not checked here. */
const VAR_REF = /var\(\s*(--[-\w]+)\s*(,)?/g;
/** `--name:` at the top of a declaration — only meaningful in CSS, which is why sources differ. */
const SET_VIA_JS = /setProperty\(\s*["'](--[-\w]+)["']/g;

/** Custom properties a stylesheet declares, plus any set at runtime through `setProperty`. */
export function definedVars(sources: { file: string; text: string }[]): Set<string> {
  const out = new Set<string>();
  for (const s of sources) {
    if (s.file.endsWith(".css")) {
      for (const d of scanDeclarations(s.text)) if (d.prop.startsWith("--")) out.add(d.prop);
    }
    for (const m of readable(s).matchAll(SET_VIA_JS)) out.add(m[1] as string);
  }
  return out;
}

/** Every `var()` reference, split by whether it carries a fallback. */
export function varRefs(sources: { file: string; text: string }[]): { needed: VarUse[]; withFallback: Set<string> } {
  const needed: VarUse[] = [];
  const withFallback = new Set<string>();
  for (const s of sources) {
    // A test file's `var(--nope)` is a FIXTURE, not a style the product ships, so it cannot be a
    // defect — but it is still a genuine reference, which is why `unreferencedVars` below counts it
    // and this does not. The asymmetry is deliberate: a token used only by a test is not dead.
    for (const m of readable(s).matchAll(VAR_REF)) {
      const name = m[1] as string;
      if (m[2]) withFallback.add(name);
      else if (!isTest(s.file)) needed.push({ name, file: s.file });
    }
  }
  return { needed, withFallback };
}

/**
 * The judgement, separate from the extraction so it can be mutated on its own — the lesson
 * `test_unique_read_guard` paid for, and `gridAreas` re-learned when its own first scanner reported
 * a clean tree because it had matched nothing.
 */
export function voidVars(sources: { file: string; text: string }[]): VarUse[] {
  const defined = definedVars(sources);
  return varRefs(sources).needed.filter((u) => !defined.has(u.name));
}

/** Tokens defined and referenced by nothing at all — the other direction. */
export function unreferencedVars(sources: { file: string; text: string }[]): string[] {
  const defined = definedVars(sources);
  const seen = new Set<string>();
  for (const s of sources) for (const m of readable(s).matchAll(VAR_REF)) seen.add(m[1] as string);
  return [...defined].filter((d) => !seen.has(d)).sort();
}
