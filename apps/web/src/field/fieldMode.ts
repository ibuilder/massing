/**
 * R24-FIELD-MODE ① — a mode, not a breakpoint.
 *
 * The queue, GPS and capture sheet already exist (`field.ts`). They still live inside the desktop
 * IA: a 52 px FAB, a queue you only see after opening the sheet, and notes that cannot be spoken.
 * This file is the mode flag plus the copy the always-visible strip uses. Contrast and 56 px
 * targets live in `fieldMode.css`, scoped to field chrome so office density is untouched.
 */
export const FIELD_MODE_KEY = "aec-field-mode";

export function readFieldMode(): boolean {
  return localStorage.getItem(FIELD_MODE_KEY) === "1";
}

export function setFieldMode(on: boolean): void {
  localStorage.setItem(FIELD_MODE_KEY, on ? "1" : "0");
  applyFieldMode();
}

/** Honour `?field=1` / `?field=0` without fighting a stored preference on a later visit. */
export function honourFieldQuery(search = typeof location === "undefined" ? "" : location.search): boolean | null {
  const v = new URLSearchParams(search).get("field");
  if (v === "1" || v === "true") { setFieldMode(true); return true; }
  if (v === "0" || v === "false") { setFieldMode(false); return false; }
  return null;
}

export function applyFieldMode(root: HTMLElement = document.documentElement): void {
  const on = readFieldMode();
  root.dataset.fieldMode = on ? "1" : "0";
}

/** Toggle + always-visible queue strip. Idempotent so remounts do not duplicate chrome. */
export function mountFieldChrome(opts: {
  queueCount: () => number;
  onOpenQueue: () => void;
}): { refreshStrip: () => void } {
  honourFieldQuery();
  applyFieldMode();

  let toggle = document.getElementById("field-mode-toggle") as HTMLButtonElement | null;
  if (!toggle) {
    toggle = document.createElement("button");
    toggle.id = "field-mode-toggle";
    toggle.type = "button";
    document.body.appendChild(toggle);
  }

  let strip = document.getElementById("field-sync-strip") as HTMLButtonElement | null;
  if (!strip) {
    strip = document.createElement("button");
    strip.id = "field-sync-strip";
    strip.type = "button";
    document.body.appendChild(strip);
  }
  strip.onclick = () => opts.onOpenQueue();
  strip.setAttribute("aria-live", "polite");
  strip.setAttribute("aria-atomic", "true");

  const paintToggle = () => {
    const on = readFieldMode();
    toggle!.textContent = on ? "Office" : "Field";
    toggle!.title = on
      ? "Leave field mode"
      : "Field mode — 56 px targets, outdoor contrast, always-visible queue";
    toggle!.setAttribute("aria-pressed", on ? "true" : "false");
  };

  const refreshStrip = () => {
    strip!.textContent = syncStripText(opts.queueCount(), navigator.onLine);
    strip!.hidden = !readFieldMode();
    paintToggle();
  };

  toggle.onclick = () => {
    setFieldMode(!readFieldMode());
    refreshStrip();
  };

  window.addEventListener("online", refreshStrip);
  window.addEventListener("offline", refreshStrip);
  refreshStrip();
  return { refreshStrip };
}

/** Permanent strip copy. Empty is a sentence, never a silent blank that looks like "nothing to do"
 *  when you are actually offline with work waiting. */
export function syncStripText(n: number, online: boolean): string {
  if (!online) {
    return n ? `Offline · ${n} waiting to sync` : "Offline · queue empty";
  }
  return n ? `${n} waiting to sync` : "Queue empty — all caught up";
}
