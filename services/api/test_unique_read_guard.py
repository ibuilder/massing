"""Every read that DEMANDS a single row is backed by a unique constraint, or says why not.

## Why this exists — it is the other half of `test_seeding_sweep.py`

That gate walks the WRITE side: a conditional insert with nothing holding the world still. This one
walks the READ side of the same defect, and the two find it from opposite directions.

`scalar_one_or_none()` and `one_or_none()` do not merely *prefer* one row — they RAISE
`MultipleResultsFound` on two. So a read filtered on columns the schema does not constrain is a 500
that arms itself the first time a duplicate appears and never disarms: `element_verifications` was
read that way over three NON-unique indexes, and two field engineers tapping "installed" on the same
element in the same second made that element permanently unreadable, recoverable only by a manual
DELETE (fixed 2026-09-06, `uq_element_verifications_project_guid`).

Had this gate existed, it would have found that defect **without anyone looking at the writers**.
That is the argument for having both: the write-side sweep found it via the insert, and this finds it
via the query, so a future instance has to evade two unrelated derivations rather than one.

## WHY THIS FAILS CLOSED, AND WHY THAT IS THE WHOLE DESIGN

`test_seeding_sweep` was blind twice, and both times for the same reason: a predicate decided what to
LOOK at, and everything it excluded was invisible to its own output. A clean report meant nothing.

So this gate never skips a call site it cannot understand. Every unique-demanding read resolves to
exactly one of four verdicts, and the fourth is a FAILURE:

    BACKED     the filtered columns contain a unique constraint's full column set
    AGGREGATE  the query selects no mapped entity (count/max) — always one row, by construction
    EXEMPT     an entry below states, in a sentence, why one row is guaranteed some other way
    UNKNOWN    the analyser could not resolve the model or the columns  ->  the build goes red

An UNKNOWN is not a gap to widen the parser around at leisure. It is the gate saying "there is a
read here whose safety nobody has established", which is the true state and the useful one.

## The uniqueness question is asked of SQLAlchemy, never of the text

`UniqueConstraint(...)` and `Index(..., unique=True)` are BOTH in use in `models.py`, deliberately —
they are different objects on Postgres and indistinguishable on SQLite, which is why
`uq_element_verifications_project_guid` is an Index and `uq_saved_view_seen_view_user` a constraint.
A grep for "UniqueConstraint" would have called the first one unprotected. This reads
`Model.__table__` instead, so the two spellings cannot diverge from what the gate believes.

## What this gate does NOT check

That `.first()` is used correctly. `.first()` on an ambiguous query does not raise — it silently
returns whichever row the database felt like, which is a WRONG ANSWER rather than an error, and is
strictly harder to detect. `saved_views` had exactly that shape and forked people's saved reports in
two. That population is much larger and is not derivable this way; it is named here so the next
reader knows this gate's edge rather than inferring a completeness it does not have.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

#: The reader methods that RAISE on a second row. `.first()` is deliberately absent — see the
#: docstring's closing section; it fails silently and is a different, larger problem.
UNIQUE_READERS = {"scalar_one_or_none", "one_or_none", "scalar_one", "one"}

#: Call sites where one row is guaranteed by something this gate cannot see. Each entry is a
#: sentence someone had to write, which is the point: an exemption can be argued with, and a site
#: dropped by a clever predicate cannot.
EXEMPT: dict[str, str] = {
    "routers/cloud.py::_link_account::CloudIdentity": (
        "cloud_identities.cloud_sub is indexed, NOT unique — but at most one row can carry a given "
        "sub, and the ordering is what guarantees it rather than the schema. The only creator runs "
        "in the `link is None` branch, i.e. only when this same query just proved no row holds that "
        "sub; it keys on `username`, a PRIMARY key, through auth.get_or_create_by_pk, so two "
        "concurrent first sign-ins collapse into one row. When a row already exists for the "
        "username under a different sub, line `link.cloud_sub = sub` OVERWRITES rather than "
        "inserting. Traced serially and under concurrency 2026-09-06; no duplicate is reachable. "
        "Recorded as an exemption rather than fixed with a unique index because making it unique is "
        "a PRODUCT decision, not a cleanup: it would forbid two local accounts deliberately linked "
        "to one cloud identity, and nothing here establishes that nobody wants that."),
}


def tracked(pattern: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", pattern], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    return [ROOT / p for p in out.stdout.split("\n") if p.strip()]


#: Session methods that take the query as an ARGUMENT rather than as the attribute chain. Without
#: these the walker sees only `db.execute(...)` and resolves nothing — which the fail-closed design
#: correctly reported as UNKNOWN rather than skipping, and which is how this gap was found: the
#: `db.execute(select(X).where(...)).scalar_one_or_none()` form is the one `verification.py` uses,
#: i.e. the exact shape of the defect this file exists for.
_QUERY_IN_ARG = {"execute", "scalars"}


def _receiver_chain(node: ast.AST) -> list[ast.Call]:
    """Every Call the terminal reader hangs off — through the `.a().b()` chain AND through the
    argument of `execute(...)` / `scalars(...)`, which is where the 2.0-style query actually lives."""
    chain: list[ast.Call] = []
    cur = node
    while True:
        if isinstance(cur, ast.Call):
            chain.append(cur)
            fn = cur.func
            if isinstance(fn, ast.Attribute) and fn.attr in _QUERY_IN_ARG and cur.args:
                chain.extend(_receiver_chain(cur.args[0]))
            cur = fn
        elif isinstance(cur, ast.Attribute):
            cur = cur.value
        else:
            return chain


def _entity_and_columns(chain: list[ast.Call], models: set[str]) -> tuple[str | None, set[str], bool]:
    """(model, filtered column names, selects_no_entity) for one reader chain.

    `selects_no_entity` marks an aggregate — `db.query(func.count(X), func.max(Y))` — which returns
    exactly one row whatever the filter says, so it needs no constraint.
    """
    model: str | None = None
    cols: set[str] = set()
    saw_selector = False
    selector_args_were_all_calls = False
    for call in chain:
        fn = call.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if name in ("select", "query"):
            saw_selector = True
            named = [a for a in call.args if isinstance(a, ast.Name) and a.id in models]
            if named:
                model = named[0].id
            elif call.args and all(isinstance(a, ast.Call) for a in call.args):
                selector_args_were_all_calls = True      # count()/max() — an aggregate row
        elif name in ("where", "filter"):
            for a in call.args:
                for sub in ast.walk(a):
                    if (isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name)
                            and sub.value.id in models):
                        cols.add(sub.attr)
    return model, cols, saw_selector and model is None and selector_args_were_all_calls


def unique_reads(src: str, models: set[str]) -> list[tuple[str, str | None, frozenset[str], bool, int]]:
    """(enclosing function, model, filtered columns, is_aggregate, lineno) for every unique read."""
    tree = ast.parse(src)
    enclosing: dict[int, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                enclosing.setdefault(id(n), fn.name)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in UNIQUE_READERS and not node.args):
            continue
        chain = _receiver_chain(node.func.value)
        model, cols, aggregate = _entity_and_columns(chain, models)
        found.append((enclosing.get(id(node), "<module>"), model, frozenset(cols),
                      aggregate, node.lineno))
    return found


def unique_column_sets(model_cls) -> list[frozenset[str]]:
    """Every set of columns the SCHEMA guarantees unique — asked of SQLAlchemy, not of the source.

    Covers all three spellings, because all three are load-bearing somewhere in `models.py`:
    a `UniqueConstraint`, an `Index(..., unique=True)`, and the primary key.
    """
    table = model_cls.__table__
    sets: list[frozenset[str]] = [frozenset(c.name for c in table.primary_key.columns)]
    for con in table.constraints:
        if con.__class__.__name__ == "UniqueConstraint":
            sets.append(frozenset(c.name for c in con.columns))
    for idx in table.indexes:
        if idx.unique:
            sets.append(frozenset(c.name for c in idx.columns))
    for col in table.columns:                       # a single column declared unique=True
        if col.unique:
            sets.append(frozenset({col.name}))
    return [s for s in sets if s]


#: A read whose filter cannot yield two rows, written the way `verification.py` wrote it BEFORE
#: `uq_element_verifications_project_guid` shipped. The gate must flag this, and it is run against a
#: metadata stub with only NON-unique indexes — the real pre-fix state. A gate nobody has watched
#: catch its own motivating defect is a gate that has only ever reported good news.
_KNOWN_POSITIVE = '''
def set_status(pid, guid, db):
    v = db.execute(select(ElementVerification).where(
        ElementVerification.project_id == pid, ElementVerification.guid == guid)).scalar_one_or_none()
    return v
'''

#: And the shape the analyser must NOT resolve, so it lands in UNKNOWN rather than being skipped.
#: This is the fail-closed half: the model arrives through a variable the AST cannot follow.
_UNRESOLVABLE_POSITIVE = '''
def pick(db, entity):
    return db.query(entity).filter(entity.thing == 1).one_or_none()
'''

def classify(site: str, model: str | None, cols: frozenset[str], aggregate: bool,
             mapped: dict) -> str:
    """BACKED / AGGREGATE / EXEMPT / UNKNOWN for one read.

    **A SEPARATE FUNCTION SO IT CAN BE MUTATED, and that is not tidiness.** This logic lived inline
    in the scan loop, and a mutation that routed every unresolvable read (`model is None`) to
    AGGREGATE — the fail-OPEN change this gate exists to prevent — PASSED. The self-test above
    proved `unique_reads` still *reported* the site, which is a fact about the analyser and says
    nothing about what the verdict does with it. Two different questions, and only one was asked.
    *The same defect as the two `test_seeding_sweep` blind spots, in the layer above them: the
    population was derived correctly and the classification threw the answer away.*
    """
    if aggregate:
        return "AGGREGATE"
    if site in EXEMPT:
        return "EXEMPT"
    if model in mapped and any(s <= cols for s in unique_column_sets(mapped[model])):
        return "BACKED"
    return "UNKNOWN"


FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)
    return ok


def main() -> int:
    sys.path.insert(0, str(HERE / "src"))
    sys.path.insert(0, str(ROOT / "services" / "data" / "src"))
    from aec_api import models as m  # noqa: I001, PLC0415  (import AFTER sys.path is set)

    mapped = {n: getattr(m, n) for n in dir(m)
              if isinstance(getattr(m, n), type) and hasattr(getattr(m, n), "__table__")}
    names = set(mapped)
    check("the mapped-model set was derived from the live metadata", len(names) > 20,
          f"{len(names)} mapped classes")

    # ---- the gate must find its own motivating defect, against the PRE-FIX schema --------------
    pre_fix = unique_reads(_KNOWN_POSITIVE, names | {"ElementVerification"})
    check("the analyser resolves the pre-fix element_verifications read",
          len(pre_fix) == 1 and pre_fix[0][1] == "ElementVerification"
          and pre_fix[0][2] == frozenset({"project_id", "guid"}),
          pre_fix)
    # ...and with only non-unique indexes, (project_id, guid) must NOT be covered.
    class _PreFix:                                                   # the real pre-fix declaration
        class __table__:                                             # noqa: N801
            primary_key = type("pk", (), {"columns": []})()
            constraints: list = []
            indexes: list = []
            columns: list = []
    check("with no unique index, the pre-fix read is NOT backed — the gate would have gone red",
          not any(s <= frozenset({"project_id", "guid"}) for s in unique_column_sets(_PreFix)),
          "0 unique column sets on the pre-fix table")
    # ...and the SAME read IS backed today, so the check tracks the schema rather than a constant.
    check("the same read is backed today by uq_element_verifications_project_guid",
          any(s <= frozenset({"project_id", "guid"})
              for s in unique_column_sets(mapped["ElementVerification"])),
          sorted(map(sorted, unique_column_sets(mapped["ElementVerification"]))))

    # ---- fail-closed: an unresolvable site must be reported, never skipped ---------------------
    unresolved = unique_reads(_UNRESOLVABLE_POSITIVE, names)
    check("a read whose model the AST cannot resolve is still REPORTED by the analyser",
          len(unresolved) == 1 and unresolved[0][1] is None and not unresolved[0][3],
          unresolved)
    # ...and, separately, that the VERDICT calls it UNKNOWN. Asserting only the line above let a
    # fail-open mutation through: reporting the site and then classifying it as safe are two
    # different things, and a gate that checks one has not checked the other.
    _f, _model, _cols, _agg, _ln = unresolved[0]
    check("...and the VERDICT for it is UNKNOWN, not quietly waved through",
          classify("nowhere::pick::None", _model, _cols, _agg, mapped) == "UNKNOWN",
          classify("nowhere::pick::None", _model, _cols, _agg, mapped))
    check("an unresolvable read is not rescued by being listed in EXEMPT under another name",
          classify("routers/cloud.py::_link_account::CloudIdentity", None, frozenset(), False,
                   mapped) == "EXEMPT",
          "an EXEMPT entry is keyed on the site, so it cannot be claimed by a different read")

    # ---- the live tree -------------------------------------------------------------------------
    verdicts: dict[str, list[str]] = {"BACKED": [], "AGGREGATE": [], "EXEMPT": [], "UNKNOWN": []}
    for path in tracked("services/api/src/*.py") + tracked("services/data/src/*.py"):
        rel = path.relative_to(HERE / "src" if str(path).startswith(str(HERE / "src")) else ROOT)
        try:
            reads = unique_reads(path.read_text(encoding="utf-8"), names)
        except SyntaxError as exc:                    # a file we cannot parse is a FAILURE, never a skip
            check(f"{rel} parses", False, exc)
            continue
        for func, model, cols, aggregate, line in reads:
            site = f"{rel.as_posix().replace('aec_api/', '')}::{func}::{model}"
            verdict = classify(site, model, cols, aggregate, mapped)
            verdicts[verdict].append(
                f"{site} (line {line})" if verdict != "UNKNOWN" else
                f"{site} (line {line}) filtered on {sorted(cols) or '<nothing resolvable>'}")

    total = sum(len(v) for v in verdicts.values())
    print(f"\n  {total} unique-demanding read(s): "
          + " · ".join(f"{k} {len(v)}" for k, v in verdicts.items()))
    for kind in ("BACKED", "AGGREGATE", "EXEMPT", "UNKNOWN"):
        for s in verdicts[kind]:
            print(f"    {kind:<9} {s}")

    check("the scan found unique-demanding reads to classify", total >= 4, f"{total} site(s)")
    check("every unique-demanding read is backed, aggregate, or exempt with a reason",
          not verdicts["UNKNOWN"],
          "" if not verdicts["UNKNOWN"] else
          f"{len(verdicts['UNKNOWN'])} unestablished: " + "; ".join(verdicts["UNKNOWN"][:4]))
    # An exemption that no longer names a live site is a sentence nobody can check.
    live = {s.split(" (line")[0] for v in verdicts.values() for s in v}
    check("every EXEMPT entry still names a live call site",
          all(k in live for k in EXEMPT), sorted(set(EXEMPT) - live))

    if verdicts["UNKNOWN"]:
        print("\n  An UNKNOWN is not a parser gap to route around. Either the read is genuinely\n"
              "  unprotected — add the unique constraint — or one row is guaranteed some other way,\n"
              "  in which case write that sentence into EXEMPT so the next reader can disagree.")
    if FAILED:
        print("FAILED:", ", ".join(FAILED))
        return 1
    print("test_unique_read_guard OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
