import { describe, expect, it } from "vitest";
import { DRAFT_ELEMENTS, familyToDraftElement, type FamilyDef } from "./draftCatalog";

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
