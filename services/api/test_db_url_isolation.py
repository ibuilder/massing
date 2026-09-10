"""A test that builds a schema must say which database it builds it in.

## The door

`aec_api.db` reads `DATABASE_URL` **once, at import**, and builds the engine from it — its own first
line documents that variable as the way you point this service at production Postgres. So a test that
imports that module inherits whatever the shell is carrying.

Under `run_tests.py` that is harmless: the runner injects `DATABASE_URL=sqlite:///./_{test}.db` per
test, so nothing ambient survives. But every one of these files also says, in its own docstring,
`Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_x.py` — and run *that* way, with
`DATABASE_URL` exported, a schema-creating test calls `create_all` against the operator's database.

**Measured, not imagined:** `test_view_config.py` run directly with an ambient DSN created **173
tables** in it, wrote rows, and **exited 0**. A passing test is the whole problem — nothing announces
it, so the damage is discovered later by someone wondering where the extra tables came from.

## What this gate asserts, and why it is not the obvious rule

The obvious rule is "no test may use `os.environ.setdefault` for DATABASE_URL", because `setdefault`
yields to the ambient value while *looking* like a declaration. That was the shape this sweep started
from, and **it is the wrong population.** `test_bootstrap_admin.py` declared DATABASE_URL by no
mechanism at all — it simply imported `engine` and called `create_all` — and is exposed identically.
A `setdefault` grep cannot see it.

*A predicate that decides what to LOOK at is more dangerous than one that decides what to report*,
because everything it excludes is invisible to its own output. So the gate is keyed on the RISK:

> **A test that can create a schema must decide its own `DATABASE_URL`, by assignment, before
> `aec_api` is imported.**

`setdefault` fails that not as a style violation but because it does not *decide* anything — the
ambient value wins. Declaring after the import fails it too, for the reason above: the engine is
already built.

## Not covered, stated rather than left implicit

The tests that create no schema and declare no database are **not** required to declare one. They
neither call `create_all` nor enter a `TestClient`, so the worst an ambient DSN does is give them a
connection they never write a table into. That is a judgement, not an oversight, and it is the reason
this file counts them and prints the number instead of quietly excluding them — a population you
cannot see is one you cannot argue with.

*This paragraph used to say "the 236 tests". It was 304 by the time anyone re-read it, and it moved
because the `create_all`/lifespan widening below reclassified 347 files out of it — a number in prose
beside a number the run prints is a copy, and the copy is what drifts. The printed one is the answer.*

The three non-test tools — `loadtest.py`, `mcp_server.py`, `seed_scale.py` — keep `setdefault` on
purpose: pointing a load test or the seeder at a real database is what they are for. They are not
`test_*.py` and so are outside this gate's population by construction rather than by exemption.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_db_url_isolation.py
"""
from __future__ import annotations

import ast
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# ── the analyser, kept separate from the reporting so it can be mutated directly ─────────────────
#
# `test_unique_read_guard.py` learned this the expensive way: its self-test asserted the analyser
# still REPORTED a site, so a mutation that routed every site to "safe" passed. Reporting a file and
# classifying it are different questions, and asserting one is not asserting the other.

