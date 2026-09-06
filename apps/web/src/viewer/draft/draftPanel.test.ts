import { describe, expect, it, vi } from "vitest";
import { installDraftPanel, type ArmedDraft } from "./draftPanel";
import { type ContentDef } from "./draftCatalog";
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

function mount(content: [ContentDef, string][] = []) {
  const body = document.createElement("div");
  document.body.appendChild(body);
  const armed: (ArmedDraft | null)[] = [];
  const handle = installDraftPanel({
    body,
    fetchFamilies: () => Promise.resolve([]), fetchContent: () => Promise.resolve(content),
    arm: (a) => { armed.push(a); },
    notify: vi.fn((_m: string, _k?: "info" | "success" | "error") => {}),
    canAuthor: () => true,
  });
  return { body, armed, handle };
}

const TREE: ContentDef = {
  key: "tree", ifc_class: "IfcGeographicElement", phase: null,
  classification: "23-45 00 00", default_dims_m: [3, 3, 6],
};

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

/**
 * CONTENT-DRAFT — content must be reachable through the SAME two affordances as everything else.
 *
 * Asserting `contentToDraftElement` returns the right object proves nothing about whether the panel
 * ever lists it: "the engine exists and nothing calls it" is the defect this file's own header names
 * as the repo's most-repeated. So these drive the real panel, and the arming case goes through
 * `armByKey` specifically — the function the viewport's `drop` handler calls — rather than through a
 * row click, because that is the path a drag actually takes.
 */
describe("CONTENT-DRAFT — content lists, arms and drags like any other element", () => {
  it("lists a content item once its catalog resolves", async () => {
    const { body } = mount([[TREE, "Landscape"]]);
    // Landscape → Site, so switch the chip before looking: an item filtered out by the discipline
    // it was assigned is indistinguishable from an item that never loaded.
    await Promise.resolve(); await Promise.resolve();
    const site = [...body.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Site");
    expect(site, "no Site discipline chip").toBeTruthy();
    site!.click();
    expect(rows(body).map((r) => r.textContent)).toContain("Tree (Landscape)GeographicElement");
  });

  it("armByKey arms a content item — the path a DROP takes", async () => {
    const { armed, handle } = mount([[TREE, "Landscape"]]);
    await Promise.resolve(); await Promise.resolve();
    expect(handle.armByKey("content:tree")).toBe("Tree (Landscape)");
    const a = armed.at(-1);
    expect(a?.recipe).toBe("place_content");
    expect(a?.points).toBe(1);
    expect(a?.build([[7, 8]])).toEqual({ category: "tree", point: [7, 8] });
  });

  it("a content row is draggable and carries its key, like the built-ins", async () => {
    const { body } = mount([[TREE, "Landscape"]]);
    await Promise.resolve(); await Promise.resolve();
    const site = [...body.querySelectorAll<HTMLButtonElement>("button")]
      .find((b) => b.textContent === "Site");
    site!.click();
    const row = rows(body).find((r) => r.textContent?.startsWith("Tree (Landscape)"));
    expect(row, "the content row is not a drag source").toBeTruthy();
    const dt = makeDT();
    row!.dispatchEvent(Object.assign(new Event("dragstart"), { dataTransfer: dt }));
    expect(readDraftDragKey(dt)).toBe("content:tree");
    expect(dt.types).toContain(DRAFT_DRAG_MIME);
  });

  it("an unknown key still refuses, so a stale drag cannot arm the wrong thing", async () => {
    const { handle } = mount([[TREE, "Landscape"]]);
    await Promise.resolve(); await Promise.resolve();
    expect(handle.armByKey("content:no_such_item")).toBeNull();
  });
});

/**
 * A query spans every discipline. Until this changed the search was ANDed with the active chip, so
 * typing "column" on the Architectural chip answered "No elements for this discipline yet." — the
 * palette denying that a column exists. A wrong answer, not a slow one.
 */
describe("the search box is not scoped to the active discipline", () => {
  const filter = (body: HTMLElement) =>
    body.querySelector<HTMLInputElement>("input[type=search]")!;
  const type = (body: HTMLElement, q: string) => {
    const f = filter(body); f.value = q; f.dispatchEvent(new Event("input"));
  };

  it("finds a Structural element while the Architectural chip is active", () => {
    const { body } = mount();
    // Architectural is the default chip, and `column` is Structural — the exact miss.
    type(body, "column");
    const labels = rows(body).map((r) => r.textContent ?? "");
    expect(labels.some((l) => l.includes("Column")), `got: ${labels.join(" | ")}`).toBe(true);
  });

  it("says which discipline an off-chip hit came from, so the result is readable", () => {
    const { body } = mount();
    type(body, "column");
    const row = rows(body).find((r) => r.textContent?.includes("Column"));
    expect(row?.textContent).toContain("Structural");
  });

  it("with no query the chip still scopes the list — the chips did not become decoration", () => {
    const { body } = mount();
    type(body, "");
    const labels = rows(body).map((r) => r.textContent ?? "");
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.some((l) => l.includes("Column")),
      "a Structural element is listed under the Architectural chip with no query").toBe(false);
  });

  it("a query that matches nothing says so in the query's terms, not the chip's", async () => {
    const { body } = mount();
    // Awaited on purpose: until the families settle the panel says "loading families…", which is the
    // correct answer to "nothing matches" when a third of the catalog has not arrived yet.
    await Promise.resolve(); await Promise.resolve();
    type(body, "zzzznotathing");
    expect(rows(body)).toHaveLength(0);
    expect(body.textContent).toContain("zzzznotathing");
  });
});
