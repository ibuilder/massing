import { closeSync, openSync, readdirSync, readFileSync, readSync, statSync } from "node:fs";
import { join, resolve, sep } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * **An item the roadmap calls OPEN must not already be implemented.**
 *
 * On 2026-08-04 the roadmap's own starred Band 1 priority — `R35-PIDLOCK-XPROC`, the item its prose
 * called the single most consequential thing left — was finished, tested and shipped in commit
 * `2b332674`, and still listed as open in three places. Reading down the list to pick the next piece
 * of work would have started it a second time.
 *
 * A sweep of the whole list found **12 of 68 open items already had a module declaring itself as
 * that item's implementation.** That is not a stale line, it is a stale *document*, and every
 * prioritisation decision made from it — including several made this same day — was drawing on it.
 *
 * ## Why this check and not a fuller one
 *
 * `roadmapLanes.test.ts` already proves every open item sits in exactly one lane, so the lane table
 * and the item list cannot disagree. **Nothing checked the item list against the code**, which is the
 * axis that actually rots: items get built, the commit says so, and nobody walks back up to the
 * roadmap.
 *
 * The signal used here is deliberately narrow: an identifier appearing in the **first line of a
 * module's docstring**, which is a module declaring "I am the implementation of X". A mere mention
 * anywhere in a file is far too loose — modules legitimately reference items they do not implement,
 * and a check built on that would need an exemption list, which is the reliable sign that the
 * population is wrong rather than the code.
 *
 * ## What a failure means, and the three honest fixes
 *
 * It does **not** mean the item is complete — this check cannot know that, and must not be read as
 * saying so. It means the roadmap says "nothing exists" while something does. Resolve it by telling
 * the truth, in one of three ways:
 *
 *   - `✅` — verified complete. Verify it: module, test, and a caller that can reach it.
 *   - `◧`  — partially shipped. Say in the bullet WHICH module exists, so the next reader starts from
 *            the code rather than from zero.
 *   - `🟡` — in flight.
 *
 * The marker set is shared with `roadmapLanes.test.ts`; keep the two in step.
 */

const REPO = resolve(__dirname, "../../../..");

/** Bullet form the roadmap uses for an item, with its optional status marker. */
const ITEM =
  /^\s*[-*] (?:(✅|◧|🟡|⭐) )?\*\*([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,}?)(?:\s*([①②③④⑤⑥]))?(?:\s|\*\*|—)/;

/** Markers that mean "something exists" — ⭐ is a PRIORITY flag, not a status, and does not count. */
const DONE_MARKERS = new Set(["✅", "◧", "🟡"]);

function openItems(md: string): Set<string> {
  const out = new Set<string>();
  for (const line of md.split("\n")) {
    const m = ITEM.exec(line);
    if (m && !DONE_MARKERS.has(m[1] ?? "")) out.add(m[2]!);
  }
  return out;
}

function pyFiles(dir: string, acc: string[] = []): string[] {
  let entries: string[];
  try { entries = readdirSync(dir); } catch { return acc; }
  for (const e of entries) {
    if (e === "__pycache__" || e === ".venv" || e === "node_modules") continue;
    const p = join(dir, e);
    let st; try { st = statSync(p); } catch { continue; }
    if (st.isDirectory()) pyFiles(p, acc);
    else if (e.endsWith(".py") && !e.startsWith("test_")) acc.push(p);
  }
  return acc;
}

/** Bytes of each module we actually need — enough for a docstring's opening line, and no more. */
const HEAD_BYTES = 500;

/**
 * Read only the first {@link HEAD_BYTES} of a file.
 *
 * `readFileSync(f).slice(0, 500)` reads the **whole file** and then throws almost all of it away.
 * That is invisible on small files and expensive here: this tree's own size guard permits modules up
 * to 5,200 lines, so the scan was pulling megabytes off disk to look at 500 bytes of each. Opening a
 * descriptor and reading one fixed-size buffer is the same answer for a fraction of the I/O.
 *
 * Errors are deliberately allowed to propagate to the caller's try/catch, which records them in
 * `failed` — a read that cannot happen must stay loud, for the reason spelled out below.
 */
function readHead(f: string): string {
  const fd = openSync(f, "r");
  try {
    const buf = Buffer.alloc(HEAD_BYTES);
    const n = readSync(fd, buf, 0, HEAD_BYTES, 0);
    return buf.subarray(0, n).toString("utf8");
  } finally {
    closeSync(fd);
  }
}

