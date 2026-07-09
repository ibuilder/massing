import { describe, expect, it } from "vitest";

import type { ElementProps } from "../api/client";
import { buildElementProps, buildRawProps, elementToText, formatValue } from "./propsView";

const sample: ElementProps = {
  guid: "3vB2eYHr1ABcDeFgHiJkLm",
  ifc_class: "IfcWallStandardCase",
  name: "Basic Wall:Exterior",
  type_name: "Exterior - Brick",
  storey: "Level 1",
  qtos: { Qto_WallBaseQuantities: { Length: 5.123456, Height: 3, GrossArea: 15.37, IsExternal: true } },
  psets: { Pset_WallCommon: { LoadBearing: false, FireRating: "2HR", ThermalTransmittance: 0.25 } },
};

describe("formatValue", () => {
  it("localizes numbers, rounds floats, maps booleans, dashes empties", () => {
    expect(formatValue(1234)).toBe((1234).toLocaleString());
    expect(formatValue(5.123456)).toBe(Number(5.123).toLocaleString(undefined, { maximumFractionDigits: 3 }));
    expect(formatValue(true)).toBe("Yes");
    expect(formatValue(false)).toBe("No");
    expect(formatValue(null)).toBe("—");
    expect(formatValue("")).toBe("—");
    expect(formatValue([])).toBe("—");
  });
  it("unwraps {value, unit} IFC wrappers", () => {
    expect(formatValue({ value: 0.25, unit: "W/m²K" })).toBe("0.25 W/m²K");
  });
});

describe("buildElementProps", () => {
  const root = buildElementProps(sample);

  it("shows the class badge, name and GUID", () => {
    expect(root.querySelector(".pv-class")?.textContent).toBe("WallStandardCase");  // Ifc stripped
    expect(root.querySelector(".pv-name")?.textContent).toBe("Basic Wall:Exterior");
    expect(root.querySelector(".pv-guid-v")?.textContent).toBe(sample.guid);
  });

  it("renders Quantities (the old panel dropped qtos entirely)", () => {
    const titles = [...root.querySelectorAll(".pv-sum-t")].map((e) => e.textContent);
    expect(titles).toContain("Quantities");
    expect(root.textContent).toContain("GrossArea");
    expect(root.textContent).toContain("FireRating");          // pset rendered too
  });

  it("groups every section and counts rows", () => {
    const groups = root.querySelectorAll(".pv-group");
    expect(groups.length).toBe(3);          // Attributes + Quantities + 1 pset
    const rows = root.querySelectorAll(".pv-row");
    expect(rows.length).toBe(4 + 4 + 3);    // attrs(4) + qto(4) + pset(3)
  });

  it("filters rows live by key/value across groups", () => {
    const r = buildElementProps(sample);
    const filter = r.querySelector<HTMLInputElement>(".pv-filter")!;
    filter.value = "firerating";
    filter.dispatchEvent(new Event("input"));
    const visible = [...r.querySelectorAll<HTMLElement>(".pv-row")].filter((row) => !row.hidden);
    expect(visible.length).toBe(1);
    expect(visible[0].textContent).toContain("FireRating");
    // its group is force-opened and others with no hits are hidden
    const hiddenGroups = [...r.querySelectorAll<HTMLElement>(".pv-group")].filter((g) => g.hidden);
    expect(hiddenGroups.length).toBe(2);
  });

  it("empty element shows a friendly note, not a blank panel", () => {
    const bare = buildElementProps({ ...sample, qtos: {}, psets: {} });
    expect(bare.querySelector(".pv-note")?.textContent).toContain("No property sets");
    expect(bare.querySelectorAll(".pv-group").length).toBe(1);   // just Attributes
  });
});

describe("elementToText (copy-all)", () => {
  it("includes attributes, quantities and property sets", () => {
    const t = elementToText(sample);
    expect(t).toContain("IfcWallStandardCase");
    expect(t).toContain("[Qto_WallBaseQuantities]");
    expect(t).toContain("FireRating: 2HR");
    expect(t).toContain("LoadBearing: No");
  });
});

