import { describe, expect, it, vi } from "vitest";

import { type SpecManual, SpecPane, sectionDomId, sectionForGuid } from "./specPane";

/**
 * The Specs canvas, and the distinction the whole pane turns on.
 *
 * `elements` is capped at 50 per section server-side while `element_count` is the true total. So for
 * a large section the pane can answer "which section is this element in" for the first 50 and cannot
 * for the rest. Those two misses must not look the same: "this element has no spec section" is a
 * claim about the model, and "I cannot see far enough to tell" is a claim about the payload. Letting
 * the second render as the first is how a UI states a falsehood confidently.
 */

function manual(over: Partial<SpecManual> = {}): SpecManual {
  return {
    system: "MasterFormat", section_count: 2, division_count: 1, note: "",
    divisions: [{
      division: "08", title: "Openings",
      sections: [
        { code: "08 11 00", title: "Metal Doors and Frames", element_count: 2,
          part1_general: "Summary", part2_products: ["Steel"], part3_execution: ["Install"],
          elements: [{ guid: "DOOR_1", name: "Door 1", ifc_class: "IfcDoor" },
            { guid: "DOOR_2", name: "Door 2", ifc_class: "IfcDoor" }] },
        // a section whose list is CAPPED: 400 real elements, 2 listed
        { code: "08 51 00", title: "Metal Windows", element_count: 400,
          part1_general: "Summary", part2_products: ["Aluminium"], part3_execution: ["Install"],
          elements: [{ guid: "WIN_1", name: "Window 1", ifc_class: "IfcWindow" },
            { guid: "WIN_2", name: "Window 2", ifc_class: "IfcWindow" }] },
      ],
    }],
    ...over,
  };
}

describe("sectionForGuid distinguishes 'no section' from 'cannot tell'", () => {
  it("finds the section that lists the element", () => {
    const hit = sectionForGuid(manual(), "DOOR_2");
    expect(hit.found?.code).toBe("08 11 00");
  });

  it("a miss where every list is COMPLETE is a real 'no spec section'", () => {
    // Only complete sections here, so absence is a fact about the model.
    const m = manual({
      divisions: [{ division: "08", title: "Openings", sections: [
        { code: "08 11 00", title: "Doors", element_count: 1, part1_general: "", part2_products: [],
          part3_execution: [], elements: [{ guid: "DOOR_1", name: "D", ifc_class: "IfcDoor" }] },
      ] }],
    });
    expect(sectionForGuid(m, "NOT_SPECIFIED")).toEqual({ found: null, truncated: false });
  });

  it("a miss where ANY list is capped reports truncated — the pane must not claim 'no section'", () => {
    // The window section lists 2 of 400. An unlisted window is unknown, not unspecified.
    expect(sectionForGuid(manual(), "WIN_137")).toEqual({ found: null, truncated: true });
  });

  it("no selection is a complete answer, not a truncated one", () => {
    expect(sectionForGuid(manual(), null)).toEqual({ found: null, truncated: false });
  });
});

describe("sectionDomId survives the punctuation in a MasterFormat code", () => {
  it("produces a selector-safe id from spaces and digits", () => {
    expect(sectionDomId("08 11 00")).toBe("spec-sec-08-11-00");
    // Distinct codes must not collide into one id, or highlighting lands on the wrong section.
    expect(sectionDomId("08 11 00")).not.toBe(sectionDomId("08 51 00"));
  });
});

describe("the pane as a canvas surface", () => {
  it("renders divisions and sections, and says when a list is capped", async () => {
    const p = new SpecPane({ load: async () => manual(), notify: () => {} });
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("[data-spec-code]").length).toBe(2));

    const capped = p.el.querySelector("#spec-sec-08-51-00");
    expect(capped?.textContent, "a capped list must say so — 400 elements shown as 2 with no note "
      + "reads as the whole set").toMatch(/400 element\(s\) — listing the first 2/);

    const complete = p.el.querySelector("#spec-sec-08-11-00");
    expect(complete?.textContent).toMatch(/2 element\(s\)/);
    expect(complete?.textContent).not.toMatch(/listing the first/);
  });

  it("reveals the section for a selection made BEFORE the pane rendered", async () => {
    // The cross-mode contract, same as the plan: the guid is stored while hidden and applied on
    // arrival, because the identity is a GlobalId rather than a node reference.
    const p = new SpecPane({ load: async () => manual(), notify: () => {} });
    p.highlight("DOOR_2");
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("[data-spec-code]").length).toBe(2));
    expect(p.el.querySelector("#spec-sec-08-11-00")?.classList.contains("on")).toBe(true);
    expect(p.el.querySelector("#spec-sec-08-51-00")?.classList.contains("on")).toBe(false);
  });

  it("says 'not in the first 50' rather than 'no spec section' for a capped miss", async () => {
    const p = new SpecPane({ load: async () => manual(), notify: () => {} });
    p.highlight("WIN_137");
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("[data-spec-code]").length).toBe(2));
    const sub = p.el.querySelector(".spec-pane-sub")?.textContent ?? "";
    expect(sub, "a capped miss reported as 'no spec section' is the pane stating a falsehood")
      .toMatch(/not in the first 50/);
    expect(sub).not.toMatch(/has no spec section/);
  });

  it("clicking an element chip selects it in the model, by GlobalId", async () => {
    const onPick = vi.fn();
    const p = new SpecPane({ load: async () => manual(), notify: () => {}, onPick });
    p.dock("full");
    await vi.waitFor(() => expect(p.el.querySelectorAll("button[data-guid]").length).toBeGreaterThan(0));
    p.el.querySelector<HTMLButtonElement>('button[data-guid="WIN_2"]')!.click();
    expect(onPick).toHaveBeenCalledWith("WIN_2");
  });

  it("a load failure explains itself instead of rendering an empty canvas", async () => {
    // A blank pane and a failed pane look identical, and only one of them is worth retrying.
    const p = new SpecPane({ load: async () => { throw new Error("needs a source IFC"); }, notify: () => {} });
    p.dock("full");
    await vi.waitFor(() => expect(p.el.textContent).toMatch(/needs a source IFC/));
  });

  it("hidden means hidden, and does not fetch", () => {
    const load = vi.fn(async () => manual());
    const p = new SpecPane({ load, notify: () => {} });
    p.dock("hidden");
    expect(p.el.style.display).toBe("none");
    expect(p.isOpen).toBe(false);
    expect(load).not.toHaveBeenCalled();
  });
});