type Declared = { ids: Map<string, string[]>; scanned: number; failed: string[] };

/**
 * The scan is memoised because it was being run **three times per file** — once by each test that
 * needed it — and each run walks and reads ~500 Python modules.
 *
 * Measured on this machine, cold: 2127 ms + 1370 ms + 484 ms across the three callers, against
 * vitest's **5 s per-test default**. Warm it is ~300 ms total, which is why it looked fine. Under a
 * full 107-file suite with other sessions competing for I/O, a session hit the 5 s timeout on the
 * first of those tests, and it passed on a standalone re-run — the exact signature of a load-sensitive
 * threshold rather than a defect in the roadmap.
 *
 * **The fix is to do the work once, not to raise the timeout.** A larger timeout would keep the same
 * three scans and move the cliff somewhere less predictable; it also degrades the signal, because a
 * gate that takes noticeably longer than it needs to is one people start running less often. The
 * memo is safe here: every caller reads the same tree at the same commit within a single run, so a
 * second scan could only ever produce the same answer more slowly.
 *
 * Note what is deliberately NOT cached: nothing about the *result* is softened. `failed` is still
 * fatal and `scanned` is still floor-checked — see the note below on why a swallowed read must never
 * be allowed to read as "nothing implemented".
 */
let _declared: Declared | null = null;

function declaringModules(): Declared {
  if (_declared) return _declared;
  _declared = scanDeclaringModules();
  return _declared;
}

/**
 * id -> modules whose OPENING docstring line declares them the implementation of that id.
 *
 * **Read failures are fatal, never skipped, and that is the whole point of `scanned`/`failed`.** The
 * first version wrapped the read in `try { … } catch { continue }`. Standalone it found 529 files and
 * passed; inside the full 107-file suite it silently under-counted under file-handle pressure and
 * failed the population check with a number that looked like a real finding. A swallowed read makes
 * this gate report "nothing is implemented" — the reassuring direction — for a reason that has
 * nothing to do with the roadmap. Surfacing the error is what stops a transient I/O problem from
 * being read as a clean bill of health.
 */
function scanDeclaringModules(): Declared {
  const ids = new Map<string, string[]>();
  const failed: string[] = [];
  let scanned = 0;
  for (const root of ["services/api/src", "services/data/src"]) {
    for (const f of pyFiles(join(REPO, root))) {
      let head: string;
      try {
        head = readHead(f);
        scanned++;
      } catch (e) {
        failed.push(`${f}: ${(e as Error).message}`);
        continue;
      }
      const t = head.trimStart();
      if (!t.startsWith('"""') && !t.startsWith("'''")) continue;   // no module docstring
      const first = t.split("\n")[0] ?? "";
      for (const m of first.matchAll(/\b([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,})\b/g)) {
        const id = m[1]!;
        ids.set(id, [...(ids.get(id) ?? []), f.slice(REPO.length + 1).replace(/\\/g, "/")]);
      }
    }
  }
  return { ids, scanned, failed };
}

