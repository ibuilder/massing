/**
 * Keyboard and assistive-technology support.
 *
 * A review tool is a record-keeping tool: what a reviewer marks up becomes a contract document, so
 * "you need a mouse to use it" excludes people from the record, not just from a convenience. Public
 * sector and large enterprise procurement asks for WCAG 2.1 AA (and EN 301 549 / Section 508)
 * conformance in writing, so this is also usually a gate on adoption.
 *
 * Everything here is small on purpose. The panels are built with plain DOM, and the failure mode is
 * always the same one — a `div` with an `onclick` that no keyboard can reach and no screen reader
 * announces. {@link activate} is the fix for that, applied everywhere, rather than each panel
 * inventing its own.
 */

/** Elements the browser already makes focusable and operable by keyboard. */
const NATIVELY_INTERACTIVE = new Set(["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "SUMMARY"]);

export interface ActivateOptions {
  /** Accessible name, when the element's text is not enough on its own. */
  label?: string;
  /** ARIA role. Defaults to `button`, or is left alone on a natively interactive element. */
  role?: string;
  /** Reflected as `aria-pressed` — for a toggle, like an armed tool. */
  pressed?: boolean;
  /** Reflected as `aria-selected` — for a row in a list that tracks a selection. */
  selected?: boolean;
  /** Reflected as `aria-current` — for the item representing the current page or sheet. */
  current?: boolean | string;
  /** Keep the element out of the tab order but still operable, for roving-tabindex containers. */
  roving?: boolean;
}

/**
 * Make an element operable by keyboard and legible to a screen reader.
 *
 * Space and Enter both activate, because a `role="button"` is expected to answer to both, and the
 * default `keydown` for Space scrolls the page — which, in a viewer, moves the drawing out from
 * under the person pressing it.
 *
 * @returns the element, so it can be used inline while building a tree.
 */
export function activate<T extends HTMLElement>(
  el: T,
  handler: (event: Event) => void,
  options: ActivateOptions = {},
): T {
  const native = NATIVELY_INTERACTIVE.has(el.tagName);
  if (!native) {
    el.setAttribute("role", options.role ?? "button");
    el.tabIndex = options.roving ? -1 : 0;
  } else if (options.role) {
    el.setAttribute("role", options.role);
  }
  if (options.label) el.setAttribute("aria-label", options.label);
  if (options.pressed !== undefined) el.setAttribute("aria-pressed", String(options.pressed));
  if (options.selected !== undefined) el.setAttribute("aria-selected", String(options.selected));
  if (options.current !== undefined && options.current !== false) {
    el.setAttribute("aria-current", options.current === true ? "true" : options.current);
  }

  el.addEventListener("click", handler);
  if (!native) {
    el.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " " && e.key !== "Spacebar") return;
      // Space scrolls by default, and in a viewer that drags the sheet away under the keypress.
      e.preventDefault();
      handler(e);
    });
  }
  return el;
}

/**
 * Give a container arrow-key navigation over its children — the roving tabindex pattern.
 *
 * A list of two hundred markups should be one stop in the tab order, not two hundred. Tab reaches
 * the list, arrows move within it, and Tab leaves.
 *
 * @param container the element holding the items
 * @param itemSelector how to find the items inside it
 * @returns a teardown function
 */
