import { execFileSync } from "node:child_process";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * R41-DELETE-RATCHET — things removed on purpose stay removed.
 *
 * Several lanes ship to main at once and nothing stopped one reintroducing a document that was
 * deliberately deleted. This is the negative assertion, over FILE PATHS.
 *
 * LINEAGE — the hard half was already solved next door
 *     `portal/register/registerOwnership.test.ts` is a delete ratchet and got there first. Its
 *     lessons are its own: *"the population is the moved code, named"*, *"a matcher that finds
 *     nothing agrees with everything"*, and — after its first run failed on the sentence explaining
 *     what a door is — *"a gate that forbids describing the rule it enforces teaches people to stop
 *     writing the description"*. Read it before extending this.
 *
 * WHY PATHS AND NOT SYMBOLS, WHICH IS THE WHOLE REASON THIS IS TRUSTWORTHY ON DAY ONE
 *     Every failure mode of a symbol ratchet is a string-matching problem, and all three bit on the
 *     first attempt at this item:
 *
 *       · `?shell=classic` was deleted — but `"classic"` still lives in `dev/liveAudit.test.ts` as a
 *         run label. The string has a legitimate other life.
 *       · the More menu is gone — but `"more"` appears in `viewer/app.ts` and `railToolbox.ts` in
 *         **prose describing the removal**. The gate would fire on the documentation of its own rule.
 *       · the register renderer's internals — I guessed `renderRegister` and `registerBoard`.
 *         **`git log -S` says neither ever existed at any commit.** That assertion would have passed
 *         forever, guarded nothing, and read as coverage. It is the exact defect this ring is about,
 *         and the only thing that caught it was checking history for a name I had invented.
 *
 *     A path has none of those. Prior existence is provable from history, current absence is one
 *     `git ls-files`, and it needs no comment-stripping, no word boundaries, and no matcher that can
 *     agree with everything. Symbols are the harder second version; deliberately not in this pass.
 *
 * WHY THESE EIGHT ARE LOAD-BEARING AND NOT BOOKKEEPING
 *     **`docs/` IS the Pages web root.** `pages.yml` copies `docs/.` into the published site, so
 *     re-adding any of these republishes a superseded planning document as a live page on the public
 *     site. Two of them — `competitive-plan.md` and `emanager-gap-analysis.md` — are competitive
 *     analyses, which a standing user directive keeps out of the public docs.
 *
 *     `services/api/test_no_comparative_names.py` already enforces that directive **by content**. It
 *     does not assert these *files* stay gone, and this does not scan content. **Neither implies the
 *     other**, which is a better argument for both existing than either makes alone.
 *
 * ENROLLMENT, SO THE NINTH ENTRY CANNOT BE INVENTED
 *     An entry must be **absent now** and **present in some earlier commit**. The second half is what
 *     stops this growing into a ban on future work: something that merely "does not exist yet" fails
 *     enrollment. Enroll at deletion time; never archaeologise history for "things that were
 *     deleted", because inference cannot tell *removed on principle* from *removed incidentally*.
 *
 * A STATED BLIND SPOT — the enrollment half cannot run in CI
 *     `actions/checkout@v7` clones with `fetch-depth: 1` unless told otherwise, and `ci.yml` does not
 *     tell it otherwise. In a shallow clone `git log --diff-filter=A` sees one commit, so the
 *     "existed before" check would report **zero** for every entry and fail all eight — a gate that
 *     goes red in CI for a reason that has nothing to do with the code.
 *
 *     So the two halves are split by what they NEED. **Absence runs everywhere and is the ratchet.**
 *     Enrollment runs only where history exists, and when it cannot run it SAYS SO rather than
 *     passing quietly — because a silently-skipped check is the failure this whole ring is about.
 *     Deepening the CI clone was rejected: it would add a 2,000-commit fetch to every run to
 *     re-verify a property that is fixed at authoring time.
 */

const REPO = join(process.cwd(), "..", "..");

const git = (...args: string[]) =>
  execFileSync("git", args, { cwd: REPO, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });

/**
 * Deleted on purpose. Each entry carries its reason, so **removing an entry is a decision, not a
 * bypass** — a future author who genuinely needs one back deletes the line and says why. A ratchet
 * with no legitimate way out gets defeated by whoever needs it out.
 */
const REMOVED: Record<string, string> = {
  "docs/capability-matrix.md":
    "competitive capability grid; superseded and off-mission for a public page",
  "docs/competitive-plan.md":
    "competitive analysis — standing user directive keeps these out of the public docs",
  "docs/developer-portal-roadmap.md":
    "superseded planning doc; the roadmap is docs/roadmap.md",
  "docs/emanager-gap-analysis.md":
    "competitive gap analysis against a named product — same directive as competitive-plan.md",
  "docs/improvement-plan.md":
    "superseded planning doc, folded into docs/roadmap.md",
  "docs/lifecycle-roadmap.md":
    "superseded planning doc, folded into docs/roadmap.md",
  "docs/roadmap-modeling-tools.md":
    "split out of the roadmap and then re-merged; a second roadmap is how the two drift",
  "docs/roadmap-platforms.md":
    "same as roadmap-modeling-tools.md — one roadmap, not three",
};

