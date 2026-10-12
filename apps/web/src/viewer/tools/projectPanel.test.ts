import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient, DisciplineTree } from "../../api/client";
import type { SpatialElement } from "../spatialSelect";
import { buildProjectPanels, type ProjectPanelDeps } from "./projectPanel";

/**
 * **The ref rule, enforced instead of merely written down.**
 *
 * R39-DECOMP-VIEWER moves code out of `app.ts` by handing it explicit parameters, and `tsc` is the
 * parity gate for that threading: a capture you fail to pass is a compile error. But `tsc` **cannot
 * see ref-vs-value**, and that is the one distinction the whole decomposition rests on. Dropping a
 * dependency from `ProjectPanelDeps` fails with two errors; **passing `{ ...refs }` instead of
 * `refs` compiles with zero**, because a copy is structurally identical to the original. The moved
 * code then writes into an object nobody is reading, silently, forever.
 *
 * So the rule is checked here **behaviourally**: construct the state, run the builder, trigger the
 * path that writes, and assert **the caller's own binding observed the write**. Each test below goes
 * red under exactly that mutation — spread the ref before passing it and the observation is lost.
 *
 * Why this matters more than it sounds for each one:
 *
 *  - `spatialElements` is not merely written, it is **rebuilt** from the fetched element list, and
 *    `A29-SPATIAL-SELECT` reads it on every pick. A value copy leaves picking permanently against a
 *    stale list — a silent wrong answer in a feature another lane shipped this week.
 *  - `discipline.tree` is assigned with `??=`, which no getter can express. It is read afterwards by
 *    `disciplineOfClass` and by the colour lookup, both of which stayed in `app.ts`.
 *  - `discipline.mode` is written by a `<select>` handler and read by the same colour lookup, so a
 *    copy means the user changes the mode and the model keeps painting the old one.
 */

const ELEMENTS = [
  { guid: "G1", storey: "L1", ifc_class: "IfcWall" },
  { guid: "G2", storey: "L2", ifc_class: "IfcDoor" },
];

const TREE = {
  ifc_class_discipline: { IfcWall: "A", IfcDoor: "A" },
  disciplines: [{ code: "A", name: "Architectural" }],
  colors: { A: "#f00" },
} as unknown as DisciplineTree;

function host() {
  document.body.innerHTML = "";
  for (const id of ["panel-tree", "panel-layers", "ifc-input"]) {
    const el = document.createElement("div");
    el.id = id;
    document.body.appendChild(el);
  }
}

/** Deps wired to real ref objects, so a test can inspect what the builder wrote into them. */
function makeDeps(over: Partial<ProjectPanelDeps> = {}) {
  const discipline: { tree: DisciplineTree | null; mode: "class" | "discipline" } =
    { tree: null, mode: "class" };
  const spatialElements: { value: SpatialElement[] } = { value: [] };

  const api = {
    elements: vi.fn(async () => ELEMENTS),
    meta: vi.fn(async () => ({ facets: { classes: ["IfcWall", "IfcDoor"], storeys: [] } })),
    disciplineTree: vi.fn(async () => TREE),
    // R43-VIEWER-CONFORMANCE. Rejecting on purpose: every project whose element index predates
    // `index_schema: 2` gets a 422 here, which is the MAJORITY case for anything already published,
    // so the rejecting arm is the one worth exercising by default. The panel must swallow it and
    // still render the four name-based group modes — a spatial-tree fetch that can take the model
    // browser down with it would be a regression paid for by every existing project.
    spatialTree: vi.fn(async () => { throw new Error("422 index predates the spatial tree"); }),
    // ELEMENTS-SILENT. A CURRENT index of exactly the two elements the fetch returns, so the
    // default fixture renders no note at all — the ordinary case must stay silent, and a fixture
    // that permanently showed a banner would hide a regression in `worthShowing`.
    elementsFreshness: vi.fn(async () => ({
      indexed_elements: ELEMENTS.length, stale: false,
      built_from_source: true, model_reachable: true, hint: null,
    })),
  } as unknown as ApiClient;

  const deps: ProjectPanelDeps = {
    api,
    projectId: "P-1",
    notify: vi.fn(),
    setStatus: vi.fn(),
    selectByGuid: vi.fn(async () => {}),
    reloadModelPins: vi.fn(async () => {}),
    colorFor: () => "#123456",
    disciplineOfClass: (c: string) => TREE.ifc_class_discipline[c] ?? null,
    discipline,
    spatialElements,
    layerMgr: {} as ProjectPanelDeps["layerMgr"],
    fitToItems: vi.fn(async () => {}),
    refreshIssues: vi.fn(async () => {}),
    ...over,
  };
  return { deps, discipline, spatialElements, api };
}

