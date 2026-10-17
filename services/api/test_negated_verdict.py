"""NEGATED-VERDICT — an all-negated verdict has no presence guard, which is why no gate could see it.

`services/api/test_verdict_coverage.py` asks whether a screen reading a verdict about a SUBSET also
reads what the engine could not evaluate. Its population is built from two shapes, and **both
require the guard to be PRESENT**: shape 1 wants a `bool(<name>)` operand, shape 3 wants at least one
plain truthiness operand. A verdict written entirely as negations —

    "navigable": not dangling and not orphans and not unparseable

— has no guard at all, so it is in neither shape, and it is **unconditionally True on empty input**.
*A predicate that requires the guard in order to look at a site cannot see the site whose defect IS
the missing guard.* That is the eighth note in `CLAUDE.md` arriving from a third direction: a
predicate deciding what to LOOK at is more dangerous than one deciding what to report.

Measured at **5** sites tree-wide before any was touched, and the five did not want the same fix:

| site | question | judged |
|---|---|---|
| `detail_refs.navigable` | can a reader navigate this set? | **FLIP** — a register with no references cannot be navigated, and `test_detail_refs.py` asserted `True` with the word *"vacuously"* beside it |
| `fin_ingest.fully_reconciled` | do the books tie out? | **FLIP** — a budget with no actuals reported *fully reconciled*, on a screen headed *Period close* |
| `roundtrip.fidelity_ok` | does my model survive export? | **FLIP** — 0 elements proved nothing, and the viewer's status line prints the bare verdict |
| `model_options.identical` | do these two models differ at element level? | **KEEP** — two element-less models genuinely do not differ; the population count was what was missing |
| `dim_constraints.solved` | are the locks satisfiable? | **KEEP** — nothing to solve IS solved, and this branch already carried `note: "no variables"` |

**The rule the split produces is not "always guard".** Flipping `solved` would report *not solved* for
a sketch carrying no locks — a false alarm in the opposite direction, which is how a check teaches
people to ignore it. *The fix for a vacuous truth is not always to make it false; sometimes it is to
say what it is true of.* So this gate demands, for every all-negated verdict, EITHER a presence guard
(after which `test_verdict_coverage.py` owns it) OR an `EMPTY-IS-CLEAN:` declaration with a reason,
in the comment block directly above the key.

**That declaration is deliberately not a central exemption list.** COURT-SPLIT paid to learn that *an
exemption list is where the next instance hides*; a marker at the site cannot hide a new instance,
because a new all-negated verdict arrives with no marker and reds the build. It is the same move
COURT-SPLIT made for the ball-in-court rule — *a premise that cannot be checked has already drifted;
the only repair is to stop inferring it and DECLARE it* — bounded to the 2 sites of 5 where the
declaration is load-bearing.

**The ≥2 threshold is measured, not chosen.** `And` with exactly ONE negated operand and no other
operand kind measures **0** on this tree, so `>= 2` and `>= 1` are the same rule today; the higher
bound is stated so that a future single-operand form is a deliberate decision rather than a silent
inclusion.

## What this gate does NOT cover, measured rather than hedged

The **bare single** `"key": not X` dict value measures **36 syntactically, and that is not the defect
count** — a distinction found by trying to use the number rather than by reading it again. Resolving
each negand to its binding gives **24** whose negand is a COLLECTION (where "empty" can mean *nothing
was examined*) and **12** whose negand is a SCALAR — `not too_new`, `not is_stale`, `not flat_plate`,
`not args.no_quality_gate` — for which the emptiness question does not arise at all. Five of the 24
already carry a sibling count in the same literal, so **18** need a judgement. *Presenting a
syntactic count as a defect count overstates in the flattering direction*, which is the one direction
a measurement is least likely to be challenged in.

**The split is structural, and that is the transferable part.** Separating `not findings` from `not
is_stale` by NAME needs a list of findings-ish words — the instrument the eighteenth note warns
against, because a rule needing an exemption list has the wrong population. Resolving the negand to a
list literal, comprehension, type annotation or `.append()` call needs no list. Not swept here
because 18 judgements is a sweep of its own and the table above is what one costs — *a rule demanding
18 edits gets abandoned halfway and leaves the tree half-declared*, COURT-SPLIT again.

**A THIRD category turned up when the sites were actually read, and it invalidated two of the three
this file first named as live.** Where the negand is computed against a FIXED population, "empty"
can only mean "all present" and there is no coverage question at all: `cde.complete` diffs against
the constant `CORE_REQS`, so an empty project reports all three missing. And where the negand is the
subject's OWN list rather than a scan's findings, empty means nothing is blocking it:
`px.ready = not blockers` is per-activity. One of the three was real — `docmanager.complete`, where
an unvalidated `phase` query parameter reached a checklist that returns `[]` for a phase it does not
know, so `?phase=NONSENSE` answered `complete: true`. *Three sites were named from their names, in
the paragraph that corrects a name-versus-structure error.* The structural split above separates
collection from scalar; it does NOT separate a findings list from a fixed-population diff, and
nothing short of reading each site does.

**And measuring this one found a SCOPE gap in the gate it extends.** `test_verdict_coverage.py` scans
`HERE / "src" / "aec_api"` only, so every subset verdict in `services/data/src/aec_data` — where the
IFC engines live — is outside its population: **6 of 14** (`qto.estimated`, `roundtrip.fidelity_ok`,
`adjacency.satisfied` twice, `adjacency.forbidden_ok`, `ifcpatch_lib.convertible`). That is 43% of
the population it would have if it looked, and `roundtrip.fidelity_ok` — flipped by this item — is
one of them, so the repair is covered HERE and not there. *A gate's root is a question about where
somebody stood*, which `test_schema_types_agree.py` paid for in the same words. Widening it is its own
change with its own consumer fixes, not a line to slip into this one; the number is the handover.
**This gate walks `git ls-files`, so it does cover `services/data`** — which is why the count above is
known at all.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MARKER = "EMPTY-IS-CLEAN:"
#: Trees whose Python is not ours to rule on.
SKIP = ("/vendor/", "integrations/pyrevit")

_fails: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        _fails.append(label)


# ─────────────────────────── the two functions, kept apart on purpose ────────────────────────────
# `is_all_negated` decides what to LOOK at; `verdict` decides what to REPORT. They are separate so
# each can be mutated directly — `test_unique_read_guard.py`'s first draft asserted only that the
# analyser still REPORTED a site, so a mutation routing every site to "safe" passed. Reporting a
# site and classifying it are two different questions.

def is_all_negated(value: ast.expr, min_negated: int = 2) -> bool:
    """`not A and not B …` with no other operand kind — the form with no presence guard.

    A `bool(<name>)` or plain-truthiness operand puts the value in `test_verdict_coverage.py`'s
    population instead, which is where a guarded verdict belongs; it must NOT also be reported here
    or the two gates would both rule on one site and neither would own it.
    """
    if not (isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And)):
        return False
    negated = 0
    for part in value.values:
        if isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.Not):
            negated += 1
        else:
            return False          # a plain, Compare or Call operand — not this gate's shape
    return negated >= min_negated


def declared_reason(lines: list[str], lineno: int) -> str | None:
    """The `EMPTY-IS-CLEAN:` reason in the comment block directly above line `lineno`, or None.

    Walks UPWARD through contiguous `#` lines only. Anchored on the key's own line rather than
    searching the enclosing function, because a marker three screens away would let one declaration
    bless every later verdict in the same `return` — which is an exemption list wearing a comment's
    clothes.
    """
    i = lineno - 2                                    # lineno is 1-based; start on the line above
    block: list[str] = []
    while i >= 0 and lines[i].lstrip().startswith("#"):
        block.append(lines[i].lstrip().lstrip("#").strip())
        i -= 1
    for text in block:
        if MARKER in text:
            reason = text.split(MARKER, 1)[1].strip()
            return reason or None                     # a bare marker with no reason is not a reason
    # ...and a marker may sit anywhere in the block, including above the sentence that explains it
    joined = " ".join(reversed(block))
    if MARKER in joined:
        reason = joined.split(MARKER, 1)[1].strip()
        return reason or None
    return None


def verdict(reason: str | None) -> str:
    """OK when the site declares why an empty population is clean; OPEN otherwise.

    Separate from the walk so a mutation can be applied to the classification alone.
    """
    return "ok" if reason else "open"


def sites(source: str) -> list[tuple[str, int, str, str | None]]:
    """`(key, lineno, expr, declared reason)` for every all-negated dict value in `source`.

    Raises on a syntax error rather than returning nothing: a file this cannot parse is a file this
    has no opinion about, and silently having no opinion is how a population shrinks unnoticed.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            if is_all_negated(v):
                out.append((k.value, k.lineno, ast.unparse(v), declared_reason(lines, k.lineno)))
    return out


