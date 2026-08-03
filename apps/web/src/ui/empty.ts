/**
 * Demo-aware "no project" empty states. The GitHub Pages build (`VITE_PAGES`) is **viewer-only** —
 * there's no backend, so the GC portal / drawings / finance can't load records there. Saying "pick a
 * project" is misleading in that build (there are none); instead we explain it's the viewer demo and
 * point at what *does* work (3D samples via Open ▾) + the full app. In the real app (backend present)
 * we give an actionable "create or open a project" hint.
 */
const IS_DEMO = !!import.meta.env.VITE_PAGES;
const DOWNLOAD = "https://massing.build/#download";

/** HTML for a "no project open" panel, tailored to demo vs full app. `tool` names the feature
 *  (e.g. "the GC portal", "drawings") so the copy reads naturally. */
export function noProjectHtml(tool: string): string {
  if (IS_DEMO) {
    return `<div class="empty-state">${tool} runs in the full app`
      + `<span class="es-hint">This is the <b>viewer-only web demo</b> — open a 3D sample from `
      + `<b>Open&nbsp;▾</b> to explore a model. ${(tool[0] ?? "").toUpperCase() + tool.slice(1)}, with live `
      + `records, runs in the free desktop app or a self-hosted stack.</span>`
      + `<a class="ref-link" href="${DOWNLOAD}" target="_blank" rel="noopener">Get the app →</a></div>`;
  }
  return `<div class="empty-state">No project open`
    + `<span class="es-hint">Create one with <b>＋ New</b> in the top bar (or pick an existing `
    + `project), then ${tool} loads here.</span></div>`;
}

/* ───────────────────────────── R36-EMPTY-STATE — a register with no rows ─────────────────────────
 *
 * **Reported as "something is wrong with specs".** Specs was fine: the module rendered in full —
 * toolbar, filters, saved views, templates, import — around a table holding zero rows, because the
 * project had never had a `spec_section` created. A complete surface wrapped around nothing reads as
 * a failure OF the surface, and the reader has no way to tell which of three unrelated situations
 * they are in:
 *
 *   1. nothing has been created yet   → an invitation. The next step is to create one.
 *   2. a filter is hiding everything  → a mistake the reader made. The next step is to clear it.
 *   3. the fetch failed               → an outage. The next step is to retry, or to tell someone.
 *
 * Those three send a reader to three different places, so rendering them identically is the whole
 * defect — not the wording of any one of them.
 *
 * **The premise-check found the plumbing could not make the distinction, so the plumbing was the
 * item.** `portal.ts` tested `filter.q || filter.state` and knew nothing of `filter.fields`, the
 * per-field panel that is the *primary* filter UI — so a register narrowed to nothing by "amount ≥
 * 1M" said "No change events yet" and offered curated advice about where change events come from,
 * which is a confident wrong answer in the one place the reader cannot check it. And case 3 did not
 * exist at all: the records fetch was the one unguarded `await` in `openModule` (its neighbours
 * `listViews` and `templates` both `.catch`), so a 500 left the "Loading…" skeleton on screen for
 * good and the rejection escaped through the `void openModule(...)` call sites.
 *
 * This lives beside `noProjectHtml` deliberately. That function already owns the adjacent case with
 * ~17 adopters and already ships the `.empty-state` class; a second empty-state vocabulary next to it
 * is how the icon set ended up speaking two languages.
 */

/** Which of the three reasons a register is showing no rows. Exhaustive by construction. */
export type RegisterEmptyKind = "none" | "filtered" | "failed";

export const REGISTER_EMPTY_KINDS: readonly RegisterEmptyKind[] = ["none", "filtered", "failed"] as const;

/** The one action each kind offers. Distinct verbs on purpose — the label IS the distinction. */
export const REGISTER_EMPTY_ACTION: Record<RegisterEmptyKind, string> = {
  none: "＋ New",
  filtered: "✕ Clear filters",
  failed: "↻ Retry",
};

