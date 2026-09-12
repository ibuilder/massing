"""Every scratch directory a test creates must be git-ignored, or `git status` lies about your work.

A stop hook flagged `services/api/_shelf_famgeom/` as uncommitted work mid-run. It was not work --
`test_family_geometry.py` creates and removes it -- but nothing in `.gitignore` covered it, so for the
seconds it existed it was indistinguishable from a file somebody forgot to commit. **That is the whole
cost: a dirty `git status` from a concurrent or crashed suite run reads exactly like real uncommitted
work, to a hook and to a person.** The suite itself already sees the residue -- it reports
"N dir(s) this runner does not own" on every run -- so the accumulation was visible to the tooling and
invisible to `.gitignore`.

Same class as the `.venv*/` fix CLAUDE.md records: *a rebuild's backup should not show up in every
lane's `git status`.*

WHY THIS IS A GATE AND NOT A LIST OF THIRTEEN PATHS
---------------------------------------------------
A hand-written list drifts the moment a test adds a fourteenth scratch dir, and nothing would say so.
So the population is DERIVED -- every `"./<name>"` directory literal in `services/api/*.py` -- and the
verdict is delegated to **git itself** rather than to a reimplementation of its matcher.

**ASK GIT WITH A TRAILING SLASH, OR IT ANSWERS A DIFFERENT QUESTION.** `.gitignore` patterns that end
in `/` match DIRECTORIES ONLY, and `git check-ignore` cannot tell that a path which does not exist on
disk is a directory. Asked as `test_storage_foo`, git says "not ignored"; asked as
`test_storage_foo/`, git says "ignored by test_storage_*/". The first draft of this derivation
omitted the slash and reported **377 uncovered directories** -- confidently, with a list -- when the
true number was 13. A second draft asked from the wrong directory and reported 35. *A checker that
asks the wrong question does not fail; it answers.* The self-tests below exist to red the build if
any way of asking wrongly comes back -- see `ignored_sources()` for each of them.

THE EXEMPTIONS ARE NOT SCRATCH DIRECTORIES AT ALL
--------------------------------------------------
The derivation is deliberately over-broad -- it matches any `"./<name>"` literal -- because a narrower
one would be a predicate deciding what to LOOK at, and everything such a predicate excludes is
invisible to its own output. The blind-spot lesson `test_seeding_sweep` had to learn twice. So the
over-matches are named here with a reason each, rather than filtered out by a cleverer regex:
nothing leaves the population silently.

**Adding a `.gitignore` pattern is the fix; adding an exemption is a claim that the literal is not a
directory.** Do not exempt a real scratch dir to get green -- ignore it instead.

Run from services/api:
  PYTHONPATH=src:../data/src ./.venv/bin/python test_scratch_ignored.py
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


#: Literals the derivation matches that are NOT directories this tree creates. Each needs a reason a
#: reader can check, because an exemption is the one way a name leaves the population.
EXEMPT: dict[str, str] = {
    "definitely_not_here_": "test_model_ensure.py builds a DELIBERATELY MISSING path as "
                            '`\"./definitely_not_here_\" + pid2 + \".ifc\"`; the regex sees the '
                            "prefix without the concatenated suffix. Nothing creates it -- the test "
                            "asserts the absence.",
    "feedback": "a TypeScript import specifier (`import { toast } from './feedback'`) quoted inside "
                "test_route_reachability.py's fixture data, not a path on this filesystem.",
    "routines": "a TypeScript import specifier quoted in a test_file_sizes.py comment, same as above.",
}

#: Extensions that mark a literal as a FILE rather than a directory.
_FILE_SUFFIXES = (".py", ".json", ".ifc", ".csv", ".db", ".txt", ".md", ".xml", ".zip", ".xlsx",
                  ".yml", ".yaml", ".html", ".pdf", ".frag", ".ids", ".bcf", ".log")

_LITERAL = re.compile(r"""["']\./([A-Za-z0-9_.\-]+)/?["']""")


def derive() -> set[str]:
    """Every `"./<name>"` literal in this package that is not obviously a file."""
    out: set[str] = set()
    for path in sorted(glob.glob(os.path.join(HERE, "*.py"))):
        src = open(path, encoding="utf-8", errors="replace").read()
        for m in _LITERAL.finditer(src):
            name = m.group(1)
            if name.endswith(_FILE_SUFFIXES):
                continue
            out.add(name)
    return out


def ignored(names: list[str]) -> set[str]:
    """Which of `names` git would ignore, as directories in this directory.

    The whole contract -- the trailing slash, the working directory, and why each was wrong in an
    earlier draft -- lives in `ignored_sources()`, which this is a projection of. One code path, so
    the set and the sources cannot disagree about what "ignored" means.
    """
    return set(ignored_sources(names))


#: The ignore file this package's own patterns live in, as `git check-ignore -v` names it. The source
#: is reported RELATIVE TO THE REPO ROOT whatever directory git is invoked from, so this string
#: distinguishes a per-directory match from a root-file one (`.gitignore`) without any path fixing up.
LOCAL_IGNORE_FILE = "services/api/.gitignore"


def ignored_sources(names: list[str], cwd: str | None = None,
                    as_dirs: bool = True) -> dict[str, str]:
    """Map each ignored name to the ignore FILE whose rule decided it.

    `-v` rather than a bare query, because "is this ignored" and "is this ignored BY THE FILE I MEAN"
    are different questions, and the self-test below needs the second. Raised in review on #539: the
    per-directory canary asserted only that its probe was ignored, while `_local_only_prefix()` rules
    the root file out by LITERAL substring — so a root *wildcard* could match the probe without ever
    containing the prefix text, and the canary would pass while the per-directory file went unread,
    which is the exact failure it exists to catch. *An assertion one step weaker than its claim is
    how a canary dies quietly.*

    Output format is `<source>:<line>:<pattern>\t<pathname>`; non-matching paths print nothing at all
    (that is why `--non-matching` is deliberately not passed — absence IS the answer). The source is
    split off from the LEFT because a gitignore *pattern* may itself contain colons, while these
    source paths cannot.

    **A NEGATED RULE IS DROPPED, AND THAT GUARD IS A REGRESSION `-v` INTRODUCED.** Without `-v`, git
    suppresses a path whose last matching pattern is negated (`builtin/check-ignore.c` clears the
    pattern unless verbose); WITH `-v` it prints that pattern, `!` prefix intact, for a path that is
    NOT ignored. So moving to `-v` to learn the source silently widened what counted as ignored --
    *making a function more informative made it less correct*, and the root `.gitignore` carries five
    `!` rules today. Raised in review on #539.

    **Honest scope:** no probe could make a TRAILING-SLASH query -- the form this always uses -- emit
    a negated record; every reproduction needed the bare-name form. That is a failure to construct
    the case, not a proof it cannot occur, so the guard stays: two lines, fails closed, and correct
    by git's documented semantics whatever the query form does.

    TWO MORE THINGS ARE LOAD-BEARING HERE, AND BOTH WERE WRONG IN AN EARLIER DRAFT.

    **The trailing slash.** `.gitignore` patterns ending in `/` match DIRECTORIES ONLY, and git
    cannot tell that a path which does not exist on disk is one. Asked as `test_storage_foo`, git
    says "not ignored"; asked as `test_storage_foo/`, it says "ignored by test_storage_*/". Omitting
    it made this derivation report **377 uncovered directories**, confidently and with a list, when
    the true number was 13.

    **The directory it asks FROM.** Names are passed bare and resolved against `cwd=HERE`, so git
    consults `services/api/.gitignore` the way it would for a real working-tree path. An earlier
    draft prefixed `services/api/` and ran from `join(HERE, "..")` -- which is `services/`, not the
    repo root -- so every path resolved to a location that does not exist, git fell back to the ROOT
    file alone, and the nineteen dirs covered only by this package's `test_ifc*/` were reported as
    uncovered. Acting on that would have added nineteen redundant patterns to fix nothing.

    *All three bugs have the same shape as the defect this file exists to prevent: **the checker did
    not fail, it answered** -- a wrong question returns a confident number, and a number with a list
    attached reads as evidence.* Hence one self-test per way of asking wrongly.

    `--no-index` lets this answer for paths that do not currently exist, which is the normal case:
    a scratch dir exists only while its test is mid-run.
    """
    if not names:
        return {}
    args = [f"{n}/" for n in names] if as_dirs else list(names)
    r = subprocess.run(["git", "check-ignore", "-v", "--no-index", *args],
                       capture_output=True, text=True, cwd=cwd or HERE)
    # exit 0 = some ignored, 1 = none ignored, >1 = real error. Anything else must not read as clean.
    if r.returncode not in (0, 1):
        raise SystemExit(f"git check-ignore failed ({r.returncode}): {r.stderr[:400]}")
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        if "\t" not in line:
            continue
        rule, _, pathname = line.partition("\t")
        source, _, pattern = rule.split(":", 2)
        # A NEGATED rule means the path is NOT ignored, and `-v` prints it anyway -- see the
        # docstring. Dropping it can only move a name from "covered" to "uncovered", which reds the
        # build, so this guard fails CLOSED.
        if pattern.startswith("!"):
            continue
        out[pathname.strip().rstrip("/")] = source
    return out


# --- the self-test runs FIRST, and nothing below may be believed until it passes ------------------
# Three probes, because a classifier that says "ignored" to everything and one that says "not
# ignored" to everything each pass a one-sided check, and because the two ways of asking wrongly fail
# differently: a dropped trailing slash breaks EVERY directory-only pattern, while asking from the
# wrong directory breaks only the per-directory ignore file. Each has its own probe.
def _local_only_prefix() -> str | None:
    """A `<prefix>*/` pattern that `services/api/.gitignore` has and the ROOT `.gitignore` does not.

    **Derived, not hardcoded.** An earlier draft named `test_ifc*/` directly, which made the canary a
    claim about one pattern rather than about the classifier: removing that pattern for a legitimate
    reason would red this self-test with a message confidently blaming the wrong thing. *A check
    whose failure message can misdiagnose is worse than one that stays silent, because somebody acts
    on it.* So the probe now tracks whatever the tree actually has.
    """
    local = os.path.join(HERE, ".gitignore")
    root = os.path.join(HERE, "..", "..", ".gitignore")
    if not (os.path.exists(local) and os.path.exists(root)):
        return None
    root_src = open(root, encoding="utf-8", errors="replace").read()
    for line in open(local, encoding="utf-8", errors="replace").read().splitlines():
        line = line.strip()
        if not line.endswith("*/") or line.startswith(("#", "!", "/")):
            continue
        prefix = line[:-2]
        # Only a prefix the ROOT file mentions nowhere can prove per-directory files are consulted.
        if prefix and prefix not in root_src:
            return prefix
    return None

_LOCAL_PREFIX = _local_only_prefix()
_LOCAL_PROBE = f"{_LOCAL_PREFIX}selftest_probe" if _LOCAL_PREFIX else None

_probe = ignored(["test_storage_selftest_probe", *( [_LOCAL_PROBE] if _LOCAL_PROBE else [] ),
                  "_gate_selftest_no_pattern_can_match_this"])
check("self-test: a name matching a directory-only pattern is classified IGNORED",
      "test_storage_selftest_probe" in _probe,
      "the classifier has stopped seeing directory-only patterns -- the likeliest cause is a missing "
      "trailing slash in ignored(), which makes git answer about a FILE and report every "
      "`test_storage_*` dir as uncovered")
_LOCAL_SOURCE = ignored_sources([_LOCAL_PROBE]).get(_LOCAL_PROBE) if _LOCAL_PROBE else None
check("self-test: per-directory .gitignore files are consulted at all",
      _LOCAL_SOURCE == LOCAL_IGNORE_FILE,
      f"probe {_LOCAL_PROBE!r} (from the `{_LOCAL_PREFIX}*/` pattern in {LOCAL_IGNORE_FILE}) was "
      f"decided by {_LOCAL_SOURCE!r}, not {LOCAL_IGNORE_FILE!r}. Either the classifier is not reading "
      "per-directory ignore files -- asking from the wrong working directory, or about a path that "
      "does not resolve, in which case every dir covered only by this package's own file is reported "
      "as uncovered -- or a ROOT pattern now wildcard-matches the probe, which makes the canary "
      "vacuous and means `_local_only_prefix()` needs a probe the root file genuinely cannot reach."
      if _LOCAL_PREFIX else
      "services/api/.gitignore no longer carries any `<prefix>*/` pattern absent from the root file, "
      "so this canary cannot be built and the per-directory question is UNPROVEN. Fails closed on "
      "purpose: restore such a pattern, or replace this probe with one that proves the same thing.")
# A NEGATED rule must not read as ignored. Run against a THROWAWAY repo rather than this one, so the
# probe cannot drift when either `.gitignore` here changes -- and so the fixture can use the bare-name
# query form, which is the only form observed to make `-v` emit a negated record at all.
def _negation_probe() -> tuple[bool, bool]:
    """`(git_emitted_a_negated_record, classifier_dropped_it)` from a temp repo.

    Both halves are returned because asserting only the second is VACUOUS: if git emitted nothing,
    "keep.log is not in the result" is true for the wrong reason and the guard is never exercised.
    *The same mistake `test_unique_read_guard` records in its own first draft -- asserting an outcome
    without asserting the path to it ran.*
    """
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True, capture_output=True)
        with open(os.path.join(tmp, ".gitignore"), "w", encoding="utf-8") as fh:
            fh.write("*.log\n!keep.log\n")
        raw = subprocess.run(["git", "check-ignore", "-v", "--no-index", "keep.log", "drop.log"],
                             capture_output=True, text=True, cwd=tmp)
        emitted = any(":!" in ln for ln in raw.stdout.splitlines())
        got = ignored_sources(["keep.log", "drop.log"], cwd=tmp, as_dirs=False)
        return emitted, ("drop.log" in got and "keep.log" not in got)

