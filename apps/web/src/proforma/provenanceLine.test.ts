import { describe, it, expect } from "vitest";
import { provenanceLine } from "./provenanceLine";
import type { ProformaProvenance } from "../api/types";

const p = (o: Partial<ProformaProvenance>): ProformaProvenance => ({
  figure_count: 6, by_basis: { declared: 6 }, defaulted_inputs: [], defaulted_input_count: 0,
  figures: {}, note: "Input provenance only", ...o,
});

describe("provenanceLine", () => {
  it("names the defaulted assumptions, because that is the number a reviewer wants", () => {
    const line = provenanceLine(p({ defaulted_inputs: ["exit.cap_rate", "debt.rate"], defaulted_input_count: 2 }));
    expect(line?.level).toBe("warn");
    expect(line?.text).toContain("2 inputs");
    expect(line?.text).toContain("exit.cap_rate, debt.rate");
    expect(line?.paths).toEqual(["exit.cap_rate", "debt.rate"]);
  });

  it("says so plainly when every input was declared", () => {
    expect(provenanceLine(p({}))).toEqual({
      text: "Every input behind these 6 figures was declared.", level: "ok", paths: [] });
  });

  it("is NULL when the server sent no provenance — absent must not read as clean", () => {
    // An older server, or a route that does not compute it. Rendering the "all declared" line here
    // would assert the opposite of what is known, on the one screen where that distinction decides
    // whether a number can be relied on.
    expect(provenanceLine(undefined)).toBeNull();
  });

  it("is null when there are no figures to qualify", () => {
    expect(provenanceLine(p({ figure_count: 0 }))).toBeNull();
  });

  it("caps the named paths and counts the rest", () => {
    const many = ["a", "b", "c", "d", "e", "f", "g", "h"];
    const line = provenanceLine(p({ defaulted_inputs: many, defaulted_input_count: 8 }));
    expect(line?.text).toContain("a, b, c, d, e, f +2 more");
    expect(line?.paths).toEqual(many);          // the full list is still carried, only the TEXT is cut
  });

  it("agrees with itself in the singular", () => {
    const line = provenanceLine(p({ defaulted_inputs: ["debt.rate"], defaulted_input_count: 1 }));
    expect(line?.text).toContain("1 input behind");
    expect(line?.text).toContain("was defaulted");
  });

  it("trusts the server's count, not the length of the list it names", () => {
    // `defaulted_input_count` is the server's dedupe of the same paths; if the two ever disagree the
    // COUNT is the claim and the list is the sample. Asserting this pins which one the line reports.
    const line = provenanceLine(p({ defaulted_inputs: ["a", "b"], defaulted_input_count: 5 }));
    expect(line?.text).toContain("5 inputs");
  });
});
