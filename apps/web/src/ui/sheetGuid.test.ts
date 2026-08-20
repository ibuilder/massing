import { describe, expect, it, vi } from "vitest";

import { ApiClient } from "../api/client";
import { guidFromEvent, guidFromMarkupData, postSheetPin, selectInViewer } from "./sheetGuid";

describe("R38-SHEET-MARKUP ③ ① — guid on generated sheets", () => {
  it("reads the GlobalId from linework, not from a wrapper", () => {
    const svg = document.createElement("div");
    svg.innerHTML = '<svg><polyline data-guid="1kP9xAbCdEf7Qa" points="0,0 1,1"/></svg>';
    const poly = svg.querySelector("polyline")!;
    const e = { target: poly } as unknown as Event;
    expect(guidFromEvent(e)).toBe("1kP9xAbCdEf7Qa");
  });

  it("empty paper is null, never a guessed guid", () => {
    const paper = document.createElement("div");
    const e = { target: paper } as unknown as Event;
    expect(guidFromEvent(e)).toBeNull();
  });

  it("markup data.guid is the stored key; other shapes are ignored", () => {
    expect(guidFromMarkupData({ guid: "WALL_A" })).toBe("WALL_A");
    expect(guidFromMarkupData({ guid: "  " })).toBeNull();
    expect(guidFromMarkupData({ guid: 12 })).toBeNull();
    expect(guidFromMarkupData(null)).toBeNull();
  });

  it("selectInViewer uses the viewer hook, not a transient node id", () => {
    const selectByGuid = vi.fn();
    (window as unknown as { __viewer: { selectByGuid: typeof selectByGuid } }).__viewer = { selectByGuid };
    selectInViewer("DOOR_5F");
    expect(selectByGuid).toHaveBeenCalledWith("DOOR_5F", true);
  });

  it("postSheetPin sends data.guid only when the click hit linework", async () => {
    // Asserts the ENCODED BODY, not a mock's arguments, and drives it through the real client —
    // postSheetPin delegates to `addDrawingMarkup`, so the claim spans both hops. Stubbing the
    // client method instead would pass even if the client dropped the guid on the floor.
    const seen: (string | null)[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      seen.push((init?.body as string) ?? null);
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
    }));
    const api = new ApiClient("http://x");

    await postSheetPin(api, "p1", "plan:L1", 10, 20, "crack", "WALL_A");
    expect(JSON.parse(String(seen[0]))).toEqual({
      sheet_id: "plan:L1", x: 10, y: 20, note: "crack", kind: "pin", data: { guid: "WALL_A" },
    });

    await postSheetPin(api, "p1", "plan:L1", 1, 2, "note", null);
    const paper = JSON.parse(String(seen[1]));
    expect(paper.data).toBeUndefined();          // absent, not `null` — the server never has to guess
    expect("data" in paper).toBe(false);
    vi.unstubAllGlobals();
  });
});
