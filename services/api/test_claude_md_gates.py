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

IT ASKS GIT, SO IT FAILS ON AN UNCOMMITTED TREE — AND THAT IS NOT A DEFECT IN THE TREE
    `git ls-files` lists TRACKED paths, so a file that exists on disk and has never been `git add`ed
    is a MISS here even though the citation is perfectly good. On 2026-10-14 a full backend suite
    came back 735/736 with this as the only failure: it was started while two newly written files —
    cited in a roadmap entry in the same change — were still untracked, and the commit landed six
    minutes later. Reproduced deliberately afterwards by citing an untracked file: the output is the
    same single line, `FAILED: every gate the standing docs name resolves to a tracked file`.

    Two things follow. **Run the suite against a tree with nothing untracked** (`git add -A` is
    enough — staged counts), or this one check fails for a reason that evaporates on commit and
    costs somebody a hunt. And asking git rather than the filesystem stays correct: an untracked
    file is not in the repository, so a doc that cites one is making a claim about a tree nobody
    else has. The alternative — `Path.exists()` — would pass locally and fail in CI, which is the
    worse way round.

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
# The SAME figure lives in `docs/roadmap.md` twice, and the gate above did not reach it. Added
# 2026-09-05, one PR after that gate: the roadmap's R39-DECOMP-VIEWER entry carried THREE figures for
# `app.ts` — a header saying "5,160 -> 3,311", a shipped block saying "5,160 -> 2,944", and the truth,
# 2,508. It also used a DIFFERENT baseline from CLAUDE.md (5,160 vs 5,064) with neither labelled, so
# nothing could tell a reader they were measured from different points; both were real, 5,064 being the
# file before the first extraction commit and 5,160 a same-day peak partway through it.
#
# The lesson is about the gate, not the numbers. The check above was written to stop a narrative copy of
# a pinned value from drifting, and it gated ONE copy of a number that lives in three places. **Gating
# the instance you happened to be looking at is not gating the class.** So this scans every doc for the
# baseline-anchored form and requires each to equal the pin — which also holds the BASELINE steady,
# since a figure measured from somewhere else no longer matches the pattern at all.
#
# Historical mentions are deliberately still matchable only by their own baseline: the corrected text
# quotes "5,160 -> 2,944" as the thing that was wrong, and that does not match this pattern, so the
# record of the error survives without failing the build.
APP_TS_BASELINE = "5,064"
_arrow = re.compile(re.escape(APP_TS_BASELINE) + r"\s*(?:->|\u2192)\s*\*{0,2}([\d,]+)")

#: Docs carrying the ARROW form, and the minimum each must contribute. PER-DOC, never summed — the
#: first draft of this check used a summed floor of 2 and reported "3 figures across 2 docs" while
#: **all three came from the roadmap**: CLAUDE.md words it "5,064 lines to", so the arrow pattern
#: never matched it and its contribution was ZERO. A mutation that reformatted only the roadmap took
#: the count to 0 and revealed it. That is the exact failure this file's own citation ratchet was
#: built to avoid, repeated one screen further down — **a summed floor lets one doc hold the number
#: up while another silently contributes nothing.** CLAUDE.md is not listed here because the two
#: checks below cover its wording directly; a doc is either in this map or covered by name, never
#: assumed.
ARROW_DOCS = {"docs/roadmap.md": 3}

_bad, _thin = [], []
for _doc, _min in ARROW_DOCS.items():
    with open(os.path.join(ROOT, _doc), encoding="utf-8") as fh:
        _hits = _arrow.findall(fh.read())
    if len(_hits) < _min:
        _thin.append(f"{_doc}={len(_hits)} (min {_min})")
    for _h in _hits:
        if _pinned and int(_h.replace(",", "")) != int(_pinned.group(1).replace("_", "")):
            _bad.append(f"{_doc}: {APP_TS_BASELINE} -> {_h}")

check(
    "every doc that quotes the app.ts figure quotes the pinned one",
    not _bad and not _thin,
    (f"below the floor: {', '.join(_thin)}; " if _thin else "")
    + (f"DISAGREE: {', '.join(_bad)}" if _bad else "all figures match the pin"),
)

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