def _boots_the_app(tree: ast.AST) -> bool:
    """Does this module enter a `TestClient(...)` as a context manager?

    **This gate made, one level down, the exact mistake its own docstring warns about.** It keyed on
    the risk — "can this file create a schema" — and then answered that question by looking for a
    literal `create_all`. But `with TestClient(app)` runs the app's lifespan, and the lifespan calls
    `init_db()`, which calls `Base.metadata.create_all`. No literal appears in the test. So **355
    files** that build the whole schema were classified as *creates no schema* and never checked;
    four of them declared no `DATABASE_URL` at all.

    **The `with` is load-bearing and is not a style preference.** A bare `TestClient(app)` does NOT
    run the lifespan — `test_samples.py` says so in a comment, and it is why that file wraps its
    client. Matching the constructor instead of the context manager would report every file holding
    a non-entering client, which is a different and larger population that carries no risk.

    Both `with X() as c:` and `with X():` are matched, and multi-item `with` statements too, since
    the risk is entering the client at all.

    **Three ways in, not one** — a review finding on PR #501, after it had merged. The first version
    matched only a literal `with TestClient(...)`, so it was blind to `c = TestClient(app)` followed
    by `with c:`, and to `from fastapi.testclient import TestClient as Client`. Measured across the
    suite, widening it changes nothing today: **353 files boot the app either way, and not one is
    caught only by the wider form** — every binding-then-entering file in the tree also contains a
    direct `with TestClient(...)`, and no file aliases the import.

    That "nothing changed" is the reason to widen it, not a reason to leave it. A predicate narrower
    than the risk it stands for is a blind spot with no current occupant, and the tree agreeing with
    it today is exactly what makes the narrowing invisible — the same shape as this file's own
    motivating defect, and as a hard-coded population in `test_frozen_paths.py` whose mutation passed
    for the same reason. **The next file to fall through would be the first evidence, and by then it
    has already written to somebody's database.**
    """
    names = {"TestClient"}
    for n in ast.walk(tree):                        # `import TestClient as Client`
        if isinstance(n, ast.ImportFrom):
            names.update(a.asname for a in n.names if a.name == "TestClient" and a.asname)

    def _is_client_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        fn = node.func
        nm = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
        return nm in names

    bound: set[str] = set()                         # `c = TestClient(app)`
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and _is_client_call(n.value):
            bound.update(t.id for t in n.targets if isinstance(t, ast.Name))
        # ...and `c: TestClient = TestClient(app)`, which is an AnnAssign and matched
        # nothing above. A THIRD binding form, found in review after the first two were
        # fixed -- which is the argument for enumerating the ways a name can be bound
        # rather than fixing the shapes as they are reported one at a time.
        elif (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
              and _is_client_call(n.value)):
            bound.add(n.target.id)

    for n in ast.walk(tree):
        if not isinstance(n, (ast.With, ast.AsyncWith)):
            continue
        for item in n.items:
            expr = item.context_expr
            if _is_client_call(expr):               # with TestClient(app):
                return True
            if isinstance(expr, ast.Name) and expr.id in bound:      # c = TestClient(app); with c:
                return True
    return False


def _creates_schema(tree: ast.AST) -> bool:
    """Can this module turn a DSN into tables?

    Two ways, and the second was invisible until 2026-09-10: calling `create_all` directly, or
    entering a `TestClient` whose lifespan calls it for you. See `_boots_the_app`.
    """
    if any(isinstance(n, ast.Attribute) and n.attr == "create_all" for n in ast.walk(tree)):
        return True
    return _boots_the_app(tree)


#: memo for `_reaches_db`; also the cycle guard, since a provisional False is stored
#: before the recursion so an import loop terminates instead of recursing forever.
_REACH_CACHE: dict[str, bool] = {}


def _module_level(tree: ast.AST):
    """Import statements that actually run when the module is imported.

    **`ast.walk` is wrong here and it cost a false positive on three files.** It reaches inside
    function and class bodies, where an import does not execute until the function is called — and
    this codebase uses function-local imports deliberately (`test_declared_imports.py` exists
    because of them). `aec_api.deal_memory` imports the database module only inside a function, so
    walking everything reported it as building the engine at import time, which it does not.

    Descends through module-level control flow (`if`, `try`, `with`) because those DO run; stops at
    every `def` and `class` because those do not.
    """
    stack = list(getattr(tree, "body", []))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        for field in ("body", "orelse", "finalbody", "handlers"):
            stack.extend(getattr(node, field, []) or [])