_NEG_EMITTED, _NEG_DROPPED = _negation_probe()
check("self-test: the negation fixture actually makes `-v` print a `!` record",
      _NEG_EMITTED,
      "git printed no negated rule for the probe, so the check below proves nothing about the guard "
      "-- it would pass even with the guard deleted. Re-build the fixture until git emits one.")
check("self-test: a path a `!` rule un-ignores is NOT counted as ignored",
      _NEG_DROPPED,
      "`-v` prints negated rules for paths that are NOT ignored; dropping them is what keeps this "
      "gate from reporting an unignored scratch dir as covered")

check("self-test: a name no pattern can match is classified NOT ignored",
      "_gate_selftest_no_pattern_can_match_this" not in _probe,
      "the classifier calls everything ignored, so this gate can only report good news")

if FAILED:
    print("\nscratch_ignored: the classifier failed its own self-test; its verdicts below mean "
          "nothing and are not printed.")
    raise SystemExit(1)

NAMES = derive()

# --- and the DERIVATION must reach, which is a different question from the classifier working ------
check("the derivation reaches a known scratch dir (_shelf_famgeom, from test_family_geometry.py)",
      "_shelf_famgeom" in NAMES,
      f"regex found {len(NAMES)} names but not that one -- the literal form has changed and this "
      "gate is now scanning for something the tree no longer writes")
