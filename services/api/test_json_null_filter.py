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
#:
#: **Keyed by the ENCLOSING FUNCTION, not by a line number, and the count is part of the key's
#: value.** The first version of this dict pinned `(file, line, subject)` and went stale TWICE in
#: two days — both times because an unrelated edit elsewhere in `modules_query.py` pushed these
#: sites down the file. A line number is a coordinate every edit to the file moves, so an exemption
#: keyed on one measures when the file was last touched rather than whether the site is still there.
#: A function name moves only when the code genuinely moves.
#:
#: Collapsing to the function loses the ability to tell two sites in one function apart, which is
#: why each entry carries HOW MANY sites it covers: delete one of `_apply_filters`' two and the
#: count no longer matches, so the exemption still cannot outlive its sites. `_exemption_count_is_
#: load_bearing` below deletes a site and requires that to be caught.
EXEMPT: dict[tuple[str, str, str], tuple[int, str]] = {
    ("src/aec_api/modules_query.py", "_apply_filters", "expr"): (2,
        "`_field_expr` returns either `t.c[name]` for a name in SYSTEM_COLUMNS — none of which is a "
        "JSON column (assert_system_columns_are_not_json below pins that) — or `_json_text(...)`, an "
        "extraction. Neither is a bare JSON column. Two sites: the `empty` and `nonempty` operators."),
    ("src/aec_api/modules_query.py", "_apply_sort", "expr"): (1,
        "`_display_expr`, which resolves through `_field_expr` for a plain field and through a "
        "joined label column for a reference field; neither yields a bare JSON column."),
    ("src/aec_api/pins.py", "pin_where", "anchor_col"): (1,
        "a parameter of `pin_where`, bound by every caller to a register `anchor` column, which "
        "declares none_as_null=True (asserted below, so this exemption cannot outlive its reason)."),
    ("src/aec_api/pins.py", "pin_where", "guids_col"): (1,
        "a parameter of `pin_where`, bound to `element_guids`, likewise none_as_null=True."),
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


#: Nodes that open a NEW scope. A binding inside one of these is not a binding of the enclosing
#: function's local, so the resolver below must not descend into them.
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _own_scope_bindings(fn: ast.AST, name: str) -> list[ast.AST]:
    """Every assignment to `name` in `fn`'s OWN scope, nested scopes excluded.

    **`ast.walk` was the wrong tool and this is the correction.** It descends into nested functions
    and lambdas, so a binding in an inner scope — a different variable that merely shares a name —
    counted as a binding of this one.
    """
    out: list[ast.AST] = []

    def visit(node, top: bool) -> None:
        if not top and isinstance(node, _NESTED_SCOPES):
            return                                    # a different scope; its bindings are not ours
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                out.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child, False)

    visit(fn, True)
    return out


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
    # A LOCAL NAME. Classified only when the binding in effect is PROVEN, never on the first
    # assignment that happens to look right.
    #
    # **The first version returned "extraction" on the first matching `ast.walk` hit**, so
    # `expr = _json_text(...)` followed by `expr = Topic.labels` followed by `expr.is_(None)` was
    # SAFE — the analyser answered instead of failing, which is the exact defect this whole change
    # is about, one level up in the thing checking for it. Found in review of this PR.
    #
    # The rule now: every binding in the function's own scope must precede the use AND be an
    # extraction. A binding at or after the use (a loop rebinding, say) means the value in effect
    # cannot be read off the source, so the answer is UNKNOWN — which reds the build until a human
    # reads the site and writes down what it is.
    if isinstance(subject, ast.Name) and fn is not None:
        binds = _own_scope_bindings(fn, subject.id)
        use_line = getattr(subject, "lineno", 0)
        before = [b for b in binds if b.lineno < use_line]
        after = [b for b in binds if b.lineno >= use_line]
        if before and not after and all(
                _extraction_source(b.value) for b in before if getattr(b, "value", None) is not None):
            return None, subject.id, "extraction"
    return None, (subject.id if isinstance(subject, ast.Name) else None), "unresolved"