def _reaches_db(mod: str) -> bool:
    """Does importing `aec_api.<mod>` transitively import `aec_api.db`, and so build the engine?

    **The first draft asked the cruder question — "is there ANY `aec_api` import before the
    assignment" — and it was wrong on three files.** `aec_api.deal_memory` imports no database
    module at all, so a test may import it, set `DATABASE_URL`, and only then import `aec_api.db`;
    the assignment is effective and the file is safe. Three were reported as defects on that rule
    and none of them was one.

    Over-reporting is the safe direction and it is still wrong: a gate that cries wolf gets edited
    to be quiet, and the edit is where the real rule dies. So the reachability is computed rather
    than approximated.
    """
    if mod in _REACH_CACHE:
        return _REACH_CACHE[mod]
    _REACH_CACHE[mod] = False                                   # cycle guard: assume no until proven
    src_dir = HERE / "src" / "aec_api"
    f = src_dir / f"{mod.replace('.', '/')}.py"
    if not f.exists():
        f = src_dir / mod.replace(".", "/") / "__init__.py"
    if not f.exists():
        return False
    try:
        tree = ast.parse(f.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        _REACH_CACHE[mod] = True                                # unreadable: assume it reaches, fail closed
        return True
    out = False
    for node in _module_level(tree):
        for name in _aec_targets(node):
            if name == "db" or _reaches_db(name):
                out = True
                break
        if out:
            break
    _REACH_CACHE[mod] = out
    return out


def _aec_targets(node: ast.AST) -> list[str]:
    """The `aec_api.X` submodules one import statement pulls in, as bare `X` names."""
    if isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        if node.level:                                    # `from .db import ...`
            return [mod.split(".")[0]] if mod else [a.name for a in node.names]
        if mod == "aec_api":
            return [a.name for a in node.names]
        if mod.startswith("aec_api."):
            return [mod[len("aec_api."):]]
    elif isinstance(node, ast.Import):
        return [a.name[len("aec_api."):] for a in node.names if a.name.startswith("aec_api.")]
    return []


def _os_aliases(tree: ast.AST) -> set[str]:
    """Module-level names bound to the `os` module — `os`, plus any `import os as _os`.

    Needed because real files in this suite do alias it: `test_provenance_report.py` and
    `test_routines.py` both write `_os.environ["DATABASE_URL"]`. Without this the gate would either
    miss them or, worse, accept `anything.environ["DATABASE_URL"]` as a declaration.
    """
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    out.add(alias.asname or "os")
    return out


def _declares_own_db(tree: ast.AST) -> bool:
    """Is there an unconditional `os.environ["DATABASE_URL"] = ...` before the engine can be built?

    "Before the engine can be built" means before the first import that transitively reaches
    `aec_api.db` — that module reads the variable once, at import, and an assignment after it is
    inert. An import of an `aec_api` module that never touches the database does not count.

    **Three things this deliberately refuses, each of which the first draft accepted** — a review bot
    found all three, and every one was the gate reporting good news it had not earned:

    * an assignment **inside a function**. The draft used `_module_level` for the imports and
      `ast.walk` for the assignment, which is an asymmetry with no defence: a `def` body does not run
      at import, so an assignment there cannot beat the engine.
    * an assignment **inside `if` or `try`**. It may not execute, and a declaration that might not
      happen is not a declaration. Only direct statements of `tree.body` count.
    * an assignment to **something that is not `os.environ`** — `fake.environ["DATABASE_URL"]` was
      accepted because the draft matched on the attribute name alone.

    *The asymmetry is the lesson.* Having reasoned carefully about which imports execute at import
    time, the draft then asked a completely different question of the assignment, in the same
    function, three lines later.
    """
    first_db_import: int | None = None
    for node in _module_level(tree):
        for name in _aec_targets(node):
            if name == "db" or _reaches_db(name):
                first_db_import = (node.lineno if first_db_import is None
                                   else min(first_db_import, node.lineno))

    aliases = _os_aliases(tree)
    for node in tree.body:                      # direct statements only: unconditional, top level
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Attribute)
                    and isinstance(tgt.value.value, ast.Name)
                    and tgt.value.value.id in aliases
                    and tgt.value.attr == "environ"
                    and isinstance(tgt.slice, ast.Constant) and tgt.slice.value == "DATABASE_URL"):
                if first_db_import is None or node.lineno < first_db_import:
                    return True
    return False


def verdict(src: str) -> str:
    """SAFE · NEEDS-DECLARATION · NO-SCHEMA — the classification, mutable on its own."""
    tree = ast.parse(src)
    if not _creates_schema(tree):
        return "NO-SCHEMA"
    return "SAFE" if _declares_own_db(tree) else "NEEDS-DECLARATION"


# ── the analyser must find the defect it was written for, before it may report anything ──────────
#
# The pre-fix `test_bootstrap_admin.py`, reduced to its shape: imports the engine, builds the schema,
# never says where. If `verdict` cannot call this NEEDS-DECLARATION, every clean result below is
# meaningless — so it runs first and hard-exits.
_PRE_FIX = '''
import os
os.environ.pop("AEC_ADMIN_EMAILS", None)
from aec_api import models
from aec_api.db import engine
models.Base.metadata.create_all(bind=engine)
'''
_TOO_LATE = '''
import os
from aec_api.db import engine
os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api import models
models.Base.metadata.create_all(bind=engine)
'''
_SETDEFAULT = '''
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///./_x.db")
from aec_api import models
from aec_api.db import engine
models.Base.metadata.create_all(bind=engine)
'''
_FIXED = '''
import os
os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api import models
from aec_api.db import engine
models.Base.metadata.create_all(bind=engine)
'''