# EVERY TRACKED MARKDOWN FILE, not the four standing docs. **The mutation run forced this.**
# Reinstating the seven shipped `docs/internal/README.md` rows did NOT red the build, because `DOCS`
# is four files and that is not one of them — so the sweep that FOUND those rows walked all of
# `docs/`, while the gate meant to hold them walked a quarter of it. *My "clean" and the gate's
# "clean" were claims about different populations, and they read identically.*
#
# `DOCS` is right for the CITATION check above: those are the documents whose backticked paths are
# offered as evidence. It is wrong for the three table checks below, which are about RENDERING and
# have no reason to care which document they are in. Measured before widening: 127 tracked markdown
# files, 1,590 body rows (up from 1,343), and zero findings of any of the three kinds — so the
# widening costs no exemptions and quadruples what is held.
MD_FILES = [p for p in tracked if p.endswith(".md")]
check(
    "the markdown sweep reaches more than the four standing docs",
    len(MD_FILES) > 100 and "docs/internal/README.md" in MD_FILES,
    f"{len(MD_FILES)} tracked .md files"
    + ("" if "docs/internal/README.md" in MD_FILES else " — docs/internal/README.md MISSING"),
)


# ---------------------------------------------------------------------------------------------
# A PIPE INSIDE BACKTICKS IS STILL A CELL DELIMITER.
#
# Round 5 of this branch's review found `` `string | null` `` in a two-column roadmap table: GitHub
# splits that row into THREE cells and the rest of the sentence — the whole verdict the row exists
# to carry — is simply not rendered. Backticks do not protect a pipe in a table, which is the kind
# of thing everybody knows and nobody checks.
#
# **It is the quiet failure mode that earns the gate, not the frequency.** A broken citation is
# loud: the path 404s and this file already reds the build. A swallowed cell renders as a shorter
# sentence that still reads as a sentence — nothing looks wrong, and these documents are the record
# the next reader works from. One instance across every tracked markdown file today, so the cost of
# the rule is zero and its value is entirely in the next one.
#
# Fenced code blocks are skipped: a line beginning with `|` inside a ``` fence is not a table row,
# and a checker that cannot tell the difference reports a confident finding about nothing.
_BACKTICK_SPAN = re.compile(r"`+[^`]*`+")
_DELIM_CELL = re.compile(r":?-{1,}:?\Z")


def _unescaped_pipes(s):
    r"""Positions of pipes that are real cell delimiters, by BACKSLASH PARITY.

    **Review of round 8 found `(?<!\\)\|` wrong in both directions**, and both were measured:

    * `| a | b \|` — a two-column row ending in an ESCAPED pipe. The old `s.endswith("|")` took it
      for an outer delimiter and dropped the last cell, so the row counted **1** and the scan
      reported a false mismatch. A gate that reds on correct markdown is worse than one that misses,
      because the next person's fix is to loosen it.
    * `| a | b \\| c |` — an escaped BACKSLASH followed by a REAL pipe. A one-character lookbehind
      sees the backslash and calls the pipe escaped, so the row counted **2** instead of 3 and a
      genuine cell break went unseen.

    *One lookbehind cannot answer a question about a RUN of characters.* An odd number of preceding
    backslashes escapes the pipe; an even number leaves it a delimiter.
    """
    out, i = [], 0
    while i < len(s):
        if s[i] == "|":
            bs = 0
            k = i - 1
            while k >= 0 and s[k] == "\\":
                bs += 1
                k -= 1
            if bs % 2 == 0:
                out.append(i)
        i += 1
    return out


def _split_cells(line):
    """A table row's cells. Outer pipes are delimiters, not cells — but only when UNESCAPED."""
    s = line.strip()
    pos = _unescaped_pipes(s)
    if not pos:
        return [s]
    parts, prev = [], 0
    for p in pos:
        parts.append(s[prev:p])
        prev = p + 1
    parts.append(s[prev:])
    if pos[0] == 0:
        parts = parts[1:]
    if pos[-1] == len(s) - 1 and len(parts) > 1:
        parts = parts[:-1]
    return parts


