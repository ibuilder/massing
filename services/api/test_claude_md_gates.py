"""
Every gate file the standing docs name must actually exist.

WHY THIS EXISTS
    On 2026-07-31 CLAUDE.md's "Verify, don't recall" section — the section arguing that prose drifts
    and that rules must be written as checks that fail — named four gates by filename. Two were
    wrong:

        check_file_sizes.py      the capability was real; the FILE is test_file_sizes.py
        test_no_competitors.py   never existed anywhere in the tree, at any commit

    A section about prose drifting had drifted, in the one list a reader is most likely to trust.
    Both failures are the expensive kind. A name that does not resolve reads as "the gate was never
    built", so the next session either rebuilds a guard that already exists under another name, or
    repeats a rule as enforced when nothing enforces it.

    The fix is not to proofread the list more carefully — that is the thing that just failed. It is
    to make the list assertable, so a name that stops resolving turns the suite red instead of
    quietly misleading whoever reads it next.

TWO LESSONS, PAID FOR
    1. A name that does not resolve is NOT a missing capability. Searching "check_file_sizes.py"
       returns nothing and reads like the gate was never built. Searching what it *does* —
       file_size, CEILING, tracked_source — finds services/api/test_file_sizes.py, which had been
       enforcing a ratchet the whole time. Search the capability before concluding anything is
       absent, and before building a replacement for something that already exists under another
       name. Grep the terms you are about to write down, too: the first draft of this note cited a
       constant named MAX_LINES, which appears nowhere in that file. The failure mode reproduces
       itself if you let it.

    2. Name the ref, and expect it to move. The same question — "is there a no-competitor-names
       gate?" — produced THREE different true answers inside one day:

         (a) "It does not exist."          The original CLAUDE.md cited test_no_competitors.py,
                                           which never existed at any commit. Correct to reject.
         (b) "It exists nowhere."          A grep over origin/main, the sibling worktrees and the
                                           LOCAL branch refs. Wrong: it never looked at
                                           origin/claude/*, where a sibling had it built and green
                                           as PR #148. A stale local ref answered for a remote that
                                           had moved.
         (c) "It exists, not on main."     True for about an hour. #148 then merged, and the claim
                                           went stale while a PR asserting it was still open.

       So: state which ref a claim is about, check the ref that would actually hold the answer, and
       prefer a claim that stays true — "ask origin/main" outlives "as of today, main lacks it".
       This is why the list above is asserted rather than described. A date-stamped sentence about
       the tree is a fact with a short shelf life; a test is a fact that re-checks itself.

SCOPE — WHY MORE THAN ONE DOC
    The first version of this test read CLAUDE.md alone. That was the same defect one level up: a
    gate scoped to a single file, passing green while the document beside it goes unchecked. As of
    2026-07-31 CLAUDE.md itself says to read docs/roadmap-directions.md FIRST, because the standing
    directions now carry the non-negotiables — and that file names more code files than CLAUDE.md
    does. A gate that covered only the doc which happened to break is a gate aimed at the past.

    So DOCS below is the list, and adding a standing doc means adding it there. A missing doc is a
    FAILURE, never a silent skip: a scan that quietly checks nothing reports PASS forever.

WHAT THIS DOES AND DOES NOT CHECK
    It checks that every code-file name these docs mention resolves to a file git tracks. It does
    NOT check that the file is a meaningful gate, that it is wired into any runner, or that it tests
    what the surrounding prose claims. Those are judgement; this is a spell-checker for claims about
    the filesystem. It catches the exact defect that occurred, which is the bar.

    Matching is by BASENAME against `git ls-files`, deliberately. These docs name gates the way a
    person says them ("ties.test.ts"), not by path; requiring full paths would make them worse to
    read and would break on every file move. The cost is that a name is satisfied by a same-named
    file anywhere in the tree. That is an acceptable trade for a doc gate, and the ambiguous case is
    printed rather than hidden.

    Only backticked tokens count. These docs consistently backtick filenames, and unbacketed prose
    mentions cannot be told apart from ordinary words ("massing.build" is not a file). One
    consequence is now a convention, recorded in CLAUDE.md: backticks are reserved for files that
    exist, and a dead or historical name goes in plain quotes. That is not a workaround for this
    test — it is the distinction whose absence caused the original bug, since a backticked name
    reads as a live citation whether or not anything backs it.
"""
import os
import re
import subprocess
import sys

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: The standing docs whose gate citations must stay true. Add a doc here when it starts naming the
#: checks people are told to rely on — that is the whole trigger.
DOCS = (
    "CLAUDE.md",
    "docs/roadmap-directions.md",
    # Added 2026-08-01 by the GATE-VACUITY-SWEEP. The roadmap cites more code files than either doc
    # above (95 backticked paths vs ~13), every one of them offered as EVIDENCE for a claim about what
    # is built — so a dead citation here is a roadmap asserting a gap or a capability against a file
    # that does not exist. It was NOT clean when added — the same commit fixed two dead citations it
    # caught immediately, one of them naming the wrong *directory* (lanes are assigned by directory,
    # so that misroutes a reader). An earlier version of this comment claimed "0 dead of 95", which
    # was my own pre-check reporting a false all-clear: it matched by BASENAME, so two wrong PATHS
    # resolved to real files elsewhere and passed. A looser reader confirming a stricter one's subject
    # is not corroboration.
    "docs/roadmap.md",
    # Added 2026-09-04. The PR template is a CHECKLIST OF CHECKS — the exact trigger this list names
    # — and it had gone stale in the way that matters: it told every contributor to run
    # `ruff check src/ ../data/src/`, the narrow scope RUFF-SCOPE replaced on 2026-09-03, and to
    # build on "Node 20" when both manifests declare `>=24` and `ci.yml` pins 24. A checklist that
    # names a command CI no longer runs is worse than no checklist: it is followed.
    #
    # This gate can only assert that the FILES it cites exist, not that its COMMANDS match CI —
    # `services/api/test_ruff_scope.py` does the latter for the ruff line specifically. Adding the
    # template here catches the cheaper half, which is a dead citation.
    #
    # `CONTRIBUTING.md` carries the same commands and was corrected in the same commit, but it is
    # NOT added: its paths live in bash fences rather than backticks, so it contributes ZERO
    # citations, and a doc that matches nothing passes vacuously — the failure this file's own
    # header calls worse than no gate at all.
    ".github/pull_request_template.md",
    # `docs/roadmap-completed.md` is deliberately NOT here. It is a historical record, and its 245
    # citations include PROPOSED names for things never built (the market-data connector was one, in an
    # "INTEGRATE (optional)" block, backticked as though it shipped — corrected to plain quotes). The
    # right rule for the archive is the convention, not the gate: backticks are reserved for files that
    # exist, and a proposal gets quotes. Gating it would force either a growing exemption list or the
    # rewriting of history, and both are worse than the convention.
)

