import { describe, expect, it } from "vitest";
import { cadCommandList, parseCadCommand } from "./cadCommands";

describe("CADCMD grammar", () => {
  it("parses WALL with two points + default height", () => {
    const r = parseCadCommand("WALL 0,0 5,0");
    expect(r.kind).toBe("recipe");
    if (r.kind !== "recipe") return;
    expect(r.steps).toEqual([{ recipe: "add_wall", params: { start: [0, 0], end: [5, 0], height: 3 } }]);
  });

  it("is case-insensitive on the verb and honors the W alias + explicit height", () => {
    const r = parseCadCommand("w 1,1 1,4 2.7");
    expect(r.kind).toBe("recipe");
    if (r.kind !== "recipe") return;
    expect(r.steps[0]!).toEqual({ recipe: "add_wall", params: { start: [1, 1], end: [1, 4], height: 2.7 } });
  });

  it("COLUMN (C) with height + square width, z-coordinate ignored", () => {
    const r = parseCadCommand("C 2,2,0 3.2 0.5");
    expect(r.kind).toBe("recipe");
    if (r.kind !== "recipe") return;
    expect(r.steps[0]!).toEqual({ recipe: "add_column", params: { point: [2, 2], height: 3.2, width: 0.5, depth: 0.5 } });
  });

  it("BEAM with width + depth", () => {
    const r = parseCadCommand("BEAM 0,0 6,0 0.4 0.6");
    expect(r.kind).toBe("recipe");
    if (r.kind !== "recipe") return;
    expect(r.steps[0]!.params).toEqual({ start: [0, 0], end: [6, 0], width: 0.4, depth: 0.6 });
  });

  it("SLAB collects ≥3 points and reads a trailing bare number as thickness", () => {
    const r = parseCadCommand("SLAB 0,0 5,0 5,5 0,5 0.25");
    expect(r.kind).toBe("recipe");
    if (r.kind !== "recipe") return;
    expect(r.steps[0]!.recipe).toBe("add_slab");
    expect(r.steps[0]!.params).toEqual({ points: [[0, 0], [5, 0], [5, 5], [0, 5]], thickness: 0.25 });
  });

  it("SLAB without a trailing thickness uses the default", () => {
    const r = parseCadCommand("S 0,0 3,0 3,3");
    if (r.kind !== "recipe") throw new Error(r.kind);
    expect(r.steps[0]!.params).toMatchObject({ thickness: 0.2 });
    expect((r.steps[0]!.params.points as unknown[]).length).toBe(3);
  });

  it("WALL accepts a relative @dx,dy second point (offset from the first)", () => {
    const r = parseCadCommand("WALL 2,3 @5,0");
    if (r.kind !== "recipe") throw new Error(r.kind);
    expect(r.steps[0]!.params).toEqual({ start: [2, 3], end: [7, 3], height: 3 });
  });

  it("WALL accepts a relative polar @d<a second point (angle° CCW from east)", () => {
    const r = parseCadCommand("WALL 0,0 @5<90");            // 5 m due north (+y)
    if (r.kind !== "recipe") throw new Error(r.kind);
    const p = r.steps[0]!.params as { end: [number, number] };
    expect(p.end[0]).toBeCloseTo(0, 6);
    expect(p.end[1]).toBeCloseTo(5, 6);
  });

  it("absolute polar d<a is measured from the origin", () => {
    const r = parseCadCommand("WALL 0,0 10<0");            // 10 m due east
    if (r.kind !== "recipe") throw new Error(r.kind);
    const p = r.steps[0]!.params as { end: [number, number] };
    expect(p.end[0]).toBeCloseTo(10, 6);
    expect(p.end[1]).toBeCloseTo(0, 6);
  });

  it("SLAB walks a square from relative-polar legs off the first point", () => {
    const r = parseCadCommand("SLAB 0,0 @4<0 @4<90 @4<180 0.3");
    if (r.kind !== "recipe") throw new Error(r.kind);
    const pts = r.steps[0]!.params.points as [number, number][];
    expect(pts.length).toBe(4);
    expect(pts[1]![0]).toBeCloseTo(4, 6); expect(pts[1]![1]).toBeCloseTo(0, 6);   // east
    expect(pts[2]![0]).toBeCloseTo(4, 6); expect(pts[2]![1]).toBeCloseTo(4, 6);   // +north
    expect(pts[3]![0]).toBeCloseTo(0, 6); expect(pts[3]![1]).toBeCloseTo(4, 6);   // west
    expect(r.steps[0]!.params.thickness).toBe(0.3);
  });

  it("rejects malformed polar tokens instead of guessing", () => {
    expect(parseCadCommand("WALL 0,0 5<").kind).toBe("error");        // angle omitted
    expect(parseCadCommand("WALL 0,0 <45").kind).toBe("error");       // distance omitted
    expect(parseCadCommand("WALL 0,0 @5<45<90").kind).toBe("error");  // double '<'
    expect(parseCadCommand("WALL 0,0 @x<45").kind).toBe("error");     // non-numeric distance
  });

  it("LEVEL adds a storey at an elevation", () => {
    const r = parseCadCommand("LEVEL L3 7.0");
    if (r.kind !== "recipe") throw new Error(r.kind);
    expect(r.steps[0]!).toEqual({ recipe: "add_storey", params: { name: "L3", elevation: 7 } });
  });

  it("SPACE rounds and defaults to 4", () => {
    expect((parseCadCommand("SPACE") as { steps: { params: Record<string, unknown> }[] }).steps[0]!.params).toEqual({ rooms_per_storey: 4 });
    expect((parseCadCommand("SP 6") as { steps: { params: Record<string, unknown> }[] }).steps[0]!.params).toEqual({ rooms_per_storey: 6 });
  });

  it("HELP lists commands; HELP <cmd> shows one usage; ? is an alias for HELP", () => {
    expect(parseCadCommand("HELP").kind).toBe("info");
    expect(parseCadCommand("?").kind).toBe("info");
    const one = parseCadCommand("HELP WALL");
    expect(one.kind).toBe("info");
    if (one.kind === "info") expect(one.text).toContain("WALL x1,y1 x2,y2");
  });

  it("rejects bad input with a usage-bearing error, never throwing", () => {
    expect(parseCadCommand("").kind).toBe("error");
    expect(parseCadCommand("WALL 0,0").kind).toBe("error");          // one point
    expect(parseCadCommand("WALL 0,0 5,0 -1").kind).toBe("error");   // bad height
    expect(parseCadCommand("COLUMN nope").kind).toBe("error");       // bad point
    expect(parseCadCommand("SLAB 0,0 1,0").kind).toBe("error");      // <3 points
    expect(parseCadCommand("FLARB 1 2").kind).toBe("error");         // unknown verb
    const e = parseCadCommand("WALL 0,0");
    if (e.kind === "error") expect(e.text.toLowerCase()).toContain("usage");
  });

  it("exposes a command list for the help panel / autocomplete", () => {
    const list = cadCommandList();
    expect(list.map((c) => c.name)).toEqual(expect.arrayContaining(["WALL", "COLUMN", "BEAM", "SLAB", "LEVEL", "SPACE"]));
    for (const c of list) { expect(c.usage).toBeTruthy(); expect(c.summary).toBeTruthy(); }
  });
});
