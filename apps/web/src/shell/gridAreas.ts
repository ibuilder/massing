/**
 * UX-4 SHELL-GRID — does every `grid-area` name an area that some `grid-template-areas` defines?
 *
 * `#pinned-rail` carried `grid-area: pins` from v0.3.764 (2026-07-28) and **nothing anywhere ever
 * defined a `pins` area**. `#app`'s template is `"topbar" "stage" "statusbar"` in a single column,
 * so the rail was auto-placed into implicit tracks instead. Measured in Chromium at 1440x900 with
 * the rail populated, before the fix:
 *
 *     rows [44px 698.156px 32px 0px 125.844px]   cols [1368px 0px 72px]
 *     #pinned-rail  x=1368 y=774  72x126   <- bottom-RIGHT corner, not a left rail
 *     #stage        1368x698             <- lost 72px of width and 126px of height
 *     #statusbar    y=742                <- detached from the bottom of the window
 *
 * The rail is `hidden` until the user has a favourite or a recent, which is why this survived six
 * weeks: it is invisible on a first run and wrong on every run after.
 *
 * **Why a static check and not a rendered one.** The rendered proof needs a browser, and putting one
 * in CI is a dependency decision that is not ours to make. What is checkable without one is the
 * property that actually failed: a name used and never defined.
 *
 * **What this does NOT check, stated plainly rather than left to be assumed.** It does not know
 * which grid an element belongs to, so an area defined on *some other* grid than the one the element
 * sits in would satisfy it. Closing that needs selector-to-element matching, i.e. a DOM. This is
 * therefore a lower bound on the defect class — it cannot raise a false alarm, and it catches the
 * shape that occurred here (defined nowhere at all).
 *
 * Named grid LINES (`grid-row: foo`, `grid-column: bar / baz`) are a second way to reference a name
 * that may not exist. They are out of scope because this tree uses none — verified, not assumed, and
 * `namedLineUsages()` below re-verifies it on every run so the scope claim cannot quietly go stale.
 */

/** A `grid-area` declaration that names an area, with the line it sits on. */
export interface AreaUse {
  name: string;
  line: number;
}

/** A `grid-area` whose value this parser cannot classify. Reported, never ignored — see `verdict`. */
export interface AreaUnknown {
  value: string;
  line: number;
}

/** CSS-wide keywords and grid keywords that are never an area name. */
const NOT_AN_AREA = new Set(["auto", "none", "inherit", "initial", "unset", "revert", "revert-layer", "span"]);

/**
 * Strip `/* ... *\/` comments, preserving newlines so reported line numbers stay true.
 *
 * Load-bearing: a commented-out `grid-template-areas` would otherwise define an area that no
 * browser has ever seen, which is the fail-open direction — the check would go quiet on exactly the
 * edit most likely to introduce the bug.
 */
export function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
}

const lineOf = (css: string, index: number): number => css.slice(0, index).split("\n").length;

/** Every area name defined by any `grid-template-areas` in `css`. */
export function definedAreas(css: string): Set<string> {
  const src = stripComments(css);
  const out = new Set<string>();
  for (const m of src.matchAll(/grid-template-areas\s*:([^;}]*)/g)) {
    for (const row of (m[1] ?? "").matchAll(/"([^"]*)"|'([^']*)'/g)) {
      for (const tok of (row[1] ?? row[2] ?? "").trim().split(/\s+/)) {
        // A run of dots is a null cell, not a name. So is an empty token from a blank row.
        if (tok && !/^\.+$/.test(tok)) out.add(tok);
      }
    }
  }
  return out;
}

/**
 * Every `grid-area` in `css`, split into the ones that name an area and the ones this parser could
 * not classify. Extraction only — the verdict is `verdict()`, deliberately a separate function so a
 * mutation to the judgement cannot hide behind an assertion that the site was merely *found*.
 */
export function areaUses(css: string): { uses: AreaUse[]; unknown: AreaUnknown[] } {
  const src = stripComments(css);
  const uses: AreaUse[] = [];
  const unknown: AreaUnknown[] = [];
  for (const m of src.matchAll(/(?<![-\w])grid-area\s*:([^;}]*)/g)) {
    const value = (m[1] ?? "").trim();
    const line = lineOf(src, m.index);
    if (/^[A-Za-z_][-\w]*$/.test(value)) {
      // A bare custom-ident. `auto`/`none`/`inherit`/... place nothing and name nothing.
      if (!NOT_AN_AREA.has(value)) uses.push({ name: value, line });
      continue;
    }
    // Line-based placement (`1 / 2 / 3 / 4`, `span 2 / auto`) references no area name. Anything else
    // — a var(), a name this regex does not recognise — is UNKNOWN and reds the build, because a
    // parser that quietly drops what it cannot read is a check that can only report good news.
    if (/^[\d\s/]+$/.test(value) || /^[-\w\s/]*$/.test(value)) continue;
    unknown.push({ value, line });
  }
  return { uses, unknown };
}

/** `grid-row`/`grid-column` values that reference a NAMED line rather than a number. */
export function namedLineUsages(css: string): { value: string; line: number }[] {
  const src = stripComments(css);
  const out: { value: string; line: number }[] = [];
  for (const m of src.matchAll(/(?<![-\w])grid-(?:row|column)(?:-start|-end)?\s*:([^;}]*)/g)) {
    const value = (m[1] ?? "").trim();
    const idents = value.split(/[\s/]+/).filter((t) => /^[A-Za-z_][-\w]*$/.test(t) && !NOT_AN_AREA.has(t));
    if (idents.length) out.push({ value, line: lineOf(src, m.index) });
  }
  return out;
}

export interface GridVerdict {
  /** Used by a `grid-area` and defined by no `grid-template-areas`. The defect. */
  orphans: AreaUse[];
  /** Defined and claimed by nothing — a renamed element, or a track nobody fills. */
  unused: string[];
  /** Values the parser could not classify. Non-empty means the answer is not trustworthy. */
  unknown: AreaUnknown[];
}

/** The judgement, separable from the extraction so it can be mutated on its own. */
export function verdict(css: string): GridVerdict {
  const defined = definedAreas(css);
  const { uses, unknown } = areaUses(css);
  const used = new Set(uses.map((u) => u.name));
  return {
    orphans: uses.filter((u) => !defined.has(u.name)),
    unused: [...defined].filter((d) => !used.has(d)).sort(),
    unknown,
  };
}