def _owners(tree: ast.AST) -> dict[int, ast.AST]:
    """Every node in `tree` mapped to its NEAREST enclosing function (absent if at module level).

    Defined at module scope rather than inside `_sites`' loop so the recursion does not close over
    loop-scoped state — which is a real hazard (ruff B023) and not merely a style point.
    """
    owner: dict[int, ast.AST] = {}
    stack: list[ast.AST] = []

    def descend(node: ast.AST) -> None:
        entered = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if entered:
            stack.append(node)
        if stack:
            owner[id(node)] = stack[-1]
        for child in ast.iter_child_nodes(node):
            descend(child)
        if entered:
            stack.pop()

    descend(tree)
    return owner


def _sites():
    """Every NULL test in the tree, with its resolved subject. Derived, never listed."""
    found = []
    for f in sorted(SRC.rglob("*.py")):
        rel = f.as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"), rel)
        # Map each node to its NEAREST enclosing function, by descending with a scope stack.
        #
        # This was `ast.walk` + `owner.setdefault`, which binds a node to whichever function the
        # outer walk reached FIRST — the outermost, not the innermost. A NULL test inside a nested
        # `def` was therefore resolved against the OUTER function's locals. That was already wrong
        # when the owner was used only by `_resolve`; it became load-bearing when the function name
        # became part of the site's IDENTITY, because a misattributed site gets a key no exemption
        # can match and no exemption can be written for. Measured on today's tree the two agree on
        # every site — *which is exactly why it would have been found only after it mattered.*
        owner = _owners(tree)
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
            fn = owner.get(id(n))
            tbl, col, kind = _resolve(subject, fn)
            found.append((rel, n.lineno, ast.unparse(subject), tbl, col, kind,
                          verdict(tbl, col, kind), getattr(fn, "name", "<module>")))
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

# --- THE RESOLVER MUST NOT ANSWER WHEN IT CANNOT KNOW ---------------------------------------------
# Review of this PR found `_resolve` returning "extraction" on the first `ast.walk` hit: a rebinding
# after the extraction, or a same-named local in a NESTED scope, both classified the site SAFE. That
# is an analyser answering instead of failing — the defect this file exists to catch, one level up in
# the thing doing the catching. Each shape is driven here, because a fix nobody ran against the case
# that motivated it is a fix on paper.
def _resolve_src(src: str, subject_line_marker: str):
    """Resolve the NULL-test subject in a one-function source snippet."""
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "f")
    for n in ast.walk(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in _NULL_METHODS and subject_line_marker in ast.unparse(n)):
            return _resolve(n.func.value, fn)
    raise AssertionError("no NULL test found in the snippet")


_REBIND = """
def f(db, t):
    expr = _json_text(db, t.c.data, 'x')
    expr = Topic.labels
    return expr.isnot(None)
"""
check("A REBINDING AFTER THE EXTRACTION IS NOT SAFE — this is the review finding",
      _resolve_src(_REBIND, "expr")[2] == "unresolved",
      f"got {_resolve_src(_REBIND, 'expr')!r} — the NULL test targets the bare JSON column, and "
      f"classifying it from an earlier, overwritten binding is the analyser answering rather than "
      f"failing")

_NESTED = """
def f(db, t):
    def inner():
        expr = _json_text(db, t.c.data, 'x')
        return expr
    expr = Topic.labels
    return expr.isnot(None)
"""
check("...and a same-named binding in a NESTED scope is not this scope's binding",
      _resolve_src(_NESTED, "expr")[2] == "unresolved",
      f"got {_resolve_src(_NESTED, 'expr')!r} — `ast.walk` descends into inner functions, so an "
      f"unrelated local sharing the name counted as a binding of this one")

_CLEAN = """
def f(db, t):
    duecol = _json_text(db, t.c.data, 'due')
    return duecol.isnot(None)
"""
check("...while a single preceding extraction still resolves, or the rule is merely stricter",
      _resolve_src(_CLEAN, "duecol")[2] == "extraction",
      f"got {_resolve_src(_CLEAN, 'duecol')!r} — tightening must not turn every real extraction "
      f"into an exemption; that would be a gate nobody can keep green")

