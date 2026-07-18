import { dynKeystroke, isDynKey, parseDynConstraint } from "./dynInput";
import { showResult, kvTable, resultNote } from "../ui/result";
import type { DraftPanelHandle } from "./draft/draftPanel";

/** REL-4 leaf — the KEYS shortcut layer + SNAP-KIT dynamic input.
 *
 *  Owns: the Revit-style 2-letter draw-tool shortcuts (WA=wall, CL=column, … · Esc disarms · ? help),
 *  the shortcut HUD, the typed distance/angle constraint buffer ("6", "<30", "6<30") with its ⌨ HUD,
 *  and the short-lived snap-glyph feedback. The draft flow reads `dynBuf()` when placing a point and
 *  clears it with `setDynBuf("")`; Escape routes back through `onEscape` (disarm). */

export interface KeysDynDeps {
  container: HTMLElement;
  notify: (msg: string, kind: "info" | "success" | "error") => void;
  /** Is a draw tool currently armed, and how many points are already placed? */
  isArmed: () => boolean;
  armedPoints: () => number;
  draftHandle: () => DraftPanelHandle | null;
  /** Escape pressed → disarm the draft tool (the host also clears the dyn buffer via setDynBuf). */
  onEscape: () => void;
}

export interface KeysDynHandle {
  dynBuf(): string;
  setDynBuf(next: string): void;
  flashSnapGlyph(e: MouseEvent, label: string): void;
}

// [code, draft-element key, label] — Revit-trained users are instantly fast
const KEY_SHORTCUTS: [string, string, string][] = [
  ["WA", "wall", "Wall"], ["SL", "slab", "Slab / floor"], ["RF", "roof", "Roof"],
  ["RA", "railing", "Railing"], ["CL", "column", "Column"], ["BM", "beam", "Beam"],
  ["SC", "steel_column", "Steel column"], ["SB", "steel_beam", "Steel beam"],
  ["RB", "rebar", "Rebar"], ["FT", "footing", "Footing"],
  ["DU", "duct", "Duct"], ["PI", "pipe", "Pipe"], ["CT", "cable_tray", "Cable tray"],
  ["WR", "wire", "Wire"],
];
const KEY_MAP: Record<string, string> = Object.fromEntries(KEY_SHORTCUTS.map(([c, k]) => [c, k]));

function showKeysHelp() {
  showResult("⌨ Keyboard shortcuts", (body) => {
    body.appendChild(resultNote("Type a 2-letter code (no modifier) to arm a draw tool, then click in "
      + "the model to place. <b>Esc</b> disarms · <b>?</b> shows this.", ""));
    body.appendChild(kvTable(KEY_SHORTCUTS.map(([c, , label]) => ({ k: c, v: label }))));
  });
}

export function installKeysDyn(d: KeysDynDeps): KeysDynHandle {
  const { container, notify } = d;

  // SNAP-KIT phase 2 — dynamic input: type "6", "<30" or "6<30" mid-draw to constrain the next click.
  let dynBuf = "";
  const dynHud = document.createElement("div");
  dynHud.className = "dyn-hud";
  dynHud.style.cssText = "position:absolute;bottom:44px;left:50%;transform:translateX(-50%);z-index:38;"
    + "display:none;background:var(--panel,#0f172a);color:var(--fg,#e2e8f0);border:1px solid "
    + "var(--accent,#4a8cff);border-radius:6px;padding:3px 10px;font-size:13px;"
    + "font-family:ui-monospace,monospace";
  container.appendChild(dynHud);
  function setDynBuf(next: string) {
    dynBuf = next;
    const c = parseDynConstraint(dynBuf);
    dynHud.style.display = dynBuf ? "block" : "none";
    dynHud.textContent = dynBuf
      ? `⌨ ${dynBuf}${c ? `  →  ${c.distance !== undefined ? c.distance + " m" : ""}${c.angle !== undefined ? " @ " + c.angle + "°" : ""} — click to place` : "  (…)"}`
      : "";
  }

  /** Flash a short-lived snap-kind glyph at the click point (the phase-2 osnap feedback). */
  function flashSnapGlyph(e: MouseEvent, label: string) {
    const r = container.getBoundingClientRect();
    const g = document.createElement("div");
    g.className = "snap-glyph";
    g.style.cssText = `position:absolute;left:${e.clientX - r.left + 10}px;top:${e.clientY - r.top - 18}px;`
      + "z-index:39;pointer-events:none;background:var(--panel,#0f172a);color:var(--accent,#4a8cff);"
      + "border:1px solid var(--accent,#4a8cff);border-radius:4px;padding:1px 6px;font-size:11px;"
      + "font-family:ui-monospace,monospace;opacity:1;transition:opacity .7s ease .3s";
    g.textContent = label;
    container.appendChild(g);
    requestAnimationFrame(() => { g.style.opacity = "0"; });
    setTimeout(() => g.remove(), 1100);
  }

  // KEYS — the 2-letter shortcut listener + its HUD
  let buf = "";
  let bufTimer = 0;
  const hud = document.createElement("div");
  hud.className = "keys-hud";
  hud.style.cssText = "position:absolute;bottom:14px;left:50%;transform:translateX(-50%);z-index:38;"
    + "display:none;background:var(--panel,#0f172a);color:var(--fg,#e2e8f0);border:1px solid "
    + "var(--border,#334155);border-radius:6px;padding:3px 10px;font-size:13px;"
    + "font-family:ui-monospace,monospace;letter-spacing:2px";
  container.appendChild(hud);
  const clearBuf = () => { buf = ""; hud.style.display = "none"; };
  window.addEventListener("keydown", (e) => {
    const t = e.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") { d.onEscape(); clearBuf(); return; }
    if (e.key === "?") { e.preventDefault(); showKeysHelp(); return; }
    // SNAP-KIT phase 2: while a draw tool is armed with a previous point, digits/./</- build the
    // typed distance/angle constraint (Backspace edits it) — it wins over every automatic snap.
    if (d.isArmed() && d.armedPoints() >= 1 && (isDynKey(e.key) || e.key === "Backspace")) {
      e.preventDefault();
      setDynBuf(dynKeystroke(dynBuf, e.key));
      return;
    }
    if (!/^[a-zA-Z]$/.test(e.key)) return;
    buf = (buf + e.key.toUpperCase()).slice(-2);
    window.clearTimeout(bufTimer);
    bufTimer = window.setTimeout(clearBuf, 900);
    hud.textContent = buf; hud.style.display = "block";
    if (buf.length === 2) {
      const key = KEY_MAP[buf];
      if (key) {
        const handle = d.draftHandle();
        const label = handle?.armByKey(key);
        if (label) notify(`${label} armed — click in the model to place`, "info");
        else if (handle) notify(`“${buf}” → ${key}: not available (needs a source IFC)`, "info");
      }
      clearBuf();
    }
  });

  return { dynBuf: () => dynBuf, setDynBuf, flashSnapGlyph };
}
