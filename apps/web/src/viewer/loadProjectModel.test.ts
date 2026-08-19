import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../api/client";
import { loadProjectModel, NO_MODEL_STATUS, type LoadProjectModelDeps } from "./loadProjectModel";

/**
 * A 404 / empty / unreadable .frag used to `return false` with no status line, so the canvas and
 * a loaded empty project looked the same. The overlay already cleared; this is the remaining gap.
 */
function deps(over: Partial<LoadProjectModelDeps> = {}): LoadProjectModelDeps {
  const setStatus = vi.fn();
  return {
    api: {
      url: (p: string) => p,
      authHeaders: () => ({}),
      proformaLive: async () => { throw new Error("skip"); },
    } as unknown as ApiClient,
    projectId: "p1",
    container: document.createElement("div"),
    loader: { disposeAll: async () => {}, loadFragments: async () => {} },
    modelLabels: new Map(),
    refreshFederation: () => {},
    fitToModels: async () => {},
    collabResync: async () => {},
    setStatus,
    canvas: () => null,
    ...over,
  };
}

describe("loadProjectModel names the empty canvas", () => {
  it("says there is no published model on a 404", async () => {
    vi.stubGlobal("fetch", async () => new Response("not found", { status: 404 }));
    const d = deps();
    document.body.appendChild(d.container);
    expect(await loadProjectModel(d)).toBe(false);
    expect(d.setStatus).toHaveBeenCalledWith(NO_MODEL_STATUS.missing);
    vi.unstubAllGlobals();
  });

  it("says the published file is empty on a 200 with no bytes", async () => {
    vi.stubGlobal("fetch", async () => new Response(new ArrayBuffer(0), { status: 200 }));
    const d = deps();
    document.body.appendChild(d.container);
    expect(await loadProjectModel(d)).toBe(false);
    expect(d.setStatus).toHaveBeenCalledWith(NO_MODEL_STATUS.empty);
    vi.unstubAllGlobals();
  });

  it("says the bytes are not Fragments when the parser rejects", async () => {
    vi.stubGlobal("fetch", async () => new Response("<!doctype html>", { status: 200 }));
    const d = deps({
      loader: { disposeAll: async () => {}, loadFragments: async () => { throw new Error("not frag"); } },
    });
    document.body.appendChild(d.container);
    expect(await loadProjectModel(d)).toBe(false);
    expect(d.setStatus).toHaveBeenCalledWith(NO_MODEL_STATUS.unreadable);
    vi.unstubAllGlobals();
  });
});
