import { describe, expect, it } from "vitest";

import { type Vital, cellText, cellTitle, compact, renderVitals } from "./vitalsBar";

/**
 * The vitals strip.
 *
 * It renders on every room and claims to be continuous proof that the model is one thing, so its
 * dangerous failure is not a wrong number but a **plausible** one. The load-bearing property here is
 * the same one the server enforces: an absent value shows an em-dash with its reason, never a `0`
 * that reads as a measurement.
 */

const V = (value: Vital["value"], unit: string, extra: Partial<Vital> = {}): Vital =>
  ({ value, unit, ...extra });

describe("a missing number never looks like a measured one", () => {
  it("null renders as an em-dash, not 0 or n/a", () => {
    expect(cellText("float", V(null, "days"))).toBe("—");
    expect(cellText("irr", V(null, "%"))).toBe("—");
    expect(cellText("cost_sf", V(null, "$/ft²"))).toBe("—");
  });

  it("...and a REAL zero still renders as zero", () => {
    // The distinction the whole feature turns on: zero float means no slack, which is a fact worth
    // showing in red — not the same statement as "this project has no schedule".
    expect(cellText("float", V(0, "days"))).toBe("0 days");
    expect(cellText("irr", V(0, "%"))).toBe("0%");
    expect(cellText("health", V(0, "%"))).toBe("0%");
  });

  it("an absent value explains itself in the tooltip", () => {
    expect(cellTitle("irr", V(null, "%", { note: "no solved scenario" })))
      .toContain("no solved scenario");
  });

  it("...and says something even when the server sent no reason", () => {
    expect(cellTitle("float", V(null, "days"))).toMatch(/not available/i);
    expect(cellTitle("float", undefined)).toMatch(/not available/i);
  });

  it("a present value shows full precision in the tooltip, not the compacted text", () => {
    // The cell says "12.5k"; hovering must give the number you would put in a report.
    expect(cellText("area", V(12543, "ft²"))).toBe("12.5k ft²");
    expect(cellTitle("area", V(12543, "ft²"))).toContain("12543");
  });
});

describe("units land where a reader expects them", () => {
  it("currency leads, percentages trail, LOD is prefixed", () => {
    expect(cellText("cost_sf", V(1801.97, "$/ft²"))).toBe("$1.8k");
    expect(cellText("health", V(84.2, "%"))).toBe("84.2%");
    expect(cellText("lod", V("300", "LOD"))).toBe("LOD 300");
  });
});

describe("compact keeps the strip scannable", () => {
  it("thousands and millions", () => {
    expect(compact(950)).toBe("950");
    expect(compact(12500)).toBe("12.5k");
    expect(compact(1_240_000)).toBe("1.24M");
  });
  it("drops trailing zeros rather than padding", () => {
    expect(compact(2000)).toBe("2k");
    expect(compact(3_000_000)).toBe("3M");
  });
  it("handles negatives — a negative float is the alarming case", () => {
    expect(compact(-4200)).toBe("-4.2k");
  });
});

describe("rendering", () => {
  const host = () => document.createElement("div");
  const PAYLOAD = {
    order: ["lod", "area", "cost_sf", "float", "irr", "health"],
    lod: V("300", "LOD"), area: V(12500, "ft²"), cost_sf: V(1801.97, "$/ft²"),
    float: V(0, "days"), irr: V(null, "%", { note: "no solved scenario" }),
    health: V(84.2, "%", { band: "good" }),
  };

  it("renders one cell per vital, in the server's order", () => {
    const h = host();
    renderVitals(h, PAYLOAD);
    const cells = [...h.querySelectorAll(".vit .vit-k")].map((e) => e.textContent);
    expect(cells).toEqual(["LOD", "Area", "$/ft²", "Float", "IRR", "Health"]);
  });

  it("marks the empty ones so they can be styled back, not forward", () => {
    const h = host();
    renderVitals(h, PAYLOAD);
    const empty = [...h.querySelectorAll(".vit-empty .vit-k")].map((e) => e.textContent);
    expect(empty).toEqual(["IRR"]);
  });

  it("puts the health band on the cell, so colour is decided once", () => {
    const h = host();
    renderVitals(h, PAYLOAD);
    expect(h.querySelector(".vit-good")).not.toBeNull();
  });

  it("renders NOTHING with no payload — not six em-dashes pretending to be data", () => {
    const h = host();
    renderVitals(h, null);
    expect(h.hidden).toBe(true);
    expect(h.innerHTML).toBe("");
  });

  it("re-rendering replaces rather than appending", () => {
    const h = host();
    renderVitals(h, PAYLOAD);
    renderVitals(h, PAYLOAD);
    expect(h.querySelectorAll(".vit").length).toBe(6);
  });

  it("server text goes in as TEXT, never markup", () => {
    const h = host();
    renderVitals(h, { order: ["lod"], lod: V('<img src=x onerror="alert(1)">', "LOD") });
    expect(h.querySelector("img")).toBeNull();
    expect(h.querySelector(".vit-v")!.textContent).toContain("<img");
  });

  it("is clickable only when a handler is given", () => {
    const plain = host();
    renderVitals(plain, PAYLOAD);
    expect(plain.querySelector("button")).toBeNull();

    const clickable = host();
    const seen: string[] = [];
    renderVitals(clickable, PAYLOAD, (k) => seen.push(k));
    clickable.querySelector<HTMLButtonElement>(".vit")!.click();
    expect(seen).toEqual(["lod"]);
  });
});