export interface RegisterEmptyOpts {
  kind: RegisterEmptyKind;
  /** The register's display name as the API serves it — e.g. `"Specifications"`, `"RFIs"`. */
  name: string;
  /** Curated upstream guidance (`ui/emptyGuide.ts`). Used by `none` only; the other two say why. */
  hint?: string;
  /** Why the fetch failed. `failed` without one still renders — it just cannot name the cause. */
  reason?: string;
  /** How many clauses are narrowing the view. `filtered` counts them so "clear" has a size. */
  filterCount?: number;
}

export interface RegisterEmptyCopy { title: string; hint: string; action: string }

/**
 * A register's name in mid-sentence, without destroying an acronym.
 *
 * The shipped line was `No ${m.name.toLowerCase()} yet`, which renders the RFI register as **"No rfis
 * yet"** — the register whose name is the most-used acronym on a jobsite. Lower-casing a display name
 * is right for `Specifications` and wrong for `RFIs`, `NCRs`, `ASIs`, and it cannot be decided from
 * the module key. The rule is on the word: a word carrying two or more consecutive capitals is an
 * acronym and is left exactly as authored; everything else lower-cases as before.
 */
export function registerNoun(name: string): string {
  return name.split(" ").map((w) => (/[A-Z]{2,}/.test(w) ? w : w.toLowerCase())).join(" ");
}

/** The three lines a register shows when it has no rows. Pure — `registerEmptyEl` renders it. */
export function registerEmptyCopy(o: RegisterEmptyOpts): RegisterEmptyCopy {
  const noun = registerNoun(o.name);
  const action = REGISTER_EMPTY_ACTION[o.kind];
  if (o.kind === "failed") {
    // Never claim the register is empty here: a request that did not answer cannot tell us whether
    // rows exist, and saying "no records" would be inventing the one fact we just failed to fetch.
    const why = o.reason ? ` ${o.reason.trim().replace(/\.?$/, ".")}` : "";
    return {
      title: `Couldn't load ${noun}`,
      hint: `This request failed, so the screen cannot say whether any ${noun} exist —`
        + ` it is a connection or server problem, not an empty register.${why}`,
      action,
    };
  }
  if (o.kind === "filtered") {
    const n = o.filterCount ?? 0;
    const lead = n > 0 ? `${n} filter${n === 1 ? " is" : "s are"}` : "A filter is";
    return {
      title: `No ${noun} match the current filters`,
      hint: `${lead} narrowing this register — anything outside ${n === 1 || n === 0 ? "it" : "them"}`
        + ` is hidden, not missing. Clear the filters to see the whole register.`,
      action,
    };
  }
  return {
    title: `No ${noun} yet`,
    hint: o.hint?.trim() || "Use “＋ New” to create the first one.",
    action,
  };
}

/**
 * The `.empty-state` element for a register with no rows.
 *
 * Everything is `textContent`: the name arrives from `module.json` and the reason from a server error
 * body, so both are untrusted strings in what used to be an `innerHTML` sink.
 *
 * `data-empty` carries the kind so a test — and a person reading the live DOM — can assert *which*
 * of the three was decided, not merely that something rendered. Three states that render three
 * different strings but are indistinguishable to a check would repeat this defect one level up.
 */
export function registerEmptyEl(o: RegisterEmptyOpts, onAction?: () => void): HTMLElement {
  const copy = registerEmptyCopy(o);
  const box = document.createElement("div");
  box.className = "empty-state";
  box.dataset.empty = o.kind;
  box.textContent = copy.title;
  const hint = document.createElement("span");
  hint.className = "es-hint";
  hint.textContent = copy.hint;
  box.appendChild(hint);
  if (onAction) {
    const btn = document.createElement("button");
    btn.className = "tool-btn";
    btn.style.cssText = "margin-top:8px";
    btn.dataset.emptyAction = o.kind;
    btn.textContent = copy.action;
    btn.onclick = onAction;
    box.appendChild(btn);
  }
  return box;
}
