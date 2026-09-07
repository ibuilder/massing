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
 * **A fallback makes it safe**, so `var(--x, #ccc)` is never reported: the fallback is what renders,
 * which is a deliberate and widely used pattern here (7 tokens exist only in that form).
 *
 * **Scope is CSS *and* TypeScript, and that is load-bearing.** A CSS-only sweep is a predicate
 * deciding what to look at: `--err` is defined in `style.css` and referenced only from
 * `accountUI.ts`, so a CSS-only "unused token" pass would have called it dead and invited deleting
 * a live one — while 13 of the 22 void sites found here live in `.ts` files, invisible to it.
 */
import { scanDeclarations } from "./gridAreas";

/** A `var()` reference that supplies no fallback, so the token must exist. */
export interface VarUse {
  name: string;
  file: string;
}

/** `var(--name` optionally followed by a comma — the comma is the fallback, and makes it safe. */
const VAR_REF = /var\(\s*(--[-\w]+)\s*(,)?/g;
/** `--name:` at the top of a declaration — only meaningful in CSS, which is why sources differ. */
const SET_VIA_JS = /setProperty\(\s*["'](--[-\w]+)["']/g;

/** Custom properties a stylesheet declares, plus any set at runtime through `setProperty`. */
export function definedVars(sources: { file: string; text: string }[]): Set<string> {
  const out = new Set<string>();
  for (const { file, text } of sources) {
    if (file.endsWith(".css")) {
      for (const d of scanDeclarations(text)) if (d.prop.startsWith("--")) out.add(d.prop);
    }
    for (const m of text.matchAll(SET_VIA_JS)) out.add(m[1] as string);
  }
  return out;
}

/** Every `var()` reference, split by whether it carries a fallback. */
export function varRefs(sources: { file: string; text: string }[]): { needed: VarUse[]; withFallback: Set<string> } {
  const needed: VarUse[] = [];
  const withFallback = new Set<string>();
  for (const { file, text } of sources) {
    for (const m of text.matchAll(VAR_REF)) {
      const name = m[1] as string;
      if (m[2]) withFallback.add(name);
      else needed.push({ name, file });
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
  for (const { text } of sources) for (const m of text.matchAll(VAR_REF)) seen.add(m[1] as string);
  return [...defined].filter((d) => !seen.has(d)).sort();
}