#: The false positive that `_module_level` exists to prevent. `aec_api.deal_memory` imports the
#: database module only INSIDE a function, so importing it builds no engine — a test may import it,
#: then declare its own DSN, and be perfectly safe. An analyser using `ast.walk` calls this a defect.
_FUNCTION_LOCAL_IMPORT_IS_NOT_AN_IMPORT = '''
import os
from aec_api.deal_memory import anything
os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api.db import engine
from aec_api import models
models.Base.metadata.create_all(engine)
'''

#: Three shapes the FIRST DRAFT accepted, each a fail-open a review bot found. They are fixtures
#: rather than prose because the draft's own author had already reasoned about which imports execute
#: at import time and then asked a different question of the assignment three lines later.
_ASSIGN_IN_FUNCTION = '''
import os
def go():
    from aec_api.db import engine
    from aec_api import models
    os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api.db import engine as e2
from aec_api import models as m2
m2.Base.metadata.create_all(e2)
'''
_ASSIGN_CONDITIONAL = '''
import os
if os.environ.get("CI"):
    os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api.db import engine
from aec_api import models
models.Base.metadata.create_all(engine)
'''
_ASSIGN_NOT_OS = '''
import os
import fake
fake.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api.db import engine
from aec_api import models
models.Base.metadata.create_all(engine)
'''
#: ...and the alias that REAL files use, which must still be accepted.
_ALIASED_OS = '''
import os as _os
_os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from aec_api.db import engine
from aec_api import models
models.Base.metadata.create_all(engine)
'''


#: DB-URL-BOOT — the shape that was invisible for two months. No `create_all` anywhere; the schema is
#: built by the app's lifespan when the client is ENTERED. 355 files in this suite are this shape,
#: and four of them declared no DSN at all: one, run with the variable exported, was measured
#: creating **173 tables** in it and exiting 0 — the same number `test_view_config.py` produced for
#: the original finding, in the population this gate could not look at.
_LIFESPAN_BOOT = '''
from fastapi.testclient import TestClient
from aec_api.main import app
with TestClient(app) as c:
    c.get("/health")
'''
#: The same shape, declared. Must be accepted, or the rule is always-fail rather than a rule.
_LIFESPAN_BOOT_FIXED = '''
import os
os.environ["DATABASE_URL"] = "sqlite:///./_x.db"
from fastapi.testclient import TestClient
from aec_api.main import app
with TestClient(app) as c:
    c.get("/health")
'''
#: **The `with` is the whole distinction.** A bare `TestClient(app)` does not run the lifespan and
#: creates nothing — `test_samples.py` says so in a comment. Matching the constructor instead would
#: demand a DSN from every file merely holding a client: a larger population carrying no risk, and a
#: gate that cries wolf gets edited to be quiet, which is where the real rule dies.
_BARE_CLIENT_NO_LIFESPAN = '''
from fastapi.testclient import TestClient
from aec_api.main import app
c = TestClient(app)
'''

#: **Bound, then entered.** `c2 = TestClient(app)` … `with c2:` runs the lifespan exactly as the
#: literal form does, and the first version of `_boots_the_app` could not see it. Two files in this
#: suite are written this way; both happen to ALSO contain a direct `with TestClient(app)`, which is
#: precisely why the narrowing left no trace in the population and why it needs a fixture rather than
#: a tree scan to hold it.
_BOUND_THEN_ENTERED = '''
from fastapi.testclient import TestClient
from aec_api.main import app
c2 = TestClient(app)
with c2:
    c2.get("/health")
'''
#: **Aliased import.** `TestClient as Client` is the same class under another name. No file in the
#: suite does this today; the fixture is the only thing keeping the alias branch honest, which is the
#: point -- a branch with no occupant is a branch nobody has run.
_ALIASED_CLIENT = '''
from fastapi.testclient import TestClient as Client
from aec_api.main import app
with Client(app) as c:
    c.get("/health")
'''
#: **Annotated binding** -- `c: TestClient = TestClient(app)`. An `ast.AnnAssign`, which the
#: Assign-only detection could not see. Reported in review after the bound and aliased forms were
#: already fixed, which is why the fixtures below now cover the binding forms as a SET.
_ANNOTATED_BINDING = '''
from fastapi.testclient import TestClient
from aec_api.main import app
c: TestClient = TestClient(app)
with c:
    c.get("/health")
'''
#: ...and bound THROUGH the alias, so neither half of the widening can be dropped alone.
_ALIASED_AND_BOUND = '''
from fastapi.testclient import TestClient as Client
from aec_api.main import app
c = Client(app)
with c:
    c.get("/health")
'''

