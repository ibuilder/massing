import { describe, expect, it } from "vitest";

import { createTestHarness } from "@massingifc/plugin-sdk";

import { MARKUP_RELOAD, MarkupToken, markupPlugin, reloadMarkup, type PinSource } from "./markupPlugin";

/** A PinOverlay stand-in. `failOn` makes the named step reject, as a real one would. */
function pins(failOn?: "load" | "modulePins") {
  const calls: string[] = [];
  const source: PinSource<{ ref?: string }> = {
    load: async (projectId) => {
      calls.push(`load:${projectId}`);
      if (failOn === "load") throw new Error("GET /pins failed: 503");
      return 2;
    },
    loadModulePins: async (projectId, onClick) => {
      calls.push(`modulePins:${projectId}`);
      if (failOn === "modulePins") throw new Error("one pin record is malformed");
      onClick({ ref: "RFI-004" });
      return 1;
    },
  };
  return { source, calls };
}

async function load(failOn?: "load" | "modulePins") {
  const p = pins(failOn);
  const clicked: string[] = [];
  const harness = createTestHarness();
  const result = await harness.load(markupPlugin({
    pins: p.source,
    onPinClick: (pin) => clicked.push(pin.ref ?? "?"),
  }));
  return { harness, p, clicked, result };
}

describe("markup is a plugin, and the host survives it failing", () => {
  it("loads and provides its capability", async () => {
    const { harness, result } = await load();
    expect(result.ok).toBe(true);
    expect(harness.kernel.capabilities.get(MarkupToken)).toBeTruthy();
  });

  it("the happy path loads both pin sets and wires the click handler", async () => {
    const { harness, p, clicked } = await load();
    const out = await reloadMarkup(harness.kernel.commands, "proj-1");
    expect(out.ok).toBe(true);
    expect(p.calls).toEqual(["load:proj-1", "modulePins:proj-1"]);
    expect(clicked).toEqual(["RFI-004"]);
    // The counts survive the round trip: "0 pins" and "pins failed" look identical on an empty
    // overlay, and only one of them is a problem worth telling somebody about.
    expect(out.detail).toBe("3 pins placed");
  });

  it("THE POINT: a pins failure comes back as a value, not an exception", async () => {
    // Before this plugin, `await pins.load(...)` was unguarded on the panel-build path, so one 503
    // aborted everything the caller had queued after it — and nothing on screen said why. The blast
    // radius of "the pins did not load" was "the rest of that setup did not run either".
    const { harness } = await load("load");
    const out = await reloadMarkup(harness.kernel.commands, "proj-1");
    expect(out.ok).toBe(false);
    expect(out.detail).toContain("503");
  });

  it("a failure part-way through is still contained", async () => {
    const { harness, p } = await load("modulePins");
    const out = await reloadMarkup(harness.kernel.commands, "proj-1");
    expect(out.ok).toBe(false);
    expect(p.calls).toEqual(["load:proj-1", "modulePins:proj-1"]);   // it got that far
  });

  it("the host is STILL USABLE after a plugin command fails", async () => {
    // "No plugin can crash the host" is the kernel's reason for existing. Asserting it on a real
    // failing path — not a synthetic one — is what makes this adoption worth the seam.
    const { harness } = await load("load");
    await reloadMarkup(harness.kernel.commands, "proj-1");
    expect(harness.kernel.capabilities.get(MarkupToken)).toBeTruthy();
    const again = await reloadMarkup(harness.kernel.commands, "proj-2");
    expect(again.ok).toBe(false);            // still failing, still not throwing
  });

  it("the command id is exported, so a caller cannot drift from the registration", () => {
    // A retyped string is a command that silently does not exist. Same class as the toolbar icon map
    // that was complete and never read.
    expect(MARKUP_RELOAD).toBe("massing.markup.reload");
  });

  it("an unknown command reports rather than throws", async () => {
    const { harness } = await load();
    const out = await reloadMarkup(harness.kernel.commands, "proj-1");
    expect(out.ok).toBe(true);
    const bogus = await harness.kernel.commands.execute("massing.markup.nope", {});
    expect(bogus.ok).toBe(false);
  });
});
