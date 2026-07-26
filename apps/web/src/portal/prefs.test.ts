import { beforeEach, describe, expect, it } from "vitest";
import { readCollapsedStages, readRoomOpen, setRoomOpen, setStageCollapsed } from "./prefs";

/**
 * R26-SHELL. Spine rooms are tri-state and stages are not, which is the only reason they do not
 * share a store. The tests below are the ones that would have caught collapsing the two: a room the
 * user has never touched must be distinguishable from one they explicitly closed, or the rail either
 * forgets an explicit collapse or overrides an explicit expansion.
 */
describe("room open/closed memory is tri-state", () => {
  beforeEach(() => localStorage.clear());

  it("says nothing about a room the user has never touched", () => {
    expect(readRoomOpen("construction:cost")).toBeNull();
  });

  it("remembers BOTH answers — closed is a decision, not an absence", () => {
    setRoomOpen("construction:cost", false);
    expect(readRoomOpen("construction:cost")).toBe(false);
    setRoomOpen("construction:cost", true);
    expect(readRoomOpen("construction:cost")).toBe(true);
  });

  it("keys per workspace, so a room folded in one is not folded in all", () => {
    setRoomOpen("construction:model", false);
    expect(readRoomOpen("design:model")).toBeNull();
  });

  it("survives a corrupt store rather than throwing on every rail build", () => {
    localStorage.setItem("portal-room-open", "{not json");
    expect(readRoomOpen("construction:cost")).toBeNull();
    setRoomOpen("construction:cost", true);           // recovers by rewriting
    expect(readRoomOpen("construction:cost")).toBe(true);
  });

  it("does not share a store with the stage memory", () => {
    setRoomOpen("construction:cost", false);
    expect(readCollapsedStages().has("construction:cost")).toBe(false);
    setStageCollapsed("construction:Money", true);
    expect(readRoomOpen("construction:Money")).toBeNull();
  });
});
