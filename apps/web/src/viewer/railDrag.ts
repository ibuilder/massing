/**
 * RAIL-DRAG — drag an element from the Library palette onto the canvas to place it.
 *
 * **Discovery, not parity.** Arm-then-click is already there and is faster once you know it; dragging
 * a door onto a wall is the mental model somebody has *before* they know anything. This adds a second
 * gesture onto the existing pipeline — it does not add a second pipeline. The drop resolves through
 * `captureDraftPoint`, so object snap, typed constraints, axis inference, grid and `placeValid` all
 * apply exactly as they do to a click. The item is explicit about why: drag without snapping "places
 * a wall at 4.03 m and calls it 4.00 m", and that point carries a GlobalId into the schedules.
 *
 * ## A drop is ONE point, and most elements need more
 *
 * `draftCatalog` elements declare `points: 1 | 2 | "poly"`. A single drop can only *finish* a
 * `points: 1` element — column, footing, MEP terminal, family. For a wall (2) or a slab (poly) the
 * drop places the **first** point and leaves the tool armed to be finished by clicking.
 *
 * That asymmetry is stated to the user rather than left to be discovered. A drag that looks like it
 * placed a wall and did not is worse than one that says "first point set" — the same reasoning behind
 * the amber proxy over an uncommitted draft: real-looking geometry with no marker is indistinguishable
 * from a committed element.
 *
 * ## Why the payload is read two different ways
 *
 * **During `dragover` the payload cannot be read at all.** The HTML drag-and-drop spec puts the
 * DataTransfer in *protected mode* for every event except `dragstart` and `drop`: `getData()` returns
 * `""` and only `types` is exposed. So the handler that decides whether to accept the drag
 * (`canAcceptDraftDrag`) must ask `types`, and only the drop handler (`readDraftDragKey`) can ask for
 * the value.
 *
 * Getting this wrong fails in the direction that looks like it works: `getData()` during `dragover`
 * returns an empty string, the handler concludes "not ours", never calls `preventDefault()` — and the
 * browser then refuses the drop **silently**, with no error anywhere. The feature would simply do
 * nothing, which is why the two functions are separate and separately tested.
 *
 * Both are also what keeps a **file** drag from arming a tool: dragging a PDF over the canvas carries
 * `Files`, not our MIME, so `canAcceptDraftDrag` is false, we never `preventDefault`, and the drop
 * falls through to whatever else wants it.
 */

/** Our private drag type. A custom MIME (not `text/plain`) so nothing else can be mistaken for it,
 *  and so dragging text from another app onto the canvas cannot arm an authoring tool. */
export const DRAFT_DRAG_MIME = "application/x-massing-draft";

/** The catalog key is opaque here (`wall`, `mep:diffuser`, `family:<id>`) — `armByKey` is the only
 *  thing that decides whether it names a real element. This bound exists so a hostile or corrupt
 *  payload cannot be carried around as an unbounded string. */
const MAX_KEY = 200;

function typeList(dt: DataTransfer | null): string[] {
  if (!dt) return [];
  try { return Array.from(dt.types ?? []); } catch { return []; }
}

/**
 * Is this drag one of ours? Answered from `types` alone, because that is all `dragover` exposes.
 *
 * A `dragover` handler must call `preventDefault()` to permit a drop, so this is the predicate that
 * decides whether the canvas is a drop target at all for this drag.
 */
export function canAcceptDraftDrag(dt: DataTransfer | null): boolean {
  return typeList(dt).includes(DRAFT_DRAG_MIME);
}

/** Attach the catalog key at `dragstart`. */
export function setDraftDragKey(dt: DataTransfer | null, key: string): void {
  if (!dt) return;
  try {
    dt.setData(DRAFT_DRAG_MIME, key);
    dt.effectAllowed = "copy";
  } catch { /* a browser that refuses the custom type simply has no drag-to-place */ }
}

/**
 * Read the catalog key at `drop`. Null when this is not our drag, or when the payload is empty or
 * implausible — the caller must treat null as "not ours" and leave the event alone.
 */
export function readDraftDragKey(dt: DataTransfer | null): string | null {
  if (!canAcceptDraftDrag(dt)) return null;
  let raw = "";
  try { raw = dt!.getData(DRAFT_DRAG_MIME) ?? ""; } catch { return null; }
  const key = raw.trim();
  if (!key || key.length > MAX_KEY) return null;
  return key;
}

export interface DropCompletion {
  /** Did this single drop finish the element, or is the tool still armed for more points? */
  completes: boolean;
  /** What to tell the user. Always says something: a drop that placed nothing visible and said
   *  nothing is indistinguishable from a drop that failed. */
  message: string;
}

/**
 * What one drop can accomplish for an element needing `points` clicks.
 *
 * `points: 1` completes. Everything else places the first point and stays armed — and says so,
 * naming the gesture that finishes it, because the user who dragged has just demonstrated they do not
 * yet know the click flow.
 */
export function dropCompletion(points: 1 | 2 | "poly", label: string): DropCompletion {
  if (points === 1) return { completes: true, message: `${label} placed` };
  if (points === 2) {
    return { completes: false, message: `${label}: first point set — click the second point` };
  }
  return { completes: false, message: `${label}: first point set — click more, double-click to close` };
}