# ─────────────────── self-tests: these run BEFORE any verdict about the tree ─────────────────────
# Frozen fixtures, not `git show`. `test_gap_records.py` failed closed on every CI build because its
# replay read history, and CI's checkout is shallow — a proof-of-reach that depends on the depth of
# somebody's clone is not a proof.

PRE_FIX_NAVIGABLE = '''
def graph(db, pid):
    return {
        "sheet_count": len(sheets),
        "detail_count": len(targets),
        "reference_count": len(edges) + len(dangling),
        "dangling": dangling,
        "orphans": orphans,
        "unparseable": unparseable,
        # a set is navigable when every callout resolves AND every detail is reachable
        "navigable": not dangling and not orphans and not unparseable,
    }
'''

DECLARED = '''
def f():
    return {
        # EMPTY-IS-CLEAN: nothing to solve IS solved; flipping this would false-alarm on a sketch
        # that carries no locks at all.
        "solved": not conflicts and not violations,
    }
'''

BARE_MARKER = '''
def f():
    return {
        # EMPTY-IS-CLEAN:
        "solved": not conflicts and not violations,
    }
'''

GUARDED_PLAIN = '''
def f():
    return {"navigable": assessed and not dangling and not orphans}
'''

GUARDED_BOOL = '''
def f():
    return {"fully_reconciled": bool(matched) and not actuals_only and not uncoded}
'''