for _label, _src, _want in (
    ("the undeclared original is caught", _PRE_FIX, "NEEDS-DECLARATION"),
    ("declaring AFTER the aec_api import is caught — the engine is already built",
     _TOO_LATE, "NEEDS-DECLARATION"),
    ("setdefault is caught: it yields to the ambient DSN rather than deciding",
     _SETDEFAULT, "NEEDS-DECLARATION"),
    ("...and the fixed shape is accepted, so the rule is not simply always-fail",
     _FIXED, "SAFE"),
    ("an aec_api import that does NOT reach the database at import time is not a violation",
     _FUNCTION_LOCAL_IMPORT_IS_NOT_AN_IMPORT, "SAFE"),
    ("an assignment inside a def does not run at import, so it declares nothing",
     _ASSIGN_IN_FUNCTION, "NEEDS-DECLARATION"),
    ("an assignment inside `if` might not run, and a maybe-declaration is not one",
     _ASSIGN_CONDITIONAL, "NEEDS-DECLARATION"),
    ("`fake.environ[...]` is not os.environ, however much it looks like it",
     _ASSIGN_NOT_OS, "NEEDS-DECLARATION"),
    ("...but `import os as _os` IS os, and two real files in this suite write it that way",
     _ALIASED_OS, "SAFE"),
    ("DB-URL-BOOT: entering a TestClient builds the schema via the lifespan, with no `create_all` "
     "in sight — the blind spot this gate had until 2026-09-10",
     _LIFESPAN_BOOT, "NEEDS-DECLARATION"),
    ("...and the same file with a declaration is accepted", _LIFESPAN_BOOT_FIXED, "SAFE"),
    ("a BARE TestClient never enters the lifespan, so it creates nothing and is not asked to declare",
     _BARE_CLIENT_NO_LIFESPAN, "NO-SCHEMA"),
    ("a client BOUND then entered runs the same lifespan — a review finding on #501, after merge",
     _BOUND_THEN_ENTERED, "NEEDS-DECLARATION"),
    ("...and an ALIASED import is the same class under another name",
     _ALIASED_CLIENT, "NEEDS-DECLARATION"),
    ("...and aliased AND bound, so neither half of the widening can be dropped on its own",
     _ALIASED_AND_BOUND, "NEEDS-DECLARATION"),
    ("...and an ANNOTATED binding, the third form — a review finding on #502",
     _ANNOTATED_BINDING, "NEEDS-DECLARATION"),
):
    got = verdict(_src)
    check(f"self-test: {_label}", got == _want, f"got {got}")

if FAILED:
    print("\nThe analyser cannot see its own motivating defect; every verdict below would be "
          "unfounded. Refusing to report.")
    raise SystemExit(1)

# ── the live tree ────────────────────────────────────────────────────────────────────────────────
buckets: dict[str, list[str]] = {"SAFE": [], "NEEDS-DECLARATION": [], "NO-SCHEMA": [], "UNPARSED": []}
for path in sorted(HERE.glob("test_*.py")):
    try:
        buckets[verdict(path.read_text(encoding="utf-8"))].append(path.name)
    except (OSError, SyntaxError):
        # Fail CLOSED: a file this gate cannot read is not a file it may call safe.
        buckets["UNPARSED"].append(path.name)

total = sum(len(v) for v in buckets.values())
check("the scan found the suite, rather than an empty directory", total > 400, f"{total} test files")
check("no schema-creating test inherits its database from the shell",
      not buckets["NEEDS-DECLARATION"],
      ", ".join(buckets["NEEDS-DECLARATION"]) or f"{len(buckets['SAFE'])} declare their own")
check("every file parsed — an unreadable one is reported, never assumed safe",
      not buckets["UNPARSED"], ", ".join(buckets["UNPARSED"]))

print(f"\n  schema-creating, declares its own DB : {len(buckets['SAFE'])}")
print(f"  schema-creating, inherits the shell  : {len(buckets['NEEDS-DECLARATION'])}")
print(f"  creates no schema (not required to)  : {len(buckets['NO-SCHEMA'])}")

if FAILED:
    print("\nFAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("\ntest_db_url_isolation OK - every test that can build a schema decides its own DATABASE_URL "
      "by assignment before aec_api is imported, so running one directly with the variable exported "
      "cannot create tables in the operator's database.")
