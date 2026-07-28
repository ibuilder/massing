import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { ROOM_IDS, spineEnabled } from "./spine";

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

  it("the default really is on — the premise of everything below", () => {
    expect(spineEnabled("")).toBe(true);
  });

  it("no doc offers `?shell=spine` as the way to switch the new shell on", () => {
    // The instruction is not merely stale, it is misleading in a specific way: a reader who follows
    // it sees no change and concludes the feature is broken.
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      if (!spineEnabled("")) continue; // if the default ever flips back, the advice is correct again
      const offers = /(?:append|add|pass|use)\s+\*{0,2}`?\?shell=spine/i.test(text);
      expect(offers, `${name} tells the reader to opt in to a shell that is already on`).toBe(false);
    }
  });

  it("...and the opt-OUT stays documented, because it is the part that still works", () => {
    expect(README).toMatch(/\?shell=classic/);
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
