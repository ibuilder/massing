import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every open roadmap item belongs to exactly one lane, and no two lanes share a path.
 *
 * Four sessions work this repo concurrently. The roadmap's lane table is what stops them editing the
 * same file, and it was **wrong in two ways** when this test was written (2026-07-30):
 *
 *  1. Lane A owned `apps/web/src/portal/` wholesale while lane B owned `portal/panels/` — a nested
 *     overlap, so the two lanes least likely to be watching each other shared a directory.
 *  2. `routers/` sat inside lane C's path with no owner of its own, which is how the same route gets
 *     added twice.
 *
 * Neither was visible by reading the table, because an overlap between row 1 and row 2 of a
 * six-row table is exactly the kind of thing prose hides. So this asserts it instead.
 *
 * **The population is defined by THIS reader.** The check extracts item codes with its own regex and
 * requires every code it finds to be assigned. It deliberately does not accept a hand-maintained
 * count: a list of "items that should be in the table" would be a second place to forget one. If a
 * new item is written in a style this regex does not match, it is not in the population and the
 * failure mode is a silent omission — which is why the extraction is asserted to find a plausible
 * number of items before anything else runs. (Same shape as `surface.test.ts`: a threshold taken
 * from a different reader is a threshold for a different question.)
 */

// process.cwd() is apps/web under vitest.
const REPO = resolve(process.cwd(), "..", "..");
const ROADMAP = readFileSync(resolve(REPO, "docs/roadmap.md"), "utf8");
const LINES = ROADMAP.split("\n");

/** The open backlog is everything above the Gated section; gated items are deliberately unassigned. */
const GATED_AT = LINES.findIndex((l) => l.startsWith("## ⛔ Gated"));
const OPEN = LINES.slice(0, GATED_AT === -1 ? LINES.length : GATED_AT);

/**
 * A roadmap item bullet: `- **CODE** …`, `* ⭐ **CODE ② — …**`, with or without a status glyph.
 *
 * **The increment marker runs ①–⑨, and it stopped at ⑥ until 2026-08-06** — the day SCALE-SEAM
 * shipped its seventh. `⑦` was not in the class, and the interesting part is what that did rather
 * than that it happened: the marker group is optional, so `**SCALE-SEAM ⑦ — …**` did not fail to
 * match. It matched and returned the code as plain `SCALE-SEAM`, **silently dropping the increment
 * number**. The item then disagreed with the lane table cell (which said `SCALE-SEAM ⑦`) and the
 * assignment check failed — loudly, but for a reason two steps from the cause.
 *
 * That is the docstring's own warning arriving: "if a new item is written in a style this regex does
 * not match, it is not in the population and the failure mode is a silent omission". Here the style
 * was not new — only the *number* was — which is worse, because nothing about writing the eighth
 * increment of an existing item looks like inventing a new notation. Had the table been updated to
 * plain `SCALE-SEAM` to make the red go away, the two lists would have agreed at the cost of the
 * roadmap no longer recording which increment was open: green, and wrong.
 *
 * ⑨ is not a considered limit either, just a further-off one. **A vocabulary this check defines is
 * part of its population, so widening it is a real change and not housekeeping.**
 */
const MARKS = "①②③④⑤⑥⑦⑧⑨";

/**
 * One source for the marker vocabulary, because there were **two** and they had already drifted.
 *
 * Widening the item regex to ⑦ was not enough: `laneRows()` matched the increment on a table cell
 * with its own separately-written `[①②③④⑤⑥]`, so the bullet parsed as `SCALE-SEAM ⑦` while the cell
 * parsed as `SCALE-SEAM` — and the item reported as *unassigned* despite being sitting right there
 * in the table. Two readers, one structure, opposite halves of the same comparison.
 *
 * This file already carries that lesson at `LANE_ROW_LINES` ("**Two readers of one structure WILL
 * drift; the second one is the bug**"), written after a narrower row matcher let an unbolded row
 * escape. It was true again, in the same file, about a different structure — which is the argument
 * for making the vocabulary a value rather than restating it correctly in two places.
 */
const ITEM = new RegExp(
  String.raw`^\s*[-*] (?:✅ |◧ |🟡 |⭐ )?\*\*([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,}?)(?:\s*([${MARKS}]))?(?:\s|\*\*|—)`,
);