const TRACKED = new Set(git("ls-files").split("\n").map((s) => s.trim()).filter(Boolean));
const SHALLOW = git("rev-parse", "--is-shallow-repository").trim() === "true";

/**
 * Every path ever ADDED under `docs/`, in any commit on any branch — or null on a shallow clone,
 * where history is not available to walk. Used by the enrollment assertion below.
 *
 * THIS RUNS AT MODULE SCOPE ON PURPOSE, AND IT IS THE SECOND FIX TO THE SAME TIMEOUT
 *     The first version ran `git log --all` once per entry — eight walks, 4.7 s — and timed out at
 *     vitest's 5 s default. That was fixed by doing the work once: a single walk over `docs/`
 *     measures 1.2 s, and the comment recorded it as "3.8x faster and clear of the limit".
 *
 *     **It timed out again on 2026-08-07**, at 1.2 s of work against a 5 s budget. Nothing about
 *     the walk had changed; the machine was busier. A full-suite run under contention took 50 s
 *     where an idle one takes 21 s, and this test went from 3.4 s standalone to over 5 s inside it.
 *
 *     So "1.2 s is clear of 5 s" was never a property of the test — it was a property of an idle
 *     machine, measured once and written down as if it were fixed. With several sessions running
 *     suites in one clone, that assumption is the thing that is actually false.
 *
 *     Raising the timeout was rejected last time for a reason that no longer applies: the objection
 *     was that it "keeps the same eight walks and moves the cliff somewhere less predictable". There
 *     is one walk now, and it is already minimal — the residual variance is scheduling, not work.
 *     But the better answer is that **the per-test budget is the wrong instrument for this cost.**
 *     `git ls-files` and `rev-parse` above have always run out here, untimed, because they are
 *     fixture setup. The history walk is the same kind of thing and belongs beside them. Moving it
 *     removes the cliff rather than relocating it, and needs no number that a future load will
 *     falsify.
 */
const EVER_ADDED_UNDER_DOCS = SHALLOW ? null : new Set(
  // `--all` so a file deleted on a branch that later merged is still found; `--diff-filter=A` lists
  // additions; `--name-only --format=` prints just the paths.
  git("log", "--all", "--diff-filter=A", "--name-only", "--format=", "--", "docs/")
    .split("\n").map((s) => s.trim().replace(/\\/g, "/")).filter(Boolean),
);

describe("deliberately removed files stay removed", () => {
  it("has a non-empty population — an empty list passes forever", () => {
    // The vacuity guard. Without it, emptying REMOVED turns every assertion below green.
    expect(Object.keys(REMOVED).length, "the removed-file list is empty; this gate measures nothing")
      .toBeGreaterThan(0);
    expect(TRACKED.size, "git ls-files returned nothing — the tree read failed").toBeGreaterThan(100);
  });

  it("none of them is back in the tree", () => {
    // THE RATCHET. Needs only the working tree, so it runs identically here and in a shallow CI clone.
    const back = Object.keys(REMOVED).filter((p) => TRACKED.has(p));
    expect(
      back.map((p) => `${p} — removed because: ${REMOVED[p]}`),
      "these were deleted on purpose and are back; docs/ is the published Pages root",
    ).toEqual([]);
  });

  it("none of them reappeared under a different directory", () => {
    // A relocation would satisfy the exact-path check while republishing the same document. Basename
    // match, because that is what a move preserves and what `--diff-filter=D` cannot distinguish.
    const moved: string[] = [];
    for (const p of Object.keys(REMOVED)) {
      const base = p.slice(p.lastIndexOf("/") + 1);
      for (const t of TRACKED) if (t !== p && t.endsWith(`/${base}`)) moved.push(`${base} reappeared at ${t}`);
    }
    expect(moved, "a removed document is back under a new path").toEqual([]);
  });

  it("every entry genuinely existed once — so the ninth cannot be invented", () => {
    if (SHALLOW) {
      // Loud, not silent. See the blind-spot note above: this is the half that needs history, and
      // CI has none. Failing here would be a false red; passing quietly would be the very defect
      // this ring exists to catch, so it says which one happened.
      console.warn(
        "[delete-ratchet] shallow clone — enrollment (\"existed before\") NOT verified. " +
        "The absence assertions above did run. Re-verify on a full clone before adding an entry.",
      );
      expect(SHALLOW).toBe(true);
      return;
    }
    // The walk itself runs at module scope — see EVER_ADDED_UNDER_DOCS for why. The SHALLOW guard
    // above is what makes this non-null here.
    const everAdded = EVER_ADDED_UNDER_DOCS!;
    expect(everAdded.size, "the history walk returned nothing — this check would pass vacuously")
      .toBeGreaterThan(20);
    const never = Object.keys(REMOVED).filter((p) => !everAdded.has(p));
    expect(
      never,
      "these were never added in any commit — enrolling a never-existent path is a gate that guards nothing",
    ).toEqual([]);
  });
});