def _is_delim_row(line):
    """A GFM delimiter row: every cell a dash run, and **at least one pipe**.

    The pipe requirement is what keeps a bare `---` (a thematic break, or a setext underline) from
    opening a phantom table. **One-column tables are legal GFM and the old regex rejected them** —
    it demanded a second `|`-prefixed cell, so `| --- |` failed and every body row of such a table
    was invisible to all three checks below. Found by review, not by this file's own canaries, which
    all used two columns.
    """
    s = line.strip()
    if "|" not in s:
        return False
    cells = _split_cells(s)
    return bool(cells) and all(_DELIM_CELL.match(c.strip()) for c in cells)


def _has_raw_pipe(text):
    """Does this span carry an unescaped pipe? Parity-aware, for the same reason as above."""
    return bool(_unescaped_pipes(text))


# A line that STARTS A NEW BLOCK ends the table, even with no blank line between — GFM breaks a
# table at "the beginning of another block-level structure". So a heading, list item, blockquote,
# fence or HTML block directly after a row is NOT absorbed prose, and reporting it would red the
# build on correct markdown. Every one of these was reported before review caught it.
_BLOCK_START = re.compile(r"^(#{1,6}\s|>|[-*+]\s|\d+[.)]\s|```|~~~|<[a-zA-Z/!]|\s*$|(\s*[-*_]){3,}\s*$)")


def table_row_lines(text):
    """Line numbers (0-based) belonging to a GFM table: the header, the delimiter, and the body.

    **Found by review: a leading `|` is not required by GFM, and the first draft keyed on one.**
    The obvious repair — match a row with or without a leading pipe — was measured before it was
    written, and it reports **39** hits across these documents, every one legitimate prose: a query
    string (`?standard=iso19650|cobie|ids`), a shell `|| true`, a CLI alternation, a literal `` `|` ``
    being described. *A rule that needs an exemption list is a rule whose population is wrong* — the
    lesson COURT-PRIMARY paid for when it bounded its own.

    So the row is identified by CONTEXT instead: a delimiter row (`---|---`) under a line containing
    a pipe opens a table, and the body runs until a blank line, a fence, or a line with no pipe.
    Measured on this tree: 1,797 rows, which is the same population the leading-pipe rule found, so
    the widening costs nothing today and catches the pipe-less row the moment one appears.

    **Requiring a pipe in each body line is DEFENSIVE, not load-bearing — mutation said so and the
    first draft of this docstring claimed the opposite.** Deleting it changes no verdict, because a
    line with no pipe cannot carry a cell-splitting pipe and so yields no hit either way. It is kept
    because this function reports which lines ARE rows, and a caller that trusts that answer should
    not be handed a prose paragraph; the canary below therefore measures the ROW SET directly rather
    than the verdict. *Reporting a site and classifying it are two different questions* —
    `test_unique_read_guard` paid for that distinction one layer up.
    """
    rows, fenced = set(), False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _is_delim_row(line) and i > 0 and "|" in lines[i - 1]:
            rows.add(i - 1)
            rows.add(i)
            j = i + 1
            while (j < len(lines) and lines[j].strip() and "|" in lines[j]
                   and not lines[j].lstrip().startswith("```")):
                rows.add(j)
                j += 1
    return rows


def pipes_in_table_cells(text):
    """Backtick spans on table rows that carry an unescaped pipe. (line number, span)."""
    lines = text.splitlines()
    hits = []
    for i in sorted(table_row_lines(text)):
        for m in _BACKTICK_SPAN.finditer(lines[i]):
            if _has_raw_pipe(m.group(0)):
                hits.append((i + 1, m.group(0).strip()))
    return hits


