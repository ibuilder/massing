import { describe, expect, it } from "vitest";
import {
  contentToDraftElement, DRAFT_ELEMENTS, familyToDraftElement, flattenContentCatalog,
  type ContentDef, type FamilyDef,
} from "./draftCatalog";

const byKey = (k: string) => DRAFT_ELEMENTS.find((e) => e.key === k)!;

describe("draft catalog build() → recipe params", () => {
  it("wall maps two points + height/thickness to add_wall params", () => {
    const wall = byKey("wall");
    expect(wall.recipe).toBe("add_wall");
    expect(wall.points).toBe(2);
    const p = wall.build([[0, 0], [5, 0]], { height: 3, thickness: 0.2 });
    expect(p).toEqual({ start: [0, 0], end: [5, 0], height: 3, thickness: 0.2 });
  });

  it("column maps one point + height/width/depth to add_column params", () => {
    const col = byKey("column");
    expect(col.points).toBe(1);
    const p = col.build([[2, 3]], { height: 4, width: 0.5, depth: 0.5 });
    expect(p).toEqual({ point: [2, 3], height: 4, width: 0.5, depth: 0.5 });
  });

  it("slab is a poly element mapping all points to add_slab", () => {
    const slab = byKey("slab");
    expect(slab.points).toBe("poly");
    const pts: [number, number][] = [[0, 0], [4, 0], [4, 4], [0, 4]];
    expect(slab.build(pts, { thickness: 0.25 })).toEqual({ points: pts, thickness: 0.25 });
  });

  it("beam maps start/end + width/depth to add_beam params", () => {
    const p = byKey("beam").build([[0, 0], [6, 0]], { width: 0.3, depth: 0.6 });
    expect(p).toEqual({ start: [0, 0], end: [6, 0], width: 0.3, depth: 0.6 });
  });

  it("R38-STAIR — stair and ramp map two plan points + width to their recipes", () => {
    // The build sends NO storey/target_storey/rise: the run is placed where it was drawn and the
    // server derives the rise (active storey → next, or +3.0 m). Compliance is reported, not
    // enforced — a run silently lengthened to satisfy a limit no longer arrives where it was drawn.
    const stair = byKey("stair");
    expect(stair.recipe).toBe("add_stair");
    expect(stair.points).toBe(2);
    expect(stair.build([[0, 0], [4, 0]], { width: 1.2 }))
      .toEqual({ start: [0, 0], end: [4, 0], width: 1.2 });
    const ramp = byKey("ramp");
    expect(ramp.recipe).toBe("add_ramp");
    expect(ramp.build([[0, 0], [12, 0]], { width: 1.5 }))
      .toEqual({ start: [0, 0], end: [12, 0], width: 1.5 });
  });

  it("every built-in element declares params and a recipe", () => {
    for (const e of DRAFT_ELEMENTS) {
      expect(e.recipe).toBeTruthy();
      expect(e.ifcClass.startsWith("Ifc")).toBe(true);
      expect(Array.isArray(e.params)).toBe(true);
    }
  });
});

describe("familyToDraftElement", () => {
  const fam: FamilyDef = { key: "toilet", label: "Toilet", ifc_class: "IfcSanitaryTerminalType", category: "Sanitary", dims: [0.4, 0.7, 0.8] };

  it("wraps a server family as a 1-point add_family element with W/D/H defaults from dims", () => {
    const el = familyToDraftElement(fam);
    expect(el.key).toBe("family:toilet");
    expect(el.recipe).toBe("add_family");
    expect(el.points).toBe(1);
    expect(el.discipline).toBe("MEP");   // Sanitary → MEP
    const defaults = Object.fromEntries(el.params.map((p) => [p.key, p.default]));
    expect(defaults).toEqual({ width: 0.4, depth: 0.7, height: 0.8 });
  });

  it("build() passes the family key + position + edited dims to add_family", () => {
    const el = familyToDraftElement(fam);
    const p = el.build([[1, 2]], { width: 0.5, depth: 0.7, height: 0.85 });
    expect(p).toEqual({ family: "toilet", position: [1, 2], dims: [0.5, 0.7, 0.85] });
  });
});

/**
 * CONTENT-DRAFT — the 19 CONTENT-1 items were the only placeable things in the app that could be
 * neither armed nor dragged.
 *
 * `DRAFT_ELEMENTS` and every family have been click- and drag-placeable from the Draw rail since
 * RAIL-DRAG. Content appeared only in the Library palette, which is a **modal**
 * (`.result-overlay` is `position: fixed; inset: 0` with a scrim), so nothing could be dragged out
 * of it and its only placement affordance was a prompt asking for "Location E, N (metres)". You
 * could not put a tree, a crane or a desk where you were pointing.
 *
 * Wrapping content as a `DraftElement` fixes both affordances at once rather than adding a second
 * placement path: `allElements()` feeds the row buttons, the search, the discipline chips AND
 * `armByKey`, which is the function the viewport's `drop` handler calls.
 */
