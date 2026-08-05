import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

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
function declaringModules(): { ids: Map<string, string[]>; scanned: number; failed: string[] } {
  const ids = new Map<string, string[]>();
  const failed: string[] = [];
  let scanned = 0;
  for (const root of ["services/api/src", "services/data/src"]) {
    for (const f of pyFiles(join(REPO, root))) {
      let head: string;
      try {
        head = readFileSync(f, "utf8").slice(0, 500);
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
    expect(openItems(md).size, "no open items extracted — has the bullet format changed?")
      .toBeGreaterThan(10);
  });

  it("reads every module it found — a swallowed read must not read as 'nothing implemented'", () => {
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

  it("the duplicate check has duplicates to look at — it is not vacuously green", () => {
    // Roughly seven ids legitimately appear more than once. If that count collapses to zero the
    // check above passes trivially, and would keep passing after the ITEM regex stopped matching.
    const counts = new Map<string, number>();
    for (const line of md.split("\n")) {
      const m = ITEM.exec(line);
      if (m) counts.set(m[2]!, (counts.get(m[2]!) ?? 0) + 1);
    }
    expect([...counts.values()].filter((c) => c > 1).length,
      "no id appears twice at all — the bullet regex has probably stopped matching").toBeGreaterThan(0);
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
