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

export interface RailToolbox {
  /** The persistent element to insert into the rail. Built once; survives panel rebuilds. */
  readonly el: HTMLElement;
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
  const el = document.createElement("div");
  el.className = "rail-toolbox";
  el.dataset.toolbox = "1";

  const bodies = new Map<ToolGroup, HTMLElement>();
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
    el.appendChild(det);
    bodies.set(g, body);
  }

  // Anything the layout table does not describe still appears — visibly tagged — because a tool that
  // quietly vanishes looks exactly like one that was deliberately removed.
  const spill = document.createElement("div");
  spill.className = "rail-toolgroup-body rail-toolbox-unlaid";
  el.appendChild(spill);

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
      if (off) btn.dataset.why = "select an element first";
      else delete btn.dataset.why;
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

  return { el, place, update, unlaid: () => unlaidTitles(registered) };
}
