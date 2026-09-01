import { afterEach, describe, expect, it, vi } from "vitest";

import {
  VIEWER_HOOK_DEV_KEYS,
  VIEWER_HOOK_PROD_KEYS,
  installTakeoffHook,
  installViewerHook,
} from "./debugHook";

type Hooks = { __viewer?: Record<string, unknown>; __takeoff?: unknown };

const win = () => window as unknown as Hooks;

afterEach(() => {
  delete win().__viewer;
  delete win().__takeoff;
});

describe("viewer debug hook — production is selection only", () => {
  it("exposes GlobalId selection and nothing else when not in DEV", () => {
    const selectByGuid = vi.fn();
    const selectByGuids = vi.fn();
    installViewerHook({
      selectByGuid,
      selectByGuids,
      viewer: { world: true },
      loader: { load: true },
      THREE: { WebGLRenderer: true },
      openFile: vi.fn(),
      fitToModels: vi.fn(),
      referenceModels: [],
    }, { dev: false });

    const hook = win().__viewer!;
    expect(Object.keys(hook).sort()).toEqual([...VIEWER_HOOK_PROD_KEYS].sort());
    expect(hook.viewer).toBeUndefined();
    expect(hook.loader).toBeUndefined();
    expect(hook.THREE).toBeUndefined();
    expect(hook.openFile).toBeUndefined();

    (hook.selectByGuid as (g: string, fit?: boolean) => void)("1kP9xAbCdEf7Qa", true);
    expect(selectByGuid).toHaveBeenCalledWith("1kP9xAbCdEf7Qa", true);
  });

  it("keeps the preview-eval surface in DEV so live verification still works", () => {
    const selectByGuid = vi.fn();
    const selectByGuids = vi.fn();
    const THREE = { REVISION: "test" };
    installViewerHook({
      selectByGuid,
      selectByGuids,
      viewer: { id: "v" },
      loader: { id: "l" },
      THREE,
      openFile: vi.fn(),
      fitToModels: vi.fn(),
      referenceModels: [{ id: "r" }],
    }, { dev: true });

    const hook = win().__viewer!;
    expect(Object.keys(hook).sort()).toEqual([...VIEWER_HOOK_DEV_KEYS].sort());
    expect(hook.THREE).toBe(THREE);
    expect(hook.viewer).toEqual({ id: "v" });
  });

  it("does not invent DEV fields the caller never passed", () => {
    installViewerHook({
      selectByGuid: vi.fn(),
      selectByGuids: vi.fn(),
    }, { dev: true });
    const hook = win().__viewer!;
    expect(Object.keys(hook).sort()).toEqual([...VIEWER_HOOK_PROD_KEYS].sort());
    expect("THREE" in hook).toBe(false);
  });
});

describe("takeoff debug hook — production has no driver", () => {
  it("does not attach __takeoff when not in DEV", () => {
    installTakeoffHook({ click: vi.fn() }, { dev: false });
    expect(win().__takeoff).toBeUndefined();
  });

  it("clears a leftover DEV hook when production install runs", () => {
    win().__takeoff = { stale: true };
    installTakeoffHook({ click: vi.fn() }, { dev: false });
    expect(win().__takeoff).toBeUndefined();
  });

  it("attaches the driver in DEV", () => {
    const click = vi.fn();
    installTakeoffHook({ click }, { dev: true });
    expect(win().__takeoff).toEqual({ click });
  });
});
