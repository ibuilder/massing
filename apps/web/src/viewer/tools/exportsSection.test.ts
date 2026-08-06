import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../api/client";
import { buildExportsSection, type ExportsDeps } from "./exportsSection";

/**
 * **The point of the extraction, demonstrated.**
 *
 * These 51 lines lived inside `buildToolsPanel` in `app.ts` and could not be tested at all —
 * nothing in the suite imports `app.ts`, because `createViewerApp` needs a WebGL context and a
 * Fragments worker. The file is untested *because* it needs a renderer and risky to split *for the
 * same reason*; the absence is self-reinforcing, and the only way out is to move the parts that
 * need no renderer.
 *
 * This section is pure DOM assembly over an API client, so once it takes explicit parameters it is
 * ordinary code. **This file is the first test any of it has ever had**, and it is what the next
 * extraction gets to lean on.
 *
 * These are not parity assertions — nothing captured the old behaviour, so nothing can claim the
 * move preserved it. `tsc` is the parity gate for the move (a capture that failed to thread is a
 * compile error); this file is the coverage the move *bought*.
 */

function harness(over: Partial<ExportsDeps> = {}) {
  const host = document.createElement("div");
  const notify = vi.fn((_m: string, _k?: "info" | "success" | "error") => {});
  const opened: string[] = [];
  vi.stubGlobal("open", (u: string) => { opened.push(u); return null; });

  const api = {
    url: (p: string) => `https://api.test${p}`,
    modelIfcUrl: (pid: string) => `https://api.test/${pid}/model.ifc`,
    modelGlbUrl: (pid: string) => `https://api.test/${pid}/model.glb`,
    modelGltfUrl: (pid: string) => `https://api.test/${pid}/model.gltf`,
    disciplineQuantities: vi.fn(async () => ({
      rebar: { estimated: false, tonnes: 12.5, count: 340 },
      mep: { duct_m: 210, pipe_m: 180, cable_m: 95, counts: { duct: 40, pipe: 33, cable: 21, fittings: 77 } },
      structure: { element_volume_m3: 1450 },
    })),
    takeoff2d: vi.fn(async () => ({})),
  } as unknown as ApiClient;

  const deps: ExportsDeps = {
    section: vi.fn(() => host),
    toolBtn2: (label, onClick) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.onclick = onClick;
      return b;
    },
    api,
    projectId: "P-1",
    notify,
    ...over,
  };
  buildExportsSection(deps);
  return { host, notify, opened, api, deps };
}

const labels = (host: HTMLElement) =>
  [...host.querySelectorAll("button")].map((b) => b.textContent ?? "");

describe("R39-DECOMP-VIEWER ① — the Exports section, extracted", () => {
  it("does nothing when the section gate refuses — no project, no source IFC", () => {
    const host = document.createElement("div");
    const section = vi.fn(() => null);
    buildExportsSection({ ...harness().deps, section });
    expect(host.children).toHaveLength(0);
    expect(section).toHaveBeenCalledWith("exports", expect.any(String),
      expect.objectContaining({ requires: "sourceIfc" }));
  });

  it("builds every export the section is meant to offer", () => {
    const { host } = harness();
    const text = labels(host).join("\n");
    for (const expected of ["Quantity takeoff", "COBie", "Space schedule", "4D schedule", "gbXML",
                            "Discipline quantities", "Closeout package", "Export IFC",
                            ".glb", ".gltf", "2D takeoff"]) {
      expect(text, `missing "${expected}"`).toContain(expected);
    }
  });

  it("gates itself on a source IFC, not merely on a project", () => {
    const { deps } = harness();
    expect(deps.section).toHaveBeenCalledWith("exports", expect.stringContaining("Exports"),
      { requires: "sourceIfc", tool: true });
  });

  // The workbook exports build their URL from projectId. A wrong id here downloads another
  // project's quantities, which is the kind of thing that is obvious in a test and invisible in a
  // 3,000-line function.
  it("addresses the caller's project in the workbook URLs", () => {
    const { host, opened } = harness();
    const qto = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Quantity takeoff"))!;
    qto.click();
    expect(opened[0]).toBe("https://api.test/projects/P-1/exports/qto.xlsx");
  });

  it("uses the IFC/glTF url builders rather than assembling paths by hand", () => {
    const { host, opened } = harness();
    for (const needle of ["Export IFC", ".glb", ".gltf"]) {
      [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(needle))!.click();
    }
    expect(opened).toEqual(["https://api.test/P-1/model.ifc", "https://api.test/P-1/model.glb",
                            "https://api.test/P-1/model.gltf"]);
  });

  it("renders the discipline quantities the API returns", async () => {
    const { host, api } = harness();
    [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Discipline quantities"))!.click();
    await vi.waitFor(() => expect(api.disciplineQuantities).toHaveBeenCalledWith("P-1"));
  });

  it("says why rather than failing silently when the quantities call throws", async () => {
    const api = {
      ...harness().api,
      disciplineQuantities: vi.fn(async () => { throw new Error("boom"); }),
    } as unknown as ApiClient;
    const { host, notify } = harness({ api });
    [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Discipline quantities"))!.click();
    await vi.waitFor(() => expect(notify).toHaveBeenCalledWith(
      expect.stringContaining("quantities failed"), "error"));
  });

  // Both handlers that need a project re-check it at CLICK time rather than at build time — the
  // section can be built while a project is open and clicked after it closes.
  it("refuses the project-dependent actions when there is no project, at click time", () => {
    const { host, notify } = harness({ projectId: null });
    for (const needle of ["Discipline quantities", "2D takeoff"]) {
      [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(needle))!.click();
    }
    expect(notify).toHaveBeenCalledTimes(2);
    expect(notify).toHaveBeenCalledWith("connect a project first", "error");
  });

  it("carries a tooltip on every export whose format is not self-evident", () => {
    const { host } = harness();
    for (const needle of ["gbXML", "Closeout package", "Export IFC", ".glb", ".gltf", "2D takeoff"]) {
      const b = [...host.querySelectorAll("button")].find((x) => x.textContent?.includes(needle))!;
      expect(b.title, `"${needle}" has no tooltip`).toBeTruthy();
    }
  });
});