function itemCodes(lines: string[]): Set<string> {
  const out = new Set<string>();
  for (const l of lines) {
    const m = ITEM.exec(l);
    if (!m?.[1]) continue;
    // ✅ items are shipped-but-not-yet-archived; they are not work anyone can pick up.
    if (l.includes("✅")) continue;
    out.add(m[2] ? `${m[1]} ${m[2]}` : m[1]);
  }
  return out;
}

/**
 * Rows of the lane table: `| **A · Name** | \`path\`, \`!excluded/path\` | ITEM · ITEM |`.
 *
 * A path prefixed `!` is a **carve-out**: the lane owns its other paths except that subtree, which
 * belongs to whichever lane claims it. The syntax exists because the table said Lane C owns
 * `services/api/src/aec_api/` "**excluding** `routers/`" in bold prose — and prose is not a boundary.
 * The disjointness check could not read it, so C and G registered as overlapping, correctly: the only
 * thing keeping two sessions out of `routers/` was a sentence. Writing the carve-out in the same
 * syntax the check reads is what makes it a rule.
 */
interface Lane { name: string; paths: string[]; excludes: string[]; items: string[] }

/**
 * Line numbers consumed by `laneRows()`. Recorded BY THE PARSER ITSELF so the "has this item left the
 * roadmap" check can subtract exactly the region it read — never a second, independently-written
 * matcher. A prior fix used its own `/^\|\s*\*\*[A-Z] · /`, which was narrower than this loop (that
 * loop tolerates an unbolded name cell via `?? nameCell`), so an unbolded row escaped the subtraction
 * and became its own evidence again — silently, and only for that row. **Two readers of one structure
 * WILL drift; the second one is the bug.**
 */
const LANE_ROW_LINES = new Set<number>();

