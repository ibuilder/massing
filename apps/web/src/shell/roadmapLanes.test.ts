import { execFileSync } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { resolve, sep } from "node:path";

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
 * **The increment marker runs ①–㉕.** It used to stop at ⑥, then ⑨, then ⑳, and each time the next
 * SCALE-SEAM increment (`⑦`, then `⑫`, then `㉑`) was not in the class. The interesting part is what that
 * does rather than that it happened: the marker group is optional, so `**SCALE-SEAM ⑫ — …**` does
 * not fail to match. It matches and returns the code as plain `SCALE-SEAM`, **silently dropping the
 * increment number**. The item then disagrees with the lane table cell and the assignment check
 * fails — loudly, but for a reason two steps from the cause.
 *
 * That is the docstring's own warning arriving: "if a new item is written in a style this regex does
 * not match, it is not in the population and the failure mode is a silent omission". Here the style
 * was not new — only the *number* was — which is worse, because nothing about writing the twelfth
 * increment of an existing item looks like inventing a new notation. Had the table been updated to
 * plain `SCALE-SEAM` to make the red go away, the two lists would have agreed at the cost of the
 * roadmap no longer recording which increment was open: green, and wrong.
 *
 * ㉕ is not a considered limit either, just a further-off one. **A vocabulary this check defines is
 * part of its population, so widening it is a real change and not housekeeping.**
 */
const MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕";

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
/**
 * `⛔` marks an item CLOSED UNBUILT or REFUSED IN PLACE. It was missing from the prefix vocabulary
 * until 2026-08-06, and the way it was missing is the point.
 *
 * Two such items were already in the open region — `- ⛔️ **R23-PICKING**` and
 * `* ⛔ **R22-PHOTO-CV defect detection — REFUSED IN PLACE**`. Neither is work anyone can pick up, so
 * neither *should* be required to hold a lane. Neither was flagged. **But not because this check
 * decided they were closed — because the regex could not see them at all.** The prefix group is
 * optional, so an unrecognised glyph makes `^\s*[-*] \*\*` fail outright and the line leaves the
 * population silently. Right answer, no reasoning: the docstring above warns about exactly this
 * ("the failure mode is a silent omission") and it had already happened twice, unnoticed.
 *
 * The difference is not cosmetic. An accidental exclusion inverts the moment anything else changes —
 * a ⛔ item still listed in the lane table reports as "assigned to a lane but not an item", which
 * names neither the item nor the cause. Recognise it, then exclude it on purpose, so the skip is a
 * line of code that a mutation can turn red.
 *
 * **`⛔` and `⛔️` are different strings** — U+26D4, and U+26D4 followed by U+FE0F (VARIATION
 * SELECTOR-16). The roadmap contains both, one per site, and an author cannot see the difference.
 * Matching `⛔️?` covers the pair; alternating `⛔️|⛔` would also work but only in that order,
 * since the bare form matches first and strands the selector. Prefer the optional-selector form:
 * it cannot be reordered into a bug.
 */
const CLOSED = "⛔";

const ITEM = new RegExp(
  String.raw`^\s*[-*] (?:✅ |◧ |🟡 |⭐ |${CLOSED}️? )?\*\*([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,}?)(?:\s*([${MARKS}]))?(?:\s|\*\*|—)`,
);