export function rovingFocus(container: HTMLElement, itemSelector: string): () => void {
  const items = () => Array.from(container.querySelectorAll<HTMLElement>(itemSelector));

  const onKey = (e: KeyboardEvent) => {
    const all = items();
    if (!all.length) return;
    const at = all.findIndex((el) => el === document.activeElement || el.contains(document.activeElement));
    let next: number;
    if (e.key === "ArrowDown") next = at < 0 ? 0 : Math.min(at + 1, all.length - 1);
    else if (e.key === "ArrowUp") next = at < 0 ? 0 : Math.max(at - 1, 0);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = all.length - 1;
    else return;

    e.preventDefault();
    for (const el of all) el.tabIndex = -1;
    const target = all[next];
    if (!target) return;
    target.tabIndex = 0;
    // Marked explicitly rather than left to `:focus-visible`. Engines disagree about whether a
    // programmatic `focus()` counts as keyboard-initiated even when it follows an arrow key —
    // Firefox does not match, which leaves a keyboard user arrowing a list with no visible focus
    // at all. The attribute is the same in every engine.
    for (const el of all) el.removeAttribute("data-kbd-focus");
    target.setAttribute("data-kbd-focus", "true");
    target.focus({ preventScroll: false });
  };

  // Clicking is not arrowing; drop the marker so a mouse user does not get a stray ring.
  const onPointer = (e: Event) => {
    const el = (e.target as HTMLElement | null)?.closest?.(itemSelector);
    if (el) el.removeAttribute("data-kbd-focus");
  };
  const onBlur = (e: FocusEvent) => {
    (e.target as HTMLElement | null)?.removeAttribute?.("data-kbd-focus");
  };

  container.addEventListener("keydown", onKey);
  container.addEventListener("pointerdown", onPointer);
  container.addEventListener("focusout", onBlur);
  return () => {
    container.removeEventListener("keydown", onKey);
    container.removeEventListener("pointerdown", onPointer);
    container.removeEventListener("focusout", onBlur);
  };
}

/**
 * Keep exactly one item in the tab order, so the list is a single tab stop.
 *
 * Called after a re-render, since rebuilding the rows discards whatever tabindex state the previous
 * ones carried. Prefers the selected row, so tabbing into the list lands where the user last was
 * rather than back at the top.
 */
export function refreshRovingTabstops(container: HTMLElement, itemSelector: string): void {
  const all = Array.from(container.querySelectorAll<HTMLElement>(itemSelector));
  if (!all.length) return;
  const preferred = all.find((el) => el.getAttribute("aria-selected") === "true")
    ?? all.find((el) => el.getAttribute("aria-current") === "true")
    ?? all[0]!;
  for (const el of all) el.tabIndex = el === preferred ? 0 : -1;
}

/**
 * A polite live region.
 *
 * Status changes — "saving", "3 markups loaded", "couldn't reach the server" — are conveyed by a
 * corner of the screen changing colour, which is invisible to a screen reader and to anyone not
 * looking at that corner. `polite` queues the message behind whatever is being read rather than
 * interrupting; `assertive` is for errors, which are worth interrupting for.
 */
export function createLiveRegion(parent: HTMLElement): {
  announce: (message: string, urgency?: "polite" | "assertive") => void;
  destroy: () => void;
} {
  const make = (live: string) => {
    const el = document.createElement("div");
    el.className = "mpdf-sr-only";
    el.setAttribute("aria-live", live);
    el.setAttribute("aria-atomic", "true");
    parent.appendChild(el);
    return el;
  };
  const polite = make("polite");
  const assertive = make("assertive");

  return {
    announce(message, urgency = "polite") {
      const region = urgency === "assertive" ? assertive : polite;
      // Re-announce an identical message: assistive tech ignores a write that does not change the
      // text, so two consecutive save failures would be reported once.
      region.textContent = "";
      // A microtask is enough for the clear to register as a change.
      queueMicrotask(() => { region.textContent = message; });
    },
    destroy() {
      polite.remove();
      assertive.remove();
    },
  };
}

/**
 * Trap Tab inside an element while it is open, and restore focus when it closes.
 *
 * Only for genuinely modal things. A panel that merely appears should not trap focus — being unable
 * to Tab back to the drawing is worse than the panel being easy to leave.
 */
export function trapFocus(container: HTMLElement): () => void {
  const previous = document.activeElement as HTMLElement | null;
  const focusable = () => Array.from(container.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )).filter((el) => el.offsetParent !== null || el === document.activeElement);

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Tab") return;
    const all = focusable();
    if (!all.length) return;
    const first = all[0]!;
    const last = all[all.length - 1]!;
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  container.addEventListener("keydown", onKey);
  focusable()[0]?.focus();

  return () => {
    container.removeEventListener("keydown", onKey);
    previous?.focus?.();
  };
}
