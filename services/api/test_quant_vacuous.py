"""QUANT-VACUOUS — a quantifier verdict that is TRUE over an empty collection.

`recipe_log.export()` answered `"replayable": all(not r["params_elided"] for r in entries)`, and
`all()` over an empty sequence is `True` — so a project that had never been authored reported
*replayable*. That is NEGATED-VERDICT's class, and **no gate in this tree could see it**:

* `services/api/test_negated_verdict.py` requires `ast.BoolOp` with `And`, and explicitly refuses a
  `Call` operand. A bare `all(…)` is a Call.
* `services/api/test_verdict_coverage.py` requires a presence guard to be PRESENT — `bool(X) and
  all(…)` — in order to look at the site at all. The missing guard IS the defect.

*A predicate that decides what to LOOK at is more dangerous than one that decides what to report*,
for the fifth time in these gates, and here the two most closely related gates excluded the shape
from opposite directions: one for being a Call, the other for lacking the thing it was missing.

## The sweep is a CLEAN NEGATIVE on symptoms, and that is the measurement rather than a hope

Nine quantifier dict-verdicts exist tree-wide; six are the vacuously-true form. One was the live
defect and is fixed. **Every one of the other five is structurally non-empty, traced to the line that
guarantees it** — which is why four of them carry a declaration rather than a flipped verdict:

| site | why empty cannot happen |
|---|---|
| `cde.exchange_acceptance.completeness` | the iterable is a literal 3-tuple — **exempt by DERIVATION**, no declaration and no name list |
| `mep_sizing.systems[].all_within_budget` | `rs` filters `runs` for a name taken from a set comprehension over `runs`, so at least one row matches |
| `edit.allocate_program.all_satisfied` | `allocation` is built from `asks`, built from `program`, which is validated non-empty with a `raise` |
| `underwrite.flag_returns.ok` | the branch above appends an info flag when `flags` is empty |
| `financials.…balance_sheet.balanced` | `hold_years = max(1, …)`, so the loop always appends |

*The fix for a vacuous truth is not always to make it false* — NEGATED-VERDICT's own conclusion, and
flipping any of these five would report a false alarm on correct input, which is how a check teaches
people to ignore it. So the deliverable here is the GATE: the shape that shipped a live defect now
reds the build unless the author either guards it or writes down why empty is clean.

## Two rules, and the one that costs nothing is the one worth naming

**The literal-iterable exemption is derived.** `cde.completeness` iterates `('info_type',
'discipline', 'originator')`, which cannot be empty, and a gate demanding a declaration there would
be demanding prose about an impossibility. Resolving the comprehension's iterable to a non-empty
literal costs no exemption list, and *an exemption list is where the next instance hides* —
COURT-SPLIT's lesson, applied before the list could be started. A comprehension with more than one
generator is NOT exempted, because the second iterable may be the empty one.

**`any(…)` alone is not in the population, and `not all(…)` is not either.** Both are FALSE over
empty input, so the vacuity question does not arise — `e57.has_color` and `schema_diag.truncated` are
correct as written. Admitting them would have doubled the population with sites that cannot carry the
defect, which is the widening this file's siblings keep paying for.

## The marker is shared with `test_negated_verdict.py` ON PURPOSE

Both gates ask the same question of different syntax, so a site moving between their populations must
not need its declaration rewritten. That sharing is asserted below by reading the other file: if it
renames its marker, this gate reds rather than silently accepting a declaration nobody writes any
more.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_quant_vacuous.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
#: Shared with `test_negated_verdict.py` — see the header. Asserted to still be its marker too.
MARKER = "EMPTY-IS-CLEAN:"
NEGATED_GATE = HERE / "test_negated_verdict.py"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# ---------------------------------------------------------------------------------------------
# THE SHAPE


def _quant_call(node: ast.expr, fn: str) -> ast.Call | None:
    """`fn(<comprehension>)` with exactly one argument, else None.

    The single-argument demand is not cosmetic: `all(x for x in a, ...)` is not valid, but
    `all(map(...))` is, and a `map` argument has no iterable this file can resolve. Refusing it here
    means such a site reaches the UNRESOLVED report rather than being silently exempted.
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == fn):
        return None
    return node if len(node.args) == 1 and not node.keywords else None


def vacuous_quantifier(node: ast.expr) -> ast.Call | None:
    """The `all(…)` or `not any(…)` in `node` — the two forms that are TRUE over empty input.

    `any(…)` and `not all(…)` are deliberately absent: both are FALSE over empty input, so they
    cannot carry this defect, and admitting them doubles the population with correct code.
    """
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _quant_call(node.operand, "any")
    return _quant_call(node, "all")


