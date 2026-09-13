"""JSON-NULL-CLASS — a NULL test on a JSON column that can hold the JSON scalar `null`.

SQLAlchemy's `JSON` type persists a Python `None` as the JSON scalar `null` unless the column
declares `none_as_null=True`. That value is **not SQL NULL**, so `WHERE <json col> IS NOT NULL`
matches every row that has ever been written and `IS NULL` matches none of them — a filter that
filters nothing, silently, with no error anywhere.

The class was found by PIN-ANCHOR on `topics.anchor` / `topics.element_guids` and the register pin
columns, which now declare `none_as_null=True`. PIN-SWEEP-PGNULL then found the same distinction one
layer up, inside the migration written to clean the first one up. Twice is a class, so it is a gate.

**What this checks, and what it deliberately does not.** The population is every NULL test in
`services/api/src/aec_api`; the question asked of each is what its SUBJECT is. Three answers are
safe and one is not:

  * a column that is not `JSON` at all
  * a `JSON` column that declares `none_as_null=True` — a Python `None` becomes SQL NULL on write
  * a JSON **extraction** (`data ->> 'x'`, `json_extract(data, '$.x')`) — that is a text scalar, and
    both backends yield SQL NULL for a missing key AND for a stored JSON `null`. The extraction is
    not the column, and conflating the two would flag every register query in the tree.
  * a `JSON` column WITHOUT `none_as_null=True` — the defect.

It does **not** assert that every JSON column declares `none_as_null=True`. Measured: 588 JSON
columns in the ORM metadata, 308 without it. Turning those on is a write-behaviour change on 308
columns, not a gate, and most of them are never the subject of a NULL test — which is what makes the
reader the right place to stand.

**Its limit, named rather than left to be discovered.** A `<x>.c.<name>` subject is resolved against
the REGISTER tables, because that is what every such site in the tree is today; a `.c.` access on some
other Core table whose column name happens to match a register's would be judged by the register's
declaration. The judgement errs safe — a name that lacks `none_as_null=True` on any register is
treated as lacking it everywhere — but it is a resolution by name, not by table, and a site that
needs the distinction should be exempted with the reason rather than trusted to it.

**It fails CLOSED.** A subject the analyser cannot resolve is reported UNKNOWN and reds the build,
because the two blind spots `test_seeding_sweep.py` records were both a predicate quietly deciding
what to LOOK at. An UNKNOWN is cleared by reading the site and adding it to `EXEMPT` with the reason
— never by widening the resolver until the site disappears from its own output.

Run: `PYTHONPATH=src:../data/src python test_json_null_filter.py`
"""
from __future__ import annotations

import ast
import pathlib
import sys

import sqlalchemy as sa

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_api import models, modules_query, modules_registry  # noqa: E402

modules_registry.load_registry()

SRC = pathlib.Path("src/aec_api")

#: `.is_(None)` and its spellings. `== None` / `!= None` are included because SQLAlchemy overloads
#: them into the same SQL, and a future author writing the shorter form must not fall out of the
#: population by doing so.
_NULL_METHODS = {"is_", "isnot", "is_not"}

#: Call shapes that produce a JSON EXTRACTION rather than the column itself.
_EXTRACTORS = {"_json_text", "json_extract"}

#: Sites whose subject the resolver cannot reach, each READ and cleared by hand. A site belongs here
#: only with a reason that says what the subject actually is — an entry that merely silences the
#: analyser is the failure this file's docstring warns about.
EXEMPT: dict[tuple[str, int, str], str] = {
    ("src/aec_api/modules_query.py", 163, "expr"):
        "`_field_expr` returns either `t.c[name]` for a name in SYSTEM_COLUMNS — none of which is a "
        "JSON column (assert_system_columns_are_not_json below pins that) — or `_json_text(...)`, an "
        "extraction. Neither is a bare JSON column.",
    ("src/aec_api/modules_query.py", 166, "expr"): "as line 163 — the same `_field_expr` result.",
    ("src/aec_api/modules_query.py", 368, "expr"):
        "`_display_expr`, which resolves through `_field_expr` for a plain field and through a "
        "joined label column for a reference field; neither yields a bare JSON column.",
    ("src/aec_api/pins.py", 98, "anchor_col"):
        "a parameter of `pin_where`, bound by every caller to a register `anchor` column, which "
        "declares none_as_null=True (asserted below, so this exemption cannot outlive its reason).",
    ("src/aec_api/pins.py", 98, "guids_col"):
        "a parameter of `pin_where`, bound to `element_guids`, likewise none_as_null=True.",
}


