import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ROOM_IDS } from "./spine";

/**
 * The docs must describe the app that exists.
 *
 * This one is written from an actual failure. The new shell became the default in v0.3.715; the
 * README went on telling readers to append `?shell=spine` "to turn it on" for **fifty releases**,
 * and the walkthrough went on telling them to click a three-tab bar that the rooms had
 * replaced. Nothing caught it, because no gate reads prose — every check we own points at code.
 *
 * The trap in a docs test is writing the expectation twice: once in the doc and once in the
 * assertion, so the pair agrees with itself while both drift away from the product. So this file
 * asserts nothing of its own. It **calls `spineEnabled()` and reads `ROOM_IDS`**, and requires the
 * prose to agree with whatever they say today. Flip the default back and this test flips with it.
 */

// process.cwd() is apps/web under vitest — not this file's directory, and not the repo root.
// (`import.meta.url` was tried here and throws "The URL must be of scheme file" in a batch run.)
const REPO = resolve(process.cwd(), "..", "..");

function doc(rel: string): string {
  const text = readFileSync(resolve(REPO, rel), "utf8");
  expect(text.length, `${rel} did not load — every assertion below would pass vacuously`)
    .toBeGreaterThan(1000);
  return text;
}

const README = doc("README.md");
const WALKTHROUGH = doc("docs/walkthrough.md");

describe("the shell docs match the shell default", () => {
  beforeEach(() => localStorage.clear());

  it("there is no shell flag left to document", async () => {
    // The premise of everything below used to be "the default really is on". With the opt-out gone
    // (v0.3.779) the premise is stronger: there is only one shell, so any doc describing a way to
    // switch shells is describing something that does not exist.
    const mod = await import("./spine") as Record<string, unknown>;
    expect(mod.spineEnabled).toBeUndefined();
  });

  it("no doc offers `?shell=spine` as the way to switch the new shell on", () => {
    // The instruction is not merely stale, it is misleading in a specific way: a reader who follows
    // it sees no change and concludes the feature is broken.
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      const offers = /(?:append|add|pass|use)\s+\*{0,2}`?\?shell=spine/i.test(text);
      expect(offers, `${name} tells the reader to opt in to a shell that is already on`).toBe(false);
    }
  });

  it("...and the deleted opt-OUT is not documented either", () => {
    // `?shell=classic` was removed in v0.3.779. Docs describing a flag that no longer exists are
    // worse than docs that omit it: the reader tries it, nothing happens, and they conclude the
    // shell is broken rather than that the instruction is stale. This is the same failure the
    // README once had in the other direction, telling readers to opt IN to a default-on shell.
    expect(README).not.toMatch(/\?shell=classic/);
    expect(WALKTHROUGH).not.toMatch(/\?shell=classic/);
  });
});

describe("the docs name the navigation the user will actually see", () => {
  it("every room appears in the README", () => {
    for (const id of ROOM_IDS) {
      expect(README.toLowerCase(), `README never mentions the "${id}" room`).toContain(id);
    }
  });

  it("the retired three-tab bar is not described as the primary nav", () => {
    // Workspaces still exist underneath — a room maps to one. What is gone is the *bar*: it is not
    // what a user clicks any more, so a doc that tells them to click it sends them looking for
    // something that is not on screen.
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      expect(text, `${name} still describes the retired three-tab bar`)
        .not.toMatch(/Model\s*\/\s*Construction\s*\/\s*Finance\s+(?:bar|tabs)/i);
    }
  });
});
