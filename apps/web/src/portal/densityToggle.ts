import { cycleDensity, readDensity } from "./prefs";

/** The row-density control: one button cycling Field (56 px) → Comfortable (36 px) → Compact (28 px).
 *
 *  Extracted from `portal.ts`'s `renderHome` on 2026-09-11 because the size ratchet refused four
 *  lines added for the prefab-kit destination, and **the ratchet's answer is to take something out,
 *  not to raise the cap.** This block was the honest candidate: it is self-contained, it is about a
 *  display preference rather than about the portal shell, and nothing else in `renderHome` reads its
 *  locals.
 *
 *  `apply` is passed in rather than imported because the caller owns what "apply" means — `PortalUI`
 *  re-lays its registers. The button re-paints itself after cycling so its label and `aria-pressed`
 *  describe the state the user just moved to, not the one they left.
 */
export function densityToggleRow(apply: () => void): HTMLElement {
  const row = document.createElement("div");
  row.style.cssText = "display:flex;justify-content:flex-end;margin-bottom:4px";
  const btn = document.createElement("button");
  btn.className = "tool-btn";
  btn.style.cssText = "font-size:11px;padding:2px 8px";
  const paint = () => {
    const d = readDensity();
    btn.textContent = d === "field" ? "☐ Field" : d === "compact" ? "⊟ Compact" : "⊞ Comfortable";
    btn.title = "Cycle Field (56 px) → Comfortable (36 px) → Compact (28 px). Applies to registers.";
    btn.setAttribute("aria-pressed", String(d !== "comfortable"));
  };
  btn.onclick = () => { cycleDensity(); apply(); paint(); };
  paint();
  row.append(btn);
  return row;
}
