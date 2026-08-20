import { describe, expect, it, vi } from "vitest";

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
    const fetchMock = vi.fn(async () => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const api = { url: (p: string) => `http://api${p}`, authHeaders: () => ({ Authorization: "Bearer t" }) };
    await postSheetPin(api, "p1", "plan:L1", 10, 20, "crack", "WALL_A");
    expect(fetchMock.mock.calls[0]).toBeTruthy();
    const tied = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(tied).toEqual({
      sheet_id: "plan:L1", x: 10, y: 20, note: "crack", kind: "pin", data: { guid: "WALL_A" },
    });
    fetchMock.mockClear();
    await postSheetPin(api, "p1", "plan:L1", 1, 2, "note", null);
    const paper = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(paper.data).toBeUndefined();
    vi.unstubAllGlobals();
  });
});
