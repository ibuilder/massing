/**
 * A29-LOCAL-PREVIEW — the draft proxy layer's state machine: pending must look pending, and a
 * failure must stay visible until the user acts.
 *
 * These tests drive the layer headless (a bare THREE.Scene, no renderer): the states under test
 * are colours, flags and child counts, all readable without compositing a frame — which also
 * means the dev-preview geometry stall (see the verify-frontend skill) cannot block them.
 *
 * What is deliberately asserted:
 *   * `pending` and `failed` are mutually exclusive views of the same children — a failed layer
 *     must NOT read as pending, or the "publish in flight" UI would show for a dead attempt.
 *   * `markFailed` changes the SHARED materials to red; `clear` restores amber. The materials are
 *     shared across all proxies in the layer, so a stale palette would paint the NEXT placement
 *     red — a fresh draft that looks pre-failed.
 *   * a new `fromParams` on a failed layer clears the corpse first — drawing again is the
 *     acknowledgement, and the old red marker must not linger under the new amber one.
 */
import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { DraftProxyLayer } from "./draftProxy";

const AMBER = 0xffb000;
const RED = 0xe5484d;

function layer() {
  return new DraftProxyLayer(new THREE.Scene());
}

function lineColor(l: DraftProxyLayer): number {
  const line = l.group.children.find((c) => (c as THREE.Line).isLine) as THREE.Line | undefined;
  return ((line?.material as THREE.LineBasicMaterial)?.color?.getHex()) ?? -1;
}

describe("DraftProxyLayer — pending", () => {
  it("an empty layer is neither pending nor failed", () => {
    const l = layer();
    expect(l.pending).toBe(false);
    expect(l.failed).toBe(false);
  });

  it("a placed proxy is PENDING and drawn in the pending colour", () => {
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    expect(l.pending).toBe(true);
    expect(l.failed).toBe(false);
    expect(lineColor(l)).toBe(AMBER);
  });

  it("clear() empties the layer — the publish-done path", () => {
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    l.clear();
    expect(l.group.children.length).toBe(0);
    expect(l.pending).toBe(false);
  });
});

describe("DraftProxyLayer — failure stays visible", () => {
  it("markFailed keeps the children but turns them red — WHERE, not just THAT", () => {
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    l.markFailed();
    expect(l.group.children.length, "a failed marker must remain visible").toBeGreaterThan(0);
    expect(lineColor(l)).toBe(RED);
  });

  it("a failed layer reads failed, NOT pending — the two states are mutually exclusive", () => {
    // If failed still read as pending, any UI keyed on `pending` would show a publish in flight
    // for an attempt that is already dead.
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    l.markFailed();
    expect(l.failed).toBe(true);
    expect(l.pending).toBe(false);
  });

  it("the NEXT draft action clears the failed marker — drawing again is the acknowledgement", () => {
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    l.markFailed();
    l.fromParams({ point: [1, 1] }, 0);
    expect(l.failed).toBe(false);
    expect(l.pending).toBe(true);
    // exactly the new proxy's children remain (box + edge lines), none of the failed line
    expect(l.group.children.some((c) => (c as THREE.Line).isLine
      && ((c as THREE.Line).material as THREE.LineBasicMaterial).color.getHex() === RED)).toBe(false);
  });

  it("clear() after a failure restores the pending palette — materials are SHARED, so a stale " +
     "red would paint the next placement as pre-failed", () => {
    const l = layer();
    l.fromParams({ start: [0, 0], end: [4, 0] }, 0);
    l.markFailed();
    l.clear();
    l.fromParams({ start: [2, 2], end: [6, 2] }, 0);
    expect(lineColor(l), "a fresh placement after clear() must be amber, not leftover red")
      .toBe(AMBER);
  });
});