pre = sites(PRE_FIX_NAVIGABLE)
check("the walk re-finds the shipped defect — pre-fix `navigable`, frozen here",
      [(s[0], verdict(s[3])) for s in pre] == [("navigable", "open")],
      f"{[(s[0], verdict(s[3])) for s in pre]}")
check("  ...and reports it OPEN rather than merely finding it",
      bool(pre) and verdict(pre[0][3]) == "open")

dec = sites(DECLARED)
check("a declared site is accepted, and the REASON is what accepts it",
      [(s[0], verdict(s[3])) for s in dec] == [("solved", "ok")]
      and "false-alarm" in (dec[0][3] or ""),
      f"reason={dec[0][3]!r}" if dec else "no site parsed")

bare = sites(BARE_MARKER)
check("  a bare marker with NO reason is not a declaration",
      [(s[0], verdict(s[3])) for s in bare] == [("solved", "open")],
      f"{[(s[0], verdict(s[3])) for s in bare]}")

check("a presence-GUARDED verdict is out of this population entirely — `test_verdict_coverage` owns it",
      sites(GUARDED_PLAIN) == [] and sites(GUARDED_BOOL) == [],
      f"plain={sites(GUARDED_PLAIN)} bool={sites(GUARDED_BOOL)}")

# MUTATION, applied to `verdict` alone: if the classification ignored the declaration, the frozen
# pre-fix site and the declared site would be indistinguishable. Asserting that they differ is what
# makes the two checks above a pair rather than one check written twice.
check("  the declaration CHANGES the classification — mutate `verdict` and these collapse",
      verdict(dec[0][3]) != verdict(pre[0][3]) if (dec and pre) else False)

check("the ≥2 threshold is the measured one — a single negated operand is a different shape",
      is_all_negated(ast.parse("{'k': not a and not b}", mode="eval").body.values[0]) is True
      and is_all_negated(ast.parse("{'k': not a}", mode="eval").body.values[0]) is False)

if _fails:
    print(f"\nnegated_verdict: SELF-TESTS FAILED — {_fails}; no verdict about the tree is printed, "
          "because a walk that cannot re-find the defect it was written for is evidence of nothing")
    sys.exit(1)

# ───────────────────────────────── the tree ──────────────────────────────────────────────────────
tracked = [f for f in subprocess.run(
    ["git", "-C", str(ROOT), "ls-files", "-z", "*.py"],
    capture_output=True, text=True, check=True).stdout.split("\0") if f]
# NUL-separated: a tracked path containing a space made the first draft of this measurement try to
# parse `/home/user/massing/in`. It raised rather than miscounting, which is the forgiving direction.
check("the file list is non-empty, or every check below passes vacuously", len(tracked) > 500,
      f"{len(tracked)} tracked .py file(s)")

found: list[tuple[str, str, int, str, str | None]] = []
unparsed: list[str] = []
for rel in tracked:
    if any(s in rel for s in SKIP):
        continue
    try:
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        unparsed.append(rel)
        continue
    try:
        for key, lineno, expr, reason in sites(src):
            found.append((rel, key, lineno, expr, reason))
    except SyntaxError:
        unparsed.append(rel)

# FAIL CLOSED. A file this cannot read is a file it has no opinion about, and the two blind spots in
# `CLAUDE.md`'s seventh note were both a predicate silently excluding what it could not handle.
check("every tracked .py file was parsed — an unreadable file is not an absent finding",
      not unparsed, f"unparsed: {unparsed[:5]}")

check("the population is non-empty, so a clean report is a measurement and not a broken walk",
      len(found) >= 2, f"{len(found)} all-negated verdict(s): "
      + ", ".join(f"{r.rsplit('/', 1)[-1]}::{k}" for r, k, _, _, _ in found))

open_sites = [(r, k, n) for r, k, n, _, reason in found if verdict(reason) == "open"]
check("no all-negated verdict is undeclared — guard it, or declare why empty is clean",
      not open_sites,
      "; ".join(f"{r}:{n} :: {k}" for r, k, n in open_sites)
      or f"{len(found)} site(s), all declared")

for rel, key, lineno, expr, reason in sorted(found):
    print(f"    {rel}:{lineno}  {key} = {expr}")
    print(f"        EMPTY-IS-CLEAN: {reason}")

print()
if _fails:
    print(f"negated_verdict: {len(_fails)} FAILED — {_fails}")
    sys.exit(1)
print(f"negated_verdict: all checks passed — {len(found)} all-negated verdict(s), every one carrying "
      f"a declared reason why an empty population is clean. Three siblings were FLIPPED rather than "
      f"declared (detail_refs.navigable, fin_ingest.fully_reconciled, roundtrip.fidelity_ok) and have "
      f"left this population by acquiring a guard. The bare single `not X` dict value is NOT covered "
      f"here: 36 syntactically, of which 24 have a COLLECTION negand and 18 of those need a "
      f"judgement — the docstring has the split and why a syntactic count is not a defect count.")