# The checker must be able to SAY YES, or its silence proves nothing — the fail-open hole
# `test_roadmap_status.py` had, where one broken regex made every item report PASS.
_TBL = "| h | h2 |\n|---|---|\n"
_canary = pipes_in_table_cells(_TBL + "| `a | b` | c |")
check(
    "the table-pipe scan can still find one",
    _canary == [(3, "`a | b`")],
    f"canary={_canary}",
)
# CodeRabbit's case: GFM does not require the leading pipe, and the first draft did.
_nolead = pipes_in_table_cells("h | h2\n---|---\na | `b | c` | d")
check(
    "...and finds one on a row with NO leading pipe",
    _nolead == [(3, "`b | c`")],
    f"no-leading-pipe canary={_nolead}",
)
# The load-bearing negative, and the reason this is context-based rather than a looser line regex:
# 39 spans in these documents are pipes inside backticks in ORDINARY PROSE, all legitimate.
_prose = pipes_in_table_cells(
    "The flag is `?standard=iso19650|cobie|ids` and the step ran `|| true`.\n"
)
check(
    "...and does NOT flag a pipe inside backticks in ordinary prose",
    _prose == [],
    f"prose canary={_prose}",
)
# **THE CANARY THAT WAS WRONG, AND WHAT IT FOUND.** This asserted that a prose line abutting a
# table is not part of it. It failed — and the RULE was right, the EXPECTATION wrong: GFM breaks a
# table at a blank line, so an unseparated following paragraph is lazy continuation and GitHub
# renders it as a ROW. Which means `docs/roadmap.md` was rendering a three-line paragraph inside a
# table, a real defect this check found by disagreeing with its author. One instance tree-wide,
# fixed by ending the table with a blank line. *A canary that fails is doing its job even when the
# thing that is wrong is the canary.*
_abut = pipes_in_table_cells(_TBL + "| a | b |\nTrusting a written number `x | y` instead.\n")
check(
    "a pipe-bearing line abutting a table IS a row, because GFM says so",
    _abut == [(4, "`x | y`")],
    f"abutting-prose canary={_abut}",
)
# The pipe requirement, measured where it actually shows: the ROW SET. Nothing in the verdict can
# see it, so a mutation deleting it survived until this existed.
_rows = table_row_lines(_TBL + "| a | b |\nTrusting a written number, no pipe here.\n")
check(
    "a pipe-less line after a table body is not counted as a row",
    _rows == {0, 1, 2},
    f"row set={sorted(_rows)} (expected the header, delimiter and one body row)",
)

# ...and a blank line is what actually ends it. This is the half the fix relies on.
_ended = pipes_in_table_cells(_TBL + "| a | b |\n\nTrusting a written number `x | y` instead.\n")
check(
    "...and a blank line ends the table, so the paragraph after one is not a row",
    _ended == [],
    f"blank-line canary={_ended}",
)
_fenced_canary = pipes_in_table_cells("```\n" + _TBL + "| `a | b` |\n```")
check(
    "...and does not report a table row inside a fenced code block",
    _fenced_canary == [],
    f"fenced canary={_fenced_canary}",
)
_escaped_canary = pipes_in_table_cells(_TBL + "| `a \\| b` | c |")
check(
    "...and accepts an escaped pipe, which is the fix it asks for",
    _escaped_canary == [],
    f"escaped canary={_escaped_canary}",
)

_pipe_hits = []
for _rel in MD_FILES:
    _abs = os.path.join(ROOT, _rel)
    if not os.path.exists(_abs):
        continue
    with open(_abs, encoding="utf-8") as _fh:
        for _n, _span in pipes_in_table_cells(_fh.read()):
            _pipe_hits.append(f"{_rel}:{_n} {_span}")

check(
    "no markdown table cell hides an unescaped pipe",
    not _pipe_hits,
    "clean" if not _pipe_hits else
    "GitHub renders each of these as an extra cell and DROPS the rest of the row — "
    "escape the pipe as `\\|`: " + " · ".join(_pipe_hits),
)

# ---------------------------------------------------------------------------------------------
# A TABLE THAT RUNS STRAIGHT INTO A PARAGRAPH SWALLOWS IT.
#
# Found by MUTATION, not by review: re-absorbing the paragraph this change separated did not red any
# check above, because those three lines carry no backticked pipe. So the defect was fixed and
# unguarded — *the worst of the two states, because the fix reads as the end of the matter.*
#
# GFM breaks a table at a blank line. Without one, the following paragraph is lazy continuation and
# GitHub renders it as a row: in `docs/roadmap.md` a three-line paragraph was being drawn inside the
# sprint table, its sentences split into cells at every stray pipe and the rest of each line
# dropped. One instance tree-wide when this was written.


