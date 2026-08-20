import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../../api/client";
import type { PortalHost } from "../portal";
import {
  appendRecordElementTies, ELEMENT_CARD_MAX, ELEMENT_CARD_MODULES,
} from "./elementTies";

function host(over: Partial<PortalHost> = {}): PortalHost {
  return {
    api: {
      tagElements: vi.fn(),
      elementLifecycle: vi.fn().mockRejectedValue(new Error("offline")),
    } as unknown as ApiClient,
    projectId: () => "p1",
    anchorPoint: () => null,
    selectedGuid: () => null,
    onSelectGuids: vi.fn(),
    onPinsChanged: () => {},
    setStatus: vi.fn(),
    ...over,
  };
}

describe("R24-ELEMENT-CARD reach", () => {
  it("names the four remaining surfaces, and only those", () => {
    expect([...ELEMENT_CARD_MODULES].sort()).toEqual(
      ["asset_register", "estimate", "owner_invoice", "rfi"]);
  });

  it("mounts a card on an RFI that already has a GlobalId", async () => {
    const root = document.createElement("div");
    const lifecycle = vi.fn().mockRejectedValue(new Error("offline"));
    appendRecordElementTies(
      root,
      host({ api: { tagElements: vi.fn(), elementLifecycle: lifecycle } as unknown as ApiClient }),
      { key: "rfi" },
      { ref: "RFI-1", element_guids: ["1kP9xAbCdEf7Qa"] },
      "rid",
      () => {},
    );
    await vi.waitFor(() => expect(lifecycle).toHaveBeenCalledWith("p1", "1kP9xAbCdEf7Qa"));
    expect(root.textContent).toContain("1kP9x…7Qa");
  });

  it("does not mount a card on a schedule activity (too many GUIDs, not a named surface)", async () => {
    const root = document.createElement("div");
    const lifecycle = vi.fn();
    appendRecordElementTies(
      root,
      host({ api: { tagElements: vi.fn(), elementLifecycle: lifecycle } as unknown as ApiClient }),
      { key: "schedule_activity" },
      { ref: "ACT-1", element_guids: ["aaaaaaaaaaaaaaaaaaaaaa"] },
      "rid",
      () => {},
    );
    expect(lifecycle).not.toHaveBeenCalled();
    expect(root.textContent).toMatch(/4D scrub/);
  });

  it("caps the number of cards rather than mounting one per GUID", async () => {
    const root = document.createElement("div");
    const lifecycle = vi.fn().mockRejectedValue(new Error("offline"));
    const guids = Array.from({ length: ELEMENT_CARD_MAX + 5 }, (_, i) => `guid${String(i).padStart(16, "0")}`);
    appendRecordElementTies(
      root,
      host({ api: { tagElements: vi.fn(), elementLifecycle: lifecycle } as unknown as ApiClient }),
      { key: "estimate" },
      { ref: "EST-1", element_guids: guids },
      "rid",
      () => {},
    );
    await vi.waitFor(() => expect(lifecycle).toHaveBeenCalledTimes(ELEMENT_CARD_MAX));
    expect(root.textContent).toMatch(/Showing 8 of 13/);
  });
});
