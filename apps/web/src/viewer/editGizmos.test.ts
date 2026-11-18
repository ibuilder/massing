import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";

import { installEditGizmos, type EditGizmoDeps } from "./editGizmos";
import { type ModelIdMap } from "./modelIds";

/**
 * R39-DECOMP-VIEWER — the edit-in-place gizmos lifted out of `app.ts`.
 *
 * These two gestures are where a drag becomes a GUID-stable recipe edit written into the IFC, and
 * before this extraction they had no direct test — every authoring assertion drove the recipe layer,
 * never the gesture that arms it. The routing / mutual-exclusion tests use an EMPTY bounding box so
 * `attach*` returns before constructing a (WebGL-adjacent) gizmo; one test feeds a real box to prove
 * the gizmo actually builds and that arming the other gesture tears its ghost back down.
 */

const MAP: ModelIdMap = { "model-1": new Set([1]) };

function harness(over: Partial<{ guid: string | null; selection: ModelIdMap | null; boxes: THREE.Box3[] }> = {}) {
  const cam = new THREE.PerspectiveCamera(60, 1.6, 0.1, 1000);
  const controls = { enabled: true };
  const scene = new THREE.Scene();
  const canvas = document.createElement("canvas");
  const renderer = { three: { domElement: canvas } };

  let selectedGuid: string | null = "guid" in over ? over.guid! : "guid-A";
  let selection: ModelIdMap | null = over.selection ?? null;
  // Empty by default: attach* calls getBBoxes (routing is observable) then returns before any
  // gizmo is constructed, which keeps the pure-state tests off the WebGL path entirely.
  const boxes = over.boxes ?? [];

  const getBBoxes = vi.fn(async () => boxes);
  const authorAndReload = vi.fn(async () => ({ applied: true, refused: false }));
  const selectByGuid = vi.fn(async () => {});
  const notify = vi.fn();
  const setStatus = vi.fn();

  const deps = {
    viewer: { world: { camera: { three: cam, controls }, renderer, scene: { three: scene } } },
    loader: { fragments: { getBBoxes } },
    projectId: "p1",
    getSnap: () => 0,
    setStatus, notify, authorAndReload, selectByGuid,
    selectedGuid: () => selectedGuid,
    selection: () => selection,
  } as unknown as EditGizmoDeps;

  const api = installEditGizmos(deps);
  return {
    api, getBBoxes, notify, setStatus, scene,
    setSelectedGuid: (g: string | null) => { selectedGuid = g; },
    setSelection: (s: ModelIdMap | null) => { selection = s; },
    btn: () => document.createElement("button"),
    ghostCount: () => scene.children.filter((o) => o instanceof THREE.Mesh).length,
  };
}

describe("installEditGizmos — routing and mutual exclusion", () => {
  it("attaches nothing on a selection change until a mode is armed", async () => {
    const h = harness();
    await h.api.onSelection(MAP);
    expect(h.getBBoxes).not.toHaveBeenCalled();
    expect(h.api.mode()).toBe("off");
  });

  it("routes a selection to the MOVE gizmo once edit-in-place is on", async () => {
    const h = harness();
    h.api.toggleMove(h.btn());
    expect(h.api.mode()).toBe("move");
    h.getBBoxes.mockClear();
    await h.api.onSelection(MAP);
    expect(h.getBBoxes).toHaveBeenCalledTimes(1);
  });

  it("routes a selection to the PUSH/PULL gizmo once that mode is on", async () => {
    const h = harness();
    h.api.togglePushPull(h.btn());
    expect(h.api.mode()).toBe("pushpull");
    h.getBBoxes.mockClear();
    await h.api.onSelection(MAP);
    expect(h.getBBoxes).toHaveBeenCalledTimes(1);
  });

  it("arming one gesture disarms the other — one gizmo on a box at a time", () => {
    const h = harness();
    h.api.toggleMove(h.btn());
    expect(h.api.mode()).toBe("move");
    h.api.togglePushPull(h.btn());
    expect(h.api.mode()).toBe("pushpull");
    h.api.toggleMove(h.btn());
    expect(h.api.mode()).toBe("move");
  });

  it("toggling a mode on with a live selection attaches immediately; toggling off reports it", () => {
    const h = harness({ selection: MAP });
    const b = h.btn();
    h.api.toggleMove(b);
    expect(h.getBBoxes).toHaveBeenCalledTimes(1);   // attached the already-selected element
    expect(b.classList.contains("on")).toBe(true);
    expect(h.notify).toHaveBeenCalledWith(expect.stringContaining("Edit-in-place on"), "info");
    h.api.toggleMove(b);
    expect(h.api.mode()).toBe("off");
    expect(b.classList.contains("on")).toBe(false);
    expect(h.setStatus).toHaveBeenCalledWith("edit-in-place off");
  });

  it("hideAll and isDragging are safe before any gizmo is constructed", () => {
    const h = harness();
    expect(() => h.api.hideAll()).not.toThrow();
    expect(h.api.isDragging()).toBe(false);
  });
});

describe("installEditGizmos — real gizmo construction", () => {
  // A unit box, so attach() builds a ghost and the gizmo is actually constructed.
  const unitBox = () => [new THREE.Box3(new THREE.Vector3(-1, 0, -1), new THREE.Vector3(1, 2, 1))];

  it("builds the move gizmo on attach and tears its ghost down when push/pull is armed", async () => {
    const h = harness({ selection: MAP, boxes: unitBox() });
    h.api.toggleMove(h.btn());
    await Promise.resolve();                 // let the async attach settle
    expect(h.ghostCount(), "move gizmo attached → amber ghost in the scene").toBeGreaterThan(0);
    // Switching to push/pull must hide the move gizmo — the `gizmo?.hide()` the mutation would drop.
    h.api.togglePushPull(h.btn());
    expect(h.ghostCount(), "arming push/pull tears the move ghost back down").toBe(0);
    expect(h.api.mode()).toBe("pushpull");
  });
});
