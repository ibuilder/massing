import { describe, expect, it, vi } from "vitest";

import type { PortalHost } from "../portal";
import {
  ELEMENT_CARD_CAP, lineGuids, recordElementGuids, renderTiedElements,
} from "./tiedElements";

function host(api: Record<string, unknown>): PortalHost {
  return {
    api,
    projectId: () => "p1",
    anchorPoint: () => null,
    selectedGuid: () => null,
    onSelectGuids: vi.fn(),
    onPinsChanged: () => undefined,
    setStatus: vi.fn(),
  } as unknown as PortalHost;
}

const STRIP = {
  guid: "1kP9xAbCdEf7Qa",
  states: [
    { key: "designed", status: "yes" },
    { key: "checked", status: "unknown" },
    { key: "priced", status: "yes" },
    { key: "scheduled", status: "none" },
    { key: "installed", status: "unknown" },
    { key: "verified", status: "unknown" },
  ],
  reached: "designed",
  done_count: 2,
  unknown_count: 3,
  next: { key: "checked", advance: null },
  inconsistencies: [],
};

describe("R24-ELEMENT-CARD ② — register call sites", () => {
  it("reads a GlobalId off an estimate line under any of the known keys", () => {
    expect(lineGuids([{ guid: "G1" }])).toEqual(["G1"]);
    expect(lineGuids([{ element_guid: "G2" }])).toEqual(["G2"]);
    expect(lineGuids([{ ExtIdentifier: "G3" }])).toEqual(["G3"]);
    expect(lineGuids([{ description: "no key" }])).toEqual([]);
  });

  it("unions tied GUIDs with line-item GUIDs and de-dupes", () => {
    expect(recordElementGuids({
      element_guids: ["A", "B"],
      data: { line_items: [{ guid: "B" }, { guid: "C" }] },
    })).toEqual(["A", "B", "C"]);
  });

  it("mounts the lifecycle card on an RFI that names an element", async () => {
    const api = {
      elementLifecycle: vi.fn().mockResolvedValue(STRIP),
      tagElements: vi.fn(),
    };
    const el = await renderTiedElements({
      pid: "p1", moduleKey: "rfi", ref: "RFI-1",
      record: { id: "r1", element_guids: ["1kP9xAbCdEf7Qa"], data: {} },
      host: host(api), onReload: () => undefined,
    });
    expect(el.querySelectorAll("[data-element-card]")).toHaveLength(1);
    expect(api.elementLifecycle).toHaveBeenCalledWith("p1", "1kP9xAbCdEf7Qa");
    expect(el.textContent).toMatch(/design/i);
  });

  it("mounts a card for an SOV / pay-app line and an asset-register / COBie row", async () => {
    const api = {
      elementLifecycle: vi.fn().mockResolvedValue(STRIP),
      tagElements: vi.fn(),
    };
    const sov = await renderTiedElements({
      pid: "p1", moduleKey: "sov", ref: "SOV-1",
      record: { id: "s1", element_guids: ["G-sov"], data: {} },
      host: host(api), onReload: () => undefined,
    });
    const ast = await renderTiedElements({
      pid: "p1", moduleKey: "asset_register", ref: "AST-1",
      record: { id: "a1", element_guids: ["G-ast"], data: {} },
      host: host(api), onReload: () => undefined,
    });
    expect(sov.querySelector("[data-element-card='G-sov']")).toBeTruthy();
    expect(ast.querySelector("[data-element-card='G-ast']")).toBeTruthy();
  });

  it("a failed lifecycle is the identity line, never a six-blank strip", async () => {
    const api = {
      elementLifecycle: vi.fn().mockRejectedValue(new Error("500")),
      tagElements: vi.fn(),
    };
    const el = await renderTiedElements({
      pid: "p1", moduleKey: "estimate", ref: "EST-1",
      record: {
        id: "e1", element_guids: null,
        data: { line_items: [{ guid: "1kP9xAbCdEf7Qa", description: "Slab" }] },
      },
      host: host(api), onReload: () => undefined,
    });
    expect(el.textContent).toContain("1kP9x…7Qa");
    expect(el.querySelector(".lcstrip")).toBeNull();
  });

  it("caps the cards and names the remainder as a sample", async () => {
    const guids = Array.from({ length: ELEMENT_CARD_CAP + 3 }, (_, i) => `G${i}`);
    const api = {
      elementLifecycle: vi.fn().mockResolvedValue(STRIP),
      tagElements: vi.fn(),
    };
    const el = await renderTiedElements({
      pid: "p1", moduleKey: "rfi", ref: "RFI-9",
      record: { id: "r9", element_guids: guids, data: {} },
      host: host(api), onReload: () => undefined,
    });
    expect(el.querySelectorAll("[data-element-card]")).toHaveLength(ELEMENT_CARD_CAP);
    expect(el.textContent).toContain(`showing the first ${ELEMENT_CARD_CAP}`);
  });
});
