/**
 * R24-KEYS — one keyboard contract, in one place, that is true.
 *
 * The audit asks for a *published* keyboard contract, and lists one: ⌘K · `G then M` · `J`/`K` ·
 * `A` · `W S C B` · ⌥click. **Most of that does not exist in this app**, and publishing it would have
 * been the easy, wrong version of this item — a contract that lies is worse than none, because the
 * user who tries `J` and gets nothing stops trusting the ones that do work. So what is published here
 * is what the handlers actually dispatch, and the audit's unbuilt keys are recorded in the roadmap as
 * open work rather than printed on a help screen.
 *
 * What was actually wrong was smaller and more embarrassing than a missing contract: **`?` gave you
 * two different answers.** `main.ts` showed a six-second toast listing six viewer keys; `keysDyn.ts`
 * opened a modal listing the fourteen two-letter draw codes. Which one you got depended on whether
 * the 3D viewer had finished loading, neither mentioned ⌘K, and neither mentioned the other. Three
 * keyboard surfaces, no overlap, and the one people press first vanished after six seconds.
 *
 * The draw codes are **not duplicated here**. They live in `viewer/keysDyn.ts` next to the handler
 * that dispatches them, and `keys.test.ts` asserts this contract and that table agree in *both*
 * directions — the same read/write-symmetry rule the IFC tables follow, because two lists encoding
 * one fact always drift and the drift is invisible until somebody presses the key.
 */
import { kvTable, resultNote, showResult } from "./result";

export interface KeyEntry {
  /** As a person would type it. Rendered verbatim. */
  keys: string;
  does: string;
}

export interface KeySection {
  title: string;
  /** Why these are here and when they work — the scope, stated, not implied. */
  note?: string;
  entries: KeyEntry[];
}

/**
 * Keys that work anywhere in the app.
 *
 * Deliberately three. The global layer is small because everything else is contextual, and claiming
 * a fourth global key that only works on some screens is how the two-`?` problem started.
 */
export const GLOBAL_KEYS: KeyEntry[] = [
  { keys: "⌘K / Ctrl-K", does: "Search or jump to anything — actions, modules, records" },
  { keys: "\\", does: "Show or hide the side panel" },
  { keys: "?", does: "This list" },
];

/** Keys the 3D view answers. They do nothing until a model is open — which the note says. */
export const VIEWER_KEYS: KeyEntry[] = [
  { keys: "F", does: "Fit the model to the view" },
  { keys: "M", does: "Measure distance (press again to stop)" },
  { keys: "A", does: "Measure area (press again to stop)" },
  { keys: "S", does: "Section box — then double-click a face" },
  { keys: "H", does: "Show everything again — clears hiding and colouring" },
  { keys: "Esc", does: "Clear the selection, or disarm the current draw tool" },
];

/**
 * The whole contract, assembled.
 *
 * `drawCodes` is passed in rather than imported so this module stays free of `viewer/` — the help
 * screen must be openable before the 3D bundle has loaded, which is exactly the moment the old toast
 * was the only thing available.
 */
export function keyContract(
  drawCodes: readonly (readonly [string, string, string])[] = [],
  snapCodes: readonly (readonly [string, string])[] = [],
): KeySection[] {
  const sections: KeySection[] = [
    { title: "Anywhere", entries: GLOBAL_KEYS },
    {
      title: "In the 3D view",
      note: "Active once a model is open.",
      entries: VIEWER_KEYS,
    },
  ];
  if (drawCodes.length) {
    sections.push({
      title: "Draw tools",
      note: "Type the two letters with no modifier to arm a tool, then click in the model to place it. "
        + "Esc disarms. While a tool is armed you can type a distance or angle — 6, <30, or 6<30.",
      entries: drawCodes.map(([code, , label]) => ({ keys: code, does: label })),
    });
  }
  // AUTH-SNAP-OVERRIDE. Same rule as the draw codes: passed in, never imported, so `?` still works
  // before the 3D bundle has loaded — and omitted entirely rather than printed as an aspiration.
  if (snapCodes.length) {
    sections.push({
      title: "Snap for one pick",
      note: "While a draw tool is armed, type one of these to aim the NEXT click at a particular snap "
        + "— it applies to that click only and is not a mode. Esc cancels it and leaves the tool armed. "
        + "If the picked element has no such snap the click takes the raw cursor and the glyph says so, "
        + "rather than quietly using a different one.",
      entries: snapCodes.map(([code, label]) => ({ keys: code, does: label })),
    });
  }
  return sections;
}

/** Flatten to `keys` strings — the shape the drift test compares. */
export function keysIn(sections: readonly KeySection[], title: string): string[] {
  return sections.find((s) => s.title === title)?.entries.map((e) => e.keys) ?? [];
}

/**
 * Show the contract.
 *
 * Reuses `showResult` so it looks like every other panel rather than inventing a fourth chrome — and
 * unlike the toast it replaces, it stays on screen until dismissed. A help surface with a six-second
 * timeout is a help surface you have to read faster than you can try.
 */
export function showKeyHelp(
  drawCodes: readonly (readonly [string, string, string])[] = [],
  snapCodes: readonly (readonly [string, string])[] = [],
): void {
  showResult("⌨ Keyboard", (body) => {
    for (const section of keyContract(drawCodes, snapCodes)) {
      const h = document.createElement("div");
      h.className = "section-title";
      h.style.marginTop = "10px";
      h.textContent = section.title;
      body.appendChild(h);
      if (section.note) body.appendChild(resultNote(section.note, ""));
      body.appendChild(kvTable(section.entries.map((e) => ({ k: e.keys, v: e.does }))));
    }
  });
}
