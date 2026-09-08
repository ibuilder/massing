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
    expect(visible[0]!.textContent).toContain("FireRating"); // safe: length asserted to be 1 above
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
      resetProp: async (pset: string, prop: string) => { calls.push(`reset:${pset}/${prop}`); },
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
    inputs[0]!.value = "Pset_Custom"; inputs[1]!.value = "Manufacturer"; inputs[2]!.value = "Acme"; // safe: edit form renders 7 inputs
    btns[0]!.click(); // safe: btns.length asserted to be 2 above
    inputs[4]!.value = "Uniclass 2015"; inputs[5]!.value = "Pr_20_93_52"; inputs[6]!.value = "Steel column"; // safe: edit form renders 7 inputs
    btns[1]!.click(); // safe: btns.length asserted to be 2 above
    await Promise.resolve(); await Promise.resolve();
    expect(calls).toContain("prop:Pset_Custom/Manufacturer=Acme:str");
    expect(calls).toContain("class:Uniclass 2015/Pr_20_93_52/Steel column");
  });

  it("requires a property name and a classification code before calling a hook", async () => {
    let called = 0;
    const hooks = { setProp: async () => { called++; }, classify: async () => { called++; },
      resetProp: async () => { called++; } };
    const root = buildElementProps(sample, hooks);
    const btns = root.querySelectorAll<HTMLButtonElement>(".pv-edit-btn");
    btns[0]!.click(); btns[1]!.click();       // both empty -> validation blocks // safe: edit form renders 2 buttons
    await Promise.resolve();
    expect(called).toBe(0);
    expect(root.querySelector(".pv-edit-status")?.classList.contains("pv-edit-err")).toBe(true);
  });

  // --- PROP-OVERRIDE: the type-vs-instance answer, and the undo ------------------------------------
  //
  // The panel shipped the OVERRIDE half (set_element_pset) with no way to see that a value WAS
  // overridden and no way to undo it — `reset_prop_to_type` was reachable from nothing. The read
  // that answers it existed too, and its only caller threw the answer away, so no reachability
  // gate could see the gap: a route with no caller is caught, a PAYLOAD WITH NO READER is not.
  const EFFECTIVE = {
    guid: "g1", type_guid: "t1", type_name: "W-200", override_count: 1,
    psets: {
      Pset_WallCommon: {
        FireRating: { value: "120", source: "instance" as const, overridden: true, type_value: "60" },
        // LoadBearing is IN the sample's pset and NOT overridden — that overlap is what makes
        // "offered only where overridden" falsifiable. The first draft used a property the sample
        // does not carry, so a mutation deleting the `overridden` guard SURVIVED: nothing else
        // lined up, and the count stayed 1 for the wrong reason. *A fixture that cannot express
        // the failure reports the check as passing.*
        LoadBearing: { value: false, source: "type" as const, overridden: false, type_value: false },
      },
    },
  };
  const overriddenRow = (root: HTMLElement) => root.querySelector<HTMLElement>(".pv-row.pv-overridden");

  it("marks an overridden value, names what the TYPE says, and offers the undo", () => {
    const hooks = { setProp: async () => {}, classify: async () => {}, resetProp: async () => {} };
    const root = buildElementProps(sample, hooks, null, EFFECTIVE);
    const r = overriddenRow(root);
    expect(r, "the overridden property is marked").not.toBeNull();
    expect(r!.querySelector(".pv-ovr")?.textContent).toBe("overridden");
    // a badge alone says a value was replaced without saying what it replaced — half an answer
    expect(r!.querySelector(".pv-ovr-was")?.textContent, "the shadowed type value is SHOWN").toBe("type: 60");
    expect(r!.querySelector(".pv-ovr-reset"), "and the undo is offered").not.toBeNull();
    // ...and only there: a value inherited from the type is not an override and gets no control
    expect(root.querySelectorAll(".pv-ovr-reset").length, "offered ONLY where overridden").toBe(1);
    // ...and it is the RIGHT row. The fixture's pset is {LoadBearing, FireRating, Thermal…} and the
    // override is the SECOND, so a positional match would mark LoadBearing and offer a Reset that
    // clears the wrong property. Asserted on the rendered key, not on an index.
    expect(r!.dataset.k, "marked the property the provenance names").toBe("FireRating");
    expect(r!.querySelector(".pv-k")?.textContent).toBe("FireRating");
  });

  it("passes the pset and property the reset recipe takes", async () => {
    const calls: string[] = [];
    const hooks = { setProp: async () => {}, classify: async () => {},
      resetProp: async (pset: string, prop: string) => { calls.push(`${pset}/${prop}`); } };
    const root = buildElementProps(sample, hooks, null, EFFECTIVE);
    root.querySelector<HTMLButtonElement>(".pv-ovr-reset")!.click();
    await Promise.resolve(); await Promise.resolve();
    expect(calls, "the (pset, prop) pair, not the row index").toEqual(["Pset_WallCommon/FireRating"]);
  });

  it("does not also COPY the row when the reset button is pressed", async () => {
    // the row copies on click; a destructive action must not carry a second, unasked-for effect
    let rowClicks = 0;
    const hooks = { setProp: async () => {}, classify: async () => {}, resetProp: async () => {} };
    const root = buildElementProps(sample, hooks, null, EFFECTIVE);
    const r = overriddenRow(root)!;
    r.addEventListener("click", () => { rowClicks++; });
    r.querySelector<HTMLButtonElement>(".pv-ovr-reset")!.click();
    await Promise.resolve();
    expect(rowClicks, "stopPropagation keeps the row's copy handler out of it").toBe(0);
  });

  it("reports a failed reset through the form's own status line, and restores the button", async () => {
    const hooks = { setProp: async () => {}, classify: async () => {},
      resetProp: async () => { throw new Error("no type value"); } };
    const root = buildElementProps(sample, hooks, null, EFFECTIVE);
    const btn = root.querySelector<HTMLButtonElement>(".pv-ovr-reset")!;
    btn.click();
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    const status = root.querySelector(".pv-edit-status");
    expect(status?.textContent, "one status surface, not a second one").toContain("no type value");
    expect(status?.classList.contains("pv-edit-err")).toBe(true);
    expect(btn.disabled, "and the control comes back").toBe(false);
    expect(btn.textContent).toBe("Reset to type");
  });

  it("SAYS SO when the provenance read failed, rather than showing an unmarked list", () => {
    // null = asked and failed. Rendering no badges would assert "nothing is overridden" — a claim
    // the panel cannot back, and indistinguishable from the absence of an answer.
    const hooks = { setProp: async () => {}, classify: async () => {}, resetProp: async () => {} };
    const failed = buildElementProps(sample, hooks, null, null);
    expect(failed.textContent, "the failure is named").toContain("Could not read which values are overridden");
    expect(failed.querySelector(".pv-overridden"), "and nothing is marked").toBeNull();
    // undefined = never asked (a read-only viewer). Different answer; it must stay silent.
    const notAsked = buildElementProps(sample, hooks, null, undefined);
    expect(notAsked.textContent).not.toContain("Could not read which values are overridden");
  });

  it("shows the marker but no control when the panel cannot write", () => {
    // read-only: the ANSWER is still worth showing; the action is not available to offer
    const root = buildElementProps(sample, undefined, null, EFFECTIVE);
    expect(overriddenRow(root), "still marked").not.toBeNull();
    expect(root.querySelector(".pv-ovr-reset"), "but no undo without hooks").toBeNull();
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