beforeEach(host);

describe("R39-DECOMP-VIEWER — the caller's ref observes what the moved code writes", () => {
  it("rebuilds spatialElements into the CALLER's object, not a copy", async () => {
    const { deps, spatialElements } = makeDeps();
    await buildProjectPanels(deps);
    expect(spatialElements.value, "A29-SPATIAL-SELECT would pick against a stale element list")
      .toEqual([{ guid: "G1", storey: "L1" }, { guid: "G2", storey: "L2" }]);
  });

  it("assigns discipline.tree into the CALLER's object — `??=` cannot be a getter", async () => {
    const { deps, discipline } = makeDeps();
    expect(discipline.tree).toBeNull();
    await buildProjectPanels(deps);
    expect(discipline.tree, "disciplineOfClass and the colour lookup still read this in app.ts")
      .toBe(TREE);
  });

  it("does not refetch the tree when the caller already holds one", async () => {
    // `??=` is the whole point: a second panel build must not pay for another fetch.
    const { deps, discipline, api } = makeDeps();
    discipline.tree = TREE;
    await buildProjectPanels(deps);
    expect(api.disciplineTree).not.toHaveBeenCalled();
  });

  it("writes discipline.mode into the CALLER's object when the select changes", async () => {
    const { deps, discipline } = makeDeps();
    await buildProjectPanels(deps);
    const sel = [...document.querySelectorAll<HTMLSelectElement>("select.mini-select")]
      .find((s) => s.value === "class");
    expect(sel, "the colour-mode select was not rendered — this test would pass vacuously").toBeTruthy();
    sel!.value = "discipline";
    sel!.dispatchEvent(new Event("change"));
    expect(discipline.mode, "the user changes mode and the model keeps painting the old one")
      .toBe("discipline");
  });

  /**
   * The mutation, run as a test rather than described.
   *
   * This is the exact defect `tsc` cannot see: spreading a ref produces a structurally identical
   * object that compiles cleanly. Asserting that the ORIGINAL is left untouched proves these tests
   * are observing the reference rather than the value — without it, every assertion above could pass
   * for the wrong reason.
   */
  it("a SPREAD ref loses every write — which is why tsc is not enough here", async () => {
    const { deps, discipline, spatialElements } = makeDeps();
    await buildProjectPanels({ ...deps,
      discipline: { ...discipline },
      spatialElements: { ...spatialElements } });
    expect(discipline.tree, "spread ref still reached the original — the test is not observing the ref")
      .toBeNull();
    expect(spatialElements.value).toEqual([]);
  });
});

/**
 * The other half, and the tests above cannot see it.
 *
 * Everything above proves the MOVED CODE writes through whatever ref it is handed. None of it
 * exercises `app.ts`, so a call site that passed `{ ...disciplineRef }` would compile, keep every
 * test green, and silently stop the writes reaching the `let`s. Source is the only reader available
 * for that — `initViewerApp` needs a WebGL context and a Fragments worker to instantiate.
 *
 * Resolved from `process.cwd()` (= `apps/web`); happy-dom gives `import.meta.url` no `file:` scheme.
 */
