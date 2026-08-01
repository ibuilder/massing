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

    cited = {
        tok
        for tok in re.findall(r"`([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)`", text)
        if tok.endswith(CODE_SUFFIXES) and tok not in NOT_A_SINGLE_FILE
    }
    total_cited += len(cited)

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

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_claude_md_gates OK")