def is_presence_guard(node: ast.expr) -> bool:
    """`bool(x)` or a bare truthiness operand — the author writing down that the subset can be empty.

    A `Compare` is NOT a guard: `history == "complete"` is a condition about the value, not about
    whether there is one, and accepting it would bless the shape this gate exists for.
    """
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool":
        return bool(node.args)
    return isinstance(node, (ast.Name, ast.Attribute, ast.Subscript))


def literal_nonempty(it: ast.expr) -> bool:
    """Can this iterable be proved non-empty from the source alone?"""
    if isinstance(it, (ast.Tuple, ast.List, ast.Set)):
        return len(it.elts) > 0
    if isinstance(it, ast.Constant) and isinstance(it.value, str):
        return len(it.value) > 0
    return False


def over_literal(call: ast.Call) -> bool:
    """The quantifier iterates a provably non-empty literal — exempt by derivation, not by name.

    A comprehension with more than one `for` is refused: the SECOND iterable may be the empty one,
    and `all(x for a in ('p',) for x in a.items)` is vacuous on an empty `items`.
    """
    arg = call.args[0]
    if not isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return False
    if len(arg.generators) != 1:
        return False
    return literal_nonempty(arg.generators[0].iter)


def comprehension_arg(call: ast.Call) -> bool:
    """Is the quantifier's argument a comprehension at all? `all(map(f, xs))` is not."""
    return isinstance(call.args[0], (ast.GeneratorExp, ast.ListComp, ast.SetComp))


def classify(value: ast.expr) -> tuple[ast.Call, bool] | None:
    """`(quantifier, guarded)` when `value` is a vacuously-true quantifier verdict, else None."""
    if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And):
        found = None
        for part in value.values:
            q = vacuous_quantifier(part)
            if q is not None:
                found = q
                break
        if found is None:
            return None
        return found, any(is_presence_guard(part) for part in value.values)
    q = vacuous_quantifier(value)
    return (q, False) if q is not None else None


def declared_reason(lines: list[str], lineno: int) -> str | None:
    """The `EMPTY-IS-CLEAN:` reason in the comment block directly above line `lineno`, or None.

    Deliberately identical in behaviour to `test_negated_verdict.declared_reason`, including the
    refusal of a bare marker with no reason: the two gates ask one question of two syntaxes, and a
    site that moves between them must not need its declaration rewritten.
    """
    i = lineno - 2
    block: list[str] = []
    while i >= 0 and lines[i].lstrip().startswith("#"):
        block.append(lines[i].lstrip().lstrip("#").strip())
        i -= 1
    joined = " ".join(reversed(block))
    if MARKER in joined:
        return joined.split(MARKER, 1)[1].strip() or None
    return None


def verdict(guarded: bool, reason: str | None) -> str:
    """OK when guarded or declared; OPEN otherwise. Separate so a mutation can hit it alone.

    `test_unique_read_guard.py` paid for this separation: its self-test asserted the analyser still
    REPORTED a site, so a mutation routing every site to "safe" passed. Reporting a site and
    classifying it are two different questions.
    """
    return "ok" if (guarded or reason) else "open"