describe("buildRawProps (in-browser fallback)", () => {
  it("renders arbitrary nested data as a collapsible tree", () => {
    const root = buildRawProps({ Name: "Wall", _category: "IFCWALL",
      IsDefinedBy: [{ Name: "Pset_X", HasProperties: [{ Name: "A", NominalValue: 1 }] }] });
    expect(root.querySelector(".props-view")).toBeNull();        // root IS .props-view
    expect(root.classList.contains("props-view")).toBe(true);
    expect(root.querySelectorAll(".pv-group").length).toBeGreaterThan(1);  // nested groups
    expect(root.textContent).toContain("IsDefinedBy");
    expect(root.textContent).toContain("Pset_X");
  });

  it("survives circular references without a stack overflow", () => {
    // getItemsData back-references would recurse forever without the cycle guard
    const a: Record<string, unknown> = { name: "A" };
    const b: Record<string, unknown> = { name: "B", parent: a };
    a.child = b; a.self = a;
    expect(() => buildRawProps({ root: a })).not.toThrow();
  });

  it("caps absurd depth instead of blowing the stack", () => {
    let deep: Record<string, unknown> = { v: 1 };
    for (let i = 0; i < 5000; i++) deep = { next: deep };
    expect(() => buildRawProps(deep)).not.toThrow();
  });

  it("adds the edit/classify form only when hooks are given, and wires the recipes", async () => {
    const calls: string[] = [];
    const hooks = {
      setProp: async (pset: string, prop: string, value: string, dtype: string) => {
        calls.push(`prop:${pset}/${prop}=${value}:${dtype}`);
      },
      classify: async (system: string, code: string, name: string) => {
        calls.push(`class:${system}/${code}/${name}`);
      },
    };
    // no hooks -> no editor
    expect(buildElementProps(sample).querySelector(".pv-edit")).toBeNull();
    // hooks -> editor present with both fieldsets
    const root = buildElementProps(sample, hooks);
    expect(root.querySelector(".pv-edit")).not.toBeNull();
    const btns = root.querySelectorAll<HTMLButtonElement>(".pv-edit-btn");
    expect(btns.length).toBe(2);
    const inputs = root.querySelectorAll<HTMLInputElement>(".pv-edit-i");
    // fieldset order: [0]Pset [1]Property [2]Value [3]Type(select) · [4]System [5]Code [6]Title
    inputs[0].value = "Pset_Custom"; inputs[1].value = "Manufacturer"; inputs[2].value = "Acme";
    btns[0].click();
    inputs[4].value = "Uniclass 2015"; inputs[5].value = "Pr_20_93_52"; inputs[6].value = "Steel column";
    btns[1].click();
    await Promise.resolve(); await Promise.resolve();
    expect(calls).toContain("prop:Pset_Custom/Manufacturer=Acme:str");
    expect(calls).toContain("class:Uniclass 2015/Pr_20_93_52/Steel column");
  });

  it("requires a property name and a classification code before calling a hook", async () => {
    let called = 0;
    const hooks = { setProp: async () => { called++; }, classify: async () => { called++; } };
    const root = buildElementProps(sample, hooks);
    const btns = root.querySelectorAll<HTMLButtonElement>(".pv-edit-btn");
    btns[0].click(); btns[1].click();       // both empty -> validation blocks
    await Promise.resolve();
    expect(called).toBe(0);
    expect(root.querySelector(".pv-edit-status")?.classList.contains("pv-edit-err")).toBe(true);
  });

  it("flattens IFC {value} / {value,type} wrappers into scalar rows, not sub-groups", () => {
    // raw getItemsData wraps every scalar — these must become rows, not 1-row groups
    const root = buildRawProps({
      _category: { value: "IFCWALL", type: 1 }, Name: { value: "Exterior Wall" }, Tag: { value: 1234 },
    });
    // 3 wrapped scalars -> 3 rows under one Element group (no per-field sub-group)
    const groups = root.querySelectorAll(".pv-group");
    expect(groups.length).toBe(1);
    expect(root.querySelectorAll(".pv-row").length).toBe(3);
    expect(root.textContent).toContain("Exterior Wall");   // unwrapped value shown
    expect(root.textContent).not.toContain("value");        // wrapper key hidden
  });
});
