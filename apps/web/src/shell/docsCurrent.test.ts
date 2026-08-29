import { globSync, readFileSync } from "node:fs";
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

/**
 * The module and section COUNTS, and the section NAMES.
 *
 * Added 2026-08-13 after finding both wrong at once. Four published docs said "133 modules / 30
 * sections" against a real 137 / 37 — drifted for four releases with nothing to catch it. The room
 * count above has been gated since the day it was wrong; the module count never was, and that gap is
 * the whole reason one drifted and the other did not. **A gate's scope is part of its claim.**
 *
 * The worse half was not the number. `gc-portal.md` — the document whose job is describing the module
 * engine — named fifteen sections, and **seven did not exist**: Preconstruction, Engineering, Field,
 * Cost, BIM, Facilities, Schedule. A wrong count is a stale fact; wrong names are a description of a
 * different product, and a reader has no way to tell which of the fifteen to trust.
 *
 * Derived from `module.json` on disk, never written down here, for the reason in the header comment:
 * an expectation stated twice agrees with itself while both halves drift.
 *
 * **Widened 2026-08-29 to the hyphenated and singular forms, because the README was wrong in
 * exactly the shape this could not see.** It read "a **near-100-module** GC portal" against a real
 * 139 -- an understatement of forty, sitting eleven lines above a correct "139 modules / 37
 * sections" in the same file. The old pattern required a SPACE and the PLURAL, so `100-module`
 * matched nothing and drifted freely while the number one screen down was gated.
 *
 * That is this block's own docstring arriving about this block: *a gate's scope is part of its
 * claim.* It was written after four docs drifted for four releases, and the fix it shipped left a
 * spelling of the same fact outside the population -- two counts of one thing, one of them checked.
 */
describe("the docs describe the module engine that exists", () => {
  const MODULES = globSync("services/api/modules/*/module.json", { cwd: REPO })
    .map((rel) => JSON.parse(readFileSync(resolve(REPO, rel), "utf8")) as { section?: string });
  const SECTIONS = new Set(MODULES.map((m) => m.section).filter((s): s is string => !!s));

  const COUNTED = [
    ["README.md", README],
    ["docs/gc-portal.md", doc("docs/gc-portal.md")],
    ["docs/user-guide/README.md", doc("docs/user-guide/README.md")],
    ["docs/user-guide/rooms.md", doc("docs/user-guide/rooms.md")],
  ] as const;

  it("the module corpus loaded — otherwise every assertion here is vacuous", () => {
    expect(MODULES.length).toBeGreaterThan(50);
    expect(SECTIONS.size).toBeGreaterThan(10);
    expect(MODULES.filter((m) => !m.section)).toEqual([]);
  });

  it("no doc states a module or register count that is not the real one", () => {
    for (const [name, text] of COUNTED) {
      for (const m of text.matchAll(/\b(\d{2,4})[- ](modules?|registers?)\b/g)) {
        expect(Number(m[1]), `${name} says "${m[0]}" — there are ${MODULES.length}`)
          .toBe(MODULES.length);
      }
    }
  });

  it("no doc states a section count that is not the real one", () => {
    for (const [name, text] of COUNTED) {
      for (const m of text.matchAll(/\b(\d{1,3})[- ](sections?)\b/g)) {
        expect(Number(m[1]), `${name} says "${m[0]}" — there are ${SECTIONS.size}`)
          .toBe(SECTIONS.size);
      }
    }
  });

  it("every section a doc names is a section that exists", () => {
    // Scoped to the sentence that introduces the sections, so ordinary prose using a word that
    // happens to be a section name ("the drawings room") is not dragged in. The failure this
    // catches is a LIST of names presented as the product's sections.
    const intro = doc("docs/gc-portal.md").match(/sections span the whole job[^.]*\./s)?.[0] ?? "";
    expect(intro, "gc-portal.md no longer introduces the sections — re-point this assertion")
      .not.toBe("");
    const named = intro.match(/[A-Z][a-z]+(?: [A-Z][a-z]+)*/g) ?? [];
    expect(named.length, "the intro sentence names no sections — the assertion below is vacuous")
      .toBeGreaterThan(5);
    const fiction = named.filter((n) => !SECTIONS.has(n));
    expect(fiction, `gc-portal.md names sections that do not exist: ${fiction.join(", ")}`)
      .toEqual([]);
  });
});

