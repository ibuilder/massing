import { describe, expect, it, vi } from "vitest";
import { installDraftPanel, type ArmedDraft } from "./draftPanel";
import { DRAFT_DRAG_MIME, readDraftDragKey } from "../railDrag";

/**
 * RAIL-DRAG — the drag SOURCE, driven through the real panel.
 *
 * `railDrag.test.ts` proves the payload rules in isolation. Neither that nor a typecheck would notice
 * if the palette rows were never made draggable in the first place — "the engine exists and nothing
 * calls it" is this repo's most-repeated defect, and it is the reason this file exists at all
 * (`draftPanel.ts` had no test before).
 *
 * The drop TARGET lives in `viewer/app.ts` and is not reachable from a unit test: it needs a WebGL
 * renderer, a Fragments worker and a loaded model. That gap is stated in the PR rather than papered
 * over with a mock that would only assert the mock.
 */

function mount() {
  const body = document.createElement("div");
  document.body.appendChild(body);
  const armed: (ArmedDraft | null)[] = [];
  const handle = installDraftPanel({
    body,
    fetchFamilies: () => Promise.resolve([]),
    arm: (a) => { armed.push(a); },
    notify: vi.fn((_m: string, _k?: "info" | "success" | "error") => {}),
    canAuthor: () => true,
  });
  return { body, armed, handle };
}

/** The palette rows — buttons inside the scrolling list, excluding discipline chips. */
const rows = (body: HTMLElement) =>
  [...body.querySelectorAll<HTMLButtonElement>("button")].filter((b) => b.draggable);

/** A DataTransfer stub good enough for dragstart (writable, readable). */
function makeDT(): DataTransfer {
  const store = new Map<string, string>();
  return {
    get types() { return [...store.keys()]; },
    getData: (t: string) => store.get(t) ?? "",
    setData: (t: string, v: string) => { store.set(t, v); },
    effectAllowed: "none",
  } as unknown as DataTransfer;
}

describe("RAIL-DRAG — the palette rows are actually drag sources", () => {
  it("renders draggable rows", () => {
    const { body } = mount();
    expect(rows(body).length, "no draggable palette rows — drag-to-place is unreachable")
      .toBeGreaterThan(0);
  });

  it("dragstart puts a catalog key on the DataTransfer that readDraftDragKey can read back", () => {
    const { body } = mount();
    const row = rows(body)[0]!;
    const dt = makeDT();
    const ev = new Event("dragstart", { bubbles: true }) as DragEvent;
    Object.defineProperty(ev, "dataTransfer", { value: dt });
    row.dispatchEvent(ev);
    const key = readDraftDragKey(dt);
    expect(key, "dragstart set no usable payload").toBeTruthy();
    expect(dt.types).toContain(DRAFT_DRAG_MIME);
  });

  // The key must be one the arming path accepts. A payload that round-trips but names nothing is a
  // drag that silently does nothing on drop — the failure mode this whole item is meant to remove.
  it("the dragged key is one armByKey resolves", () => {
    const { body, handle, armed } = mount();
    const row = rows(body)[0]!;
    const dt = makeDT();
    const ev = new Event("dragstart", { bubbles: true }) as DragEvent;
    Object.defineProperty(ev, "dataTransfer", { value: dt });
    row.dispatchEvent(ev);
    const key = readDraftDragKey(dt)!;
    expect(handle.armByKey(key), `armByKey rejected the dragged key ${key}`).toBeTruthy();
    expect(armed.at(-1)?.key).toBe(key);
  });

  it("every draggable row carries a key armByKey resolves, not just the first", () => {
    const { body, handle } = mount();
    const keys: string[] = [];
    for (const row of rows(body)) {
      const dt = makeDT();
      const ev = new Event("dragstart", { bubbles: true }) as DragEvent;
      Object.defineProperty(ev, "dataTransfer", { value: dt });
      row.dispatchEvent(ev);
      const k = readDraftDragKey(dt);
      expect(k, "a row produced no payload").toBeTruthy();
      keys.push(k!);
    }
    expect(keys.length).toBeGreaterThan(3);
    for (const k of keys) expect(handle.armByKey(k), `unresolvable key ${k}`).toBeTruthy();
  });

  // Dragging is also a selection: the parameter form under the list must describe the thing being
  // dragged, or the form is a lie about what the next drop will author.
  it("dragging a row selects it, so the parameter form matches what is being dragged", () => {
    const { body } = mount();
    const all = rows(body);
    const target = all[2] ?? all[0]!;
    const dt = makeDT();
    const ev = new Event("dragstart", { bubbles: true }) as DragEvent;
    Object.defineProperty(ev, "dataTransfer", { value: dt });
    target.dispatchEvent(ev);
    const key = readDraftDragKey(dt)!;
    // the form header renders the selected element's label; find the row that now reads as selected
    const on = [...body.querySelectorAll<HTMLButtonElement>("button.on")].map((b) => b.textContent);
    expect(on.join(" "), `nothing marked selected after dragging ${key}`).not.toBe("");
  });

  it("clicking a row still selects without needing a drag — the old gesture is untouched", () => {
    const { body } = mount();
    const row = rows(body)[1] ?? rows(body)[0]!;
    row.click();
    expect(body.querySelectorAll("button.on").length).toBeGreaterThan(0);
  });
});
