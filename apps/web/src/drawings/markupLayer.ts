// The sheet markup layer — extracted from `DrawingsUI` (R36-VIEWER-SUBAPP slice 6).
//
// Numbered pins and takeoff markups drawn over a sheet, anchored by GlobalId where they have one.
// It lived as private state on the Drawings room — `markup`, `pinLayer`, `svgHost`, `scale` — which
// meant marking up a drawing was only possible in the room that happened to own that state. Slice 6
// wants it on the Sheets canvas too, *"so a drawing is marked up where it is being looked at, rather
// than in a different room"*, and a layer coupled to one room's fields cannot be mounted twice.
//
// **The markup key is the sheet id, and that is what makes two surfaces one feature.** The Drawings
// room keys a storey plan `plan:<name>`; the viewer's plan pane shows the same storey. Give both the
// same key and a pin dropped in one appears in the other, with no syncing and no second store —
// the identity does the work.
//
// ## Two sources, one surface
//
// A sheet's own pins come from `drawingMarkup(pid, id)`, and the PDF editor's takeoff markups from
// `drawingMarkup(pid, id + "#pdf")`. Takeoffs carry a NORMALISED anchor (`nx`, `ny`) because they were
// placed on a PDF at a different size, so they are mapped through the rendered SVG's content box;
// pins carry absolute coordinates. A takeoff without `nx` cannot be placed at all and is dropped —
// rendering it at 0,0 would put a measurement in the corner of an unrelated drawing.
//
// ## Failure is quiet on purpose
//
// A markup fetch that fails leaves the sheet rendered and the layer empty. The drawing is the thing
// the user came for; an error banner over a legible drawing because its annotations are late is a
// worse answer than no annotations.

import type { DrawingMarkupItem } from "../api/client";
import { askText } from "../ui/prompt";

/**
 * The GlobalId a markup is tied to, if any.
 *
 * Defined HERE rather than imported from `ui/sheetGuid`, which is where it used to live: that module
 * imports `viewer/planPane` for its DOM helpers, so importing it from a layer the plan pane itself
 * mounts closed a cycle — `markupLayer -> sheetGuid -> planPane -> markupLayer`, caught by the
 * import-cycle guard. It is a pure data reader with no DOM in it, so it belongs beside the thing that
 * reads markups; `sheetGuid` re-exports it for its existing callers.
 */
export function guidFromMarkupData(data: { guid?: unknown } | null | undefined): string | null {
  const g = data?.guid;
  return typeof g === "string" && g.trim() ? g.trim() : null;
}

/** The slice of the API client this layer needs. Narrow on purpose: it is mountable, so it should not
 *  drag the whole client into every host that wants pins. */
export interface MarkupApi {
  drawingMarkup(pid: string, sheetId: string): Promise<DrawingMarkupItem[]>;
  promoteDrawingMarkup(pid: string, id: string): Promise<{ topic: { title: string } }>;
  deleteDrawingMarkup(pid: string, id: string): Promise<unknown>;
}

export interface MarkupLayerDeps {
  /** Absolutely-positioned element the pins are appended to. */
  readonly pinLayer: HTMLElement;
  /** Element containing the rendered `<svg>` — pins are positioned against its content box. */
  readonly svgHost: HTMLElement;
  /** Current zoom, so a normalised anchor lands in the same place at any zoom. */
  readonly getScale: () => number;
  readonly api: MarkupApi;
  readonly projectId: () => string | null;
  /**
   * The markup key for what is on screen — `plan:<storeyGuid>`, `elev:north`… `null` when nothing
   * is shown. **New markups are always written under this key.**
   */
  readonly sheetId: () => string | null;
  /**
   * The pre-GUID key the same surface used to be stored under, READ-ONLY and merged into the
   * displayed set. `null` when there is no legacy form (elevations and sections were never keyed on
   * a renameable thing).
   *
   * Storey plans were keyed `plan:<storeyName>` until the R36 premise-check found that keying markup
   * on a renameable name orphans every pin on the level the moment somebody renames it — against the
   * project's first non-negotiable, *reference by GlobalId, never a transient id*. Switching the key
   * without reading the old one would have "fixed" the bug by hiding every markup already stored,
   * which is the same data loss arriving through the front door.
   *
   * Nothing is written here and nothing is rewritten: a markup stored under the legacy key stays
   * there and stays visible. **The residual limitation is real and stated rather than hidden** — a
   * pin created before this change still orphans if its level is renamed, because rekeying it needs
   * a name→GlobalId map that only the source IFC holds. New pins are immune from here on.
   */
  readonly legacySheetId?: () => string | null;
  readonly setStatus: (message: string) => void;
  /** Called after every render with the number of markups, for a host that shows a count. */
  readonly onCount?: (n: number) => void;
  /**
   * Reveal the element a markup is tied to. **Injected, because how you reveal something is a
   * property of the SURFACE, not of the markup** — the Drawings room selects in the 3D viewer and
   * lights the plan, the viewer's own plan pane already has a pick handler. A layer that reached for
   * one of those directly could only ever be mounted where that one was correct, which is the
   * coupling this extraction exists to remove.
   */
  readonly onReveal?: (guid: string) => void;
  /** Injected so a test can answer the prompt without a DOM dialog. */
  readonly prompt?: typeof askText;
}