/**
 * `docs/status.html` is titled "Massing — current status" and is linked from `index.html`,
 * `guide.html`, `capabilities.html` and the docs index. On 2026-08-13 its "Recently shipped" section
 * still showcased v0.3.573–581 as "the latest wave" against a live **v0.3.932** — 352 releases, six
 * weeks. Nothing was wrong with the page; it simply stopped being true, and no check reads prose.
 *
 * The version BADGE on that page is live (a shields.io release image), which is what made the rot
 * invisible: the number at the top was correct while the story underneath it was a year of releases
 * out of date. **A live widget beside stale prose reads as a fresh page.**
 *
 * The bound is deliberately loose. This is not asking the page to track every release — it is asking
 * that a page calling itself "current" is not a whole ring of work behind. Tighten it and it fails on
 * every release; drop it and it fails never, which is where this started.
 */
describe("the page that calls itself 'current status' is not a ring behind", () => {
  const LAG = 75;
  const version = (s: string) => Number(/^0\.3\.(\d+)$/.exec(s)?.[1] ?? NaN);

  it("compares against a real version, or it is measuring nothing", () => {
    const pkg = JSON.parse(readFileSync(resolve(REPO, "apps/web/package.json"), "utf8")) as {
      version: string;
    };
    expect(Number.isFinite(version(pkg.version)), `unparseable version ${pkg.version}`).toBe(true);
  });

  it("names a release within reach of the shipped one", () => {
    const pkg = JSON.parse(readFileSync(resolve(REPO, "apps/web/package.json"), "utf8")) as {
      version: string;
    };
    const now = version(pkg.version);
    const html = readFileSync(resolve(REPO, "docs/status.html"), "utf8");
    // `\d{3,}`, not `\d{3}`. THE THIRD WAY THIS FAMILY OF GATE HAS BEEN WRONG, and the worst:
    // `\d{3}` matched the first three digits of a FOUR-digit release, so `v0.3.1018` was read as
    // **101** — smaller than the v0.3.928 already on the page. Past v0.3.999 the gate could no
    // longer see any release at all: it reported a growing lag that refreshing the page could not
    // fix, because the newest number it was capable of reading was frozen in the 900s. A bound that
    // cannot be satisfied by doing the right thing teaches the next reader to raise the bound.
    const named = [...html.matchAll(/v0\.3\.(\d{3,})/g)].map((m) => Number(m[1]));
    expect(named.length, "status.html names no release at all — this assertion is vacuous")
      .toBeGreaterThan(3);
    const newest = Math.max(...named);
    expect(
      now - newest,
      `status.html's newest release is v0.3.${newest} but the app is v0.3.${now} — ` +
        `${now - newest} behind. It calls itself "current status"; refresh "Recently shipped".`,
    ).toBeLessThanOrEqual(LAG);
  });
});

/**
 * `CHANGELOG.md` stopped at v0.3.881 on 2026-08-07 and **fifty-two releases shipped without an
 * entry** — 22 of them tagged — before a documentation audit noticed on 2026-08-13. Nothing warned:
 * the release flow bumps four version files and tags, and the changelog is a fifth step that simply
 * stopped being taken. A missing entry is invisible in exactly the way a wrong one is not.
 *
 * **This gate was wrong when first written, in the two ways that matter most.** It is recorded here
 * because both are easy to repeat:
 *
 * 1. The bound was 75 — *larger than the 52-release gap it was written for*. It passed on the exact
 *    incident it existed to catch. A threshold looser than the failure you are guarding against is
 *    decoration. Mutation-testing found it; reading it did not.
 * 2. Headings here are RANGES (`## v0.3.882–933`), and the first regex captured only the opening
 *    number. A changelog current to 933 would have been read as stopping at 882 and failed a
 *    correctly-maintained file — the mirror error, and the one that would have got the gate deleted.
 *
 * So: parse both ends of a range, and keep the bound below the size of a real lapse.
 */