_BRANCHED = """
def f(db, t):
    if pg:
        col = t.c.data.op('->>')('k')
    else:
        col = func.json_extract(t.c.data, '$.k')
    return col.isnot(None)
"""
check("...and an if/else where BOTH branches extract still resolves (sync.py's real shape)",
      _resolve_src(_BRANCHED, "col")[2] == "extraction",
      f"got {_resolve_src(_BRANCHED, 'col')!r}")

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
#: Keyed like `EXEMPT`, and for the same reason — see the note there.
KNOWN_INSTANCES: dict[tuple[str, str, str], tuple[int, str]] = {
    ("src/aec_api/client_portal.py", "_feedback_topic", "Topic.labels"): (1,
        "Topic.labels — over-fetches, does not answer wrongly: the query narrows on `type == "
        "'info'` and then applies the real test in Python. Fixing it needs a sweep of the existing "
        "`'null'` rows to mean anything, which is a migration of its own."),
}

def site_key(s) -> tuple[str, str, str]:
    """A site's identity: file, enclosing function, subject text. Deliberately NOT the line number
    — see the note on `EXEMPT`. Kept as a function so a mutation can be aimed at it."""
    return (s[0], s[7], s[2])


def covered(keys, sites) -> tuple[list, list]:
    """`(uncovered_sites, bad_entries)` for a keyed dict of `(count, reason)` against `sites`.

    Both directions, because either alone passes while the other is broken: an entry whose sites
    are gone is a claim nobody can check, and a site no entry covers is the thing the gate exists
    to report. The COUNT is checked as well as the key — collapsing a line number to a function
    would otherwise let an entry keep covering one site after its twin was deleted."""
    seen: dict[tuple[str, str, str], int] = {}
    for s in sites:
        seen[site_key(s)] = seen.get(site_key(s), 0) + 1
    uncovered = [s for s in sites if site_key(s) not in keys]
    bad = [(k, n, seen.get(k, 0)) for k, (n, _r) in keys.items() if seen.get(k, 0) != n]
    return uncovered, bad


# **The self-tests for the key itself, run before any verdict.** The dict this replaces went stale
# twice in two days, so the two properties that fix it are asserted rather than described.
# `next(..., None)` and a check, never a bare `next(...)`: a StopIteration here would kill the gate
# before it printed anything, which is the same "dies instead of reporting" family the PR that added
# these self-tests had just fixed one file over. A self-test whose SETUP can abort the run is worse
# than no self-test, because the run looks crashed rather than failed.
#: **The nearest-enclosing-function fix, asserted rather than described.** A synthetic module with a
#: NULL test inside a nested `def` must attribute it to the INNER function. The previous
#: `ast.walk` + `setdefault` walker returns the OUTER one here, so this check distinguishes the two
#: implementations — which matters because on today's real tree they agree on every site, and a fix
#: nothing can tell apart from the bug is a fix nobody can keep.
#:
#: **It calls `_owners` — THE function `_sites` uses — and not a copy of it.** The first draft
#: mirrored the traversal into a local `_probe`, so `_owners` could regress to outer-function
#: attribution and this check would still pass: *a self-test written to stop a fix being silently
#: reverted, testing a copy of the fix.* That is the same "cannot fail" family the whole gate is
#: about, one level up, and the mutation run to verify it was aimed at the COPY, so it proved the
#: copy behaved as advertised and said nothing about the gate. **Mutate the thing under test, and
#: make sure the test can reach it.**
#:
#: Named `_NESTED_OWNERS` rather than reusing `_NESTED` above, which is a different fixture for the
#: resolver self-tests — the first draft shadowed it, and the only reason that was harmless is that
#: the earlier checks happen to run first.
_NESTED_OWNERS = """
def outer(col):
    def inner(other):
        return other.is_(None)
    return inner
"""
_nt = ast.parse(_NESTED_OWNERS)
_nowner = _owners(_nt)
_ncall = next((n for n in ast.walk(_nt)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "is_"), None)
check("a NULL test in a NESTED def belongs to the INNER function, not the outer one",
      _ncall is not None and getattr(_nowner.get(id(_ncall)), "name", None) == "inner",
      f"attributed to {getattr(_nowner.get(id(_ncall)), 'name', None)!r} — `ast.walk` + "
      f"`setdefault` binds a node to the OUTERMOST enclosing function, so a nested site resolves "
      f"against the wrong locals and gets a key no exemption can match")