/**
 * Split the two markup sources.
 *
 * Exported because it is the rule that decides what is placeable, and it is worth asserting directly:
 * a takeoff without a normalised anchor is dropped, and everything else is kept in order.
 */
export function placeable(pins: readonly DrawingMarkupItem[],
                          takeoff: readonly DrawingMarkupItem[]): DrawingMarkupItem[] {
  return [...pins, ...takeoff.filter((m) => m.data?.nx != null)];
}

export class MarkupLayer {
  private items: DrawingMarkupItem[] = [];

  constructor(private readonly d: MarkupLayerDeps) {}

  get count(): number { return this.items.length; }

  /** Fetch both sources for the current sheet and render. Safe to call repeatedly. */
  async load(): Promise<void> {
    const pid = this.d.projectId();
    const id = this.d.sheetId();
    if (!pid || !id) { this.items = []; this.render(); return; }
    // The legacy key is read only when it is genuinely a DIFFERENT key. Comparing rather than
    // assuming matters: a host that wires `legacySheetId` to the same accessor as `sheetId` would
    // otherwise fetch every markup twice and render each pin twice, which reads as duplicated work
    // by the user rather than as a bug in the wiring.
    const legacyKey = ((k) => (k && k !== id ? k : null))(this.d.legacySheetId?.() ?? null);
    const none = Promise.resolve([] as DrawingMarkupItem[]);
    try {
      // The PRIMARY fetch is the only one without a catch, deliberately: an unreachable API still
      // empties the layer exactly as it did before the legacy read existed. Both legacy fetches
      // swallow their own failures, so a missing or unreadable legacy key can never take down the
      // markups that are stored correctly.
      const [pins, takeoff, oldPins, oldTakeoff] = await Promise.all([
        this.d.api.drawingMarkup(pid, id),
        this.d.api.drawingMarkup(pid, `${id}#pdf`).catch(() => [] as DrawingMarkupItem[]),
        legacyKey ? this.d.api.drawingMarkup(pid, legacyKey).catch(() => []) : none,
        legacyKey ? this.d.api.drawingMarkup(pid, `${legacyKey}#pdf`).catch(() => []) : none,
      ]);
      this.items = placeable([...pins, ...oldPins], [...takeoff, ...oldTakeoff]);
    } catch {
      this.items = [];                 // see the header: a legible drawing beats an error banner
    }
    this.render();
  }

  render(): void {
    this.d.pinLayer.innerHTML = "";
    const pid = this.d.projectId();
    // Content box, scale-invariant: normalised takeoff anchors map into the same space as pins.
    const svg = this.d.svgHost.querySelector("svg");
    const rect = svg?.getBoundingClientRect();
    const scale = this.d.getScale();
    const cw = rect && scale ? rect.width / scale : 0;
    const ch = rect && scale ? rect.height / scale : 0;

    this.items.forEach((p, i) => {
      const takeoff = !!p.kind && p.kind !== "pin" && p.data?.nx != null;
      const tied = guidFromMarkupData(p.data);
      const carried = !!p.data?.carried_from;   // MARKUP-2a: predates the current sheet revision
      const el = document.createElement("div");
      el.className = "dwg-pin" + (p.topic_id ? " linked" : "") + (takeoff ? " takeoff" : "")
        + (carried ? " carried" : "") + (tied ? " tied" : "");
      el.textContent = takeoff ? "◆" : String(i + 1);
      el.style.left = `${takeoff && cw ? p.data!.nx! * cw : p.x}px`;
      el.style.top = `${takeoff && ch ? p.data!.ny! * ch : p.y}px`;
      const meas = takeoff && p.data?.value ? ` — ${p.data.value} ${p.data.unit || ""}` : "";
      el.title = (p.note || (takeoff ? p.kind! : "")) + meas
        + (tied ? `  · ${tied}` : "")
        + (p.topic_id ? "  · linked to RFI" : "")
        + (carried ? `  · carried from Rev ${p.data!.carried_from} — verify against the current revision` : "");
      el.onclick = (ev) => { ev.stopPropagation(); void this.onPinClick(p, i, tied, pid); };
      this.d.pinLayer.appendChild(el);
    });
    this.d.onCount?.(this.items.length);
  }

  /**
   * A pin click: reveal the element it is tied to, then offer to raise an RFI or delete it.
   *
   * The reveal happens BEFORE the prompt and regardless of what the user then chooses, because
   * "show me what this is about" is the common case and should not cost a dialog.
   */
  private async onPinClick(p: DrawingMarkupItem, i: number, tied: string | null,
                           pid: string | null): Promise<void> {
    if (tied) this.d.onReveal?.(tied);
    if (!pid) return;
    const ask = this.d.prompt ?? askText;
    const linked = p.topic_id ? " (already an RFI)" : "";
    const choice = await ask(`Markup #${i + 1}`, {
      label: `"${p.note || ""}"${linked} — type "rfi" to raise an RFI, or "del" to delete.`, value: "" });
    if (choice == null) return;
    try {
      const want = choice.trim().toLowerCase();
      if (want === "rfi" && !p.topic_id) {
        const r = await this.d.api.promoteDrawingMarkup(pid, p.id);
        this.d.setStatus(`RFI raised: ${r.topic.title}`);
      } else if (want === "del") {
        await this.d.api.deleteDrawingMarkup(pid, p.id);
      }
      await this.load();
    } catch {
      this.d.setStatus("markup action failed (needs reviewer)");
    }
  }
}