def sites(source: str, filename: str = "<unknown>") -> list[dict]:
    """Every vacuously-true quantifier dict-verdict in `source`.

    `filename` is passed through to `ast.parse` only so that a `SyntaxWarning` from a file with a bad
    escape sequence names the FILE. Two such warnings fire on this tree, and `<unknown>:245` is a
    line number with no file attached — unactionable noise sitting directly above a verdict.
    """
    tree = ast.parse(source, filename=filename)
    lines = source.splitlines()
    out: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for k, v in zip(node.keys, node.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            hit = classify(v)
            if hit is None:
                continue
            quant, guarded = hit
            if not comprehension_arg(quant):
                out.append({"key": k.value, "lineno": k.lineno, "expr": ast.unparse(v),
                            "state": "unresolved", "reason": None})
                continue
            if over_literal(quant):
                continue                        # exempt by derivation — see `over_literal`
            reason = declared_reason(lines, k.lineno)
            out.append({"key": k.value, "lineno": k.lineno, "expr": ast.unparse(v),
                        "state": verdict(guarded, reason), "reason": reason})
    return out


def tracked_relpaths() -> list[str]:
    """EVERY tracked `.py` in the repository, NUL-separated.

    **No root list, and that is the repair for two defects the first draft had** — both found by a
    dry run against the live tree before this file existed, which is the only reason they are a note
    rather than a shipped gate:

    * It named `services/converter` as a Python source root. That directory is **JavaScript** — six
      tracked files, `.mjs` and `.json`, zero `.py` — so the precondition "every root contributed
      files" could never pass. *A root asserted to contribute, that cannot*, is the confident-number
      failure `test_scratch_ignored` paid for twice.
    * Its per-root count was keyed on `Path.name`, and `services/api/src` and `services/data/src`
      share the name `src` — so the dict held two entries for three roots and one root's count was
      silently overwritten by another's.

    Both disappear rather than get fixed, because the root list was never load-bearing: **measured
    over all 1,438 tracked `.py`, every site is under `services/api/src` or `services/data/src` and
    there are ZERO elsewhere.** Scanning everything therefore costs nothing and removes a predicate
    that decides what to look at. All 1,438 also parse as Python 3 — including the three IronPython
    2.7 scripts under `integrations/pyrevit/` — so no exclusion list is needed for that either.

    `-z` is not a detail. `git ls-files` output split on whitespace turns the three pyrevit paths
    that contain SPACES ("Open in Massing.pushbutton") into five phantom paths and loses the real
    ones: 1,443 "files" where there are 1,438, three of them unreadable and the rest invented. The
    canary below is derived from that — it asserts a space-containing path is in the population,
    rather than asserting the count.
    """
    raw = subprocess.run(["git", "ls-files", "-z", "*.py"], cwd=ROOT,
                         capture_output=True, check=True).stdout
    return sorted(r for r in raw.decode("utf-8").split("\0") if r)


# ---------------------------------------------------------------------------------------------
# SELF-TESTS — every one runs BEFORE the verdict, because a walk that finds nothing reads exactly
# like a clean tree.

#: The verdict as `recipe_log.export()` shipped it, frozen here rather than fetched. A proof-of-reach
#: that reads history depends on the depth of somebody's clone, which `test_gap_records` had to learn
#: when its `git show` worked locally and failed in CI's shallow checkout.
PRE_FIX = '''
def export(pid):
    d = _load(pid)
    return {
        "count": len(d["entries"]), "entries": d["entries"],
        "replayable": all(not r.get("params_elided") for r in d["entries"]),
    }
'''
_pre = sites(PRE_FIX)
check("PROOF OF REACH: the shipped pre-fix `replayable` is found and reported OPEN",
      [s["key"] for s in _pre if s["state"] == "open"] == ["replayable"],
      f"found {_pre}")

#: And its repair is clean — `bool(entries)` is the guard, so `test_verdict_coverage` owns it from
#: here. Asserted because a gate that reds on the FIX is worse than one that misses the defect.
POST_FIX = '''
def export(pid):
    return {"replayable": bool(entries) and not elided and history == "complete"}
'''
check("  ...and its repair is not reported", sites(POST_FIX) == [], sites(POST_FIX))

GUARDED = '''
def f():
    return {"clean": bool(rows) and all(r["ok"] for r in rows)}
'''
check("a guarded quantifier is accepted", [s["state"] for s in sites(GUARDED)] == ["ok"],
      sites(GUARDED))

LITERAL = '''
def f():
    return {"complete": all((d.get(x) or "").strip() for x in ("a", "b", "c"))}
'''
VARIABLE = '''
def f():
    return {"complete": all((d.get(x) or "").strip() for x in fields)}
'''
check("the literal-iterable exemption is DERIVED, not a name list",
      sites(LITERAL) == [] and [s["state"] for s in sites(VARIABLE)] == ["open"],
      f"literal={sites(LITERAL)} variable={sites(VARIABLE)}")

TWO_FOR = '''
def f():
    return {"ok": all(x for a in ("p",) for x in a.items)}
'''
check("  ...and a two-generator comprehension is NOT exempted — the second iterable may be empty",
      [s["state"] for s in sites(TWO_FOR)] == ["open"], sites(TWO_FOR))

FALSE_ON_EMPTY = '''
def f():
    return {"has_any": any(s.flag for s in scans), "none_ok": not all(s.flag for s in scans)}
'''
check("`any(...)` and `not all(...)` are outside the population — both are FALSE over empty input",
      sites(FALSE_ON_EMPTY) == [], sites(FALSE_ON_EMPTY))

NOT_ANY = '''
def f():
    return {"ok": not any(f["level"] == "high" for f in flags)}
'''
check("`not any(...)` IS in the population — it is TRUE over empty input",
      [s["state"] for s in sites(NOT_ANY)] == ["open"], sites(NOT_ANY))

DECLARED = '''
def f():
    return {
        # EMPTY-IS-CLEAN: `flags` cannot be empty — the branch above appends an info flag.
        "ok": not any(f["level"] == "high" for f in flags),
    }
'''
BARE_MARKER = '''
def f():
    return {
        # EMPTY-IS-CLEAN:
        "ok": not any(f["level"] == "high" for f in flags),
    }
'''
check("a declaration with a reason is accepted…", [s["state"] for s in sites(DECLARED)] == ["ok"],
      sites(DECLARED))
check("  …and a bare marker with no reason is not a reason",
      [s["state"] for s in sites(BARE_MARKER)] == ["open"], sites(BARE_MARKER))

UNRESOLVED = '''
def f():
    return {"ok": all(map(bool, rows))}
'''
check("a quantifier this file cannot resolve is reported UNRESOLVED, never exempted",
      [s["state"] for s in sites(UNRESOLVED)] == ["unresolved"], sites(UNRESOLVED))

check("the shared marker is still `test_negated_verdict.py`'s marker too",
      f'MARKER = "{MARKER}"' in NEGATED_GATE.read_text(encoding="utf-8")
      or f"MARKER = '{MARKER}'" in NEGATED_GATE.read_text(encoding="utf-8"),
      f"{NEGATED_GATE.name} no longer declares {MARKER!r} — the two gates ask one question of two "
      "syntaxes, and a declaration written for one must satisfy the other")

# ---------------------------------------------------------------------------------------------
# PRECONDITIONS — each is a way this file could report a clean tree while seeing nothing.

_FILES = tracked_relpaths()
check(f"the walk reaches the whole tree ({len(_FILES)} tracked .py)", len(_FILES) >= 1_400,
      f"only {len(_FILES)} tracked .py found from {ROOT} — a narrowed population reads exactly like "
      "a clean tree")

#: DERIVED from the defect, not from the count. `git ls-files` split on whitespace invents paths out
#: of the three pyrevit scripts whose directories contain spaces and loses the real ones; asserting a
#: space-containing path is PRESENT catches that, while asserting a total would pass at 1,443.
_SPACED = [r for r in _FILES if " " in r]
check(f"paths containing spaces survive the listing ({len(_SPACED)})", len(_SPACED) >= 1,
      "no space-containing path is in the population — `git ls-files` was split on whitespace, "
      "which turns one such path into several that do not exist and drops the one that does")

# ---------------------------------------------------------------------------------------------
# THE VERDICT

_ALL: list[tuple[str, dict]] = []
_BROKEN: list[tuple[str, str]] = []
for rel in _FILES:
    try:
        src = (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:       # noqa: PERF203 — collected, not swallowed
        _BROKEN.append((rel, f"unreadable: {e}"))
        continue
    try:
        for s in sites(src, rel):
            _ALL.append((rel, s))
    except SyntaxError as e:
        _BROKEN.append((rel, f"does not parse: {e}"))

# Collected and reported ONCE rather than as a check per file: 1,438 passing lines would bury the
# verdict, and the number that matters is zero. Measured at 0 today — every tracked .py parses as
# Python 3, the three IronPython 2.7 scripts included — so this is a floor, not a tolerance.
check(f"every tracked .py was read and parsed ({len(_BROKEN)} could not be)", not _BROKEN,
      "; ".join(f"{rel}: {why}" for rel, why in _BROKEN[:6])
      + " — a file this walk cannot read is a file it cannot rule on, and silence about it reads "
        "exactly like a clean one")

check(f"the population is non-empty ({len(_ALL)} quantifier verdict(s))", len(_ALL) >= 4,
      f"only {len(_ALL)} found — the rule below would be a statement about an empty population, "
      "which reads exactly like a clean tree")

_OPEN = [(rel, s) for rel, s in _ALL if s["state"] == "open"]
_UNRESOLVED = [(rel, s) for rel, s in _ALL if s["state"] == "unresolved"]

check("no quantifier verdict is vacuously true without a guard or a declaration",
      not _OPEN,
      "; ".join(f"{rel}:{s['lineno']} {s['key']!r} = {s['expr'][:90]}" for rel, s in _OPEN)
      + " — `all(...)` is True over an empty sequence and `not any(...)` is too, so this answers "
        "yes when nothing was examined. Guard it with `bool(<collection>) and ...`, after which "
        "`test_verdict_coverage.py` owns it, or write `# " + MARKER + " <reason>` above the key")

check("every quantifier argument resolved — an unresolvable one is reported, not skipped",
      not _UNRESOLVED,
      "; ".join(f"{rel}:{s['lineno']} {s['key']!r} = {s['expr'][:90]}" for rel, s in _UNRESOLVED)
      + " — the argument is not a comprehension, so this file cannot resolve its iterable. Rewrite "
        "it as a comprehension, or guard the verdict")

print()
print(f"  population ({len(_ALL)}) — measured across all {len(_FILES)} tracked .py:")
for rel, s in _ALL:
    print(f"    {s['state']:10} {rel}:{s['lineno']:<5} {s['key']}")
if FAILED:
    print(f"quant_vacuous: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"quant_vacuous: all checks passed — {len(_ALL)} quantifier verdict(s), "
      f"{sum(1 for _r, s in _ALL if s['reason'])} carrying a declaration, 0 vacuous")
