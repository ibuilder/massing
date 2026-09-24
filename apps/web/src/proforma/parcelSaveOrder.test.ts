import { describe, expect, it, vi } from "vitest";

import type { LoadedParcel } from "./parcelBoundary";

/**
 * SITE-1, review round — the parcel-boundary save must land in SELECTION order.
 *
 * The first version fired one `saveProperty` per selection and forgot it (`void …`). Select parcel
 * A, then B, and both PUTs are in flight at once: `put_property` merges under the project lock, so
 * the lock decides which write wins and it decides by ARRIVAL. If A's request settles second, the
 * stored boundary is A while the tab shows B — and the viewer then draws a lot line for a parcel
 * nobody has selected. **A lock orders the writes; it cannot order the intentions.**
 *
 * The worst case is a CLEAR, because it is the one whose loss is silent in the other direction: a
 * late select-then-clear pair resurrects a parcel the user removed, and nothing on screen disagrees.
 *
 * Driven through the real `renderMassingTab` with the boundary control mocked down to the callback
 * it hands back, because the ordering lives in the tab and not in the control.
 */
const captured: { onChange?: (p: LoadedParcel | null) => void } = {};
vi.mock("./parcelBoundary", () => ({
  parcelBoundaryControl: (_host: unknown, onChange: (p: LoadedParcel | null) => void) => {
    captured.onChange = onChange;
    return { el: document.createElement("div"), get: () => null };
  },
}));

const { renderMassingTab } = await import("./massingTab");

const parcel = (tag: string): LoadedParcel => ({
  ring: [[0, 0], [1, 0], [1, 1]], areaM2: 1, areaAcres: 1, rectM2: 1,
  widthM: 1, depthM: 1, vertices: 3, source: tag,
} as unknown as LoadedParcel);

function harness(pid: string | null = "p1") {
  const landed: string[] = [];
  const settle: (() => void)[] = [];
  const status: string[] = [];
  const api = {
    saveProperty: vi.fn((_pid: string, body: { parcel_boundary: { vertices?: number } | null }) =>
      new Promise<void>((resolve) => {
        settle.push(() => { landed.push(body.parcel_boundary ? "set" : "clear"); resolve(); });
      })),
  };
  const root = document.createElement("div");
  renderMassingTab(root, {
    api: api as never, projectId: () => pid,
    setStatus: (m: string) => status.push(m), adoptAssumptions: () => undefined,
  });
  return { landed, settle, status, api };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("SITE-1: parcel-boundary saves", () => {
  it("reach the server in selection order even when the FIRST is slower to settle", async () => {
    const h = harness();
    captured.onChange!(parcel("A"));
    captured.onChange!(parcel("B"));
    captured.onChange!(null);                 // …and a clear, the one that must not be resurrected
    await flush();

    // Only ONE request may be in flight: that is what makes arrival order equal selection order.
    // Without the chain all three are issued at once and the network decides the winner.
    expect(h.api.saveProperty, "more than one save in flight — the order is the network's to pick")
      .toHaveBeenCalledTimes(1);

    // Settle them in the WORST order the old code allowed: release each as it is issued, but prove
    // the next is not issued until the previous resolves.
    for (let i = 0; i < 3; i++) { h.settle[i]?.(); await flush(); }
    expect(h.landed).toEqual(["set", "set", "clear"]);
    expect(h.api.saveProperty).toHaveBeenCalledTimes(3);

    // The LAST thing the server was told is the clear, which is what the tab is showing.
    const last = h.api.saveProperty.mock.calls.at(-1)?.[1] as { parcel_boundary: unknown };
    expect(last.parcel_boundary, "the clear did not land last — a removed parcel can come back")
      .toBeNull();
  });

  it("does not break the chain when one save fails — the next selection still saves", async () => {
    const h = harness();
    h.api.saveProperty.mockImplementationOnce(() => Promise.reject(new Error("boom")));
    captured.onChange!(parcel("A"));
    captured.onChange!(parcel("B"));
    await flush(); await flush();
    expect(h.status.some((m) => m.includes("parcel boundary not saved: boom")),
      "a failed save must be reported").toBe(true);
    h.settle[0]?.(); await flush();
    expect(h.api.saveProperty, "a rejection stalled the chain — every later selection is lost")
      .toHaveBeenCalledTimes(2);
  });

  it("says so when there is no project to save to, rather than skipping silently", () => {
    const h = harness(null);
    captured.onChange!(parcel("A"));
    expect(h.api.saveProperty).not.toHaveBeenCalled();
    expect(h.status.join(" "), "a skipped save with no message reads as a saved one")
      .toMatch(/open a project first/);
  });
});