def prose_absorbed_by_table(text):
    """First pipe-less line of each table body — a paragraph GFM is rendering as a row."""
    # `table_row_lines` rescans the whole document, so calling it per row is O(rows x lines).
    # Measured when review raised it: **9.8 s** for this one check over the 127 tracked markdown
    # files — on every CI run and every local invocation. It was graded a trivial nitpick and the
    # number is not trivial, because the cost only became real an hour earlier when the sweep went
    # from 4 files to 127. *A performance note's severity depends on a population that moves.*
    lines, out = text.splitlines(), []
    rows = table_row_lines(text)
    for i in sorted(rows):
        j = i + 1
        if j >= len(lines):
            continue
        # No `j in rows` skip. It was here, and mutation showed **deleting it changes nothing**: for
        # an interior row the next line IS a row, so it contains a pipe and the test below already
        # rejects it. Provably equivalent, therefore impossible to mutation-test — and the house rule
        # is that a surviving mutation gets fixtured or deleted as unmeasured. The performance
        # argument for it died when `rows` stopped being recomputed per row.
        nxt = lines[j]
        if nxt.strip() and "|" not in nxt and not _BLOCK_START.match(nxt):
            out.append((j + 1, nxt.strip()[:70]))
    return out


_absorb_canary = prose_absorbed_by_table(_TBL + "| a | b |\nA trailing paragraph with no pipe.\n")
check(
    "the absorbed-paragraph scan can still find one",
    len(_absorb_canary) == 1,
    f"canary={_absorb_canary}",
)
_absorb_ok = prose_absorbed_by_table(_TBL + "| a | b |\n\nA trailing paragraph with no pipe.\n")
check(
    "...and a blank line is what makes it a paragraph again",
    _absorb_ok == [],
    f"separated canary={_absorb_ok}",
)

_absorbed = []
for _rel in MD_FILES:
    _abs = os.path.join(ROOT, _rel)
    if not os.path.exists(_abs):
        continue
    with open(_abs, encoding="utf-8") as _fh:
        for _n, _txt in prose_absorbed_by_table(_fh.read()):
            _absorbed.append(f"{_rel}:{_n} {_txt}")

check(
    "no table body runs straight into a paragraph",
    not _absorbed,
    "clean" if not _absorbed else
    "GitHub renders each of these as a table ROW, splitting the sentence at every pipe — "
    "put a blank line between the table and the paragraph: " + " · ".join(_absorbed),
)

# ---------------------------------------------------------------------------------------------
# A ROW WITH THE WRONG NUMBER OF CELLS LOSES OR SHIFTS ITS CONTENT.
#
# **This check exists because the one above it is a SUBSET of the real problem, and I defended that
# one at length before measuring this.** `pipes_in_table_cells` only looks inside backtick spans — a
# BARE unescaped pipe in cell text splits a cell just as completely and is invisible to it. Asking
# the stronger question found **eight rows the backtick check calls clean**:
#
#   * `docs/internal/README.md` rows 72–78 — a two-column table with THREE cells. GFM ignores the
#     excess, so an author's status qualifier ("not superseded — active") had never rendered once,
#     in seven rows.
#   * `docs/roadmap.md` row 4891 — a five-column header with FOUR cells. GFM pads the missing one at
#     the END, so every value shifted one column left: the Outcome text rendered under Size and
#     Outcome came out blank.
#
# *The two failure directions are not symmetric.* Too many cells DELETES content silently; too few
# SHIFTS it, which is worse, because a shifted row still looks like data and the reader has no way
# to know the columns have slipped. Both render without any warning from GitHub.
#
# Parity subsumes the backtick rule — a backticked pipe that splits a cell also changes the count —
# and needs **no exemptions**: 1,343 body rows, zero mismatches after the eight fixes. The backtick
# check is kept because it names the cause precisely ("escape this pipe") where this one only names
# the symptom ("this row has one cell too many").


