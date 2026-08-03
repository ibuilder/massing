/**
 * R26-COLOUR-DISCIPLINE — what each colour is allowed to mean, and a way to keep it that way.
 *
 * The audit's finding: the primary blue marked Open, Save, the selected tab, the selected rail item,
 * **every KPI number**, PDF Takeoff, Paper space and Zoom-to-cursor. When one colour means eight
 * things it means nothing — a dashboard of blue numbers has no emphasis left to spend on the number
 * that actually needs attention.
 *
 * The contract:
 *
 * | token            | means                                                       |
 * |------------------|-------------------------------------------------------------|
 * | `--accent`       | **you can act on this** — controls, selection, focus, links |
 * | `--status-good`  | solved / passing                                            |
 * | `--status-warn`  | needs attention                                             |
 * | `--status-crit`  | blocking                                                    |
 * | `--text`/`--muted` | everything else, including data                           |
 *
 * A rule with no enforcement is a comment. `ACCENT_ALLOWED` below is the reviewed list of selectors
 * that may paint text or background with `--accent`, and `colorContract.test.ts` asserts it matches
 * the stylesheet **in both directions** — a new accent-coloured selector fails the build, and a stale
 * entry here fails it too. That is deliberately annoying: the point is that colouring something blue
 * becomes a decision somebody makes on purpose rather than a default reached for while styling.
 *
 * Borders, outlines and shadows are **not** covered. A focus ring or a hover border is the colour
 * doing exactly its job — marking interaction — and gating those would be noise with no signal.
 */

/**
 * Selectors permitted to set `color:` or `background:` to `var(--accent)`.
 *
 * Every one of these is something the user can act on, or the mark of what they have acted on. If a
 * new entry does not fit that sentence, the fix is to use `--text` rather than to extend this list.
 */
export const ACCENT_ALLOWED: string[] = [
  // selection — "this is the one you picked"
  ".ws-btn.active",
  ".rail-btn.active",
  ".pnav-item.active",
  // R26-INSPECTOR ② — the selected Inspector tab. Same meaning as every other `.active` above:
  // "this is where you are". The tab MARKS deliberately carry no colour — they mean ready/none/
  // unknown, and that is a second axis; giving it colour too would put two meanings on one channel.
  ".insp-tab.active",
  ".pnav-showall.active",
  ".sb-toggle.on",
  ".tool-btn.on",
  "#viewer-tools .tool-btn.on",
  // RAIL-TOOLBOX — an ARMED tool in the rail. Identical meaning to `.tool-btn.on` above, which it
  // replaces as the tools move off the floating bar and into the rail: "this is the one you picked,
  // and it is waiting for your next click in the canvas". The DIMMED state deliberately carries no
  // colour at all — unusable-right-now is a second axis, and putting it on the same channel is what
  // made the accent meaningless in the first place.
  ".rail-tool.on",
  // primary actions — the button that does the thing
  ".file-btn",
  ".pv-edit-btn",
  // hover/affordance — "this responds to you"
  "#rail-resize:hover",
  ".menu-item:hover",
  ".tree-node:hover",
  ".selset-row .selset-name:hover",
  "#props-close:hover",
  ".pv-guid-c:hover",
  ".pv-copy:hover",
  ".pf-addopt:hover",
  // links into a record — a reference you can follow
  ".ref-link",
  ".kc-ref",
  ".chip2-info",
  // a pin is a clickable marker on the model
  ".pin",
  // the node editor's own language: you drag from an output socket along a wire, so the colour is
  // marking the thing you manipulate, not decorating a diagram
  ".studio-edge",
  ".studio-dot-out",
  // the ONE number that stays blue — see the note in colorContract.test.ts
  ".kpi-click .kpi-v",
];

/** Strip comments and collapse whitespace so a rule can be matched as one line. */
function normalise(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\s+/g, " ");
}

/**
 * Selectors in `css` that paint **text or background** with `var(--accent)`.
 *
 * Deliberately ignores `border`, `outline` and `box-shadow`: those are the colour marking
 * interaction, which is what it is for.
 */
export function accentSelectors(css: string): string[] {
  const out: string[] = [];
  const rule = /([^{}]+)\{([^{}]*)\}/g;
  let m: RegExpExecArray | null;
  const text = normalise(css);
  while ((m = rule.exec(text)) !== null) {
    const [, rawSel, body] = m;
    if (!rawSel || !body) continue;
    const sel = rawSel.trim();
    if (!sel || sel.startsWith("@") || sel.startsWith(":root")) continue;
    for (const decl of body.split(";")) {
      const i = decl.indexOf(":");
      if (i < 0) continue;
      const prop = decl.slice(0, i).trim();
      const val = decl.slice(i + 1);
      if (!/var\(--accent\)/.test(val)) continue;
      // `background: linear-gradient(...)` and `background-color` both count; borders do not.
      if (/^(color|background|background-color|background-image|fill|stroke)$/.test(prop)) {
        out.push(sel);
        break;
      }
    }
  }
  return [...new Set(out)];
}