# ------------------------------------------------------------------------------------------------
# The column facts, from the metadata rather than from a list.
# ------------------------------------------------------------------------------------------------
def _json_columns() -> dict[tuple[str, str], bool]:
    """`(table, column) -> none_as_null` for every JSON column the models declare."""
    out: dict[tuple[str, str], bool] = {}
    for t in models.Base.metadata.sorted_tables:
        for c in t.columns:
            if isinstance(c.type, sa.JSON):
                out[(t.name, c.name)] = bool(getattr(c.type, "none_as_null", False))
    return out


JSON_COLS = _json_columns()
check("the metadata scan found JSON columns", len(JSON_COLS) > 50,
      f"{len(JSON_COLS)} — a derivation that collapses makes every verdict below vacuously SAFE")

#: Column name -> none_as_null, for the register tables, which share one builder. A name that is a
#: JSON column on SOME register is treated as one everywhere: `t.c.<name>` cannot say which table.
_REG_JSON: dict[str, bool] = {}
for _t in modules_registry.TABLES.values():
    for _c in _t.columns:
        if isinstance(_c.type, sa.JSON):
            _REG_JSON[_c.name] = _REG_JSON.get(_c.name, True) and bool(
                getattr(_c.type, "none_as_null", False))
check("the register scan found JSON columns", len(_REG_JSON) >= 2,
      f"{sorted(_REG_JSON)} — register tables carry at least `data` and `links`")

#: Every ORM class by name, so `Topic.labels` resolves to (topics, labels).
_MODELS = {n: o for n, o in vars(models).items()
           if isinstance(o, type) and hasattr(o, "__tablename__")}
check("the ORM classes were found", len(_MODELS) > 10, f"{len(_MODELS)} mapped classes")


# ------------------------------------------------------------------------------------------------
# THE VERDICT, as a function of its own, so a mutation can be aimed at it directly.
#
# `test_unique_read_guard.py` learned this the expensive way: its self-test asserted the analyser
# still REPORTED an unresolvable read, so a mutation routing every unresolvable read to "safe"
# PASSED. Reporting a site and classifying it are two different questions.
# ------------------------------------------------------------------------------------------------
def verdict(table: str | None, column: str | None, kind: str) -> str:
    """`SAFE` | `JSON_NULL_TEST` | `UNKNOWN` for one resolved subject.

    `kind` is how the subject was reached: "orm" (Model.attr), "register" (t.c.<name>),
    "extraction" (a `->>` / json_extract expression) or "unresolved".
    """
    if kind == "extraction":
        return "SAFE"
    if kind == "orm":
        none_as_null = JSON_COLS.get((table, column))
        if none_as_null is None:
            return "SAFE"                      # not a JSON column at all
        return "SAFE" if none_as_null else "JSON_NULL_TEST"
    if kind == "register":
        if column not in _REG_JSON:
            return "SAFE"                      # not a JSON column on any register
        return "SAFE" if _REG_JSON[column] else "JSON_NULL_TEST"
    return "UNKNOWN"