#: Only code files. These docs also name other docs (`docs/roadmap.md`) and commands (`node -v`);
#: those are linked or run, not gates, and pulling them in would make this test about something else.
CODE_SUFFIXES = (".py", ".ts", ".tsx")

#: Named in prose as a data-file *kind*, not as one file on disk. `module.json` has ~130 instances
#: and resolving it proves nothing. Exempt by name, never by pattern — an inferred exemption is how
#: a gate stops gating.
NOT_A_SINGLE_FILE = frozenset({"module.json"})

out = subprocess.run(
    ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=120,
)
check("git ls-files returned a tree", out.returncode == 0 and out.stdout.count("\n") > 100)

tracked = [p.strip().replace("\\", "/") for p in out.stdout.splitlines() if p.strip()]

by_base = {}
for path in tracked:
    by_base.setdefault(path.rsplit("/", 1)[-1], []).append(path)


def resolve(name):
    """Full path, path suffix, or bare basename — all three are how a person cites a file."""
    name = name.replace("\\", "/")
    if "/" in name:
        return [p for p in tracked if p == name or p.endswith("/" + name)]
    return by_base.get(name, [])


total_cited = 0
per_doc: dict[str, int] = {}   # citations found PER doc — a summed floor lets one doc drop to zero
missing = []

for doc in DOCS:
    path = os.path.join(ROOT, doc)

    # A doc that vanished (renamed, moved) must fail here. Skipping it silently would leave this
    # test green while its whole subject went unchecked.
    if not os.path.isfile(path):
        check(f"{doc} exists to be scanned", False, "not found — renamed, or DOCS is stale")
        continue

    # Read from disk, not from any cached idea of what it says. This test's subject is prose that
    # drifted away from the tree; reading a remembered copy would defeat it entirely.
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    # The path may carry a LOCATOR — `foo.py:64`, `foo.py:64-67`, `foo.py::register`, `foo.ts#anchor`.
    # The original pattern required the closing backtick immediately after the extension, so every
    # located citation was invisible: 21 roadmap files were cited ONLY that way and went unchecked
    # while the gate reported a confident count. A citation is *more* precise when it names a line,
    # so the most specific references were exactly the ones escaping the check.
    cited = {
        tok
        for tok in re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)(?:[:#][^`]*)?`", text)
        if tok.endswith(CODE_SUFFIXES) and tok not in NOT_A_SINGLE_FILE
    }
    total_cited += len(cited)
    per_doc[doc] = len(cited)

    print(f"\n  {doc}  ({len(cited)} gate name(s) cited)")
    for name in sorted(cited):
        hits = resolve(name)
        if hits:
            where = hits[0] + (f"  (+{len(hits) - 1} more)" if len(hits) > 1 else "")
            print(f"    ok    {name:<42} -> {where}")
        else:
            print(f"    MISS  {name}")
            missing.append(f"{doc}:{name}")

print()

# A gate that matches nothing passes vacuously and is worse than no gate, because it reports PASS
# forever. If the citation style in these docs ever changes, this is the check that notices.
#
# PER-DOC, not summed. A single total lets one doc's contribution fall to ZERO while the others hold
# the number up — split `roadmap.md`, stub it, or reformat its citations and the gate stays green with
# its largest subject silently unscanned. The floor has to bind on every doc or it does not bind on
# any of them; the same argument as asserting families as SETS rather than counts.
#: Per-doc RATCHET, not a floor of 1. `roadmap.md` contributes ~118 of ~131 citations, so ">= 1"
#: would let a restructure leave a single citation and pass with ~117 unscanned — the floor has to
#: bind near the real number to bind at all. Set below today's counts with headroom for ordinary
#: editing; raise them when a doc grows. Lowering one is a deliberate act that should be argued for
#: in the commit, which is the point of a ratchet.
MIN_CITATIONS = {
    "CLAUDE.md": 4,                    # 6 today
    "docs/roadmap-directions.md": 5,   # 7 today
    "docs/roadmap.md": 90,             # 118 today
    ".github/pull_request_template.md": 3,   # 4 today
}
_thin = sorted(
    f"{d}={n} (min {MIN_CITATIONS[d]})"
    for d, n in per_doc.items() if n < MIN_CITATIONS.get(d, 1)
)
check(
    "every scanned doc still contributes its expected citations",
    not _thin,
    f"below the ratchet: {', '.join(_thin)}" if _thin else
    " · ".join(f"{d}={n}" for d, n in per_doc.items()),
)
check(
    "the citation scan actually found gate names to check",
    total_cited >= 5,
    f"{total_cited} cited across {len(DOCS)} doc(s)",
)

check(
    "every gate the standing docs name resolves to a tracked file",
    not missing,
    "; ".join(missing),
)

if missing:
    # Point at the fix, not just the failure. The 2026-07-31 case was a REAL guard under a different
    # name, so "delete the reference" is the wrong first instinct and is called out here.
    print(
        "\n  A name above does not resolve. Before removing it from the doc, search for the\n"
        "  CAPABILITY rather than the literal filename — the size guard was cited for months as\n"
        "  'check_file_sizes.py' while really living in `test_file_sizes.py`, and grepping for\n"
        "  'file_size' or 'CEILING' is what found it. Only if no file does the job is the citation\n"
        "  fiction; then either write the gate, or say plainly in the doc that the rule is\n"
        "  unenforced. Do not cite a gate that does not exist — that is the bug this test caught."
    )

# ---------------------------------------------------------------------------------------------
# CLAUDE.md quotes a line count that a GATE already owns. Added 2026-09-05.
#
# The viewer section states the current size of `apps/web/src/viewer/app.ts` as evidence for how far
# the decomposition has run. That exact number drifted three times: it sat at "3,444" for weeks, was
# corrected to "2,570", and was stale again **inside the same pull request** because a decomposition
# slice landed beside the correction and a review bot, not the author, noticed.
#
# The check above asks whether a cited FILE exists. This asks whether a cited NUMBER is still true,
# which is the harder half and the one that keeps failing here. It is cheap only because the number
# is not really CLAUDE.md's to hold: `test_file_sizes.py` pins the same file at an exact size and
# fails the build when it moves, so the prose is a COPY of a gated value, and a copy is what drifts.
#
# The rule this encodes is narrow on purpose: a doc may quote a number that a gate owns, but the two
# have to be compared by something. Prose that reasons ABOUT the pin ("pins its exact size", "2,507"
# as a mutation-check witness) is not a claim about today's file, so only the figure attached to the
# "has gone from 5,064 lines to N" sentence is read.
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
PIN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_file_sizes.py")

with open(CLAUDE_MD, encoding="utf-8") as fh:
    _claude = fh.read()
with open(PIN_FILE, encoding="utf-8") as fh:
    _pins = fh.read()

_stated = re.search(
    r"`apps/web/src/viewer/app\.ts`\s+has gone from\s+[\d,_]+\s+lines to\s*\n?\s*\*\*([\d,_]+)\*\*",
    _claude,
)
_pinned = re.search(
    r'"apps/web/src/viewer/app\.ts"\s*:\s*([\d_]+)', _pins,
)

# Both halves must be FOUND, not just agree. If either pattern stops matching — the sentence is
# reworded, the ratchet key is renamed — this check would otherwise pass on two Nones, which is the
# vacuous-green failure this file's own header calls worse than no gate.
check(
    "CLAUDE.md's app.ts sentence and the ratchet pin are both readable",
    bool(_stated) and bool(_pinned),
    f"prose={'found' if _stated else 'NOT FOUND'} · pin={'found' if _pinned else 'NOT FOUND'}",
)

if _stated and _pinned:
    _n_prose = int(_stated.group(1).replace(",", "").replace("_", ""))
    _n_pin = int(_pinned.group(1).replace("_", ""))
    check(
        "CLAUDE.md's stated app.ts size matches the size the ratchet pins",
        _n_prose == _n_pin,
        f"CLAUDE.md says {_n_prose:,}; test_file_sizes.py pins {_n_pin:,}"
        + ("" if _n_prose == _n_pin else
           " — update the prose in the SAME EDIT as the slice that moved it, not the same commit"),
    )

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_claude_md_gates OK")
