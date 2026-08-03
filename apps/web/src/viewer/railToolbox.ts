/**
 * RAIL-TOOLBOX — the viewer's tools live in the RAIL, not floating over the model.
 *
 * The floating bar showed ~5 labelled verbs and hid 23 under **More**, sitting on top of the
 * geometry it acts on. That was a reasonable answer while the rail was *navigation* and the bar was
 * *the tools*. It stops being reasonable once the rail is meant to be the design tool itself:
 *
 *   - a tool you cannot see is a tool you do not know you have, and 23 of 28 were one click deep;
 *   - the bar covered the model — the thing the tools operate on;
 *   - and it makes drag-to-place impossible, because half the palette floats over the drop target.
 *
 * So the window becomes a pure canvas and the rail becomes the instrument. That is the Revit
 * toolbox / ArchiCAD / Figma shape, and it is what lets the canvas later swap between 3D and 2D
 * without the tools moving with it.
 *
 * **This is a re-parenting pass, not a rewrite of 28 call sites.** Every tool is still created by
 * the module that owns its behaviour, through the same `toolBtn` seam; only its parent and its
 * presentation change. A pass that moves nodes cannot lose one — the same property that made the
 * original More-menu layout safe.
 *
 * ## Two rules the floating bar had to break and the rail does not
 *
 * **Nothing is demoted.** The bar had a hard cap (`MAX_PRIMARY`), so promoting one verb silently
 * pushed another into More — a defect this repo hit twice, once shipping a tool that relocated
 * itself whenever you selected something. A rail scrolls. Every tool is visible in its group,
 * always, at the same place.
 *
 * **Context DIMS rather than HIDES.** `data-cap` styling already follows the house rule — *"a dimmed
 * button that says 'needs Editor' is onboarding, a missing one is a support ticket"* — and the same
 * logic now covers selection: Move/Copy/Delete stay put and go quiet until something is selected,
 * instead of appearing and disappearing under the cursor.
 */
import { GROUP_LABELS, type ToolContext, type ToolGroup, specFor, unlaidTitles } from "./toolbarLayout";

/**
 * RAIL-SPLIT — which rail PANEL each tool group belongs to.
 *
 * v0.3.836 put all five groups in one container inside `panel-tools`. Measured live straight after,
 * that panel held **182 buttons under 7 headings** — 154 of them already there before the toolbox
 * arrived, doing about ten unrelated jobs. "Tools" was not a category; it was where a control went
 * when nobody decided, which is the same failure `rooms.py` records about the retired "Engineering"
 * section, arriving in the rail instead of the module list.
 *
 * So the groups distribute by the job they serve, not by the fact that they happen to be viewer
 * buttons: looking at the model is navigation, changing it is authoring, asking it questions is
 * coordination. Each lands in the rail item a user would open for that job.
 */
export const GROUP_PANEL: Record<ToolGroup, string> = {
  look: "view",          // NAVIGATE ▸ View — how you look at the model
  measure: "view",       // measuring is looking with a number attached
  author: "build",       // AUTHOR ▸ Build — the verbs that change the model
  // COORDINATE ▸ Analyse. This fold into Review was conditional and the condition has been met:
  // "Ask the model" was the only tool in this group, and the analysis it belongs beside (code,
  // egress, cost, 4D) sat inside the 1087-line `qa` tool-group Review hosts — a one-button rail
  // item is the thin version of the empty-room failure. R24-TOOLS-SPLIT cut `qa` in two at the
  // source, so this group now lands beside those analyses instead of away from them.
  analyse: "analyse",
  collaborate: "view",   // sharing what is ON SCREEN: it belongs with the view it captures
};

export interface RailToolbox {
  /** The panel element for a rail key, or null when that key hosts no tool group. Persistent —
   *  built once, survives panel rebuilds, must be re-inserted rather than recreated. */
  hostFor(railKey: string): HTMLElement | null;
  /** Every rail key this toolbox owns a panel for. */
  hostKeys(): string[];
  /** Adopt a freshly created tool button into its group. Called by `toolBtn`. */
  place(button: HTMLButtonElement, title: string): void;
  /** Re-evaluate which tools are usable right now. Dims, never hides, never moves. */
  update(ctx: ToolContext): void;
  /** Titles the layout table does not describe — empty in a correct build. */
  unlaid(): string[];
}

/** Tools that only mean something with a selection, keyed by the label in `toolbarLayout`. */
const NEEDS_SELECTION = new Set([
  "Show all", "Isolate", "Colour", "Edit in place", "Push/pull", "Move", "Copy",
  "Rotate", "Delete", "Property", "Add door", "Add window",
]);