describe("the roadmap does not call an implemented item open", () => {
  const md = readFileSync(join(REPO, "docs/roadmap.md"), "utf8");

  it("finds items to check — the population is not silently empty", () => {
    // Without this the whole file passes trivially if the ITEM regex ever stops matching, which is
    // how a gate becomes decorative. Same failure the lane test guards against.
    // 10 -> 5 on 2026-08-26 for the reason spelled out in `roadmapSelfConsistent.test.ts`: this
    // floor measures vacuity, not backlog size, and archiving shrinks the population by design.
    expect(openItems(md).size, "no open items extracted — has the bullet format changed?")
      .toBeGreaterThan(5);
  });

  // The only test that pays for the scan (every later caller hits the memo). Measured cold on this
  // machine after both optimisations: ~2.0-2.4 s, against vitest's 5 s default. Subagent 3 hit that
  // default during a full 107-file suite with three other sessions competing for I/O, and it passed
  // standalone on re-run — a load-sensitive threshold, not a roadmap defect.
  //
  // The timeout is raised ONLY AFTER the work was actually minimised: three scans became one, and
  // whole-file reads became 500-byte reads. Raising it first would have been the tempting fix and the
  // wrong one — it hides the cost rather than removing it, and leaves the same cliff a bit further
  // out. What remains is irreducible directory-walk I/O over ~500 modules, so 20 s is ~8x the
  // measured cost: enough that a loaded machine cannot reach it, small enough that a genuine hang
  // still fails the build rather than stalling CI.
  it("reads every module it found — a swallowed read must not read as 'nothing implemented'", { timeout: 20_000 }, () => {
    const { scanned, failed } = declaringModules();
    expect(failed, "modules could not be read; this gate's answer is meaningless until they can")
      .toEqual([]);
    // The tree has ~500 python modules. A collapse to a handful means the walk broke, not that the
    // codebase shrank — and the collapse would otherwise present as a clean pass.
    expect(scanned, "far fewer modules scanned than this tree contains").toBeGreaterThan(300);
  });

  it("finds modules that declare themselves — the other half is not empty either", () => {
    expect(declaringModules().ids.size,
      "no self-declaring modules found — has the docstring convention changed?").toBeGreaterThan(20);
  });

  it("no OPEN item already has a module implementing it", () => {
    const open = openItems(md);
    const declared = declaringModules().ids;
    const offenders = [...declared.entries()]
      .filter(([id]) => open.has(id))
      .map(([id, files]) => `${id} <- ${files.slice(0, 2).join(", ")}`)
      .sort();
    expect(offenders,
      "these roadmap items are listed as open but a module already declares itself their " +
      "implementation. Mark them ✅ (verified complete), ◧ (partially shipped — name the module), " +
      "or 🟡 (in flight). See this file's header for why each marker means something different.")
      .toEqual([]);
  });

  /**
   * **One ID must not be both open and done at the same time.**
   *
   * On 2026-08-05 a sweep found seven IDs defined more than once and **four of the duplicates
   * disagreed**. The worst was `R36-AUTHOR-MENU`: marked ✅ SHIPPED (v0.3.836–843) in one entry and
   * sitting *unmarked* — i.e. open work — about twenty lines below it. Anyone reading down to pick up
   * the next item would have rebuilt a feature that shipped four days earlier.
   *
   * That is the same incident `roadmapStale` was written for, and **this file could not see it.** The
   * check above compares an open item against the *code*; nothing compared an entry against its own
   * twin. A gate written for a class of bug that misses another instance of that class is the failure
   * worth guarding hardest, because its green result reads as coverage.
   *
   * ## Why "open AND done" rather than "no duplicates"
   *
   * Duplicates are legitimate: `R22-PHOTO-CV` has three bullets (Tier 1, the Tier 2 decision, the
   * Tier 2 validation), all ✅ and all true. Banning duplication outright would need an exemption
   * list, and an exemption list is the reliable sign that the *property* is wrong rather than the
   * document. Contradiction is the thing that actually misleads, and it needs no exemptions.
   *
   * ## What this deliberately does NOT catch
   *
   *   - **Disagreeing sizes.** `R22-PUBLIC-VIEWER` was S in one entry and M in another, which lands it
   *     in a different sprint. Sub-items legitimately differ in size, so a gate here would fire on
   *     honest entries; it is left to review.
   *   - **A heading that contradicts its own body.** `R31-CITE-HIGHLIGHT` was headed "S — premise
   *     HOLDS" above a ⚠️ CORRECTION withdrawing exactly that. Prose disagreeing with prose is not
   *     mechanically checkable, and pretending otherwise would be worse than admitting the gap.
   *   - **ID collisions** — two *different* items sharing a name, which is how `SEC-PLUGIN-SANDBOX`
   *     covered both `sandbox.py` and `plugin_registry.py`. It was renamed to `SEC-PLUGIN-LOADER`;
   *     detecting the next one needs a human reading two entries, not a regex.
   */
  it("no item is listed as done in one place and open in another", () => {
    const seen = new Map<string, Set<boolean>>();
    for (const line of md.split("\n")) {
      const m = ITEM.exec(line);
      if (!m) continue;
      const id = m[2]!;
      if (!seen.has(id)) seen.set(id, new Set());
      seen.get(id)!.add(DONE_MARKERS.has(m[1] ?? ""));
    }
    const conflicted = [...seen.entries()].filter(([, v]) => v.size > 1).map(([id]) => id).sort();
    expect(conflicted,
      "these ids appear BOTH marked done (✅/◧/🟡) and unmarked (open). One of the two is wrong and " +
      "a reader has no way to tell which. Resolve the entry — mark the stale one and point it at the " +
      "live one — rather than deleting it, so the disagreement stays visible.")
      .toEqual([]);
  });

  it("can SEE an id repeated — the duplicate check's reader, not its population", () => {
    // This required the live roadmap to contain at least one repeated id ("roughly seven do"), on
    // the reasoning that a collapse to zero would leave the check above passing trivially. The
    // 2026-08-25 reconciliation took it to **zero**, legitimately: nearly every repeat was one item
    // written twice — a band summary bullet AND a ring entry — and archiving the shipped ones took
    // both copies. R43-MASSINGBILL-CORE, the last survivor, was a live entry plus the review it
    // rests on, and the second bullet was renamed so it stops parsing as an item.
    //
    // **So an empty population here is the goal, not a regression** — a duplicated id is exactly
    // the defect the check above exists to find. A vacuity guard that goes red when the file gets
    // clean teaches one lesson: leave a duplicate lying around to keep the gate fed.
    //
    // What it was really protecting is the READER — if `ITEM` stops matching, "no id appears twice"
    // and "nothing parses at all" are the same observation. A reader is testable without a
    // population, so it is tested against a synthetic pair instead, the same way the ⭐ case below
    // has always been.
    const fixture = [
      "- ◧ **ZZ-TWICE** *(M)* — first entry",
      "- **ZZ-TWICE** *(M)* — second entry, same id",
      "- **ZZ-ONCE** *(S)* — appears once",
    ].join("\n");
    const counts = new Map<string, number>();
    for (const line of fixture.split("\n")) {
      const m = ITEM.exec(line);
      if (m) counts.set(m[2]!, (counts.get(m[2]!) ?? 0) + 1);
    }
    expect(counts.get("ZZ-TWICE"), "ITEM must match BOTH bullets or the check above cannot see a repeat")
      .toBe(2);
    expect(counts.get("ZZ-ONCE"), "...and must still count a single occurrence once").toBe(1);
  });

  it("⭐ is a priority flag and must NOT satisfy this check", () => {
    // The subtle way this gate could be defeated: ⭐ appears in the same slot as the status markers,
    // so treating it as "done" would silently exempt every high-priority item — precisely the ones
    // that matter. R35-PIDLOCK-XPROC carried ⭐ while being both open AND already built.
    const starred = "- ⭐ **ZZ-FAKE-ITEM** *(M)* — a starred but unfinished item\n";
    expect(openItems(starred).has("ZZ-FAKE-ITEM"), "⭐ must not count as a completion marker")
      .toBe(true);
    for (const mk of ["✅", "◧", "🟡"]) {
      expect(openItems(`- ${mk} **ZZ-FAKE-ITEM** *(M)* — done\n`).has("ZZ-FAKE-ITEM"),
        `${mk} should mark an item as not-open`).toBe(false);
    }
  });
});

