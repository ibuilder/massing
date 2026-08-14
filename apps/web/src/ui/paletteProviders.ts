/**
 * R24-CMDK-VERBS — the four sections the palette declared and never filled.
 *
 * `R24-CMDK-GROUPS` (v0.3.780) gave the palette its sections, and `GROUP_ORDER` has named
 * **Do · Records · Elements · Reports · Modules · Go to** ever since. Only three of those six could
 * ever contain anything: `main.ts` registered workspaces, six hardcoded actions, and 130-odd modules.
 * **Elements and Reports were headings with no possible contents** — declared, ordered, and
 * unreachable, which is the same failure `paint()` had before the grouping was wired, one layer up.
 *
 * Everything here is a pure function over injected data, with no import of the viewer, the API client
 * or the DOM. That is not tidiness: it is what lets the sections be tested without a toolbar, and it
 * is why `verbCommands` takes the tool table as an argument instead of importing
 * `viewer/toolbarLayout` — `ui/` importing from `viewer/` would invert the layering for a list of
 * strings.
 *
 * ## The authoring verbs dispatch to the real button
 *
 * `verbCommands` does **not** reimplement Move, Copy, Rotate or Add door. It finds the toolbar button
 * whose `title` matches and clicks it. Two reasons, and the second is the one that matters:
 *
 * * A second implementation of "Move" is a second thing to keep correct, and the palette copy would
 *   be the one nobody notices has drifted.
 * * `viewer/toolbarLayout.ts` already keys the whole tool table on the button's `title` **verbatim**,
 *   with a gate that fails when an installed button is not in the table. Reusing that key means the
 *   palette inherits the gate: a retitled button cannot silently lose its palette row, because it
 *   cannot silently lose its toolbar row either.
 *
 * A verb whose button is not currently installed is **omitted, not disabled**. The toolbar is only
 * built once a model is loaded, so before then every authoring verb would be a row that looks
 * available and does nothing — and a palette that lies about what it can do is worse than a short one.
 *
 * ## Elements is a GlobalId lookup, and deliberately not a name search
 *
 * The non-negotiable is that elements are addressed by IFC GlobalId, never by a transient viewer id,
 * so the palette's element row is the GUID itself. There is no server-side element *text* search to
 * call — `/elements` filters by class and storey — and faking one by pulling every element down to
 * filter in the browser would be both slow and a quiet violation of "never parse the model in the
 * browser". So the section answers the two questions that can be answered exactly: **this GlobalId**,
 * and **this IFC class**.
 */
import type { Command } from "./palette";
import { shortGuid } from "./elementCard";

/**
 * The part of a toolbar tool this module needs — structural, so the tool table stays in `viewer/`.
 * `title` is the identity (it is the DOM `title` attribute); `label` is the short verb shown to a user.
 */
export interface VerbSpec {
  title: string;
  label: string;
  group: string;
}

/**
 * An IFC GlobalId: 22 characters of IFC's own base-64 alphabet (`0-9 A-Z a-z _ $`).
 *
 * Anchored and exact-length on purpose. A loose test would match the leading 22 characters of any
 * long word and offer an element row for a query that is plainly a search phrase — and the row would
 * then 404 against a GUID the user never typed.
 */
const GUID_RE = /^[0-9A-Za-z_$]{22}$/;

export function isGlobalId(q: string): boolean {
  return GUID_RE.test(q);
}

/** An IFC class name as typed in the palette — `IfcWall`, `ifcdoor`. Case-insensitive, letters only. */
const IFC_CLASS_RE = /^ifc[a-z]{3,40}$/i;

export function isIfcClass(q: string): boolean {
  return IFC_CLASS_RE.test(q);
}

/** `ifcwall` → `IfcWall`. The server matches the canonical spelling; users type whatever they like. */
export function canonicalIfcClass(q: string): string {
  return "Ifc" + q.slice(3).charAt(0).toUpperCase() + q.slice(4).toLowerCase();
}

/**
 * Authoring (and measuring, and analysing) verbs as **Do** rows, one per installed toolbar button.
 *
 * `groups` selects which tool groups become palette verbs. `look` is excluded by the caller: those
 * are view states you toggle while looking at the model, and reaching them through a modal overlay
 * that closes itself is a worse interaction than the button already sitting on screen.
 */
export function verbCommands(
  tools: readonly VerbSpec[],
  opts: {
    groups: readonly string[];
    /** Is this button installed right now? A verb that is not installed is not offered. */
    present: (title: string) => boolean;
    run: (title: string) => void;
  },
): Command[] {
  const out: Command[] = [];
  for (const t of tools) {
    if (!opts.groups.includes(t.group) || !opts.present(t.title)) continue;
    out.push({
      id: "verb:" + t.title,
      label: t.label,
      // The tool's own group, capitalised — "Move · Author" reads as what it is. The palette section
      // is set explicitly below, so the hint is free to carry this instead of being load-bearing.
      hint: t.group.charAt(0).toUpperCase() + t.group.slice(1),
      group: "Do",
      run: () => opts.run(t.title),
    });
  }
  return out;
}

/**
 * The **Elements** section for a query: an exact GlobalId, or an IFC class to list.
 *
 * Returns `[]` for anything else rather than guessing. An element row that cannot resolve is worse
 * than no element row: the section header appears, promises a hit, and the row fails on click.
 */
export function elementCommands(
  q: string,
  opts: {
    openGuid: (guid: string) => void;
    openClass: (ifcClass: string) => void;
  },
): Command[] {
  const t = q.trim();
  if (isGlobalId(t)) {
    return [{
      id: "el:" + t,
      label: "Open element " + shortGuid(t),
      hint: "GlobalId",
      group: "Elements",
      run: () => opts.openGuid(t),
    }];
  }
  if (isIfcClass(t)) {
    const cls = canonicalIfcClass(t);
    return [{
      id: "elcls:" + cls,
      label: "List every " + cls,
      hint: "IFC class",
      group: "Elements",
      run: () => opts.openClass(cls),
    }];
  }
  return [];
}

/**
 * The **Reports** section, from the server's own catalog.
 *
 * Static rows rather than an async provider, because the catalog is one small fetch that does not
 * change during a session — and because static rows go through the palette's ranking and recency,
 * so the two reports you actually run each month rise to the top of the section on their own.
 */
export function reportCommands(
  reports: readonly { id: string; name: string; group: string }[],
  open: (id: string) => void,
): Command[] {
  return reports.map((r) => ({
    id: "rep:" + r.id,
    label: r.name,
    hint: r.group || "Report",
    group: "Reports",
    run: () => open(r.id),
  }));
}

/**
 * The last row: hand the query to the model's plain-English assistant.
 *
 * Its group is deliberately **not** in `GROUP_ORDER`, so it sorts after every known section — and it
 * is passed to the palette as `fallback`, which appends it *after* the per-section cap. A fallback
 * the cap can delete is not a fallback; it would vanish exactly when the query matched a lot of
 * things badly, which is when it is most useful.
 */
export function askFallback(q: string, ask: (q: string) => void): Command {
  return {
    id: "ask:model",
    label: `Ask the model: “${q}”`,
    hint: "Assistant",
    group: "Ask",
    run: () => ask(q),
  };
}