describe("app.ts hands over the ref itself, not a copy of it", () => {
  const src = readFileSync(resolve(process.cwd(), "src/viewer/app.ts"), "utf8");
  const call = src.slice(src.indexOf("buildProjectPanels({"), src.indexOf("buildProjectPanels({") + 500);

  it("found the call site — not vacuously green", () => {
    expect(call).toContain("discipline:");
    expect(call.length).toBeGreaterThan(50);
  });

  it("passes the ref by name, never spread", () => {
    expect(call, "a spread ref compiles and silently drops every write")
      .not.toMatch(/discipline:\s*\{\s*\.\.\./);
    expect(call, "a spread ref compiles and silently drops every write")
      .not.toMatch(/spatialElements:\s*\{\s*\.\.\.[a-zA-Z]/);
    expect(call).toMatch(/discipline:\s*disciplineRef/);
  });
});

/**
 * ELEMENTS-SILENT — the index note, and the regression that writing it caused.
 *
 * The panel annotates its element list with `/elements/freshness`: whether the index still matches
 * the model, and whether `limit: 5000` capped it. `/elements` returns a bare array with no total, so
 * that route carries the only denominator in the API.
 *
 * **The first draft of this took the whole panel down**, and the test that caught it is the colour
 * mode one above, which is about something else entirely. Both calls sat in one `Promise.all` inside
 * the `try` that decides `noModel`, and a client without the method threw *synchronously* — so a
 * TypeError about an annotation was caught by the branch that means "this project has no model", and
 * the browser rendered the empty state over a model that was right there. The fetch is now started
 * outside that `try`, through a `Promise.resolve().then(...)` so a synchronous throw is a rejection
 * too. *A failure in the thing that describes the answer must not be able to replace the answer.*
 */
describe("the index note", () => {
  it("renders nothing when the index is current and nothing was capped", async () => {
    const { deps } = makeDeps();
    await buildProjectPanels(deps);
    const panel = document.getElementById("panel-tree")!;
    expect(panel.textContent).not.toContain("capped");
    expect(panel.textContent).not.toContain("older version");
  });

  it("names both numbers when the page is capped", async () => {
    const { deps, api } = makeDeps();
    (api.elementsFreshness as ReturnType<typeof vi.fn>).mockResolvedValue({
      indexed_elements: 12000, stale: false,
      built_from_source: true, model_reachable: true, hint: null,
    });
    await buildProjectPanels(deps);
    const text = document.getElementById("panel-tree")!.textContent!;
    expect(text).toContain("12000");
    expect(text).toContain("spatial selection");
  });

  it("says a stale index is stale, above the tree", async () => {
    const { deps, api } = makeDeps();
    (api.elementsFreshness as ReturnType<typeof vi.fn>).mockResolvedValue({
      indexed_elements: 2, stale: true, built_from_source: true,
      model_reachable: true, hint: "republish to rebuild the index from the current model",
    });
    await buildProjectPanels(deps);
    const text = document.getElementById("panel-tree")!.textContent!;
    expect(text).toContain("older version of the model");
    expect(text).toContain("republish");
  });

  it("still renders the tree when the freshness call REJECTS", async () => {
    const { deps, api } = makeDeps();
    (api.elementsFreshness as ReturnType<typeof vi.fn>)
      .mockRejectedValue(new Error("404 no properties index for project"));
    await buildProjectPanels(deps);
    const panel = document.getElementById("panel-tree")!;
    expect(panel.textContent, "a missing annotation must not become a missing panel")
      .not.toContain("No model in this project yet");
    expect(panel.querySelectorAll(".tree-node, .tree-row, button").length).toBeGreaterThan(0);
  });

  it("still renders the tree when the client has NO SUCH METHOD — the shipped regression", async () => {
    // Not a hypothetical: this is exactly what the first draft did, and it was indistinguishable
    // from a project with no model. A synchronous TypeError, not a rejection, which is why
    // `.catch()` alone was not enough.
    const { deps, api } = makeDeps();
    delete (api as unknown as Record<string, unknown>).elementsFreshness;
    await buildProjectPanels(deps);
    const panel = document.getElementById("panel-tree")!;
    expect(panel.textContent).not.toContain("No model in this project yet");
    expect(panel.textContent).not.toContain("published with no elements");
  });
});