/**
 * **The same check, over the WEB tree — because the scan above is Python-only.**
 *
 * `declaringModules()` walks `services/api/src` and `services/data/src`. Everything in
 * `apps/web/src` was therefore outside the population while being inside the claim: the describe
 * above reads as *"the roadmap does not call an implemented item open"*, and for the whole frontend
 * it was silent. On 2026-08-06 five items were found marked open with a web module already
 * implementing them — `R38-NODE-SLIDERS` (nine passing tests, wired, and a session was one command
 * from rebuilding it), `R38-SYNC-VIEW`, `R28-UNIFY`, `R24-ELEMENT-CARD` and the `snapEngine`
 * resolver. None was visible here. **A gate's scope is part of its claim.**
 *
 * ## The measured yield, stated so nobody reads "low" as "broken"
 *
 * Of **162** non-test `.ts`/`.tsx` files under `apps/web/src`, **93** open with a block comment and
 * **34** name an item id on its first content line. That is the population this can see.
 *
 * An earlier probe of the same idea reported **6 of 158** and was nearly taken as proof the port was
 * not worth building. It measured the wrong line. Python puts its docstring text on the *same* line
 * as the opening `"""`, so "the first line" is the summary; JSDoc opens with a bare `/**` and the
 * summary is on line **two**. Reading line one literally returns `/**` for almost every TS module.
 * **The signal was fine; the probe was shaped for the other language** — which is why `firstDocLine`
 * below is tested against both comment shapes rather than trusted.
 *
 * This does not subsume the roadmap-internal consistency check and is not subsumed by it: that one
 * answers *"the document contradicts itself"*, this one answers *"code exists that nobody marked
 * done"*. Of the five found that day, two came from modules and the rest from the document's own
 * prose.
 */

/** First CONTENT line of a leading block comment — the TS equivalent of Python's first docstring
 *  line. Returns null when the module has no leading block comment at all. */
