import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import type { ResolvedPin } from "../api/types";
import { describePin, handleRecordPinClick, type PinOpenDeps } from "./pinOpen";

function pin(over: Partial<ResolvedPin> = {}): ResolvedPin {
  return {
    source: "rfi", id: "rec-7", guid: "RFI-004", kind: "rfi", label: "Slab edge query",
    status: "open", element_guid: "2O2Fr$t4X7Zf8NOew3FNr2", icon: "?", source_name: "RFIs",
    x: 1, y: 2, z: 3, ...over,
  };
}

function deps() {
  const selected: Array<[string, boolean | undefined]> = [];
  const status: string[] = [];
  const opened: Array<[string, string]> = [];
  const d: PinOpenDeps = {
    selectByGuid: async (g, fit) => { selected.push([g, fit]); },
    setStatus: (m) => { status.push(m); },
    openRecord: (k, id) => { opened.push([k, id]); },
  };
  return { d, selected, status, opened };
}

describe("PIN-OPEN-ROW — clicking a register pin reaches the record", () => {
  it("opens the record the pin stands for", async () => {
    const { d, opened } = deps();
    await handleRecordPinClick(pin(), d);
    expect(opened).toEqual([["rfi", "rec-7"]]);
  });

  it("selects the element FIRST, so the highlight is still there on the way back", async () => {
    const order: string[] = [];
    await handleRecordPinClick(pin(), {
      selectByGuid: async () => { order.push("select"); },
      setStatus: () => { order.push("status"); },
      openRecord: () => { order.push("open"); },
    });
    expect(order).toEqual(["select", "status", "open"]);
  });

  it("selects by GlobalId and asks for a fit — never a transient viewer id", async () => {
    const { d, selected } = deps();
    await handleRecordPinClick(pin(), d);
    expect(selected).toEqual([["2O2Fr$t4X7Zf8NOew3FNr2", true]]);
  });

  it("still opens a pin that is tied to no element — `element_guid` is nullable, and a record "
     + "placed in space is exactly the case where the pin is the only way in", async () => {
    const { d, selected, opened } = deps();
    await handleRecordPinClick(pin({ element_guid: null }), d);
    expect(selected).toEqual([]);
    expect(opened).toEqual([["rfi", "rec-7"]]);
  });

  it("does NOT open for a topic pin — `source` would be the literal \"topic\", which is not a "
     + "module key, so the lookup would be a silent nothing", async () => {
    const { d, status, opened } = deps();
    await handleRecordPinClick(pin({ source: "topic", kind: "clash" }), d);
    expect(opened).toEqual([]);
    expect(status).toHaveLength(1);        // it still says what was clicked
  });

  it("still opens the record when selection REJECTS — the record id came from the pin, not from "
     + "the scene, so a stalled worker must not take the jump with it", async () => {
    const opened: Array<[string, string]> = [];
    const status: string[] = [];
    await handleRecordPinClick(pin(), {
      selectByGuid: () => Promise.reject(new Error("fragments worker stalled")),
      setStatus: (m) => { status.push(m); },
      openRecord: (k, id) => { opened.push([k, id]); },
    });
    expect(opened).toEqual([["rfi", "rec-7"]]);
    expect(status[0]).toContain("could not highlight");   // reported, not swallowed
  });

  it("a marker click does not also reach the canvas — `app.ts` raycasts container clicks and "
     + "clears the selection on a miss, which would undo the highlight a few frames later", () => {
    const src = readFileSync(join(process.cwd(), "src", "pins", "pins.ts"), "utf8");
    // Both arms: a topic marker is as deliberate a click target as a record one.
    expect(src.match(/el\.onclick = [^;]*stopPropagation/gs)?.length).toBe(2);
  });

  it("`main.ts` waits for the portal's own init rather than a fixed delay, at EVERY site — a "
     + "timeout standing in for a signal reports success either way, and there were three copies", () => {
    const src = readFileSync(join(process.cwd(), "src", "main.ts"), "utf8");
    expect(src).toMatch(/await openPortalTab\(\)/);
    // The guess, as CODE — the docstring quotes the old line on purpose and must not count.
    expect(src).not.toMatch(/^\s*if \(portal\.moduleList\(\)\.length\) go\(\);/m);
    // …and every caller goes through the one wait, so a fourth copy cannot appear quietly.
    expect(src.match(/void withPortal\(/g)?.length).toBe(2);
  });

  it("keeps the status line it always showed, including a pin with no status", () => {
    expect(describePin(pin())).toBe("RFI-004 · RFIs · open");
    expect(describePin(pin({ status: null }))).toBe("RFI-004 · RFIs");
  });

  /**
   * **The wire, not the handler.** Everything above passes on a handler nobody calls, and on a
   * `ViewerCtx` that never receives an opener — which is the state this item shipped in for months.
   * `openRecord` being required makes a MISSING wire a compile error; these two assert the wire
   * that exists is the real one, because `openRecord: () => {}` would also compile.
   */
  it("`app.ts` routes the pin click through this module rather than re-implementing it", () => {
    const src = readFileSync(join(process.cwd(), "src", "viewer", "app.ts"), "utf8");
    expect(src).toContain("handleRecordPinClick");
    expect(src).toMatch(/onPinClick:[^}]*handleRecordPinClick/s);
  });

  it("`main.ts` hands the viewer the SAME opener the command palette jumps with — two openers "
     + "would be two answers to the UX question this item was filed as needing", () => {
    const src = readFileSync(join(process.cwd(), "src", "main.ts"), "utf8");
    expect(src).toMatch(/openRecord:\s*jumpToRecord/);
    // The palette's own record hit must go through it too, or the shared function is shared with
    // nobody and the next edit drifts one of the two paths.
    expect(src).toMatch(/run:\s*\(\)\s*=>\s*jumpToRecord\(/);
  });
});