function itemCodes(lines: string[]): Set<string> {
  const out = new Set<string>();
  for (const l of lines) {
    const m = ITEM.exec(l);
    if (!m?.[1]) continue;
    // ✅ items are shipped-but-not-yet-archived; they are not work anyone can pick up.
    if (l.includes("✅")) continue;
    // ⛔ items are closed unbuilt or refused in place — likewise not pickable work. Deliberate,
    // and asserted below, so that removing this line goes red rather than quietly widening the
    // population back to what the un-widened regex used to exclude by accident.
    if (l.includes(CLOSED)) continue;
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

/**
 * Resolve a lane's path claim to a repo-relative path.
 *
 * **Why this replaced a `replace(/^apps\/web\/src\//, "")`.** The table mixes notations —
 * `apps/web/src/shell/` beside bare `main.ts`, `portal/panels/`, `field/`, `inference.ts`, `main.py` —
 * and the old normaliser stripped exactly one prefix, `apps/web/src/`. That worked for the web lanes
 * and was **blind on the services side**, which is where it mattered:
 *
 *   Lane G claims bare `main.py`  ->  services/api/src/aec_api/main.py
 *   Lane C claims                     services/api/src/aec_api/   (carving out only routers/)
 *
 * C contains G's `main.py`, so the FastAPI entry point belonged to two lanes at once, and the
 * disjointness check could not see it because those two strings never compared. That is the same
 * defect the 2026-07-30 nested overlap was, in the half of the table nobody had normalised.
 *
 * Resolution is grounded in the repo rather than in a convention: walk each of the lane's QUALIFIED
 * paths and their ancestor directories, and take the first that yields a tracked path. `inference.ts`
 * resolves to `apps/web/src/viewer/inference.ts` and `main.py` to `services/api/src/aec_api/main.py`
 * for the same reason, without either being special-cased.
 *
 * **A limit worth stating rather than discovering.** This takes the path alone, not the lane, so one
 * bare name always resolves the same way whoever claims it. That is exactly what makes a duplicate
 * claim detectable — and it means two lanes legitimately using the same bare name for *different*
 * files (an `index.ts` in two directories) would be reported as a clash they do not have. No such
 * pair exists today. If one appears, the fix is to qualify it in the table, which is the better
 * outcome anyway: a bare name that is ambiguous to this resolver is ambiguous to a human reader too.
 */
const TRACKED: ReadonlySet<string> = new Set(
  execFileSync("git", ["ls-files"], { cwd: resolve(REPO), encoding: "utf8", maxBuffer: 1 << 26 })
    .split(/\r?\n/).map((l) => l.trim()).filter(Boolean),
);
const TRACKED_DIRS: ReadonlySet<string> = new Set(
  [...TRACKED].flatMap((f) => {
    const parts = f.split("/"); const out: string[] = [];
    for (let i = 1; i < parts.length; i++) out.push(parts.slice(0, i).join("/") + "/");
    return out;
  }),
);

const ROOTS = ["apps/", "services/", "docs/", "scripts/", "integrations/", ".github/"];

function qualify(p: string): string {
  const raw = p.replace(/^\.\//, "").replace(/^!/, "");
  if (ROOTS.some((r) => raw.startsWith(r)) || raw === "README.md") return raw;
  for (const lane of LANES) {
    if (!lane.paths.includes(p) && !lane.excludes.includes(p)) continue;
    for (const q of lane.paths.map((x) => x.replace(/^!/, ""))) {
      if (!ROOTS.some((r) => q.startsWith(r))) continue;
      const segs = q.replace(/\/$/, "").split("/");
      for (let i = segs.length; i > 0; i--) {
        const cand = segs.slice(0, i).join("/") + "/" + raw;
        if (TRACKED.has(cand) || TRACKED_DIRS.has(cand)) return cand;
      }
    }
  }
  return raw;
}

const CODES = itemCodes(OPEN);

describe("the roadmap lane table", () => {
  it("reads a plausible number of lanes and items — else every assertion below is vacuous", () => {
    // The can't-fail shape this repo keeps getting bitten by: a green check over an empty set.
    expect(LANES.length, `parsed ${LANES.length} lane rows`).toBeGreaterThanOrEqual(8);
    // 38 → 37: BUILD-WORKTREE-CHUNKS closed (✅). 37 → 35: R24-RUNS-INBOX + R38-SYNC-VIEW
    // closed (✅); ARRAY-LIVE was already not in this extractor's open set in the same way.
    // 35 → 33: R21-4D-CLASH + R28-BUNDLE ② closed (✅).
    // 33 → 32: R39-VIEWER-OBS ② closed (✅) — it had shipped on 2026-08-07 in #249 and was still
    // listed open a fortnight later, so this is a correction to the record rather than new work.
    // 32 → 31: R23-BATCH-OVERLAYS closed (✅) — likewise already resolved in every clause, verified
    // against the tree (cameraProfile.ts, the gridOverlay texture cache, gridOverlay.test.ts) rather
    // than read off the entry. Both drops are the record catching up with the code, not scope cuts.
    // 31 → 30: R38-SOLVER-LOCKS ③ closed (✅) — built end to end, verified in the tree. Its entry
    // still said the solve route had no client caller; `api/authoring.ts` has had one for weeks.
    // 30 → 29: R41-MODEL-ALIGN closed (✅) — both halves built, the second in v0.3.1070.
    // 29 → 27: R41-UPLOAD-WARK and R39-UPLOAD-CAP-APP ① closed (✅, v0.3.1069). Both had TWO
    // entries — a summary bullet and a ring entry — and the first pass updated only one, so they
    // kept reading as open. Two places describing one item; the item marker is the authority.
    expect(CODES.size, `extracted ${CODES.size} open item codes`).toBeGreaterThanOrEqual(27);
  });

  it("SEES a closed ⛔ item and then excludes it — both halves, in both spellings", () => {
    // Two assertions on purpose, because "excluded" alone is satisfied by a regex that cannot parse
    // the line — which is exactly the state this file was in until 2026-08-06, for two real items.
    // Only the pair distinguishes a decision from an accident.
    for (const glyph of ["⛔", "⛔️"]) {
      const line = `- ${glyph} **ZZFAKE-CLOSED ② — closed unbuilt, fixture only**`;
      expect(ITEM.exec(line)?.[1], `${glyph} (${[...glyph].length} code points) must PARSE as an item`)
        .toBe("ZZFAKE-CLOSED");
      expect([...itemCodes([line])], `${glyph} must then be EXCLUDED from pickable work`).toEqual([]);
    }
    // ...and against the real document, so the fixture cannot drift away from what it describes.
    // Located by content, never by line number: every lane edits this file, so an index would
    // assert about whichever line happened to slide into position.
    const picking = LINES.find((l) => /^\s*[-*] .*\*\*R23-PICKING\*\*/.test(l));
    expect(picking, "the R23-PICKING bullet is still in docs/roadmap.md").toBeDefined();
    expect(ITEM.test(picking!), "and it parses — a ⛔ item must be seen before it is skipped").toBe(true);
    expect(CODES.has("R23-PICKING"), "R23-PICKING is CLOSED UNBUILT and needs no lane").toBe(false);
  });

  it("owns disjoint paths — a nested path is an overlap, not a boundary", () => {
    // The real defect: `apps/web/src/portal/` (lane A) CONTAINED `portal/panels/` (lane B). Equality
    // is not the test — containment is, and only in the direction that matters: if one lane's path is
    // a prefix of another's, edits inside the deeper path belong to two lanes at once.
    const norm = qualify;
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
    const norm = qualify;
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

  it("gives each item code exactly one bullet", () => {
    // ADDED 2026-08-17, after two duplicates survived every other check in this file.
    //
    // The assertions above are about MEMBERSHIP — every code is in a lane, every lane names a real
    // code. Neither can see a code that appears TWICE, because both are satisfied by the first
    // occurrence and never look for a second. `R31-CITE-HIGHLIGHT` and `R22-PIPELINE` each had two
    // bullets for months; the open-item count, the lane table and this file were all green.
    //
    // Worse, the first sweep for this found only ONE of the two, because it grepped for the code
    // somebody had already noticed. Counting every bullet is what found the other — the same
    // "enumerate the population, do not search for the names you know" lesson the roadmap keeps
    // re-learning about itself.
    //
    // A secondary mention is legitimate and stays: a scan ring often notes an item it did not
    // originate. It just must not be formatted as a `- **CODE**` bullet, or it becomes a second
    // ITEM rather than a reference to one.
    const seen = new Map<string, number>();
    for (const m of ROADMAP.matchAll(/^- (?:◧ |✅ |⛔ )?\*\*([A-Z][A-Z0-9]+-[A-Z0-9-]+)\*\*/gm)) {
      const code = m[1]!;
      seen.set(code, (seen.get(code) ?? 0) + 1);
    }
    const dupes = [...seen.entries()].filter(([, n]) => n > 1).map(([c, n]) => `${c} x${n}`);
    expect(
      dupes,
      "these codes have more than one bullet — a duplicated item is counted twice in every total "
        + "and can be marked done in one place while staying open in the other. Make the secondary "
        + "one a bold cross-reference rather than a bullet: "
        + dupes.join(", "),
    ).toEqual([]);

    // The twin: the scan must be able to SEE a duplicate, or it passes on any file at all.
    const planted = ["- **AAA-BBB** one", "- ◧ **AAA-BBB** two", ""].join(String.fromCharCode(10));
    const plantedSeen = [...planted.matchAll(/^- (?:◧ |✅ |⛔ )?\*\*([A-Z][A-Z0-9]+-[A-Z0-9-]+)\*\*/gm)];
    expect(plantedSeen.length, "the duplicate scan must match a planted pair").toBe(2);
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

/**
 * LANE-COVERAGE — the question the disjointness check above cannot ask.
 *
 * That check asserts no two lanes claim the same path, and it is right to. But **disjointness and
 * coverage are two different claims, and only the first was tested.** A lane table that is perfectly
 * disjoint and owns 62% of the tree passes every assertion above, and the remaining 38% is invisible:
 * not contested, simply unclaimed.
 *
 * That is not theoretical. The table's own note records Lane J being created on 2026-08-06 after
 * "three sessions in one day flagged a path belonging to no lane... Each flagged it correctly and
 * then had to edit it anyway", and concludes: **"An unowned shared path is not neutral ground; it is
 * a collision nobody is watching for."** The measurement that prompted this check found 152 of 390
 * tracked files under `apps/web/src` unowned — 56 once vendored code is set aside — including
 * `proforma/`, where a defect was fixed the same day under a one-change lane assignment because
 * there was no row to point at.
 *
 * A RATCHET, not a wall. Requiring zero today would ship a red test, and a red test everyone learns
 * to ignore protects nothing. The number only ever goes down, and it goes down by adding a row to the
 * table — which is the actual work.
 */
function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = `${dir}/${e.name}`;
    if (e.isDirectory()) walk(p, out); else out.push(p);
  }
  return out;
}

/** Not lanes: vendored copies re-synced by overwrite, and ambient type declarations. */
const NOT_A_LANE = (rel: string) =>
  rel.startsWith("apps/web/src/vendor/") || rel.endsWith(".d.ts");

//: Measured 2026-08-07 BY THIS READER. Only ever revised DOWN, and the way down is a new row in the
//: lane table rather than a bigger number here.
//:
//: 53, not the 56 my own probe reported. The gap is exactly the three `.d.ts` files this gate exempts
//: by name and that probe did not — both counts are right for their own exclusions, and a threshold
//: taken from a different reader is a threshold for a different question. `surface.test.ts` records
//: being bitten by precisely this (698 from a probe vs 696 from the gate), so the number is read back
//: out of the assertion that enforces it.
const UNOWNED_CEILING = 39;  // 53 → 48: Lane J claimed `apps/web/src/tooling/` (v0.3.1017).
//                             48 → 39: Lane E claimed `apps/web/src/tree/` (v0.3.1055), and the
//                             ceiling is re-seated to the MEASURED number rather than lowered by
//                             the size of that directory — 48 had slack in it that nobody had
//                             spent, and a ratchet carrying unspent slack is a ratchet that lets
//                             the next few files in for free.

describe("the lane table covers the tree it governs", () => {
  const WEB = resolve(REPO, "apps/web/src");
  const ROOT = resolve(REPO).split(sep).join("/");
  const all = walk(WEB).map((p) => p.split(sep).join("/").slice(ROOT.length + 1));
  // The table mixes notations: `apps/web/src/shell/` alongside bare `main.ts`, `portal/panels/`,
  // `field/`. The bare ones are relative to `apps/web/src/`. Resolving them is not cosmetic — my
  // first version filtered on `startsWith("apps/web/")` and reported 90 unowned instead of 56,
  // because it silently dropped every relative claim. A population error, in the gate written to
  // catch population errors.
  //
  // Worth flagging separately: the DISJOINTNESS check above compares these strings raw, so two lanes
  // claiming the same directory in different notations — `field/` and `apps/web/src/field/` — would
  // read as disjoint. That is a live gap in that check, not this one.
  const claimed = LANES.flatMap((l) => l.paths)
    .filter((p) => !p.startsWith("!") && !p.startsWith("services/") && !p.startsWith("docs/") && p !== "README.md")
    .map((p) => (p.startsWith("apps/") ? p : `apps/web/src/${p}`))
    .filter((p) => p.startsWith("apps/web/src/"));
  const unowned = all.filter((f) => !NOT_A_LANE(f) && !claimed.some((p) => f === p || f.startsWith(p)));

  it("can see the tree and the claims — else every count below is vacuous", () => {
    // Both halves. An empty file list reports zero unowned and looks like total coverage; an empty
    // claim list reports everything unowned and looks like a catastrophe. Neither is a measurement.
    expect(all.length, "no web source files found — the walk is broken, not the table").toBeGreaterThan(200);
    expect(claimed.length, "no lane claims any apps/web path — the table parse is broken").toBeGreaterThan(5);
  });

  it("does not grow the set of files no lane owns", () => {
    const byDir = [...new Set(unowned.map((f) => f.split("/").slice(0, 4).join("/")))].sort();
    expect(unowned.length,
      `${unowned.length} file(s) under apps/web/src belong to no lane. Add a row to the lane table ` +
      `in docs/roadmap.md rather than raising this number. Locations: ${byDir.join(", ")}`)
      .toBeLessThanOrEqual(UNOWNED_CEILING);
  });

  it("names a path the table genuinely does not claim — so the checker is not always empty", () => {
    // The paired control. A matcher that is too loose returns zero unowned for any table at all,
    // which is indistinguishable from full coverage. `vendor/` is excluded by name above, so use a
    // real unclaimed source path: this must be found, and it must stop being found once a row lands.
    expect(unowned.some((f) => f.startsWith("apps/web/src/proforma/")),
      "proforma/ is unclaimed today — if this fails, either a row was added (update this test) " +
      "or the matcher stopped working").toBe(true);
  });
});
