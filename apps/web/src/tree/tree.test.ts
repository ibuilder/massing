/**
 * R43-VIEWER-CONFORMANCE — the model browser groups on the storey's GlobalId, not on its NAME.
 *
 * The tree had four group-by modes and every one of them keyed on a string. "By level" used
 * `el.storey`, which is an IfcBuildingStorey's `Name` — and a name is not an identity. One site with
 * two buildings, each having a "Level 2", is the ordinary case on any campus or multi-tower job, and
 * the string-keyed tree merged them into a single node with no symptom at all: the count was right,
 * the elements were all there, and they were shown as being on one floor of one building.
 *
 * So the assertions here are mostly about that ONE model. `twoTowers()` is the fixture, and the
 * central test is that "Level 2" appears twice under two different parents — which the old grouping
 * cannot do and which is therefore the thing worth asserting rather than the happy path.
 *
 * The rest guard the ways a fix like this quietly reverts:
 *
 *   - **The mode is absent when the server sends no tree.** A project whose element index predates
 *     `index_schema: 2` gets a 422, and the panel passes `null`. A "By spatial structure" option
 *     that silently fell back to storey names would be the original defect wearing the fix's label —
 *     strictly worse than not offering it, because the label now vouches for it.
 *   - **Elements with no `storey_guid` get their own bucket** rather than being filed under a
 *     guessed storey. "We do not know where this is" is an answer.
 *   - **Siblings that share a name are disambiguated.** Grouping by guid and then LABELLING by name
 *     re-introduces the collision one level up if two buildings are also called the same thing.
 */
import { describe, expect, it } from "vitest";
import type { ElementProps, SpatialNode } from "../api/client";
import { buildTree } from "./tree";

const node = (guid: string, ifcClass: string, name: string, children: SpatialNode[] = []): SpatialNode =>
  ({ ref: { modelId: "m1", guid }, ifcClass, name, children });

/** One site, two buildings, a same-named storey in each — the model that separates the two designs. */
function twoTowers(): SpatialNode {
  return node("proj00", "IfcProject", "Two Towers", [
    node("site00", "IfcSite", "Riverside", [
      node("bldgA0", "IfcBuilding", "Tower A", [node("stA200", "IfcBuildingStorey", "Level 2")]),
      node("bldgB0", "IfcBuilding", "Tower B", [node("stB200", "IfcBuildingStorey", "Level 2")]),
    ]),
  ]);
}

const el = (guid: string, storeyGuid: string | null, ifcClass = "IfcWall"): ElementProps => ({
  guid,
  ifc_class: ifcClass,
  name: `el-${guid}`,
  type_name: null,
  storey: "Level 2",          // the SAME name on purpose: the string cannot tell these apart
  storey_guid: storeyGuid,
  psets: {},
  qtos: {},
});

const ELEMENTS = [el("w1", "stA200"), el("w2", "stB200"), el("w3", null)];

/**
 * Every group label in the tree, read back out of the DOM after opening it fully.
 *
 * The tree builds a group's children lazily, on the click that expands it — so a naive
 * `querySelectorAll` sees only the top row and every assertion below would pass or fail on the wrong
 * evidence. This clicks until no new header appears, which is also a cheap check that expansion
 * terminates. `.tree-node` only: an earlier version also matched bare `li`, which counted each
 * header twice and turned "one node" into "two".
 */
function labels(root: HTMLElement): string[] {
  for (let guard = 0; guard < 20; guard++) {
    const closed = [...root.querySelectorAll<HTMLElement>(".tree-node")]
      .filter((h) => h.textContent?.startsWith("▸"));
    if (closed.length === 0) break;
    for (const h of closed) h.click();
  }
  return [...root.querySelectorAll<HTMLElement>(".tree-node")]
    .map((n) => (n.textContent ?? "").replace(/^[▸▾]\s*/, ""))
    .filter(Boolean);
}

function modeOptions(root: HTMLElement): string[] {
  return [...root.querySelectorAll<HTMLOptionElement>(".tree-groupby option")].map((o) => o.value);
}