_a_site = next((s for s in SITES if s[0] == "src/aec_api/modules_query.py"
                and s[7] == "_apply_filters"), None)
check("the site these self-tests are built on still exists", _a_site is not None,
      "no NULL test remains in `modules_query._apply_filters` — if that is intended, delete its "
      "EXEMPT entry and re-aim these self-tests at another multi-site function; until then the two "
      "checks below are measuring nothing")
_moved = (_a_site[0], _a_site[1] + 137, *_a_site[2:]) if _a_site else None
check("a site's identity does not move when only its LINE moves — the whole point of the rekey",
      bool(_a_site) and site_key(_moved) == site_key(_a_site),
      f"{site_key(_moved)} != {site_key(_a_site)} — a key carrying the line number is a key every "
      f"unrelated edit to the file invalidates, which is the defect this replaced"
      if _a_site else "no site to move")

#: `_exemption_count_is_load_bearing`: delete ONE of `_apply_filters`' two sites and require the
#: count to catch it. Without this, collapsing the line number into the function would let an
#: exemption keep covering a survivor after its twin was deleted — trading one silent failure for
#: another. A mutation on the analyser is the only way to know which of the two we got.
_unknowns = [s for s in SITES if s[6] == "UNKNOWN"]
_one_deleted = [s for s in _unknowns if s is not _a_site]
_, _bad_after = covered(EXEMPT, _one_deleted)
check("deleting ONE of two sites under a single exemption is caught by the count",
      any(k == site_key(_a_site) for k, _n, _got in _bad_after),
      f"the mutated tree reported {_bad_after!r} — an exemption claiming 2 sites while only 1 "
      f"remains is exactly the claim nobody can check that the line-number key used to catch")
_, _bad_before = covered(EXEMPT, _unknowns)
check("...and the unmutated tree is clean, so the check above is not passing for free",
      not _bad_before,
      f"{_bad_before!r} — a mutation test whose baseline already fails proves nothing")

_unknown, _stale = covered(EXEMPT, [s for s in SITES if s[6] == "UNKNOWN"])
check("every NULL test resolves, or is exempted with a reason", not _unknown,
      "unresolved subject(s) — read each and add it to EXEMPT with what the subject actually is, "
      "never by widening the resolver until it stops appearing: "
      + "; ".join(f"{s[0]}:{s[1]} in {s[7]} — {s[2]}" for s in _unknown))

check("no exemption outlives its sites, and covers exactly as many as it claims", not _stale,
      "; ".join(f"{k} claims {n} site(s), found {got}" for k, n, got in _stale)
      + " — an exemption for a call site that no longer exists is a claim nobody can check, and one "
        "that silently covers fewer sites than it says has stopped describing the code")

_defects, _stale_known = covered(KNOWN_INSTANCES,
                                 [s for s in SITES if s[6] == "JSON_NULL_TEST"])
check("no NULL test is applied to a JSON column that can hold the scalar `null`", not _defects,
      "a `IS NULL` / `IS NOT NULL` here filters nothing, silently — declare `none_as_null=True` on "
      "the column and sweep the existing rows, or move the test into Python: "
      + "; ".join(f"{s[0]}:{s[1]} in {s[7]} — {s[2]}" for s in _defects))

check("no KNOWN_INSTANCE outlives its defect", not _stale_known,
      "; ".join(f"{k} claims {n} site(s), found {got}" for k, n, got in _stale_known)
      + " — this site is no longer in the class; delete the entry so the list keeps measuring "
        "something")

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