/** The order groups read in the rail: look at it, measure it, change it, ask it, share it. */
const ORDER: ToolGroup[] = ["look", "measure", "author", "analyse", "collaborate"];

export function createRailToolbox(): RailToolbox {
  /** One persistent container per rail panel that hosts at least one group. */
  const hosts = new Map<string, HTMLElement>();
  const bodies = new Map<ToolGroup, HTMLElement>();

  function hostEl(railKey: string): HTMLElement {
    let h = hosts.get(railKey);
    if (!h) {
      h = document.createElement("div");
      h.className = "rail-toolbox";
      h.dataset.toolbox = railKey;
      hosts.set(railKey, h);
    }
    return h;
  }

  for (const g of ORDER) {
    const label = GROUP_LABELS.find(([id]) => id === g)?.[1] ?? g;
    const det = document.createElement("details");
    det.className = "rail-toolgroup";
    det.dataset.group = g;
    det.open = true;                       // the instrument is open by default; it IS the surface
    const sum = document.createElement("summary");
    sum.className = "rail-toolgroup-head";
    sum.textContent = label;
    const body = document.createElement("div");
    body.className = "rail-toolgroup-body";
    det.append(sum, body);
    hostEl(GROUP_PANEL[g]).appendChild(det);
    bodies.set(g, body);
  }

  // Anything the layout table does not describe still appears — visibly tagged — because a tool that
  // quietly vanishes looks exactly like one that was deliberately removed. It lands in the Build
  // panel: an undescribed tool is most likely a new authoring verb, and it must be somewhere a
  // person actually opens.
  const spill = document.createElement("div");
  spill.className = "rail-toolgroup-body rail-toolbox-unlaid";
  hostEl("build").appendChild(spill);

  const registered: string[] = [];
  const buttons: { btn: HTMLButtonElement; label: string }[] = [];

  function place(button: HTMLButtonElement, title: string): void {
    registered.push(title);
    const spec = specFor(title);
    // Label via a data attribute rendered by CSS — **never by rewriting the button's content.**
    //
    // The first version injected `<span class=ic>` + `<span class=rail-tool-label>` into the button.
    // Live verification caught what that breaks: the presence tool re-renders its OWN button to show
    // who is viewing (its title becomes "Live presence — no one else viewing" and its content a live
    // count), which wiped the injected spans and left an unlabelled glyph. Any module that updates
    // its button would do the same.
    //
    // These buttons belong to the modules that created them. The toolbox may re-parent and decorate
    // them; it may not own their contents. `data-label` survives any innerHTML the owner writes.
    button.dataset.label = spec?.label ?? title;
    button.classList.add("rail-tool");
    button.classList.remove("icon-btn");   // no longer a bare glyph in a cramped bar
    if (spec) {
      button.dataset.toolGroup = spec.group;
      buttons.push({ btn: button, label: spec.label });
      bodies.get(spec.group)!.appendChild(button);
    } else {
      button.dataset.unlaid = "1";
      spill.appendChild(button);
    }
  }

  function update(ctx: ToolContext): void {
    for (const { btn, label } of buttons) {
      const needsSel = NEEDS_SELECTION.has(label);
      // Dim, never hide: the tool keeps its place so it can be learned, and says why it is quiet.
      const off = needsSel && !ctx.selection;
      btn.classList.toggle("rail-tool-off", off);
      btn.setAttribute("aria-disabled", String(off));
      // The reason is a TOOLTIP, not inline text. Rendered inline it was a third string competing
      // with the glyph and the label inside a 150px rail — the dimming already says "not now", and
      // three strings in that width read as jumble rather than as an explanation. Appended to the
      // owner's own title rather than replacing it, so the tool's real description survives.
      if (off) {
        btn.dataset.why = "select an element first";
        if (!btn.dataset.titleBase) btn.dataset.titleBase = btn.getAttribute("title") ?? "";
        btn.title = `${btn.dataset.titleBase} — select an element first`;
      } else {
        delete btn.dataset.why;
        if (btn.dataset.titleBase !== undefined) btn.title = btn.dataset.titleBase;
      }
    }
    // Groups that are entirely unusable collapse their body but keep their heading — the user can
    // still see the capability exists.
    for (const [g, body] of bodies) {
      const any = [...body.querySelectorAll(".rail-tool")].length > 0;
      (body.parentElement as HTMLElement).style.display = any ? "" : "none";
      void g;
    }
    spill.style.display = spill.children.length ? "" : "none";
  }

  return {
    hostFor: (railKey: string) => hosts.get(railKey) ?? null,
    hostKeys: () => [...hosts.keys()],
    place,
    update,
    unlaid: () => unlaidTitles(registered),
  };
}
