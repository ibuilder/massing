import { describe, expect, it } from "vitest";

import { rotatedModels, runAlignmentPanel, type AlignmentPanelDeps, type FitReply } from "./alignmentPanel";

/**
 * This covers the WIRING, because the panel was extracted out of `qaSection.ts` as a block of DOM
 * construction and a mistake in that move — a call not made, a branch that renders nothing — would
 * leave the alignment check silently doing less than it did before, with every other test green.
 *
 * The load-bearing cases are the failure ones: a project with one model, and a model whose geometry
 * cannot be read. Both used to be impossible to hit because the panel did not fetch fits at all.
 */
const fit = (discipline: string, over: Partial<NonNullable<FitReply["fit"]>> = {}): FitReply => ({
  model: `m-${discipline}`, discipline,
  fit: {
    yaw_deg: -37, currently_at_deg: 37, extent_m: [78, 54],
    obb_area_m2: 4212, aabb_area_m2: 8538, area_saving: 0.507,
    accepted: true, reason: "rotated rather than ragged", ...over,
  },
});

function harness(over: {
  report?: unknown; models?: Array<{ id: string; discipline: string }>;
  fits?: Record<string, FitReply | Error>;
} = {}) {
  const body = document.createElement("div");
  const toasts: string[] = [];
  const out: string[] = [];
  const deps: AlignmentPanelDeps = {
    pid: "p1",
    api: {
      modelAlignment: async () => {
        if (over.report instanceof Error) throw over.report;
        return (over.report ?? { aligned: true, message: "all good", models: [], issues: [] }) as never;
      },
      projectModels: async () => over.models ?? [],
      modelAlignmentFit: async (_pid, mid) => {
        const f = over.fits?.[mid];
        if (f instanceof Error) throw f;
        if (!f) throw new Error("no fit");
        return f;
      },
    },
    toast: (m) => toasts.push(m),
    setOut: (t) => out.push(t),
    showResult: (_title, build) => build(body),
    resultNote: (text) => { const d = document.createElement("div"); d.textContent = text; return d; },
    kvTable: (rows) => {
      const d = document.createElement("div");
      d.textContent = rows.map((r) => `${r.k}=${r.v}`).join("|");
      return d;
    },
  };
  return { deps, body, toasts, out };
}

describe("rotatedModels", () => {
  it("keeps only the fits that were ACCEPTED", () => {
    const fits = [fit("STR"), fit("MEP", { accepted: false, area_saving: 0.04 }),
                  { model: "m-x", discipline: "ARCH", fit: null }];
    expect(rotatedModels(fits).map((f) => f.discipline)).toEqual(["STR"]);
  });
});

describe("the report half still works after the extraction", () => {
  it("renders the message, the model table and each issue", async () => {
    const h = harness({
      report: {
        aligned: false, message: "2 models disagree",
        models: [{ name: "STR", storey_count: 4, georef: {} }, { name: "MEP", storey_count: 3, georef: null }],
        issues: [{ type: "storey", severity: "high", model: "MEP", detail: "storey count differs" }],
      },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.textContent).toContain("2 models disagree");
    expect(h.body.textContent).toContain("STR=4 storeys · georef");
    expect(h.body.textContent).toContain("storey count differs");
    expect(h.out[0]).toBe("1 alignment issue(s)");
  });

  it("a project with fewer than two models is told what to do, not shown an error", async () => {
    const h = harness({ report: new Error("409") });
    await runAlignmentPanel(h.deps);
    expect(h.toasts[0]).toMatch(/Add discipline IFC/);
    expect(h.body.textContent).toBe("");
  });
});

describe("the yaw fit — the half that is new", () => {
  it("names a rotated model, the angle to apply, and its true extent", async () => {
    const h = harness({
      report: { aligned: true, message: "aligned", models: [], issues: [] },
      models: [{ id: "m-STR", discipline: "STR" }],
      fits: { "m-STR": fit("STR") },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.textContent).toContain("Rotated models");
    expect(h.body.textContent).toContain("sits at 37.0°");
    expect(h.body.textContent).toContain("rotate -37.0°");
    expect(h.body.textContent).toContain("78.0 × 54.0 m");
    expect(h.body.textContent).toContain("51% tighter");
  });

  // A rotated model IS an alignment problem even when storeys and origin agree — which is exactly the
  // case the report cannot see, and the reason the fit was worth adding.
  it("counts a rotated model as an issue even when the report says aligned", async () => {
    const h = harness({
      report: { aligned: true, message: "aligned", models: [], issues: [] },
      models: [{ id: "m-STR", discipline: "STR" }],
      fits: { "m-STR": fit("STR") },
    });
    await runAlignmentPanel(h.deps);
    expect(h.out[0]).toBe("1 alignment issue(s)");
  });

  it("says nothing about models that are already square-on", async () => {
    const h = harness({
      report: { aligned: true, message: "aligned", models: [], issues: [] },
      models: [{ id: "m-STR", discipline: "STR" }],
      fits: { "m-STR": fit("STR", { accepted: false, area_saving: 0.01 }) },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.textContent).not.toContain("Rotated models");
    expect(h.out[0]).toBe("Models aligned ✓");
  });

  it("states that a fit is a proposal, so nobody reads it as an applied change", async () => {
    const h = harness({
      report: { aligned: true, message: "aligned", models: [], issues: [] },
      models: [{ id: "m-STR", discipline: "STR" }],
      fits: { "m-STR": fit("STR") },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.textContent).toContain("source IFC is never modified");
  });
});

describe("one bad model does not cost the report", () => {
  it("an unreadable model is skipped, and the others still render", async () => {
    const h = harness({
      report: { aligned: false, message: "disagree", models: [], issues: [] },
      models: [{ id: "m-BAD", discipline: "BAD" }, { id: "m-STR", discipline: "STR" }],
      fits: { "m-BAD": new Error("cannot open"), "m-STR": fit("STR") },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.textContent).toContain("sits at 37.0°");
    expect(h.body.textContent).not.toContain("BAD sits");
  });

  it("no model list at all still shows the report", async () => {
    const h = harness({
      report: { aligned: false, message: "disagree", models: [], issues: [] },
      models: undefined,
    });
    const failing = { ...h.deps, api: { ...h.deps.api, projectModels: async () => { throw new Error("nope"); } } };
    await runAlignmentPanel(failing);
    expect(h.body.textContent).toContain("disagree");
  });
});

describe("issue text is inserted as TEXT, not markup", () => {
  // The original block built this with innerHTML and a server-supplied model name. The names come
  // from IFC files a user uploads, so they are not ours to trust.
  it("a model name containing markup is escaped by construction", async () => {
    const h = harness({
      report: {
        aligned: false, message: "x", models: [],
        issues: [{ type: "t", severity: "high", model: "<img src=x onerror=alert(1)>", detail: "d" }],
      },
    });
    await runAlignmentPanel(h.deps);
    expect(h.body.querySelector("img"), "no element was created from the name").toBeNull();
    expect(h.body.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