# ------------------------------------------------------------------------------------------------
# The population, and the resolution of each subject to (table, column, kind).
# ------------------------------------------------------------------------------------------------
def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _extraction_source(node) -> bool:
    """Is this expression a JSON extraction rather than a column?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in _EXTRACTORS:
                return True
            if isinstance(f, ast.Attribute) and f.attr in _EXTRACTORS:
                return True
            # `col.op("->>")(key)` — the operator is the giveaway, on either backend.
            if (isinstance(f, ast.Call) and isinstance(f.func, ast.Attribute)
                    and f.func.attr == "op" and f.args
                    and isinstance(f.args[0], ast.Constant) and "->>" in str(f.args[0].value)):
                return True
    return False


def _resolve(subject, fn: ast.AST | None):
    """`(table, column, kind)` for the expression a NULL test is applied to."""
    # Model.attr
    if isinstance(subject, ast.Attribute) and isinstance(subject.value, ast.Name):
        base = subject.value.id
        if base in _MODELS:
            return _MODELS[base].__tablename__, subject.attr, "orm"
        # t.c.<name> / x.c.<name> — a register table built by modules_registry
        if base == "c":
            return None, subject.attr, "register"
    if (isinstance(subject, ast.Attribute) and isinstance(subject.value, ast.Attribute)
            and subject.value.attr == "c"):
        return None, subject.attr, "register"
    # A local name: classify by what it was assigned from, inside the same function.
    if isinstance(subject, ast.Name) and fn is not None:
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign) and any(
                    isinstance(tg, ast.Name) and tg.id == subject.id for tg in n.targets):
                if _extraction_source(n.value):
                    return None, subject.id, "extraction"
    return None, (subject.id if isinstance(subject, ast.Name) else None), "unresolved"


def _sites():
    """Every NULL test in the tree, with its resolved subject. Derived, never listed."""
    found = []
    for f in sorted(SRC.rglob("*.py")):
        rel = f.as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"), rel)
        # map each node to its enclosing function, so a local name can be resolved
        owner: dict[int, ast.AST] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    owner.setdefault(id(n), fn)
        for n in ast.walk(tree):
            subject = None
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in _NULL_METHODS and len(n.args) == 1 and _is_none(n.args[0])):
                subject = n.func.value
            elif (isinstance(n, ast.Compare) and len(n.ops) == 1
                  and isinstance(n.ops[0], (ast.Eq, ast.NotEq)) and _is_none(n.comparators[0])):
                subject = n.left
            if subject is None:
                continue
            tbl, col, kind = _resolve(subject, owner.get(id(n)))
            found.append((rel, n.lineno, ast.unparse(subject), tbl, col, kind,
                          verdict(tbl, col, kind)))
    return found


SITES = _sites()
check("the population is non-trivial", len(SITES) >= 15,
      f"{len(SITES)} NULL tests found — a walker that stops matching reports a clean tree")

# --- THE ANALYSER MUST FIND THE KNOWN INSTANCE ---------------------------------------------------
# `Topic.labels` is a JSON column with no `none_as_null=True`, and `client_portal.py` tests it for
# NULL. It is the one live member of the class, and it is NOT a wrong answer today: the query
# narrows to `type == "info"` first and then does the real check in Python, so it over-fetches and
# nothing is reported wrongly. It is listed rather than fixed because making it right means sweeping
# the existing `'null'` rows, which is a migration and a decision of its own.
#
# **This is the self-test: the gate is run against a defect known to be there BEFORE it is allowed
# to report anything.** A derivation that reports a clean tree is indistinguishable from a
# derivation that reports nothing, and the second one is what ships.
_KNOWN = [s for s in SITES if s[3] == "topics" and s[4] == "labels"]
check("the analyser reaches the known instance at all", len(_KNOWN) == 1,
      f"found {len(_KNOWN)} — `Topic.labels.isnot(None)` is in client_portal.py and the resolver "
      f"must reach it, or every verdict below is measured on a population that excludes the defect")
check("...and CLASSIFIES it as the defect, not merely reports it",
      bool(_KNOWN) and _KNOWN[0][6] == "JSON_NULL_TEST",
      f"verdict was {_KNOWN[0][6] if _KNOWN else 'n/a'} — reporting a site and classifying it are "
      f"two different questions, and only the second one is the check")
check("...and `verdict` itself is what decided that, so a mutation can be aimed at it",
      verdict("topics", "labels", "orm") == "JSON_NULL_TEST"
      and verdict("topics", "anchor", "orm") == "SAFE"
      and verdict("projects", "name", "orm") == "SAFE"
      and verdict(None, None, "unresolved") == "UNKNOWN"
      and verdict(None, "data", "extraction") == "SAFE",
      "the verdict function does not separate the four answers")

# The reasons two exemptions give must stay true, or the exemption is a stale claim.
check("no SYSTEM_COLUMN is a JSON column — the modules_query exemptions rest on this",
      not (set(modules_query.SYSTEM_COLUMNS) & set(_REG_JSON)),
      "a system column is now JSON, so `_field_expr`'s `t.c[name]` branch can return a bare JSON "
      "column and the modules_query.py exemptions above no longer hold")
check("the register pin columns still declare none_as_null — the pins.py exemptions rest on this",
      _REG_JSON.get("anchor") is True and _REG_JSON.get("element_guids") is True,
      f"anchor={_REG_JSON.get('anchor')} element_guids={_REG_JSON.get('element_guids')} — the "
      f"`pin_where` exemptions say these are safe; if they stop being so, the exemptions are wrong")

# --- THE VERDICTS --------------------------------------------------------------------------------
#: The one member of the class that is live today, with why it is recorded rather than fixed.
KNOWN_INSTANCES: dict[tuple[str, int], str] = {
    ("src/aec_api/client_portal.py", 274):
        "Topic.labels — over-fetches, does not answer wrongly: the query narrows on `type == "
        "'info'` and then applies the real test in Python. Fixing it needs a sweep of the existing "
        "`'null'` rows to mean anything, which is a migration of its own.",
}

_unknown = [s for s in SITES if s[6] == "UNKNOWN" and (s[0], s[1], s[2]) not in EXEMPT]
check("every NULL test resolves, or is exempted with a reason", not _unknown,
      "unresolved subject(s) — read each and add it to EXEMPT with what the subject actually is, "
      "never by widening the resolver until it stops appearing: "
      + "; ".join(f"{s[0]}:{s[1]} {s[2]}" for s in _unknown))

_stale = [k for k in EXEMPT if not any((s[0], s[1], s[2]) == k for s in SITES)]
check("no exemption outlives its site", not _stale,
      f"{_stale!r} — an exemption for a call site that no longer exists is a claim nobody can check")

_defects = [s for s in SITES if s[6] == "JSON_NULL_TEST" and (s[0], s[1]) not in KNOWN_INSTANCES]
check("no NULL test is applied to a JSON column that can hold the scalar `null`", not _defects,
      "a `IS NULL` / `IS NOT NULL` here filters nothing, silently — declare `none_as_null=True` on "
      "the column and sweep the existing rows, or move the test into Python: "
      + "; ".join(f"{s[0]}:{s[1]} {s[2]}" for s in _defects))

_stale_known = [k for k in KNOWN_INSTANCES
                if not any((s[0], s[1]) == k and s[6] == "JSON_NULL_TEST" for s in SITES)]
check("no KNOWN_INSTANCE outlives its defect", not _stale_known,
      f"{_stale_known!r} — this site is no longer in the class; delete the entry so the list keeps "
      f"measuring something")

if FAILED:
    print("FAIL test_json_null_filter")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
_by = {}
for _s in SITES:
    _by[_s[6]] = _by.get(_s[6], 0) + 1
print(f"test_json_null_filter OK  ({len(SITES)} NULL tests: "
      f"{_by.get('SAFE', 0)} safe, {len(EXEMPT)} exempt-unresolved, "
      f"{len(KNOWN_INSTANCES)} known instance; {len(JSON_COLS)} JSON columns in the metadata, "
      f"{sum(1 for v in JSON_COLS.values() if not v)} of them without none_as_null)")
