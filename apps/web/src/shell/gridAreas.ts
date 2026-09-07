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

/** One CSS declaration, as the scanner found it. */
export interface Decl {
  /** The property name exactly as written — `grid-area`, or `--grid-area` for a custom property. */
  prop: string;
  value: string;
  line: number;
}

// `(--)?` — an OPTIONAL custom-property prefix. Written `--?` at first, which requires a LEADING
// hyphen and therefore matched only custom properties, rejecting `grid-area` itself: the scanner
// found nothing at all and every "clean" answer it gave was clean because it had looked at nothing.
const IDENT = /^(--)?[A-Za-z_][-\w]*$/;

/**
 * Walk `css` once and yield its declarations, tracking comment and string state as it goes.
 *
 * **This replaced three regexes, and each of them had a distinct bug** — found by review, then
 * reproduced before being believed:
 *
 *  1. `/grid-template-areas\s*:/` also matched the CUSTOM PROPERTY `--grid-template-areas`, so
 *     `:root { --grid-template-areas: "pins" }` DEFINED a phantom `pins` area and the orphan check
 *     went silent. **That is the fail-open direction** — the same shape this whole gate exists to
 *     catch, in the gate itself.
 *  2. Declaration text inside a *string* was read as a declaration, so `content: "grid-area: ghost;"`
 *     invented an orphan that is not there.
 *  3. `/*` and `*\/` inside strings were treated as real comment delimiters, so a `content: "/*"`
 *     anywhere above could erase every live declaration until the next `content: "*\/"`.
 *
 * A property name is only recognised inside a block (`depth > 0`) and only when the text before the
 * colon is a bare identifier — which is what keeps `@media (max-width: 900px)` and selectors out.
 * `--grid-template-areas` is an identifier too, and `prop` keeps the leading dashes precisely so the
 * callers below can reject it by exact match rather than by substring.
 */
export function scanDeclarations(css: string): Decl[] {
  const out: Decl[] = [];
  let i = 0, line = 1, depth = 0, buf = "";
  const n = css.length;

  /** Consume a quoted string starting at `i` (on the quote); returns the index after it. */
  const skipString = (from: number): number => {
    const quote = css[from];
    let j = from + 1;
    while (j < n) {
      const c = css[j];
      if (c === "\\") { if (css[j + 1] === "\n") line++; j += 2; continue; }
      if (c === "\n") { line++; j++; continue; }   // unterminated string: CSS ends it at the newline
      if (c === quote) return j + 1;
      j++;
    }
    return j;
  };

  while (i < n) {
    const c = css[i];

    if (c === "/" && css[i + 1] === "*") {
      i += 2;
      while (i < n && !(css[i] === "*" && css[i + 1] === "/")) { if (css[i] === "\n") line++; i++; }
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") { buf += css.slice(i, (i = skipString(i))); continue; }
    if (c === "\n") { line++; buf += c; i++; continue; }

    if (c === "{") { depth++; buf = ""; i++; continue; }
    if (c === "}") { depth = Math.max(0, depth - 1); buf = ""; i++; continue; }
    if (c === ";") { buf = ""; i++; continue; }

    if (c === ":" && depth > 0 && IDENT.test(buf.trim())) {
      const prop = buf.trim();
      const declLine = line;
      // Collect the value up to `;` or `}`, honouring strings so a `;` inside one does not end it.
      let value = "";
      i++;
      while (i < n) {
        const v = css[i];
        if (v === '"' || v === "'") { value += css.slice(i, (i = skipString(i))); continue; }
        if (v === "/" && css[i + 1] === "*") {
          i += 2;
          while (i < n && !(css[i] === "*" && css[i + 1] === "/")) { if (css[i] === "\n") line++; i++; }
          i += 2;
          continue;
        }
        if (v === ";" || v === "}") break;
        if (v === "\n") line++;
        value += v;
        i++;
      }
      out.push({ prop, value: value.trim(), line: declLine });
      buf = "";
      continue;
    }

    buf += c;
    i++;
  }
  return out;
}

/**
 * Strip `/* ... *\/` comments, preserving newlines so reported line numbers stay true — and NOT
 * treating comment markers inside strings as delimiters, which is bug 3 above.
 *
 * Load-bearing in the other direction too: a commented-out `grid-template-areas` would otherwise
 * define an area no browser has ever seen, silencing the check on exactly the edit most likely to
 * introduce the bug.
 */
export function stripComments(css: string): string {
  let out = "", i = 0;
  const n = css.length;
  while (i < n) {
    const c = css[i];
    if (c === "/" && css[i + 1] === "*") {
      i += 2;
      while (i < n && !(css[i] === "*" && css[i + 1] === "/")) { out += css[i] === "\n" ? "\n" : " "; i++; }
      out += "  ";
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") {
      const quote = c;
      out += c; i++;
      while (i < n) {
        if (css[i] === "\\") { out += css.slice(i, i + 2); i += 2; continue; }
        if (css[i] === "\n" || css[i] === quote) break;
        out += css[i]; i++;
      }
      if (i < n) { out += css[i]; i++; }
      continue;
    }
    out += c; i++;
  }
  return out;
}

/** Every area name defined by any real `grid-template-areas` declaration in `css`. */
export function definedAreas(css: string): Set<string> {
  const out = new Set<string>();
  for (const d of scanDeclarations(css)) {
    // EXACT match. `--grid-template-areas` is a custom property and defines no area; matching it by
    // substring is what made this function report phantom definitions.
    if (d.prop !== "grid-template-areas") continue;
    for (const row of d.value.matchAll(/"([^"]*)"|'([^']*)'/g)) {
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
  const uses: AreaUse[] = [];
  const unknown: AreaUnknown[] = [];
  for (const d of scanDeclarations(css)) {
    if (d.prop !== "grid-area") continue;
    const value = d.value;
    if (/^[A-Za-z_][-\w]*$/.test(value)) {
      if (!NOT_AN_AREA.has(value)) uses.push({ name: value, line: d.line });
      continue;
    }
    // Line-based placement (`1 / 2 / 3 / 4`, `span 2 / auto`) references no area name. Anything else
    // — a var(), a name this parser does not recognise — is UNKNOWN and reds the build, because a
    // parser that quietly drops what it cannot read is a check that can only report good news.
    if (/^[\d\s/]+$/.test(value) || /^[-\w\s/]*$/.test(value)) continue;
    unknown.push({ value, line: d.line });
  }
  return uses.length || unknown.length ? { uses, unknown } : { uses, unknown };
}

/** `grid-row`/`grid-column` values that reference a NAMED line rather than a number. */
export function namedLineUsages(css: string): { value: string; line: number }[] {
  const out: { value: string; line: number }[] = [];
  for (const d of scanDeclarations(css)) {
    if (!/^grid-(row|column)(-start|-end)?$/.test(d.prop)) continue;
    const idents = d.value.split(/[\s/]+/).filter((t) => /^[A-Za-z_][-\w]*$/.test(t) && !NOT_AN_AREA.has(t));
    if (idents.length) out.push({ value: d.value, line: d.line });
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