describe("the changelog is not a ring behind the shipped version", () => {
  // Under the 52-release gap this was written for, and above a normal batch — several releases a day
  // land here, and entries are legitimately written per-batch rather than per-release.
  const LAG = 25;

  it("names a release within reach of the shipped one", () => {
    const pkg = JSON.parse(readFileSync(resolve(REPO, "apps/web/package.json"), "utf8")) as {
      version: string;
    };
    const now = Number(/^0\.3\.(\d+)$/.exec(pkg.version)?.[1] ?? NaN);
    expect(Number.isFinite(now), `unparseable version ${pkg.version}`).toBe(true);

    const log = readFileSync(resolve(REPO, "CHANGELOG.md"), "utf8");
    // Both ends: `## v0.3.877` and `## v0.3.882–933` / `## v0.3.878-881`.
    // `\d{3,}` on BOTH halves — same digit-boundary trap as the status gate above, and this one
    // already had a range bug recorded in the docstring. A heading `## v0.3.1002–1018` parsed as
    // 100–101 under the old pattern.
    const named = [...log.matchAll(/^## v0\.3\.(\d{3,})(?:\s*[–—-]\s*(\d{3,}))?/gm)]
      .flatMap((m) => [Number(m[1]), m[2] ? Number(m[2]) : Number(m[1])]);
    expect(named.length, "CHANGELOG.md has no `## v0.3.x` headings — this assertion is vacuous")
      .toBeGreaterThan(3);
    const newest = Math.max(...named);
    expect(
      now - newest,
      `CHANGELOG.md's newest entry is v0.3.${newest} but the app is v0.3.${now} — ${now - newest} ` +
        `releases unrecorded. Add an entry, or reconcile the range from the release commits.`,
    ).toBeLessThanOrEqual(LAG);
  });
});

/**
 * `apps/web/README.md`'s pinned-version table must agree with `apps/web/package.json`.
 *
 * CLAUDE.md calls the `@thatopen/components` <-> `@thatopen/fragments` <-> `three` coupling the #1
 * risk in this project, and that table is where a human reads it. On 2026-08-25 **six of its ten
 * rows were wrong** — components 3.4.6 (really 3.4.8), fragments 3.4.5 (3.4.7), components-front
 * 3.4.3 (3.4.4), ui 3.4.3 (3.4.10), three 0.184.0 (0.185.1), @types/three 0.184.1 (0.185.4) — and
 * the `vite` row was wrong three times over in one cell: it named 6.4.3, declared the repo pinned
 * to v6, and justified it with "this machine has 20.3.1" while the repo shipped vite 8.2.1 on
 * node >=24.
 *
 * The table had been *edited* at v0.3.1048 without being *re-derived*, which is the failure this
 * whole file exists for, aimed at the one document whose job is to say what is installed. Same
 * construction as the rest of the file: **the expectation is not written twice.** The manifest is
 * the source, the prose has to agree with it, and bumping a dependency without touching the README
 * is what goes red.
 */
describe("apps/web/README.md's pinned versions", () => {
  it("match apps/web/package.json exactly", () => {
    const pkg = JSON.parse(readFileSync(resolve(REPO, "apps/web/package.json"), "utf8")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };
    const manifest = { ...pkg.dependencies, ...pkg.devDependencies };

    const text = doc("apps/web/README.md");
    // Table rows only: `| name | version | notes |`. The version cell may carry a "(dev)" tag.
    const rows = [...text.matchAll(/^\|\s*([@a-z0-9/.-]+)\s*\|\s*([0-9][^|]*?)\s*\|/gm)]
      .map((m) => ({ name: m[1] ?? "", cell: (m[2] ?? "").replace(/\s*\(dev\)\s*$/, "").trim() }));

    // Anti-vacuity, and it is not decoration: a heading rename or a switch to a bullet list would
    // otherwise leave this suite green while measuring an empty table.
    expect(rows.length, "no version rows parsed from apps/web/README.md — this assertion is vacuous")
      .toBeGreaterThanOrEqual(8);

    // A row naming a package the manifest does not install is the STALEST row the table can hold,
    // and the first draft of this block dropped exactly those rows with the comment "not this
    // check's business" — so removing a dependency from `package.json` while leaving its README row
    // behind would have left the table describing a package nobody installs, green.
    //
    // That is the one-directional-gate shape this repository keeps re-finding: the version
    // comparison only ever ran over rows that survived a filter derived from the thing being
    // checked, so the population was defined to exclude the failure. `test_env_documented` is
    // bidirectional for the same reason, and `test_lock_satisfies_requirements` records two
    // incidents from the half of its own claim it left unstated. Filtering by the source of truth
    // is how a check quietly stops asking its own question.
    //
    // Every row is now accounted for: named-and-installed, or named-and-not-installed and reported.
    const uninstalled = rows.filter((r) => !(r.name in manifest)).map((r) => r.name);
    expect(uninstalled, "apps/web/README.md's version table lists packages apps/web/package.json " +
      "does not install — delete the rows, or restore the dependencies").toEqual([]);

    const wrong = rows
      .filter((r) => r.name in manifest)
      .filter((r) => (manifest[r.name] ?? "").replace(/^[\^~]/, "") !== r.cell)
      .map((r) => `${r.name}: README says ${r.cell}, package.json says ${manifest[r.name]}`);
    expect(wrong, "the README's pinned-version table disagrees with package.json — re-derive it " +
      "from the manifest rather than editing the number you noticed").toEqual([]);
  });
});
