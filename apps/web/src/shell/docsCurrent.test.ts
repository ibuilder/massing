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

  /**
   * Naming every room is not the same as counting them correctly, and the difference is not academic:
   * on 2026-07-29 the README opened with "reached through **six** rooms" and listed six by name, three
   * releases after `operate` made seven (R30). The check above passed the whole time — `toContain("operate")`
   * was satisfied by the word "operate" sitting in an unrelated sentence further down ("coordinate,
   * schedule, underwrite & operate it"). The walkthrough carried the same wrong number.
   *
   * A reader who counts six tabs and sees seven concludes the docs describe a different version. So the
   * count is asserted against `ROOM_IDS.length` rather than written down here — the number word is
   * derived, not duplicated, so adding room eight fails this and cannot be satisfied by prose drift.
   */
  const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

  it("no doc counts the rooms and then lists them wrongly", () => {
    /**
     * Scoped to the shape the defect actually takes: a count word *immediately followed by an
     * enumeration* ("six rooms — Design, Planning, Cost, Schedule, Deal, Work"). A bare number near the
     * word "rooms" is not a claim about how many exist — "move between two rooms" and "no two rooms can
     * quote different figures" are both fine, and an earlier draft of this test failed on both. Past-tense
     * history ("restructured around five rooms", true at v0.3.684) is likewise not a claim about today,
     * and is not followed by a list.
     */
    const expected = NUMBER_WORDS[ROOM_IDS.length]!;
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      for (const m of text.matchAll(/\b([a-z]+)\s+rooms\b(.{0,160})/gis) as Iterable<RegExpMatchArray>) {
        const word = m[1]!.toLowerCase();
        if (!NUMBER_WORDS.includes(word)) continue;
        const named = ROOM_IDS.filter((id) => new RegExp(`\\b${id}\\b`, "i").test(m[2] ?? "")).length;
        if (named < 3) continue;   // not an enumeration, so not a count of the rooms
        expect(word, `${name} says "${word} rooms" and then lists them, but there are ${ROOM_IDS.length}`)
          .toBe(expected);
      }
    }
  });

  it("every doc that introduces the rooms names all of them", () => {
    // The other half: a count can be right while the list is short. Both README and the walkthrough
    // introduce the navigation, so both must name the full set somewhere — otherwise a reader learns
    // six tabs and finds seven. Derived from ROOM_IDS, so room eight fails this on the day it lands.
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      const missing = ROOM_IDS.filter((id) => !new RegExp(`\\b${id}\\b`, "i").test(text));
      expect(missing, `${name} never names the ${missing.join(", ")} room(s) by name`).toEqual([]);
    }
  });

  it("a doc that enumerates the rooms lists them in the shipped ORDER", () => {
    /*
     * COUNT and MEMBERSHIP were gated above; ORDER was not, and order is what a reader follows.
     * `ROOM_IDS` is the tab strip left-to-right, so a doc that walks the rooms in a different
     * sequence describes a screen nobody has — the same class of defect as a wrong count, and
     * invisible to both checks above because every name is present and there are seven of them.
     *
     * Only a genuine LIST is judged — >= 4 room names separated by nothing but punctuation,
     * conjunctions and formatting. A proximity window was tried first and was wrong: it read the
     * click-through's *route* ("Schedule → Budget … back in Design … the Cost room … Work") as a
     * claim about tab order and failed on correct prose. A navigation sequence is not an
     * enumeration, and a gate that cannot tell them apart would be answered by rewriting good
     * writing to suit it — the same false-positive trap as matching "X like" without a hyphen.
     *
     * Requiring the separators to be verb-free is what makes the difference: "Deal, Design,
     * Planning, …" is a list; "go to Schedule, then back in Design" is not.
     */
    const canonical = ROOM_IDS.join(" > ");
    const SEP = "[\\s,;·•/&>→—–-]|\\*\\*|and|then";           // list glue, never a verb
    const listRe = new RegExp(
      `\\b(?:(?:${ROOM_IDS.join("|")})\\b(?:${SEP})+){3,}(?:${ROOM_IDS.join("|")})\\b`, "gi");
    for (const [name, text] of [["README.md", README], ["walkthrough.md", WALKTHROUGH]] as const) {
      for (const m of text.matchAll(listRe)) {
        const seen: string[] = [];
        for (const h of m[0].matchAll(new RegExp(`\\b(${ROOM_IDS.join("|")})\\b`, "gi"))) {
          const id = h[1]!.toLowerCase();
          if (!seen.includes(id)) seen.push(id);
        }
        if (seen.length < 4) continue;
        const expectedOrder = ROOM_IDS.filter((id) => seen.includes(id));
        expect(seen, `${name} lists the rooms as "${seen.join(" > ")}" but they ship as `
          + `"${canonical}" — a reader following this doc clicks along a strip that is not there`)
          .toEqual([...expectedOrder]);
      }
    }
  });

  it("the walkthrough SAYS something about every room, not just names it once", () => {
    /*
     * The membership check above is satisfied by a single headline enumeration — and it was. On
     * 2026-08-01 the walkthrough named all seven rooms in one line and then never mentioned
     * `planning`, `work` or `operate` again: three of seven rooms were listed and never explained,
     * while `cost` got eleven mentions. A reader was told the room exists and never told what it is
     * for, which is the doc-level version of a tab that highlights but does not navigate.
     *
     * The bar is deliberately low — mentioned at least twice, i.e. somewhere beyond the enumeration.
     * It cannot judge prose quality; it can prove a room was not silently dropped from the tour.
     */
    const counts = Object.fromEntries(ROOM_IDS.map((id) =>
      [id, (WALKTHROUGH.match(new RegExp(`\\b${id}\\b`, "gi")) ?? []).length]));
    const namedOnce = ROOM_IDS.filter((id) => counts[id]! < 2);
    expect(namedOnce, `walkthrough.md names ${namedOnce.join(", ")} in the room list and nowhere `
      + `else, so the tour never visits it. Counts: ${JSON.stringify(counts)}`).toEqual([]);
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
