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

The 236 tests that create no schema and declare no database are **not** required to declare one. They
never call `create_all`, so the worst an ambient DSN does is give them a connection they never write
a table into. That is a judgement, not an oversight, and it is the reason this file counts them and
prints the number instead of quietly excluding them — a population you cannot see is one you cannot
argue with.

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

def _creates_schema(tree: ast.AST) -> bool:
    """Does this module call `create_all` anywhere? That is what turns a DSN into tables."""
    return any(isinstance(n, ast.Attribute) and n.attr == "create_all" for n in ast.walk(tree))


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


def _declares_own_db(tree: ast.AST) -> bool:
    """Is there an `os.environ["DATABASE_URL"] = ...` before the engine can be built?

    "Before the engine can be built" means before the first import that transitively reaches
    `aec_api.db` — that module reads the variable once, at import, and an assignment after it is
    inert. An import of an `aec_api` module that never touches the database does not count, which
    is the whole difference between this and the draft `_reaches_db` describes.
    """
    first_db_import: int | None = None
    for node in _module_level(tree):
        for name in _aec_targets(node):
            if name == "db" or _reaches_db(name):
                first_db_import = (node.lineno if first_db_import is None
                                   else min(first_db_import, node.lineno))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == "environ"
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