describe("contentToDraftElement", () => {
  const tree: ContentDef = {
    key: "tree", ifc_class: "IfcGeographicElement", phase: null,
    classification: "23-45 00 00 Landscape", default_dims_m: [3, 3, 6],
  };

  it("wraps a catalog item as a 1-point place_content element", () => {
    const el = contentToDraftElement(tree, "Landscape");
    expect(el.key).toBe("content:tree");
    expect(el.label).toBe("Tree (Landscape)");
    expect(el.recipe).toBe("place_content");
    expect(el.points).toBe(1);
    expect(el.ifcClass).toBe("IfcGeographicElement");
  });

  it("has NO params, because place_content sizes from the catalog and takes no dims", () => {
    // Asserted rather than left implicit: a dims form here would render inputs the recipe discards,
    // which is a control that looks like it does something and does not.
    expect(contentToDraftElement(tree, "Landscape").params).toEqual([]);
  });

  it("build() sends the catalog KEY as `category`, which is what the server names it", () => {
    // The catalog calls the string `key` and the recipe calls it `category`. Sending the label
    // instead 400s with "unknown content category" — hence a test on the exact payload.
    expect(contentToDraftElement(tree, "Landscape").build([[4, 5]], {}))
      .toEqual({ category: "tree", point: [4, 5] });
  });

  it("maps each catalog bucket to the discipline chip that lists it", () => {
    expect(contentToDraftElement(tree, "Landscape").discipline).toBe("Site");
    expect(contentToDraftElement({ ...tree, key: "hoist" }, "Site Logistics").discipline).toBe("Site");
    expect(contentToDraftElement({ ...tree, key: "desk" }, "FF&E").discipline).toBe("Architectural");
    // an unknown bucket must still LIST somewhere — a default of undefined would hide the item from
    // every chip, which reads as "the catalog shrank" rather than "a bucket was added".
    expect(contentToDraftElement({ ...tree, key: "x" }, "Newly Added Bucket").discipline).toBe("Site");
  });

  it("humanises the key AND names the bucket, because 8 of 19 keys collide with a family", () => {
    // bed, chair, desk, planter, shrub, sofa, table, tree all exist as families too, and the row's
    // meta badge strips "Ifc"/"Type" so IfcFurnitureType and IfcFurniture both read "Furniture".
    // Two rows saying "Desk" that author different recipes is the papercut this suffix prevents.
    expect(contentToDraftElement({ ...tree, key: "site_office" }, "Site Logistics").label)
      .toBe("Site office (Site Logistics)");
    expect(contentToDraftElement({ ...tree, key: "desk" }, "FF&E").label).toBe("Desk (FF&E)");
  });

  it("the hint names the item, not the decorated label", () => {
    expect(contentToDraftElement(tree, "Landscape").hint).toBe("Click where to place the tree.");
  });
});

describe("flattenContentCatalog", () => {
  it("pairs every item with its bucket", () => {
    const c: ContentDef = {
      key: "desk", ifc_class: "IfcFurniture", phase: null, classification: "", default_dims_m: [1, 1, 1],
    };
    expect(flattenContentCatalog({ groups: { "FF&E": [c], Landscape: [{ ...c, key: "tree" }] } }))
      .toEqual([[c, "FF&E"], [{ ...c, key: "tree" }, "Landscape"]]);
  });

  it("survives an empty or absent groups map rather than throwing into the panel", () => {
    // The panel loads this lazily and catches, but a throw here would take the whole Draw list with
    // it on a server that returns a shape we did not expect.
    expect(flattenContentCatalog({ groups: {} })).toEqual([]);
    expect(flattenContentCatalog({} as { groups: Record<string, ContentDef[]> })).toEqual([]);
  });
});

/**
 * DARK-RECIPES — `extrude_profile` was implemented, tested and reachable from nothing.
 *
 * The engine side is covered by `services/api/test_wall_slope.py`. What no test covered is the
 * CONTRACT between this catalog entry and the recipe's parameter names, and that is where the risk
 * is: `build()` returns `Record<string, unknown>`, so a key typo — `ifcClass` for `ifc_class` —
 * typechecks perfectly and fails only at runtime, against a real model, after a round trip. The
 * sibling content entry had exactly this shape of trap (`category` vs `key`).
 *
 * Verified against the live recipe while writing this: these params authored an
 * IfcBuildingElementProxy contained in the active storey, and switching `ifc_class` to IfcSlab
 * authored an IfcSlab.
 */
describe("extrude_profile — sketch-to-BIM", () => {
  const el = () => DRAFT_ELEMENTS.find((e) => e.key === "extrusion")!;

  it("is a poly-point element on the extrude_profile recipe", () => {
    expect(el()).toBeTruthy();
    expect(el().recipe).toBe("extrude_profile");
    expect(el().points).toBe("poly");
  });

  it("build() emits exactly the keys the recipe reads", () => {
    // edit.py: extrude_profile(m, p["points"], p.get("height"), p.get("ifc_class"), p.get("name"),
    //                          p.get("storey"), p.get("z"))
    const p = el().build([[0, 0], [6, 0], [6, 4], [0, 4]],
                         { height: 3, z: 0.5, ifc_class: "IfcSlab" });
    expect(p).toEqual({ points: [[0, 0], [6, 0], [6, 4], [0, 4]], height: 3, z: 0.5, ifc_class: "IfcSlab" });
    // `storey` is deliberately absent: finishDraft injects the active level, and a value baked in
    // here would override the level the user is working on — the LEVEL-PLACE defect, inverted.
    expect(Object.keys(p)).not.toContain("storey");
  });

  it("defaults to a generic mass, which is the recipe's own default", () => {
    const byKey = Object.fromEntries(el().params.map((x) => [x.key, x.default]));
    expect(byKey.ifc_class).toBe("IfcBuildingElementProxy");
    expect(byKey.height).toBe(3);
  });
});
