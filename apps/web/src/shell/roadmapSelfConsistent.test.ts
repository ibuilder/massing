import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The roadmap must not say an item shipped in one place and open in another.
 *
 * WHY THIS EXISTS, AND WHY IT IS NOT THE GATE IT WAS COMMISSIONED AS
 *     Three items — `A29-PLACE-VALID ②`, `A29-SPATIAL-SELECT ②`, `A29-UNDO-LOCAL ③` — sat in the
 *     roadmap declaring **SHIPPED in their own text with no ✅ marker**, so every reader and every
 *     check treated them as available work. They were found by hand.
 *
 *     The proposed fix was to port `roadmapStale.test.ts` to TypeScript. That gate scans module
 *     **docstrings** for an item id and asks "does code exist that nobody marked done?"; its
 *     population is `services/api/src` + `services/data/src`, Python only, and all three items are
 *     TypeScript.
 *
 *     **The port was measured and rejected.** The convention it depends on barely exists in the TS
 *     tree: of **158** hand-written TS modules, **6** declare an item id on the first comment line,
 *     and **none of the six is one of the three items that motivated the work**. A port would have
 *     covered ~4% of its claimed population — the same "the check could not see it" defect this repo
 *     hit five times on 2026-08-06, and the only instance we would have *built on purpose*, having
 *     spent that day naming it. Widening the scan from the first line to the whole file body does not
 *     rescue it either: an item id mentioned in passing is not a declaration, so that trades false
 *     positives for a coverage hole it still does not close. **A wider predicate is not a better one.**
 *
 *     Do not re-propose the port. The measurement above is the reason, and it is cheap to re-run.
 *
 * WHAT THIS CHECKS INSTEAD
 *     How the three were actually found: by reading the **roadmap**, not the code. That question has
 *     no language population to get wrong, cannot rot when a file is renamed, and its population is
 *     the document it is about. `roadmapStale.test.ts` is NOT replaced — the two answer different
 *     questions: *code exists that nobody marked done* versus *the document contradicts itself*.
 *
 * THE DISCRIMINATOR THAT MAKES IT SHIPPABLE
 *     A naive "body says SHIPPED but no ✅" rule flagged **11**, of which four were correct as
 *     written, because `◧` and `🟡` already mean **a half shipped**:
 *
 *         ◧ SEC-PLUGIN-SANDBOX  "the binding half SHIPPED …; the setrlimit half is REFUSED"
 *         🟡 R24-CHARTS-GRAMMAR  "no-data rule SHIPPED v0.3.783, **the rest open**"
 *
 *     Excluding those glyphs leaves the real cases with no false positives. A gate that cries wolf
 *     about correct entries is one people switch off inside a week.
 *
 * A STATED BLIND SPOT — read this before trusting a green run
 *     `laneClaims` deliberately reads only **item-scoped** annotations, `CODE *(… SHIPPED …)*`. A
 *     lane row may also make a **row-level** claim covering every code in the cell, and this gate
 *     does not act on those, because their scope is genuinely ambiguous and resolving one is the lane
 *     owner's call rather than a matcher's.
 *
 *     That is not hypothetical. As of 2026-08-06 the Lane D row reads "**all SHIPPED and MERGED**
 *     (PRs #176/#178/#179)" over eight codes, and **only two of the eight bullets carry ✅** — while
 *     one of the eight, `SEC-PLUGIN-SANDBOX`, is marked `◧` with half of it explicitly REFUSED, so
 *     "all" is false on its face. Reported rather than auto-marked: writing six ✅ marks from an
 *     ambiguous sentence is the confident-wrong failure this repo keeps paying for.
 */

// process.cwd() is apps/web under vitest; happy-dom leaves import.meta.url without a file: scheme,
// so resolve from cwd the way shell/roadmapLanes.test.ts does.
const REPO = join(process.cwd(), "..", "..");
const LINES = readFileSync(join(REPO, "docs/roadmap.md"), "utf8").split("\n");

/** Gated items are deliberately unmarked; the open backlog is everything above that heading. */
const GATED_AT = LINES.findIndex((l) => l.startsWith("## ⛔ Gated"));
const OPEN = LINES.slice(0, GATED_AT === -1 ? LINES.length : GATED_AT);

/** One source for the increment vocabulary — the same lesson `roadmapLanes.test.ts` records twice. */
const MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕";

/**
 * Status glyphs a bullet may carry. **`⛔` is here and is NOT in `roadmapLanes.test.ts`'s copy** —
 * found by the loose/strict comparison below, which flagged two live bullets on first run:
 *
 *     L672   - ⛔️ **R23-PICKING** *(M)* — CLOSED UNBUILT 2026-07-31, on a measurement…
 *     L1251  * ⛔ **R22-PHOTO-CV defect detection — REFUSED IN PLACE**…
 *
 * Both forms appear: bare `⛔` (U+26D4) and `⛔️` with a variation selector (U+FE0F), which are
 * different strings and must both be listed. Closed and refused items arguably *should* sit outside
 * the assignable population — but in the lane gate they do so **by accident**, because nobody added
 * the glyph, not because anyone decided it. An exclusion that works by omission also hides a live
 * item that adopts the glyph by mistake. Reported to the lane gate's owner rather than edited here.
 */
const GLYPHS = "(?:✅ |◧ |🟡 |⭐ |⛔️ |⛔ )?";

const ITEM = new RegExp(
  String.raw`^\s*[-*] ${GLYPHS}\*\*([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,}?)(?:\s*([${MARKS}]))?(?:\s|\*\*|—)`,
);

interface Bullet { line: number; done: boolean; partial: boolean; bodyShipped: boolean }

/** code -> the bullet's own claims. A bullet's body runs until the next bullet or heading. */
function bullets(): Map<string, Bullet> {
  const out = new Map<string, Bullet>();
  for (let i = 0; i < OPEN.length; i++) {
    const head = OPEN[i] ?? "";
    const m = ITEM.exec(head);
    if (!m?.[1]) continue;
    let body = head;
    for (let j = i + 1; j < OPEN.length; j++) {
      const l = OPEN[j] ?? "";
      if (ITEM.test(l) || l.startsWith("#")) break;
      body += "\n" + l;
    }
    out.set(m[2] ? `${m[1]} ${m[2]}` : m[1], {
      line: i + 1,
      done: head.includes("✅"),
      // ◧ / 🟡 mean "a half shipped", so SHIPPED in the body is correct rather than contradictory.
      //
      // Alternation, NOT a character class. `🟡` is U+1F7E1 — outside the BMP, so a non-`u` regex
      // stores it as a surrogate PAIR, and `[◧🟡]` becomes a class of three code units that matches
      // either half on its own. eslint's `no-misleading-character-class` caught it. The bug it would
      // have caused is a false *positive* — a lone surrogate is not something this file will meet —
      // but the class was not matching what it appeared to, which is the same defect as a regex that
      // matches nothing: the code says one thing and the engine does another.
      partial: /◧|🟡/.test(head),
      bodyShipped: /\bSHIPPED\b/.test(body),
    });
  }
  return out;
}

/**
 * code -> the lane cell's annotation, for ITEM-SCOPED claims only.
 *
 * Requires the SHIPPED word inside a `*(…)*` that immediately follows the code, so a row-level
 * sentence trailing the last code in a cell is not misattributed to it — which is exactly what a
 * naive split on "·" does. See the blind-spot note above.
 */
function laneClaims(lines: readonly string[] = OPEN): Map<string, string> {
  const out = new Map<string, string>();
  const CLAIM = new RegExp(
    String.raw`^([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]+(?: [${MARKS}])?)\s*\*\(([^)]*)\)\*`,
  );
  for (const l of lines) {
    if (!/^\|\s*\*\*[A-Z] · /.test(l)) continue;
    const cell = l.split("|")[3] ?? "";
    for (const part of cell.split("·")) {
      const m = CLAIM.exec(part.trim());
      if (m?.[1] && /\bSHIPPED\b/i.test(m[2] ?? "")) out.set(m[1], part.trim());
    }
  }
  return out;
}

const BULLETS = bullets();
const CLAIMS = laneClaims();

describe("the roadmap is self-consistent about what has shipped", () => {
  it("extracts a plausible number of items — otherwise every assertion below is vacuous", () => {
    // The failure mode of every gate that bit this repo on 2026-08-06: a regex drifts, matches
    // nothing, and the suite goes green by measuring an empty set. 85 bullets when written; 43
    // after the 2026-08-20 reconciliation archived fifteen shipped items.
    //
    // The floor moved 50 -> 25, and the reason it is legitimate this once is worth stating,
    // because "the gate went red so I lowered the bound" is normally the mistake: this guard is
    // about VACUITY, not about how much work is outstanding. Archiving shrinks the population by
    // design, so a floor seated just under today's count would go red on the next reconciliation
    // and teach whoever hits it to lower it again — the ratchet-in-reverse. 25 still fails hard on
    // the thing it exists to catch (a drifted ITEM regex yields ~0, not 25) while surviving a
    // couple more archive passes. **A floor tracking a deliberately shrinking population must be
    // set from what makes it non-vacuous, never from what the file happens to contain today.**
    expect(BULLETS.size, `only ${BULLETS.size} roadmap bullets parsed — has the format changed?`)
      .toBeGreaterThan(25);
  });

  it("leaves no bullet that LOOKS like an item behind — a floor cannot see partial drift", () => {
    // The floor above was mutation-tested and did NOT fail: mangling four bullets left 81, still
    // clear of 50. **A population floor only detects total collapse.** Partial drift — one ring
    // adopting a slightly different bullet style — silently shrinks the population while the count
    // stays healthy, and that is precisely the "silent omission" `roadmapLanes.test.ts` warns about
    // in its own docstring.
    //
    // So this compares two readers on purpose: a LOOSE one that only asks "does this line open with
    // a bold item code?", and the STRICT `ITEM` that the assertions actually use. Anything the loose
    // reader sees and the strict one drops is named here. Two readers of one structure normally
    // drift and the second is the bug — that is true when both are supposed to agree by accident.
    // Here disagreement IS the signal, which is the one case where a second reader earns its keep.
    // NOTE the leading prefix is `(?:[^*\s]{1,3} )?` and NOT the glyph alternation `ITEM` uses.
    // Sharing that alternation was the first draft's bug: a bullet adopting a NEW status glyph would
    // be missed by both readers identically, so the comparison could not see the one drift most
    // likely to actually happen. A second reader that inherits the first one's blind spot is not a
    // second reader.
    const LOOSE = /^\s*[-*] (?:[^*\s]{1,3} )?\*\*([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,})/;
    const missed: string[] = [];
    for (let i = 0; i < OPEN.length; i++) {
      const l = OPEN[i] ?? "";
      if (!LOOSE.test(l)) continue;
      if (ITEM.test(l)) continue;
      missed.push(`L${i + 1}: ${l.trim().slice(0, 90)}`);
    }
    expect(missed, "these read as item bullets but ITEM does not match — the population is shrinking silently")
      .toEqual([]);
  });

  it("can parse a lane-table SHIPPED annotation at all — the cross-check's reader, not its population", () => {
    // This asserted `CLAIMS.size > 0` against the live document until 2026-08-25, and the
    // 2026-08-25 reconciliation took it to **zero** — legitimately. Every lane cell carrying a
    // `*(✅ SHIPPED …, pending archive)*` note was there because a shipped item had never been
    // moved out of `roadmap.md`; archiving all twenty removed the annotations along with them.
    //
    // **So the empty population is the goal state, not a regression** — and a guard that goes red
    // when the file gets *clean* teaches exactly one lesson, which is to leave a shipped item
    // lying around to keep the gate fed. That is the ratchet-in-reverse the floor above warns
    // about, wearing a different hat.
    //
    // What the guard was actually protecting is the READER: if `CLAIM` drifts and matches nothing,
    // "agrees with its own lane table" passes over an empty set and proves nothing. A reader is
    // testable without a population, so it is tested against a synthetic row instead — the same
    // split `roadmapLanes.test.ts` makes for ⛔ (a fixture proves the regex parses, the live
    // document proves the fixture is faithful). Here only the first half is available today, and
    // saying so is the honest version.
    const fixture = laneClaims([
      "| **Z · Fixture** | `nowhere/` | ZZFAKE-SHIPPED ② *(✅ SHIPPED v0.3.999, pending archive)* · ZZFAKE-OPEN *(M — still open)* |",
    ]);
    expect([...fixture.keys()], "CLAIM must find the SHIPPED annotation and only that one")
      .toEqual(["ZZFAKE-SHIPPED ②"]);

    // ...and the live count is reported rather than bounded, so a future cell reappearing is
    // cross-checked by the assertion below without this one having an opinion about how many
    // there should be.
    expect(CLAIMS.size, `live lane-table SHIPPED annotations: ${CLAIMS.size}`)
      .toBeGreaterThanOrEqual(0);
  });

  it("marks an item ✅ when its own text says it shipped", () => {
    // The original defect. An item whose body says SHIPPED but which carries no ✅ reads as open
    // work to every agent picking up the roadmap, and to `roadmapLanes.test.ts`, which excludes ✅
    // items from the assignable population.
    const wrong = [...BULLETS].filter(([, b]) => !b.done && !b.partial && b.bodyShipped);
    expect(
      wrong.map(([c, b]) => `${c} (L${b.line})`),
      "these say SHIPPED in their own body but carry no ✅ marker",
    ).toEqual([]);
  });

  it("agrees with its own lane table about what has shipped", () => {
    // Corroboration that already lives inside the artefact: the lane cell and the bullet are two
    // independent statements about one fact, so they can be checked against each other without any
    // reference to code. This is what caught RAIL-DRAG, whose bullet carried 🟡 — deliberately
    // tolerated by the assertion above — while its lane cell said "SHIPPED PR #197, pending archive".
    const wrong = [...CLAIMS].filter(([code]) => BULLETS.has(code) && !BULLETS.get(code)!.done);
    expect(
      wrong.map(([code, cell]) => `${code}: lane table says ${cell}`),
      "the lane table calls these shipped while their bullets carry no ✅",
    ).toEqual([]);
  });
});
