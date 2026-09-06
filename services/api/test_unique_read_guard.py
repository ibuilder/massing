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

**And the first version of this file failed closed in its verdicts while failing OPEN in its
analysis — two holes, both found in review on the day it shipped.** The filter's columns were
collected with `ast.walk`, which unions an OR's two branches into one set: `where(or_(a == 1,
b == 2))` reported `{a, b}`, so a unique key on `(a, b)` made a genuinely two-row read look BACKED.
And "the selector's arguments are all `ast.Call`" was read as "this is an aggregate", so
`db.query(func.lower(X))` was exempted from the gate entirely. *Both holes are the same mistake in
different clothes: answering a question about MEANING with a test of SHAPE.* Neither could ever have
been caught by a clean report — the verdicts they produced were BACKED and AGGREGATE, which is what
a healthy tree looks like. `_OR_PREDICATE_POSITIVE`, `_OR_OPERATOR_POSITIVE` and
`_SCALAR_FUNC_POSITIVE` below were each run against the pre-fix analyser and each came back safe.

**And the FIX for those had a third hole, found by the same review.** Narrowing the collector to
AND-shaped `==` still accepted `X.a == X.b` — an equality whose right side is another mapped column.
That correlates two columns instead of pinning either, so `where(EV.project_id == EV.guid,
EV.guid == EV.project_id)` assembled the whole composite key out of predicates restricting nothing,
and came back BACKED. `_COLUMN_TO_COLUMN_POSITIVE` covers it, and the rule is now that the
comparator must contain no mapped attribute at all. *The lesson is not about SQLAlchemy: **a
narrowed rule is not a sound rule**, and the second draft of a fail-closed check earns no more trust
than the first — it was written by someone who had just been wrong about the same function.*

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
two. It is named here so the next reader knows this gate's edge rather than inferring a completeness
it does not have.

**That edge has now been MEASURED rather than left as a warning, and walking it found a live defect
on the authorisation table.** 35 `.first()` sites across both service trees: 10 carry an `order_by`
or `limit` (the choice is deterministic and intended — "the latest scenario"), 2 filter on a unique
key, 8 could not be resolved to a model, and **11 were ambiguous**. Five of the eleven were
`project_members`, where `rbac.grant` is a read-decide-insert on `(project_id, user)` over two
SEPARATE non-unique indexes — so `remove_member`, which deletes `.first()`, removed one of two rows
and left the person with the project while returning 200. Fixed in `a3c7d9e4f218`; see
`services/api/test_member_role_race.py`.

**Six ambiguous sites remain and are deliberately NOT gated here** — `Topic(guid, project_id)` ×2,
`Viewpoint(guid)`, `ModelVersion(project_id, version)` ×3 — because none of them has been traced to
a reachable duplicate yet, and a gate that demands a constraint before anyone has established one is
wanted would be answering a question nobody asked. They are recorded as the next sweep axis in
`docs/roadmap.md` rather than as an `EXEMPT` entry here, because an exemption asserts safety and
nothing here has established theirs.
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


#: SQL functions that collapse any number of rows to exactly one. Named explicitly, because the
#: question "does this query return one row by construction" is answered by WHICH function was
#: called, not by the fact that A function was called. Matched on the function name only, so an
#: aliased namespace (`from sqlalchemy import func as _f`, which `bim.py` uses) still resolves.
_AGGREGATE_FUNCS = {"count", "max", "min", "sum", "avg"}


def _is_aggregate_call(node: ast.AST) -> bool:
    """`func.count(...)` / `_f.max(...)` — an aggregate. `func.lower(...)` is NOT one."""
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in _AGGREGATE_FUNCS)


def _pinned_columns(node: ast.AST, models: set[str]) -> set[str]:
    """Columns this predicate pins to a value on EVERY row it admits.

    Only AND-shaped structure and `==` comparisons count. An OR branch contributes NOTHING, because
    a row matching the other branch is not pinned by it — `where(or_(a == 1, b == 2))` admits rows
    that agree on neither column, so a unique key on `(a, b)` does not make it single-rowed.
    Anything else — `in_`, `!=`, `<`, `ilike`, a helper call — also contributes nothing, which
    leaves the site short of a full unique key and therefore UNKNOWN. That is the fail-closed
    direction on purpose: under-collecting turns the build red, over-collecting waves a defect
    through.
    """
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return set().union(*(_pinned_columns(v, models) for v in node.values))
        return set()                                     # `or` — proves nothing about any column
    if isinstance(node, ast.BinOp):                      # SQLAlchemy overloads `&` and `|`
        if isinstance(node.op, ast.BitAnd):
            return _pinned_columns(node.left, models) | _pinned_columns(node.right, models)
        return set()
    if isinstance(node, ast.Compare):
        if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
            target = node.left
            # The right-hand side must be a VALUE. `X.a == X.b` and `Topic.id == Comment.topic_id`
            # are equalities that pin nothing: they correlate two columns, and every row where the
            # two happen to agree still qualifies. Collecting `a` from those let a self-comparison
            # assemble a whole composite key out of predicates that restrict nothing. Any mapped
            # attribute anywhere in the comparator disqualifies it, which also rejects
            # `X.a == func.lower(Y.b)`.
            compares_to_a_column = any(
                isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id in models
                for n in ast.walk(node.comparators[0]))
            if (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id in models and not compares_to_a_column):
                return {target.attr}
        return set()
    if isinstance(node, ast.Call):
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if name == "and_":
            return set().union(set(), *(_pinned_columns(a, models) for a in node.args))
        return set()
    return set()


def _entity_and_columns(chain: list[ast.Call], models: set[str]) -> tuple[str | None, set[str], bool]:
    """(model, PINNED column names, selects_only_aggregates) for one reader chain.

    `selects_only_aggregates` marks `db.query(func.count(X), func.max(Y))` — one row whatever the
    filter says, so it needs no constraint. Both halves used to be answered by shape rather than by
    meaning: any `ast.Call` in the selector counted as an aggregate (so `func.lower(...)` did), and
    the filter's columns were collected with `ast.walk`, which unions an OR's two branches into one
    set that looks like a conjunction. Both errors point the same way — they make a read look SAFER
    than it is, in a gate whose entire value is that it fails closed.
    """
    model: str | None = None
    cols: set[str] = set()
    saw_selector = False
    selector_args_were_all_aggregates = False
    for call in chain:
        fn = call.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if name in ("select", "query"):
            saw_selector = True
            named = [a for a in call.args if isinstance(a, ast.Name) and a.id in models]
            if named:
                model = named[0].id
            elif call.args and all(_is_aggregate_call(a) for a in call.args):
                selector_args_were_all_aggregates = True
        elif name in ("where", "filter"):
            for a in call.args:
                cols |= _pinned_columns(a, models)
    return model, cols, saw_selector and model is None and selector_args_were_all_aggregates


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

#: An OR over the two halves of a unique key. Every column of `uq_element_verifications_project_guid`
#: appears, so a collector built on `ast.walk` reports the full key and the site is judged BACKED —
#: while the query itself admits every row of the project AND every row carrying that guid, which is
#: exactly the two-row read this gate exists to catch. Found by review on the day it shipped.
_OR_PREDICATE_POSITIVE = '''
def pick(pid, guid, db):
    return db.execute(select(ElementVerification).where(or_(
        ElementVerification.project_id == pid,
        ElementVerification.guid == guid))).scalar_one_or_none()
'''

#: The same hole in SQLAlchemy's operator spelling — `|` is a BinOp, not a BoolOp, so a fix that
#: only taught the collector about `or_(...)` would still miss this one.
_OR_OPERATOR_POSITIVE = '''
def pick(pid, guid, db):
    return db.execute(select(ElementVerification).where(
        (ElementVerification.project_id == pid) | (ElementVerification.guid == guid),
    )).scalar_one_or_none()
'''

#: Both halves of a unique key, each compared to the OTHER half rather than to a value. Every
#: column of `uq_element_verifications_project_guid` appears in an `==` inside a conjunction, which
#: is exactly the shape the fix above looks for — but the predicate admits every row whose two
#: columns happen to agree, so it does not pin either one. Found by review on the fix for the OR
#: hole: *narrowing a rule is not the same as making it sound, and the second draft of a
#: fail-closed check is no more trustworthy than the first.*
_COLUMN_TO_COLUMN_POSITIVE = '''
def pick(db):
    return db.execute(select(ElementVerification).where(
        ElementVerification.project_id == ElementVerification.guid,
        ElementVerification.guid == ElementVerification.project_id)).scalar_one_or_none()
'''

#: An ordinary scalar function in the selector. `func.lower(...)` returns one value PER ROW, so this
#: read demands uniqueness like any other — but "the selector's arguments are all calls" called it an
#: aggregate and exempted it from the whole gate.
_SCALAR_FUNC_POSITIVE = '''
def pick(name, db):
    return db.query(func.lower(Project.name)).filter(Project.name == name).one_or_none()
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
    # ---- fail-closed: neither an OR predicate nor a scalar function may look safe ---------------
    # Each of these was a live fail-OPEN hole in the first version of this file, and each is asserted
    # on the VERDICT rather than on what the analyser reported — the distinction that let the earlier
    # AGGREGATE mutation through. They are checked here, against the CURRENT schema, so they cannot
    # be satisfied by the constraint being absent.
    for label, src in (("or_(...)", _OR_PREDICATE_POSITIVE), ("the `|` operator", _OR_OPERATOR_POSITIVE)):
        (_f2, _m2, _c2, _a2, _l2), = unique_reads(src, names | {"ElementVerification"})
        check(f"an OR predicate written with {label} pins NO column, so it cannot borrow a unique key",
              _m2 == "ElementVerification" and _c2 == frozenset()
              and classify("x::pick::ElementVerification", _m2, _c2, _a2, mapped) == "UNKNOWN",
              (_m2, sorted(_c2), classify("x::pick::ElementVerification", _m2, _c2, _a2, mapped)))
    # ...and the conjunction of the SAME two columns still is backed, so the rule above narrowed the
    # collector rather than breaking it.
    (_f3, _m3, _c3, _a3, _l3), = unique_reads(_KNOWN_POSITIVE, names | {"ElementVerification"})
    check("the AND of those same two columns is still BACKED — the narrowing did not blunt the gate",
          classify("x::set_status::ElementVerification", _m3, _c3, _a3, mapped) == "BACKED",
          sorted(_c3))
    (_f5, _m5, _c5, _a5, _l5), = unique_reads(_COLUMN_TO_COLUMN_POSITIVE, names | {"ElementVerification"})
    check("an equality between two mapped COLUMNS pins neither, so it cannot assemble a unique key",
          _c5 == frozenset()
          and classify("x::pick::ElementVerification", _m5, _c5, _a5, mapped) == "UNKNOWN",
          (sorted(_c5), classify("x::pick::ElementVerification", _m5, _c5, _a5, mapped)))
    (_f4, _m4, _c4, _a4, _l4), = unique_reads(_SCALAR_FUNC_POSITIVE, names)
    check("a scalar function in the selector is NOT an aggregate and is not waved through",
          _a4 is False and classify("x::pick::None", _m4, _c4, _a4, mapped) == "UNKNOWN",
          (_a4, classify("x::pick::None", _m4, _c4, _a4, mapped)))

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