describe("model browser — spatial grouping", () => {
  it("offers the spatial mode only when the server actually sent a tree", () => {
    expect(modeOptions(buildTree(ELEMENTS, () => {}, twoTowers()))).toContain("spatial");
    // The twin, and the one that matters: no tree, no mode. A 422 (index predates the tree) and a
    // 404 (model has no IfcProject) both arrive here as null.
    expect(modeOptions(buildTree(ELEMENTS, () => {}, null))).not.toContain("spatial");
    expect(modeOptions(buildTree(ELEMENTS, () => {}))).not.toContain("spatial");
  });

  it("treats a NON-node payload as no tree — the Pages demo serves `[]` for an uncaptured GET", () => {
    // `demo/demoApi.ts` degrades an uncaptured GET to `[]` instead of throwing, and `[]` is truthy.
    // Before the shape check, that reached the walk, read `.children` off an array as `undefined`,
    // and took the model browser down in the one build that has no backend to blame.
    const junk = [] as unknown as SpatialNode;
    expect(() => buildTree(ELEMENTS, () => {}, junk)).not.toThrow();
    expect(modeOptions(buildTree(ELEMENTS, () => {}, junk))).not.toContain("spatial");
    const half = { ref: { modelId: "m", guid: "g" }, ifcClass: "IfcProject", name: "P" } as SpatialNode;
    expect(modeOptions(buildTree(ELEMENTS, () => {}, half))).not.toContain("spatial");
  });

  it("defaults to the spatial mode when it is available", () => {
    const tree = buildTree(ELEMENTS, () => {}, twoTowers());
    expect((tree.querySelector(".tree-groupby") as HTMLSelectElement).value).toBe("spatial");
  });

  it("keeps two same-named storeys apart, under their own buildings", () => {
    const text = labels(buildTree(ELEMENTS, () => {}, twoTowers())).join(" | ");
    expect(text).toContain("Tower A");
    expect(text).toContain("Tower B");
    // The proof this is not the string-grouped tree: "Level 2" is rendered twice, once per building.
    const levelTwos = labels(buildTree(ELEMENTS, () => {}, twoTowers()))
      .filter((t) => t.startsWith("Level 2 ("));
    expect(levelTwos.length, "one node per storey GUID, not one per storey NAME").toBe(2);
  });

  it("...whereas the name-keyed mode merges them — the defect, asserted so it stays visible", () => {
    const tree = buildTree(ELEMENTS, () => {}, twoTowers());
    const select = tree.querySelector(".tree-groupby") as HTMLSelectElement;
    select.value = "storey";
    select.onchange?.(new Event("change"));
    const levelTwos = labels(tree).filter((t) => t.startsWith("Level 2 ("));
    expect(levelTwos.length, "'By level' groups on the NAME and therefore merges; that is what "
      + "'By spatial structure' exists to fix, and this asserts the difference is real").toBe(1);
  });

  it("files an element with no storey_guid under (not placed), never under a guessed storey", () => {
    const text = labels(buildTree(ELEMENTS, () => {}, twoTowers())).join(" | ");
    expect(text).toContain("(not placed)");
  });

  it("disambiguates siblings that share a name, so the collision cannot reappear one level up", () => {
    const twins = node("proj00", "IfcProject", "P", [
      node("site00", "IfcSite", "S", [
        node("bldgA0", "IfcBuilding", "Tower", [node("stA200", "IfcBuildingStorey", "L2")]),
        node("bldgB0", "IfcBuilding", "Tower", [node("stB200", "IfcBuildingStorey", "L2")]),
      ]),
    ]);
    const text = labels(buildTree(ELEMENTS, () => {}, twins)).join(" | ");
    expect(text).toContain("Tower · bldgA0");
    expect(text).toContain("Tower · bldgB0");
    // ...and both storeys still resolve, rather than one shadowing the other.
    expect(labels(buildTree(ELEMENTS, () => {}, twins)).filter((t) => t.startsWith("L2 (")).length)
      .toBe(2);
  });

  it("selecting a leaf still reports the element's GUID — the only key that survives a reload", () => {
    const picked: string[] = [];
    const tree = buildTree(ELEMENTS, (g) => picked.push(g), twoTowers());
    labels(tree);                                   // leaves are built lazily, on expansion
    const leaves = [...tree.querySelectorAll<HTMLElement>(".tree-leaf")];
    // Asserted BEFORE the click, and not folded into the assertion after it. The first version of
    // this test said `picked.length === 0 || picked[0]`, which passes when nothing is clickable at
    // all — a selection test that cannot fail if selection is broken.
    expect(leaves.length, "every element must be reachable as a leaf").toBe(ELEMENTS.length);
    leaves[0]!.click();
    expect(picked.length, "one click, one selection").toBe(1);
    expect(picked[0], "the leaf reports the element's GlobalId, not its label or its index")
      .toBe(ELEMENTS.find((e) => `el-${e.guid}` === leaves[0]!.textContent)?.guid);
  });
});