def _cell_count(line):
    """Cells in a GFM table row — see `_split_cells` for why this is parity-aware."""
    return len(_split_cells(line))


def cell_count_mismatches(text):
    """(line, header cells, row cells) for each body row that disagrees with its header."""
    lines, out, fenced = text.splitlines(), [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _is_delim_row(line) and i > 0 and "|" in lines[i - 1]:
            header = _cell_count(lines[i - 1])
            # GFM: the delimiter row MUST match the header or no table is recognised at all.
            if _cell_count(line) != header:
                out.append((i + 1, header, _cell_count(line)))
            j = i + 1
            while (j < len(lines) and lines[j].strip() and "|" in lines[j]
                   and not lines[j].lstrip().startswith("```")):
                if _cell_count(lines[j]) != header:
                    out.append((j + 1, header, _cell_count(lines[j])))
                j += 1
    return out


_TOO_MANY = cell_count_mismatches("| a | b |\n|---|---|\n| x | y | z |\n")
check(
    "the cell-count scan finds a row with too MANY cells",
    _TOO_MANY == [(3, 2, 3)],
    f"canary={_TOO_MANY}",
)
_TOO_FEW = cell_count_mismatches("| a | b | c |\n|---|---|---|\n| x | y |\n")
check(
    "...and one with too FEW, which shifts rather than drops",
    _TOO_FEW == [(3, 3, 2)],
    f"canary={_TOO_FEW}",
)
_ESCAPED_CELL = cell_count_mismatches("| a | b |\n|---|---|\n| x | `p \\| q` |\n")
check(
    "...and an ESCAPED pipe is not counted as a cell break",
    _ESCAPED_CELL == [],
    f"canary={_ESCAPED_CELL}",
)
_BARE = cell_count_mismatches("| a | b |\n|---|---|\n| x | p | q |\n")
check(
    "...and a BARE pipe is caught where the backtick scan cannot see it",
    _BARE == [(3, 2, 3)] and pipes_in_table_cells("| a | b |\n|---|---|\n| x | p | q |\n") == [],
    "the bare-pipe row is caught here and invisible to the backtick scan — "
    "which is why this check exists",
)

# ROUND 8's three code findings, each with the measurement that confirmed it.
_one_col = cell_count_mismatches("| h |\n| --- |\n| x | y |\n")
check(
    "a ONE-COLUMN table is scanned — legal GFM the first delimiter regex rejected",
    _one_col == [(3, 1, 2)],
    f"one-column canary={_one_col}",
)
check(
    "...and a bare `---` still does not open a phantom table",
    not _is_delim_row("---") and not _is_delim_row("- - -") and _is_delim_row("| --- |"),
    f"bare={_is_delim_row('---')} spaced={_is_delim_row('- - -')} piped={_is_delim_row('| --- |')}",
)

# A heading after a row ends the table; reporting it would RED THE BUILD on correct markdown.
_heading = prose_absorbed_by_table(_TBL + "| a | b |\n## Next section\n")
check(
    "a block start after a table row is not absorbed prose",
    _heading == [],
    f"heading canary={_heading}",
)
_still = prose_absorbed_by_table(_TBL + "| a | b |\nOrdinary prose with no pipe.\n")
check(
    "...and ordinary prose after a row is still reported",
    len(_still) == 1,
    f"prose canary={_still}",
)

# Backslash parity, both directions, both measured before the fix.
_esc_end = _cell_count("| a | b \\|")
check(
    "a row ending in an ESCAPED pipe keeps both its cells",
    _esc_end == 2,
    f"cells={_esc_end} (the old one-char lookbehind gave 1, a false mismatch)",
)
_esc_bs = _cell_count("| a | b \\\\| c |")
check(
    "...and an escaped BACKSLASH leaves the pipe after it a real cell break",
    _esc_bs == 3,
    f"cells={_esc_bs} (the old lookbehind gave 2, missing the break)",
)

_cellbad = []
for _rel in MD_FILES:
    _abs = os.path.join(ROOT, _rel)
    if not os.path.exists(_abs):
        continue
    with open(_abs, encoding="utf-8") as _fh:
        for _n, _h, _c in cell_count_mismatches(_fh.read()):
            _cellbad.append(f"{_rel}:{_n} header={_h} row={_c}")

check(
    "every table row has exactly as many cells as its header",
    not _cellbad,
    "clean" if not _cellbad else
    "GitHub DROPS excess cells and PADS missing ones at the end, so each of these loses or shifts "
    "content with no warning: " + " · ".join(_cellbad),
)

# ---------------------------------------------------------------------------------------------
# TWO ROWS FOR ONE FILE ARE TWO ANSWERS TO ONE QUESTION.
#
# Round 8 found `docs/internal/README.md` carrying `plan-2026-08-10.md` TWICE: one row calling CC0
# an open user decision, the other recording *"CC0 settled 2026-08-19"*. **A stale OPEN record** —
# the class `test_gap_records.py` exists for, which guards the roadmap and the threat model and had
# no view of this index. *A stale OPEN costs more than a stale CLOSED*, because it sends the next
# reader at work that is already done, and here it misreported a decision as still the user's.
#
# Scoped to a BACKTICKED first cell on purpose: that column is an identifier — a filename, a path, a
# code symbol — where two rows is a contradiction. A prose first column legitimately repeats, and
# including it would need an exemption list, which is the mistake round 6 paid for.
#
# Zero across every tracked markdown file after the fix, so no exemptions. The replay below is the
# removed row itself, frozen rather than fetched — `test_gap_records.py` learned that depending on
# `git show` breaks under CI's shallow checkout.
_DUP_FIXTURE = (
    "| File | Status |\n| --- | --- |\n"
    "| `plan-2026-08-10.md` | **LIVE** — the two decisions that are the user's (CC0 on the "
    "permitted list; massingviser vs modelmaker as the platform). |\n"
    "| `vendorable-core-standard.md` | **LIVE, not superseded** — the standard. |\n"
    "| `plan-2026-08-10.md` | **LIVE** — **CC0 settled 2026-08-19**, massingviser vs modelmaker "
    "still the user's. |\n"
)


def duplicate_key_rows(text):
    """(line, key) for each table row whose backticked first cell already appeared in that table."""
    lines, out, fenced = text.splitlines(), [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _is_delim_row(line) and i > 0 and "|" in lines[i - 1]:
            seen, j = {}, i + 1
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                cells = _split_cells(lines[j])
                if cells:
                    key = cells[0].strip()
                    if re.fullmatch(r"`[^`]+`", key):
                        if key in seen:
                            out.append((j + 1, key))
                        else:
                            seen[key] = j + 1
                j += 1
    return out


_dup_canary = duplicate_key_rows(_DUP_FIXTURE)
check(
    "PROOF OF REACH: the row round 8 removed is re-found in its frozen form",
    _dup_canary == [(5, "`plan-2026-08-10.md`")],
    f"replay={_dup_canary}",
)
_dup_clean = duplicate_key_rows("| File | Status |\n| --- | --- |\n| `a.md` | x |\n| `b.md` | y |\n")
check(
    "...and distinct identifiers are not reported",
    _dup_clean == [],
    f"clean canary={_dup_clean}",
)
_dup_prose = duplicate_key_rows("| What | Why |\n| --- | --- |\n| same | x |\n| same | y |\n")
check(
    "...and a repeated PROSE first cell is not an identifier, so not a contradiction",
    _dup_prose == [],
    f"prose canary={_dup_prose}",
)

_dupes = []
for _rel in MD_FILES:
    _abs = os.path.join(ROOT, _rel)
    if not os.path.exists(_abs):
        continue
    with open(_abs, encoding="utf-8") as _fh:
        for _n, _key in duplicate_key_rows(_fh.read()):
            _dupes.append(f"{_rel}:{_n} {_key}")

check(
    "no table gives one identifier two rows",
    not _dupes,
    "clean" if not _dupes else
    "two rows for one identifier are two answers to one question — and the stale one is read as "
    "live: " + " · ".join(_dupes),
)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_claude_md_gates OK")
