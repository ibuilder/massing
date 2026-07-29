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

describe("the walkthrough describes the app as it ships now", () => {
  /**
   * The walkthrough is the demo script — it is what somebody reads before recording, and a scene that
   * is not in it does not get demoed. On 2026-07-29 it had **zero** mentions of the vitals strip
   * (shipped v0.3.773) or the `.mass` container (the thing every sample actually IS), while being
   * otherwise current: it knew all six rooms. Staleness here is not a wrong sentence, it is a missing
   * one, which no spell-check or link-check finds and no reader misses.
   *
   * These assert on *features that exist*, not on prose. If one is deleted from the product, delete
   * its line here too — that is a decision, and it should look like one.
   */
  it("mentions the vitals strip — the continuous proof of the one-model claim", () => {
    expect(WALKTHROUGH.toLowerCase()).toContain("vitals");
  });

  it("says what a sample IS, not just that one exists", () => {
    // "Sample library" alone reads as "some meshes to look at". The point of the library is that a
    // sample opens as a PROJECT — geometry plus every table — which is the whole difference between
    // this and a viewer.
    expect(WALKTHROUGH).toMatch(/\.mass/);
  });

  it("does not offer a room the product does not have", () => {
    // The inverse failure, and the one the demo snapshot actually committed: naming `model` as a room
    // after it was renamed `design` at v0.3.766.
    expect(WALKTHROUGH).not.toMatch(/\b(?:the\s+)?Model\s+room\b/i);
  });
});

describe("the public Pages site does not send visitors after things that were deleted", () => {
  /**
   * `docs/*.html` is the GitHub Pages site — the first thing a stranger reads, and the copy least
   * likely to be re-read by anyone who works here. On 2026-07-29 `guide.html` step 2 still said
   * "Open ▾ → BasicHouse", a sample **deleted at v0.3.777** along with the two other bundled `.frag`
   * files. A reader follows that, finds no such entry, and concludes the app is broken — which is a
   * worse outcome than the instruction simply being absent.
   *
   * The three deleted sample names are asserted individually rather than as a regex alternation so a
   * failure names which one came back.
   */
  const GUIDE = doc("docs/guide.html");
  const INDEX = doc("docs/index.html");

  for (const gone of ["BasicHouse", "school_str", "school_arq"]) {
    it(`does not offer the deleted "${gone}" sample`, () => {
      expect(GUIDE, `guide.html still points at ${gone}`).not.toContain(gone);
      expect(INDEX, `index.html still points at ${gone}`).not.toContain(gone);
    });
  }

  it("names the rooms a visitor will actually land in", () => {
    // Being silent about the entire navigation is its own kind of stale. The landing page describes
    // what the product IS; six rooms is what it is.
    for (const id of ROOM_IDS) {
      const label = id[0]!.toUpperCase() + id.slice(1);
      expect(INDEX, `index.html never names the ${label} room`).toContain(label);
    }
  });
});