check("...and a known STORAGE_DIR scratch dir (_storage_jobs)",
      "_storage_jobs" in NAMES, sorted(NAMES)[:10])
check("the population is the whole package, not a handful",
      len(NAMES) > 300, len(NAMES))

_IGNORED = ignored(sorted(NAMES))
UNCOVERED = sorted(n for n in NAMES if n not in _IGNORED and n not in EXEMPT)

check("every derived scratch directory is git-ignored", not UNCOVERED,
      f"{len(UNCOVERED)} not ignored and not exempt: {UNCOVERED} -- add a pattern to .gitignore "
      "(preferred), or, if the literal is not a directory at all, add it to EXEMPT with a reason")

# An exemption for something git already ignores is dead weight that outlives its reason.
_STALE = sorted(n for n in EXEMPT if n in _IGNORED)
check("no exemption covers a name .gitignore already handles", not _STALE,
      f"{_STALE} -- drop these from EXEMPT; a rule kept past its cause is the thing this repo keeps "
      "re-learning")

# An exemption for a name the derivation no longer finds is the same rot in the other direction.
_ORPHAN = sorted(n for n in EXEMPT if n not in NAMES)
check("no exemption names a literal that has left the tree", not _ORPHAN,
      f"{_ORPHAN} -- the literal is gone; drop the exemption rather than carrying a reason for "
      "something nobody can check")

print()
if FAILED:
    print(f"scratch_ignored: {len(FAILED)} FAILED -- {FAILED}")
    raise SystemExit(1)
print(f"scratch_ignored: all checks passed -- {len(NAMES)} scratch-directory literals derived from "
      f"services/api/*.py, {len(NAMES) - len(EXEMPT)} of them git-ignored and {len(EXEMPT)} exempt as "
      "non-directories with a stated reason. The classifier passed all five of its own self-tests "
      "first -- a dropped trailing slash, a wrong working directory, a per-directory canary "
      "satisfied by the WRONG ignore file, and a `!` rule counted as ignored are each caught "
      "before any verdict above is printed; the negation probe also asserts git EMITTED the "
      "record it drops, so that check cannot pass vacuously.")