function laneRows(): Lane[] {
  const start = LINES.findIndex((l) => l.startsWith("| Lane | Owns these paths"));
  expect(start, "the lane table header moved or was renamed — this whole file is measuring nothing")
    .toBeGreaterThan(-1);
  const rows: Lane[] = [];
  for (let i = start + 2; i < LINES.length; i++) {
    const line = LINES[i];
    if (!line?.startsWith("|")) break;
    LANE_ROW_LINES.add(i);
    const cells = line.split("|").slice(1, -1).map((c) => c.trim());
    const [nameCell, pathCell, itemCell] = cells;
    if (nameCell === undefined || pathCell === undefined || itemCell === undefined) continue;
    const name = /\*\*(.+?)\*\*/.exec(nameCell)?.[1] ?? nameCell;
    const all = [...pathCell.matchAll(/`([^`]+)`/g)]
      .map((m) => m[1]).filter((p): p is string => Boolean(p));
    const paths = all.filter((p) => !p.startsWith("!"));
    const excludes = all.filter((p) => p.startsWith("!")).map((p) => p.slice(1));
    const items = itemCell.split("·").map((s) => s.trim())
      // Only take things shaped like a code; prose cells ("no standalone items…") contribute none.
      .map((s) => new RegExp(String.raw`^([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]+(?: [${MARKS}])?)`).exec(s)?.[1])
      .filter((s): s is string => Boolean(s));
    rows.push({ name, paths, excludes, items });
  }
  return rows;
}

/** Explicitly not pickable: user decisions, BIG-TICKET commitments, gated work. */
function parkedCodes(): Set<string> {
  const i = LINES.findIndex((l) => l.startsWith("**Parked — not available to pick up.**"));
  expect(i, "the Parked paragraph is gone — decisions would read as available sprint items")
    .toBeGreaterThan(-1);
  let text = "";
  for (let j = i; j < LINES.length; j++) {
    const line = LINES[j];
    if (line === undefined || line.trim() === "") break;
    text += `${line} `;
  }
  return new Set([...text.matchAll(/\b([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,})\b/g)]
    .map((m) => m[1]).filter((c): c is string => Boolean(c)));
}

const LANES = laneRows();
const CODES = itemCodes(OPEN);

describe("the roadmap lane table", () => {
  it("reads a plausible number of lanes and items — else every assertion below is vacuous", () => {
    // The can't-fail shape this repo keeps getting bitten by: a green check over an empty set.
    expect(LANES.length, `parsed ${LANES.length} lane rows`).toBeGreaterThanOrEqual(8);
    expect(CODES.size, `extracted ${CODES.size} open item codes`).toBeGreaterThanOrEqual(40);
  });

  it("owns disjoint paths — a nested path is an overlap, not a boundary", () => {
    // The real defect: `apps/web/src/portal/` (lane A) CONTAINED `portal/panels/` (lane B). Equality
    // is not the test — containment is, and only in the direction that matters: if one lane's path is
    // a prefix of another's, edits inside the deeper path belong to two lanes at once.
    const norm = (p: string) => p.replace(/^apps\/web\/src\//, "").replace(/^\.\//, "");
    const clashes: string[] = [];
    for (const a of LANES) {
      // A carve-out only excuses the overlap it actually names, and only for the lane that declared it.
      const carved = a.excludes.map(norm);
      for (const b of LANES) {
        if (a === b) continue;
        for (const pa of a.paths.map(norm)) {
          for (const pb of b.paths.map(norm)) {
            // Only directories can contain; a file path equal to another is still a clash.
            if (!(pa === pb || (pa.endsWith("/") && pb.startsWith(pa)))) continue;
            if (carved.some((x) => pb === x || pb.startsWith(x))) continue;
            clashes.push(`${a.name} owns ${pa} which covers ${b.name}'s ${pb}`);
          }
        }
      }
    }
    expect([...new Set(clashes)], "lanes are not disjoint — two sessions can collide").toEqual([]);
  });

  it("leaves no carve-out unclaimed — an excluded subtree with no owner is how this started", () => {
    // The failure mode a carve-out introduces: `!routers/` removes it from lane C, and if no row then
    // claims it, the directory has no owner and any session may edit it — which is the exact state that
    // let one route be added twice. So an exclusion must hand the path to someone, not just drop it.
    const norm = (p: string) => p.replace(/^apps\/web\/src\//, "").replace(/^\.\//, "");
    const orphanCarves: string[] = [];
    for (const l of LANES) {
      for (const x of l.excludes.map(norm)) {
        // Deliberately searched among the OTHER lanes. The carving lane's own broader path is by
        // definition a prefix of its carve-out, so including it would make this pass vacuously — the
        // check would confirm that C owns the thing C just disclaimed.
        const claimed = LANES.filter((o) => o !== l)
          .flatMap((o) => o.paths.map(norm))
          .some((p) => p === x || x.startsWith(p));
        if (!claimed) orphanCarves.push(`${l.name} carves out ${x}, which no other lane row claims`);
      }
    }
    expect(orphanCarves, "a carved-out path with no owner is editable by everyone").toEqual([]);
  });

  it("assigns every open item to a lane, or parks it explicitly", () => {
    // A hand-maintained list needs a completeness check or it silently stops covering new rows.
    // This is that check: an item added to a ring but not to the table fails here, naming itself.
    const assigned = new Set(LANES.flatMap((l) => l.items));
    const parked = parkedCodes();
    // A code carries an optional slice numeral ("SCALE-SEAM ⑥"); Parked lists the bare code, so the
    // base is what to look up there. `?? c` keeps a code with no space intact rather than silently
    // becoming undefined — the split cannot fail today, and a check that quietly stops looking is
    // exactly the failure this file exists to prevent.
    const base = (c: string) => c.split(" ")[0] ?? c;
    const orphans = [...CODES].filter((c) => !assigned.has(c) && !parked.has(base(c)));
    expect(orphans, `unassigned roadmap items — add each to a lane row or to Parked: ${orphans.join(", ")}`)
      .toEqual([]);
  });

  it("names no item that has left the roadmap", () => {
    // The other direction, and the one that rots quietly: an item ships, its entry is archived, and
    // the lane row goes on advertising it. An agent then claims work that no longer exists.
    //
    // This asserted `ROADMAP.includes(code)` until 2026-07-31 and was VACUOUS for exactly the case it
    // names. `ROADMAP` is the whole file *including the lane table*, so a lane entry satisfied its own
    // existence check: archive an item's entry, leave it in a lane row, and the substring is still
    // there. Found by archiving 18 shipped items — the check stayed green while six lane entries went
    // on advertising work that had shipped. A check whose evidence is the thing under test cannot fail.
    //
    // The fix is to search the roadmap MINUS the lane table, so a row can no longer be its own evidence.
    //
    // Deliberately NOT `CODES` (the open-item set), which was the first attempt and was wrong in the
    // expensive direction: it flagged two LIVE items as archived. `CODES` is built by the ITEM regex,
    // which needs 2+ chars after the hyphen (so `REL-4` never matches) and captures only the FIRST code
    // on a line (so `R24-MONO-DATA`, sitting second, never matches). Tightening a check by borrowing a
    // narrower population inherits that population's blind spots — and a gate that reports live work as
    // dead gets items deleted.
    // Requires a real ENTRY, not a mention. Subtracting only lane rows was still too weak: the Band
    // index lines and any planning paragraph could vouch for an archived item — and the roadmap itself
    // calls those index lines "a cache of the detail entries… never invalidated", so they are the least
    // trustworthy evidence in the file. Four shipped R27 items survived exactly that way.
    //
    // An entry is the code appearing as the SUBJECT of a bullet or a table row: bolded, on a line that
    // starts with `-`/`*` or `|`, outside the lane table. Band rows start with a glyph (⭐/◧/🟡) and
    // prose starts with a word, so neither qualifies. `~~STRIKETHROUGH~~` is allowed — a struck row is
    // still a real entry recording a decision.
    //
    // Verified against every lane item before adopting: 48 of 48 still resolve, so this tightens the
    // check without the false-positive class that sank the CODES attempt (REL-4, R24-MONO-DATA).
    const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const base = (c: string) => c.split(" ")[0] ?? c;
    const hasEntry = (code: string) => LINES.some((l, i) => {
      if (LANE_ROW_LINES.has(i)) return false;
      if (!/^\s*[-*] /.test(l) && !/^\|/.test(l)) return false;
      return new RegExp(`\\*\\*~{0,2}${esc(code)}\\b`).test(l);
    });
    const stale = LANES.flatMap((l) => l.items).filter((c) => !hasEntry(base(c)));
    expect([...new Set(stale)],
      `lane rows advertise items with no entry left in the roadmap: ${stale.join(", ")}`)
      .toEqual([]);
  });

  it("owns the portal shell and the register renderer in DIFFERENT lanes", () => {
    // The one boundary this file could not see, asserted here because a second reader of the lane
    // table would drift from `laneRows()` — the mistake the LANE_ROW_LINES note above is about.
    //
    // Until 2026-08-03 the generic register renderer lived inside `portal/portal.ts`. Lane A owned
    // that file; every register-shaped item is Lane B's, because a register is a data surface. The
    // paths were disjoint, every assertion above was green, and Lane B still had to edit a Lane A
    // file to do its own work — `R36-EMPTY-STATE` shipped exactly that way, `R24-MONO-DATA` gave up
    // and said so in `ui/monoData.test.ts`. **Disjointness is a property of paths; this was a
    // mismatch between a path and the work**, and no version of the check above can reach it.
    //
    // v0.3.850 made the boundary statable by making the renderer a file. What can rot from here is
    // the assignment: drop `portal/register/` from Lane B and the directory has no owner, which
    // every session may then edit — the state the carve-out check above exists to forbid. So the
    // claim is named. Two paths, not a general coverage rule, because the lanes do NOT cover the
    // tree today (`drawings/`, `proforma/`, `studio/` and others are unowned) and a rule that fails
    // for reasons nobody has decided yet is a rule people turn off.
    const ownerOf = (path: string) =>
      LANES.filter((l) => l.paths.some((p) => p === path || p.endsWith(path))).map((l) => l.name);
    const shell = ownerOf("portal/portal.ts");
    const register = ownerOf("portal/register/");
    expect(shell, "no lane owns portal/portal.ts").toHaveLength(1);
    expect(register, "no lane owns portal/register/ — an unowned path is editable by everyone")
      .toHaveLength(1);
    expect(register[0],
      "the portal shell and the register renderer are back in one lane; the point of the v0.3.850 "
      + "split was that a register item must not have to reach into a Shell & IA file")
      .not.toBe(shell[0]);
  });

  it("claims no item in two lanes at once", () => {
    const seen = new Map<string, string>();
    const dupes: string[] = [];
    for (const l of LANES) {
      for (const c of l.items) {
        const prev = seen.get(c);
        if (prev) dupes.push(`${c} in both ${prev} and ${l.name}`);
        else seen.set(c, l.name);
      }
    }
    expect(dupes, "an item in two lanes puts two sessions on one job").toEqual([]);
  });
});