export function firstDocLine(src: string): string | null {
  const t = src.trimStart();
  if (!t.startsWith("/*")) return null;
  for (const raw of t.split("\n")) {
    const line = raw.replace(/^\s*\/\*+/, "").replace(/^\s*\*+/, "").trim();
    if (line && line !== "/") return line;
  }
  return null;
}

function tsFiles(dir: string, acc: string[] = []): string[] {
  let entries: string[];
  try { entries = readdirSync(dir); } catch { return acc; }
  for (const e of entries) {
    if (e === "node_modules" || e === "dist" || e === "vendor") continue;
    const p = join(dir, e);
    let st; try { st = statSync(p); } catch { continue; }
    if (st.isDirectory()) tsFiles(p, acc);
    // `.test.ts` excluded: a test naming the item it covers is not a claim that the item is built.
    else if (/\.tsx?$/.test(e) && !/\.test\.tsx?$/.test(e)) acc.push(p);
  }
  return acc;
}

/** id -> web modules whose first docstring line declares them the implementation of that id. */
function webModulesDeclaring(): { ids: Map<string, string[]>; scanned: number; withDoc: number } {
  const ids = new Map<string, string[]>();
  let scanned = 0, withDoc = 0;
  for (const f of tsFiles(join(REPO, "apps/web/src"))) {
    scanned++;
    const first = firstDocLine(readFileSync(f, "utf8").slice(0, 800));
    if (first === null) continue;
    withDoc++;
    for (const m of first.matchAll(/\b([A-Z][A-Z0-9]{1,5}-[A-Z0-9-]{2,})\b/g)) {
      const id = m[1]!;
      ids.set(id, [...(ids.get(id) ?? []), f.slice(REPO.length + 1).split(sep).join("/")]);
    }
  }
  return { ids, scanned, withDoc };
}

describe("the roadmap does not call an implemented WEB item open", () => {
  const md = readFileSync(join(REPO, "docs/roadmap.md"), "utf8");

  // The population floor. A walk that silently stops covering .ts — a moved directory, a changed
  // extension, a thrown readdir — would otherwise report "nothing implemented", which is the
  // reassuring direction and indistinguishable from a clean bill of health.
  it("walks a plausible number of web modules — a broken walk must not read as 'nothing found'", () => {
    const { scanned, withDoc } = webModulesDeclaring();
    expect(scanned, "far fewer web modules than this tree contains").toBeGreaterThan(100);
    expect(withDoc, "no module has a leading block comment — has the walk or the reader broken?")
      .toBeGreaterThan(40);
  });

  it("finds modules that declare themselves — the signal is not dead", () => {
    // 34 at the time of writing. A floor well under that catches the signal breaking without
    // failing every time a module is renamed.
    expect(webModulesDeclaring().ids.size,
      "no web module declares an item id — has the docstring convention changed?").toBeGreaterThan(15);
  });

  it("no OPEN item already has a web module implementing it", () => {
    const open = openItems(md);
    const offenders = [...webModulesDeclaring().ids.entries()]
      .filter(([id]) => open.has(id))
      .map(([id, files]) => `${id} <- ${files.slice(0, 2).join(", ")}`)
      .sort();
    expect(offenders,
      "these roadmap items are listed as open but a WEB module already declares itself their " +
      "implementation. Mark them ✅ (verified complete), ◧ (partially shipped — name the module), " +
      "or 🟡 (in flight). See this file's header for why each marker means something different.")
      .toEqual([]);
  });

  /**
   * `firstDocLine` is tested against both comment shapes on purpose.
   *
   * Getting it wrong is not hypothetical — it is exactly what made an earlier probe report 6
   * declaring modules instead of 34, and nearly retired the idea as low-yield. The failure is
   * silent and one-directional: read the wrong line and you find almost nothing, which looks like
   * a clean tree rather than a broken reader.
   */
  it("reads the SUMMARY line, not the comment opener", () => {
    expect(firstDocLine("/**\n * R38-FAKE — the summary is on line two.\n */\n")).toContain("R38-FAKE");
    expect(firstDocLine("/** R38-FAKE — the summary is on line one. */\n")).toContain("R38-FAKE");
    expect(firstDocLine("/*\n * R38-FAKE — a plain block comment.\n */\n")).toContain("R38-FAKE");
    expect(firstDocLine("// R38-FAKE — a line comment is not a docstring\n")).toBeNull();
    expect(firstDocLine("import x from 'y';\n")).toBeNull();
    // the bug, pinned: line one of a JSDoc block is the opener and must never be the answer
    expect(firstDocLine("/**\n * R38-FAKE\n */")).not.toBe("/**");
  });
});
