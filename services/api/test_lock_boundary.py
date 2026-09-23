"""A field the project lock protects SOMEWHERE must be protected EVERYWHERE.

## Why this exists, and why `test_rmw_sweep` could not have found it

`test_rmw_sweep` derives **read-modify-writes** and asks whether each is serialised. That population
is the right one for the defect it was built for, and it is structurally blind to this one.
`p.source_ifc = str(ifc_path)` READS NOTHING — it installs a new pointer — so it is not a
read-modify-write and never enters the sweep. Neither does the conditional-create shape
`if not p.source_ifc: ... p.source_ifc = ...`.

The consequence, measured rather than feared: G-11 was closed on 2026-09-13 by locking every
`source_ifc` read-modify-write in `routers/authoring.py`, and **five writers of that same column were
left unlocked** — four this gate reported as violations plus one it could only report as an
unresolvable receiver — two of them in `authoring.py` itself. A pointer swap that reads nothing still
destroys the version another worker is deriving from — *a lock one side does not take protects
nothing*, which is the sentence the `dev_property` pair and the `connections` pair each cost a
release to learn.

**The first diagnosis of this was wrong in a way worth recording.** It read as a FILE boundary —
`generate.py` contains no `pid_lock` reference at all, so the closure looked like it had stopped at
the edge of the file it was working in. It had not: two of the four are inside the "closed" file.
What bounds the coverage is the SHAPE, and the file boundary was a coincidence that lined up with
the wrong explanation. *A coincidence that corroborates a wrong theory is the expensive kind,
because it ends the search.*

## What the rule is, and what it deliberately is NOT

The population is derived from the code's own behaviour, not from a ledger anyone maintains:

> **SEED** — a `(model, attribute)` pair is *protected* if at least one function writes it with every
> mention of that attribute inside `with pid_lock.mutating(...)`.
> **RULE** — every other writer of that same `(model, attribute)` must be inside the lock too.

**This finds INCONSISTENT protection, not ABSENT protection, and the difference is not a weakness to
paper over — it is why this file and `test_rmw_sweep` are both necessary.** A field with no locked
writer anywhere never enters the seed, so this gate cannot speak about it at all; `test_rmw_sweep`
reaches those through a different derivation, naming the read-modify-writes among them. Each
derivation is blind where the other sees. A future instance must now evade both.

(`Project.dev_budget` used to be the example here, described as having "no lock anywhere". That
stopped being true in this very change — `_finalize_generated`'s seed is now locked — while the
sentence claiming it stayed. It is a *different* case now, and the section below says which. **Two
paragraphs of one docstring disagreeing about one field is the same defect this tree fixed in the
threat model a day earlier**, and it took a re-read to catch, not a test.)

## The SEED can fail open too — found here, and closed here

**This section described a live blind spot; it now records the fix, which is what it asked its next
reader to do.** `generate._finalize_generated` wrote `.dev_budget` entirely inside the lock, but
received `p` as an UN-ANNOTATED parameter — so the analyser reported UNKNOWN, the pair
`(Project, dev_budget)` never entered the seed, and the three unlocked writers in
`routers/proforma.py` went unreported. The gate said nothing about the one field in the tree that had
both a locked writer and unlocked ones.

The asymmetry is the lesson and it outlives the instance: **UNKNOWN is fail-CLOSED where it could
excuse an unlocked write, and was fail-OPEN where it could establish that a field is protected at
all.** *A predicate that decides what to LOOK at is more dangerous than one that decides what to
report* — and the seed is exactly such a predicate, so this file was not exempt from the rule it was
written to enforce.

Closed by binding form 5 below (a parameter's type annotation), which put the pair in the seed, which
immediately reported the three `proforma` writers — all now under `pid_lock.mutating(pid)`. The fix
had to be both halves: the form alone would have reported three violations and shipped red, and the
locks alone would have left the gate unable to see whether they stayed. **Note which half found
which:** the annotation was a one-line change to a signature, and it is what turned a silent gate
into one that named three live defects.

## Fail closed, and the exact shape of "closed"

A receiver this analyser cannot resolve to a mapped model is UNKNOWN. An UNKNOWN receiver **cannot be
used to excuse an unlocked write**: UNKNOWN-and-unlocked on a protected attribute NAME is a failure,
because the analyser cannot rule out that it is the protected model. UNKNOWN-and-locked passes —
whatever model it is, it is serialised, so the identity does not change the verdict.

Resolving the receiver is load-bearing rather than tidy, and that was established by a false positive
rather than assumed: `modules.save_view` writes `.config`, which matches `Connection.config` by name,
but `v` there is a `SavedView` from `get_or_create_by_key` — a per-user saved view replaced wholesale
from an already-validated body, with no relationship to the connection blob. A name-only rule would
have demanded a lock on it.

Four binding forms are supported, and **every one of them was added because a probe reported UNKNOWN
rather than because it was anticipated** — which is the argument for failing closed rather than
guessing. A resolver that guesses turns each of these into a confident wrong model name:

  1. `p = db.get(Project, pid)` — inline.
  2. `from ..models import Project as _P` then `db.get(_P, pid)` — **import aliasing**. Without it
     `_P` and `Project` are two different models and the pair never matches.
  3. `v, _created = auth.get_or_create_by_key(db, SavedView, ...)` — the model is a call ARGUMENT,
     and the callee is an *attribute* (`auth.…`), not a bare name. A first draft keyed on
     `isinstance(func, ast.Name)` and silently missed it.
  4. `p = _project(db, pid)` where `_project` is `from .authoring_shared import project_with_source
     as _project` — an aliased import of a helper in ANOTHER module, resolved through its return
     annotation. A first draft looked for a module-local `def` and left 13 sites unresolved.
  5. `def _finalize_generated(db, p: Project, ...)` — a PARAMETER's annotation. Added to close the
     seed blind spot described above; a helper taking an already-fetched row is a normal shape, and
     without this form every one of them is UNKNOWN and can never establish that a field is
     protected.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_lock_boundary.py
"""
from __future__ import annotations

import ast
import os
import pathlib
import shutil
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./_lockboundary_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_lockboundary")

HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "data" / "src"))

from sqlalchemy.orm import configure_mappers

import aec_api.models  # noqa: E402,F401  -- importing it is what populates the mapper registry
from aec_api.db import Base  # noqa: E402

#: Every mapped class name, read from SQLAlchemy's registry rather than listed here. A list would be
#: a copy, and a copy is what drifts.
#: `configure_mappers()` is REQUIRED before reading the registry: mappers configure lazily, and the
#: first probe of `m.attrs` on an unconfigured one returned 0 of 183. `MODELS` is what every receiver
#: resolution is checked against, so an unconfigured registry would leave it empty, resolve nothing,
#: and produce an empty SEED -- a gate reporting on nothing while printing a clean verdict. The
#: self-tests below assert it is populated before any verdict prints.
configure_mappers()
MODELS: set[str] = {m.class_.__name__ for m in Base.registry.mappers}

#: A receiver PROVED not to be a mapped instance -- distinct from `None`, which means "unresolved"
#: and fails closed. Only a derivation that cannot be wrong may use this.
NOT_A_MODEL = "<not-a-model>"

#: A DYNAMIC attribute write -- `setattr(obj, k, v)`, where `k` is a runtime value. The attribute
#: cannot be named, so such a site never SEEDS a protected pair; it is only ever judged against pairs
#: something else seeded. See `dynamic_writes`.
DYNAMIC_ATTR = "<setattr>"

#: DECLARED non-model receivers: (repo-relative path, function, local variable) -> why.
#:
#: Everything not named here that the analyser cannot resolve is UNKNOWN, which reds the build. That
#: is the point: the alternative -- inferring "not a model" from the shape of the binding -- is what
#: round 6 shipped and round 8 removed, because an inference that decides what to STOP asking about
#: is invisible in its own output. **A declaration is auditable and an inference is not**, and the
#: cost of the stricter rule is bounded by how many sites actually need it, which is measured
#: (deleting this ledger reds exactly one site) rather than assumed.
#:
#: An entry that no longer matches a live unresolved receiver reds too, so the ledger cannot rot
#: into a list of exemptions for code that has moved -- the failure mode `test_unique_read_guard`'s
#: exemption list is checked against for the same reason.
NON_MODEL_RECEIVERS: dict[tuple[str, str, str], str] = {
    ("services/data/src/aec_data/massing.py", "stamp_conformance", "fn"):
        "`fn = header.file_name` on an ifcopenshell file header. `header` comes from `model.header` "
        "where `model` is an `ifcopenshell.file`; the `.name` it writes is the IFC header's "
        "FILE_NAME field, which collides by name with the protected `Connection.name` and nothing "
        "else. aec_data has no ORM session and this function never touches one.",
    #: Three more arrived with `dynamic_writes` -- the `setattr` receivers. Each is declared rather
    #: than inferred, for the reason the paragraph above gives, and each states what the object IS.
    ("services/api/src/aec_api/bcf_io.py", "import_bcfzip", "existing"):
        "`existing = next((v for v in topic.viewpoints if v.camera is not None), None)` -- a mapped "
        "`Viewpoint`, reached through a generator over a relationship, which none of the five "
        "binding forms expresses. Declaring it is the honest option and costs nothing here: "
        "`Viewpoint` has no protected attribute, so resolving it would change no verdict. The "
        "SIBLING receiver in the same function, `topic`, DOES resolve -- through form 3, "
        "`auth.get_or_create_by_key(db, Topic, ...)` -- which is why only this one is listed.",
    ("services/data/src/aec_data/cost_ifc.py", "_quantity", "q"):
        "`q = model.create_entity(...)` on an `ifcopenshell.file`. The attribute written is an IFC "
        "quantity field named by `QUANTITY_KINDS[basis]['attr']`; there is no ORM session in "
        "aec_data and no mapped instance anywhere in this call.",
    ("services/data/src/aec_data/ifcpatch_lib.py", "convert_length_unit", "e"):
        "`for e in entities` over ifcopenshell entities, rescaling IFC length attributes by a unit "
        "ratio. Same reason as `_quantity` above: an IFC entity, not a mapped row.",
}

SRC_ROOTS = [HERE / "src", HERE.parent / "data" / "src"]

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail if not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the analyser -----------------------------------------------------------------------------

def _own_nodes(node: ast.AST):
    """Every node lexically inside `node` WITHOUT descending into nested function bodies.

    Scope is the point. `_alias_map` and `pid_lock_names` used `ast.walk` over the whole file, so a
    function-local `from .. import pid_lock` -- which is how most of this tree spells it -- became a
    binding for EVERY function in that file. One function's alias could then certify another's
    `lock.mutating(...)`, or resolve another's receiver to the wrong mapped model. *A binding that
    is not scoped the way Python scopes it is a fact about the wrong program.*
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(n))


def _lock_import_names(node: ast.AST) -> dict[str, str]:
    """{name: "module" | "mutating"} for every name `node` binds to the PROJECT LOCK.

    THE ONE PLACE that decides what an import of the lock looks like. `pid_lock_names` reads it and
    `_bound_names` reads it in the negative, so the two cannot drift into disagreeing -- which they
    did, in both directions at once, in round 12:

      * **Fail-open.** Matching `a.name == "pid_lock"` from ANY module certified
        `from .fakes import pid_lock` as the project lock. The `import_shadow` probe missed it
        because that probe renames (`stub as pid_lock`) and this one does not -- *a probe written
        against one spelling of a substitution does not cover the substitution.*
      * **Fail-closed, and contrary to the docstring.** `from ..pid_lock import mutating` bound no
        lock name here, so `_bound_names(skip_lock_imports=True)` added `"mutating"` to the shadow
        set and `pid_lock_names` could never return `bare=True`. The form its own docstring promised
        to accept had become unreachable -- **a regression introduced by the shadowing fix itself**,
        invisible because nothing in this tree spells it that way.

    The source module is what distinguishes them. `pid_lock` lives at `aec_api/pid_lock.py` and
    every importer in this tree spells it `from . import pid_lock` or `from .. import pid_lock`
    (module `None` with a non-zero `level`, verified by grep), so binding the MODULE requires the
    lock's own package.

    **EXACT MODULE PATHS, NOT A SUFFIX, and the first version of this function used a suffix.** It
    read `(node.module or "").endswith("pid_lock")`, which accepts `from .fake_pid_lock import
    mutating`, `from .fakes.pid_lock import mutating` and `from tests.pid_lock import mutating` --
    and the `ast.Import` branch matched `a.name.split(".")[-1]`, which certifies
    `import fakes.pid_lock as pid_lock`. **That is the very fail-open this function was written to
    close, surviving in the two spellings the fix did not look at**: round 13 closed it for
    `from <somewhere> import pid_lock` and left it open for the bare `mutating` form and the
    `import` form. *A fix aimed at the spelling that was reported closes that spelling* — the rule
    the paragraph above states ("the source module is what distinguishes them") was right, and the
    code underneath it went on matching a suffix, so the docstring was true and the test was not.

    The `ast.Import` branch also recorded a binding Python does not make: without `as`,
    `import aec_api.pid_lock` binds **`aec_api`**, not `pid_lock`. It is now accepted only when
    aliased, which is the only form that binds a usable name.
    """
    out: dict[str, str] = {}
    if isinstance(node, ast.ImportFrom):
        #: `from . import pid_lock` / `from .. import pid_lock` (relative, no module), or the
        #: absolute `from aec_api import pid_lock`. Nothing else names the lock's package.
        from_lock_pkg = (node.module is None and node.level > 0) or (
            node.module == "aec_api" and node.level == 0)
        #: `from ..pid_lock import mutating` (relative) or `from aec_api.pid_lock import mutating`.
        from_lock_mod = (node.module == "pid_lock" and node.level > 0) or (
            node.module == "aec_api.pid_lock" and node.level == 0)
        for a in node.names:
            if a.name == "pid_lock" and from_lock_pkg:
                out[a.asname or a.name] = "module"
            elif a.name == "mutating" and from_lock_mod:
                out[a.asname or a.name] = "mutating"
    elif isinstance(node, ast.Import):
        for a in node.names:
            if a.name == "aec_api.pid_lock" and a.asname:
                out[a.asname] = "module"
    return out


def _bound_names(scope: ast.AST, *, skip_lock_imports: bool = False) -> set[str]:
    """Every name `scope` BINDS in its own body, derived from the grammar rather than enumerated.

    This is the third time a rule in this analyser was written as a list of statement types, and the
    third time the list was short. `_stored_attrs` moved from `Assign`/`AnnAssign`/`AugAssign` to
    `ctx=Store` because tuple, starred, `for` and `with` targets are not any of those; the shadowing
    check in `pid_lock_names` then repeated the mistake with the same three types plus two, and
    still certified an arbitrary object as the project lock for `pid_lock, _x = other, 1`,
    `from .fakes import stub as pid_lock`, `except Exception as pid_lock:`, a nested
    `def pid_lock(...)`, and a module-level rebinding after the import. **The fix for an incomplete
    enumeration is not a longer enumeration** -- ask the grammar:

      * `ctx=Store` on `ast.Name` is the exact, complete marking of a name assignment in EVERY
        spelling, the same fact `_stored_attrs` leans on one node type over;
      * the binding forms that carry their name as a plain `str` field rather than as a `Name` node
        -- `ExceptHandler.name`, `FunctionDef/AsyncFunctionDef/ClassDef.name`, import aliases,
        `global`/`nonlocal`, and the MATCH-pattern captures `MatchAs.name`, `MatchStar.name` and
        `MatchMapping.rest` -- are named explicitly, because the grammar gives no other handle on
        them.

    **The first draft of this docstring said that list was "closed by the language" and it named
    four of the seven.** `case pid_lock:` binds the name through `MatchAs`, which carries no `Name`
    node at all, so a captured object was certified as the project lock. *A completeness claim about
    a hand-written list is a claim the list cannot check* -- the same failure as the statement-type
    enumeration this function replaced, one layer up, and it was made in the sentence explaining why
    enumerations fail. The three match forms are now here; the honest statement is that this list is
    as complete as the last reading of the grammar, not that it cannot be short again.

    Scoped with `_own_nodes`, so a nested body binds in ITS scope and not in this one -- the rule
    every traversal here has had to learn. A comprehension target is counted as bound although
    Python scopes it to the comprehension: that over-marks, which for both callers means refusing to
    resolve or refusing to certify, and a certifier's safe direction is to refuse.
    """
    out: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        a = scope.args
        for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs,
                    *([a.vararg] if a.vararg else []), *([a.kwarg] if a.kwarg else [])]:
            out.add(arg.arg)
    for n in _own_nodes(scope):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            out.add(n.rest)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            lockish = _lock_import_names(n)          # {name: "module"|"mutating"}
            for al in n.names:
                if al.name == "*":
                    continue
                bound = al.asname or (al.name if isinstance(n, ast.ImportFrom)
                                      else al.name.split(".")[0])
                if skip_lock_imports and bound in lockish:
                    continue
                out.add(bound)
    return out


def _imports_of(nodes) -> dict[str, tuple[str, str]]:
    """local name -> (module, original name) for the import statements among `nodes`."""
    out: dict[str, tuple[str, str]] = {}
    for n in nodes:
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out[a.asname or a.name] = (n.module or "", a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name] = ("", a.name)
    return out


_PARENTS: dict[int, dict] = {}       #: id(tree) -> {child: parent}, built once per module


def _scope_chain(tree: ast.AST, fn: ast.AST | None) -> list[ast.AST]:
    """`fn` and every function lexically enclosing it, OUTERMOST first, or [] when `fn` is None.

    A nested function closes over its enclosing function's names, so its visible bindings are the
    chain, not just its own body -- `content_import` binds `p` and `_content_import_locked` uses it.
    Shadowing then falls out of applying the chain in order.
    """
    if fn is None:
        return []
    #: Memoised per tree: this is called three times per function and rebuilding the parent map each
    #: time made the whole scan quadratic (the first version did not finish in two minutes).
    parent = _PARENTS.get(id(tree))
    if parent is None:
        parent = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        _PARENTS[id(tree)] = parent
    chain, cur = [], fn
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chain.append(cur)
        cur = parent.get(cur)
    return list(reversed(chain))


def _alias_map(tree: ast.AST, fn: ast.AST | None = None) -> dict[str, tuple[str, str]]:
    """Import bindings visible inside `fn`: module level, then each enclosing scope, then `fn`."""
    out = _imports_of(_own_nodes(tree))
    for scope in _scope_chain(tree, fn):
        out.update(_imports_of(_own_nodes(scope)))
    return out


def _return_types(tree: ast.AST) -> dict[str, str]:
    """function name -> its return annotation, when that annotation is a bare name."""
    return {n.name: n.returns.id
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(n.returns, ast.Name)}


def _model_of_call(call: ast.Call, alias: dict) -> str | None:
    """The mapped model this call yields, or None.

    Scans the positional arguments for a name that resolves to a mapped model. That covers
    `db.get(Project, pid)`, `db.query(Project)` and `auth.get_or_create_by_key(db, SavedView, ...)`
    with one rule instead of three, and does not care whether the callee is `f` or `mod.f` --
    the distinction a first draft keyed on and lost `save_view` to.
    """
    for arg in call.args:
        if isinstance(arg, ast.Name):
            resolved = alias.get(arg.id, ("", arg.id))[1]
            if resolved in MODELS:
                return resolved
    return None


def _stored_attrs(fn: ast.AST):
    """Every SYNTACTIC `<name>.<attr>` write in `fn`, derived from the LANGUAGE, not enumerated.

    **"Syntactic" is load-bearing and was missing from this sentence.** `ctx=Store` is the exact,
    complete marking of an attribute write *in the grammar* -- and `setattr(obj, k, v)` is an
    attribute write the grammar does not spell as one, so it carries no `Store` and no `Attribute`
    and this function cannot see it however carefully it reads the AST. One live route swapped the
    protected `Project.source_ifc` that way. `dynamic_writes` covers them; see its docstring.

    An attribute write is not a list of statement types -- it is `ast.Attribute` carrying
    `ctx=Store`, which is how Python itself marks one, in every form it has. Round 7 replaced a
    one-form matcher (`ast.Assign`) with a three-form one (`+AnnAssign, +AugAssign`) and that was
    the same mistake one size larger: *the fix for an incomplete enumeration is not a longer
    enumeration.* Five further spellings were still invisible and the gate ACCEPTED each --

        p.x, q.y = a, b          # a Tuple target; the top-level target is not an Attribute
        p.x, *rest = a
        (p.x, (q.y, r.z)) = v    # nested arbitrarily deep
        for p.x in seq: ...      # `For.target`, reached by no assignment statement at all
        with ctx as p.x: ...     # `withitem.optional_vars`, likewise
        [i for p.x in seq]       # a comprehension target, likewise

    -- all legal Python, all writes, none of them an `Assign`/`AnnAssign`/`AugAssign` target.
    `ctx=Store` admits every one of them and admits nothing else: a read (`v = p.x`), a call
    argument (`f(p.x)`) and `del p.x` carry `Load`, `Load` and `Del`. There is no seventh form to
    miss, because the set is no longer a list somebody maintains.

    **The receiver is NOT filtered here, and that restriction was this function's own defect.**
    The first draft yielded only `<Name>.attr`, so `ctx.project.source_ifc = v` -- whose outer node
    carries `Store` exactly like any other write, but whose receiver is an `ast.Attribute` -- never
    entered the site list at all and the gate ACCEPTED it. *A completeness claim followed by a
    filter is no longer a completeness claim*: the docstring above argued the set is the grammar's
    own and then narrowed it one line later, which is the same shape as the two enumerations it
    replaced. Deciding whether a receiver resolves is `collect`'s job, and an unresolvable one is
    reported UNKNOWN, which reds -- so the narrow version traded a fail-CLOSED report for silence.
    """
    #: `_own_nodes`, not `ast.walk`: a write inside a NESTED function belongs to that function, which
    #: `collect` visits in its own right. Walking into nested bodies attributed the write to the
    #: enclosing function while the scope maps stopped at the boundary -- so a locked write in an
    #: inner helper (the `run_in_threadpool` shape used by every `async def` route here) was reported
    #: unlocked. *Two traversals over the same tree must agree on where a function ends.*
    for n in _own_nodes(fn):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store):
            yield n


def dynamic_writes(fn: ast.AST):
    """Every `setattr(<name>, ...)` in this function -- an attribute write with no attribute name.

    `_stored_attrs` asks the grammar for `ctx=Store`, which is exact and complete **for writes the
    grammar expresses as writes**. `setattr()` is an ordinary function call: it has no `Store`
    context, no `Attribute` node, and nothing about it says "assignment" to an AST walker. So the
    one route that can swap `Project.source_ifc` through a PATCH body -- `bim.patch_project`, which
    loops `setattr(p, k, v)` over a validated `ProjectPatch` that declares `source_ifc` -- was
    invisible to this analyser while being exactly the writer it exists to find.

    *A derivation that asks the grammar is only as complete as the grammar's own account of what it
    is looking for*, and "attribute write" is a concept the language spells two ways: syntactically,
    and through the reflection API. The docstring of `_stored_attrs` claimed the first was every
    spelling; it is every SYNTACTIC spelling, which is a different and smaller claim.

    Bounded, and measured rather than assumed: seven `setattr` sites exist in the whole tree, one on
    a `Project` and the rest on `Topic` or on ifcopenshell entities. A receiver that does not resolve
    is reported UNKNOWN like any other, which is what puts the aec_data ones in the declared ledger
    rather than in silence.
    """
    for n in _own_nodes(fn):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "setattr" and n.args):
            yield n


def _rel(p: pathlib.Path) -> str:
    """Repo-relative path, or the bare path when `p` is outside the tree (the self-test probe)."""
    #: `.as_posix()`, not `str()`: on Windows -- which is where this repository is developed --
    #: `str()` yields backslashes, and `_bindings` compares that against the `/`-separated keys in
    #: `NON_MODEL_RECEIVERS`. The declared exemption would never match, `stamp_conformance`'s `fn`
    #: would fall through to UNRESOLVED, and the REAL-TREE verdict would red -- while the ledger
    #: self-test kept passing, because that one normalises separators before comparing. *A check
    #: that normalises in one place and not the other is green where it looks and red where it runs.*
    return _posix_rel(p, HERE.parent.parent)


def _posix_rel(p, root) -> str:
    """`p` relative to `root`, ALWAYS with `/` separators -- the separable half of `_rel`.

    Split out so the self-test can call it with `PureWindowsPath`s, which are platform-independent.
    The first draft of that check asserted the property against `PureWindowsPath` directly and never
    touched this code, so reverting the fix red NOTHING: **a static check that still passes with the
    guard removed is not testing the guard** -- the rule this file states about `_system_field` and
    then broke about itself, one round later. The mutation now reaches the code under test.
    """
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.as_posix()


CONFLICT = "<conflicting-binds>"

#: A name this scope BINDS but whose model the analyser could not pin down -- a bare parameter, a
#: `for` target, a value from a helper with no annotated return. Distinct from "absent": absent means
#: the enclosing scope's binding is still in force, and this means it is NOT, because Python has
#: rebound the name here. Dropping these at the end of `_bindings` -- which is what CONFLICT used to
#: do -- let `collect`'s scope merge fall back to the OUTER model for a name the inner scope had
#: taken over, so an unlocked write reached neither the violations nor the unknowns. *A sentinel that
#: is filtered before the merge cannot shadow anything; the filter has to run AFTER the last merge.*
UNRESOLVED = "<unresolved-local>"


def _resolved(binds: dict[str, str]) -> dict[str, str]:
    """Drop every name that means two models or none, AFTER the whole scope chain has been merged.

    The two sentinels are opposites -- one name with too many meanings, one with too few -- and both
    resolve to the same verdict: the receiver is UNKNOWN, which is fail-CLOSED and reds the build.
    """
    return {k: v for k, v in binds.items() if v not in (CONFLICT, UNRESOLVED)}


def _bind(out: dict, name: str, model: str) -> None:
    """Bind `name` to `model`, or to CONFLICT when it already means a DIFFERENT model here.

    `_bindings` used to keep the LAST binding and `collect` applied it to every write in the
    function -- so in

        p = db.get(Project, pid)
        p.source_ifc = v            # a Project write...
        p = db.get(SavedView, vid)  # ...reclassified as a SavedView one by a later line

    the unlocked `Project.source_ifc` write left the violations entirely, and the `seen` set could
    merge the two sites so only one was ever considered. *A binding read at the END of a function
    is not the binding in force in the MIDDLE of it.*

    Resolving each site by source position would need real flow analysis; refusing to resolve a name
    that means two things does not, and errs the only safe way -- the receiver becomes UNKNOWN, which
    is fail-CLOSED and reds. A name with one consistent meaning, which is every real site in this
    tree, is unaffected.
    """
    prev = out.get(name)
    out[name] = CONFLICT if (prev is not None and prev != model) else model


def _bindings(fn: ast.AST, alias: dict, local_types: dict, foreign_types: dict,
              relpath: str = "") -> dict[str, str]:
    """local variable -> mapped model name, for the five forms the module docstring lists."""
    out: dict[str, str] = {}
    #: Form 7: a DECLARED non-model receiver. Not inferred -- declared, in `NON_MODEL_RECEIVERS`
    #: above, with a stated reason and a self-test that the site still exists.
    #:
    #: Round 6 inferred this instead: "a variable bound from an attribute chain touching no mapped
    #: attribute name cannot be a mapped instance, because reaching one by attribute access means
    #: traversing a mapped relationship." That reads like a proof and is not one. It holds for
    #: chains *through the ORM* and says nothing about a chain through anything else: `p = ctx.row`
    #: on a plain container holding a `Project` touches no mapped attribute name and is a mapped
    #: instance. **The rule was a fail-OPEN wearing the shape of a proof, and it applied tree-wide**
    #: -- the same defect as the module predicate it replaced, one layer smaller and better argued.
    #:
    #: The population it was carrying turned out to be ONE site, which is what makes declaring
    #: viable: a rule demanding many declarations gets abandoned half-done, a rule demanding one
    #: does not. Everything else now falls through to UNKNOWN, which is fail-CLOSED and reds.
    #:
    #: This matcher and the model-resolving one below are BOTH `ast.Assign`-only, deliberately, and
    #: that is not the defect `_stored_attrs` fixes. They fail CLOSED: a binding form they miss
    #: leaves the receiver unresolved, the site is reported UNKNOWN and the build reds. `collect`
    #: was the only place a missed spelling meant a write was never LOOKED at. *Whether an
    #: incomplete matcher is a hole depends entirely on which direction its silence points.*
    for (decl_path, decl_fn, decl_var) in NON_MODEL_RECEIVERS:
        if decl_path == relpath and decl_fn == getattr(fn, "name", None):
            out.setdefault(decl_var, NOT_A_MODEL)
    #: Form 5: a PARAMETER whose annotation names a model. Added to close this gate's own seed blind
    #: spot: `generate._finalize_generated` locks `.dev_budget` but received `p` unannotated, so the
    #: pair never entered the seed and three unlocked writers of it went unreported. A helper that
    #: takes an already-fetched row is a normal shape, and without this every one of them is UNKNOWN.
    for arg in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]:
        if isinstance(arg.annotation, ast.Name):
            resolved = alias.get(arg.annotation.id, ("", arg.annotation.id))[1]
            if resolved in MODELS:
                out[arg.arg] = resolved
    #: `_own_nodes`, matching `_stored_attrs`. With `ast.walk` this descended into nested functions,
    #: so a name rebound inside a HELPER polluted the enclosing function's map -- and once `_bind`
    #: exists, that pollution is a fail-OPEN rather than a mere inaccuracy: the enclosing locked
    #: write's receiver becomes CONFLICT, its `(model, attribute)` pair never enters the SEED, and an
    #: unlocked writer of that same pair elsewhere is then not a violation because nothing protects
    #: it. *The conflict rule and the over-wide traversal were each defensible alone and a hole
    #: together* -- and `collect` already accumulates bindings down the scope chain, so a nested
    #: function still inherits its caller's receiver. Third instance of one lesson: **every traversal
    #: in this analyser must agree on where a function ends.**
    for n in _own_nodes(fn):
        if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
            continue
        names = [t.id for t in n.targets if isinstance(t, ast.Name)]
        if not names and isinstance(n.targets[0], ast.Tuple):       # `v, _created = helper(...)`
            names = [e.id for e in n.targets[0].elts if isinstance(e, ast.Name)][:1]
        if not names:
            continue
        if (model := _model_of_call(n.value, alias)):
            _bind(out, names[0], model)
            continue
        fnc = n.value.func                       # ...otherwise a helper whose RETURN TYPE names one
        if isinstance(fnc, ast.Name):
            if (t := local_types.get(fnc.id)) and t in MODELS:
                _bind(out, names[0], t)
            elif fnc.id in alias:
                mod, real = alias[fnc.id]
                if (t := foreign_types.get((mod.rsplit(".", 1)[-1], real))) and t in MODELS:
                    _bind(out, names[0], t)
    #: Everything else this scope binds and none of the forms above could resolve. Recording it is
    #: what makes the scope merge in `collect` a SHADOWING merge rather than an inheriting one: the
    #: five forms resolve a minority of locals, and for the rest the honest answer is "this name
    #: means something local that I cannot name", not "this name still means whatever the enclosing
    #: function fetched". The sentinels survive the merge and `_resolved` removes them at the end.
    for name in _bound_names(fn):
        out.setdefault(name, UNRESOLVED)
    return out


def pid_lock_names(tree: ast.AST, fn: ast.AST | None = None) -> tuple[set[str], set[str]]:
    """Which names in this module mean the `pid_lock` MODULE, and is `mutating` imported bare?

    Every call site in this tree spells it `from .. import pid_lock` (often function-locally) and
    then `pid_lock.mutating(...)`, so the module name is what has to be resolved. The bare-`mutating`
    half is accepted too, for the `from ..pid_lock import mutating` form that nothing uses today --
    a rule that only admits the one spelling in the tree would fail CLOSED on the other, which is
    safe, but would also be a lie about what the lock is.
    """
    names: set[str] = set()
    chain = _scope_chain(tree, fn)
    nodes = list(_own_nodes(tree))
    for scope in chain:
        nodes += list(_own_nodes(scope))
    #: ONE recognition rule, read from `_lock_import_names` rather than restated here -- the two
    #: copies disagreed in both directions at once until round 13. See that function's docstring.
    bare_names: set[str] = set()
    for n in nodes:
        for nm, kind in _lock_import_names(n).items():
            if kind == "module":
                names.add(nm)
            else:
                bare_names.add(nm)

    #: SHADOWING. `def writer(p, pid_lock):` binds a PARAMETER of that name, and Python resolves the
    #: `with pid_lock.mutating(...)` inside it to the parameter -- not to the imported module. So did
    #: `pid_lock = other`. The analyser still had "pid_lock" in `lock_names` and certified an
    #: arbitrary object as the project lock. The `impostor_alias` probe missed this because it tests
    #: a name bound in a DIFFERENT function; *the dangerous case is the same scope, where the name
    #: is right and the binding is wrong.* Removed rather than resolved: this is a certifier, and
    #: refusing a name it cannot prove is the module is the fail-CLOSED direction.
    #: `_bound_names`, not a list of statement types -- see its docstring. The first version of this
    #: check named five and still certified an arbitrary object as the project lock for a tuple
    #: target, a non-lock import under the name, an `except ... as`, a nested `def`, and a
    #: module-level rebinding. **MODULE SCOPE IS IN THE LIST**: `chain` holds only functions, so
    #: `pid_lock = _install_double()` beside the import was invisible to a per-function scan while
    #: being the one rebinding that affects every function in the file.
    shadowed: set[str] = set()
    for scope in [tree, *chain]:
        shadowed |= _bound_names(scope, skip_lock_imports=True)
    #: The bare form returns the NAMES it bound, not a boolean. Collecting them and then answering
    #: yes/no was this file's own recurring failure one more time: `is_the_lock` fell back to the
    #: literal spelling `mutating`, so `from ..pid_lock import mutating as held` plus a PARAMETER
    #: named `mutating` certified the parameter -- `bare_names` was {"held"}, `shadowed` held
    #: "mutating", the intersection was empty, and the flag said yes about a name nobody had bound
    #: to the lock. The genuine `held(pid)` was never certified at all, so the rule was wrong in
    #: both directions at once and the docstring promising the bare form was false.
    #: *Asking the right question and then throwing the answer away* -- the lesson
    #: `services/api/test_pin_pgnull.py` records, arriving here by a different door.
    return names - shadowed, bare_names - shadowed


def lock_spans(fn: ast.AST, attr: str, lock_names: set[str],
               bare_mutating: frozenset[str] | set[str] = frozenset(),
               nodes: set[int] | None = None) -> tuple[bool, list[int]]:
    """Is EVERY mention of `attr` in this function inside `with pid_lock.mutating(...)`?

    With `nodes` -- a set of `id()`s -- it answers the same question about those NODES instead, for
    the dynamic `setattr(obj, k, v)` writers that have no attribute name to look for. Deliberately
    the same traversal rather than a second one beside it: this file has already paid twice for two
    walks disagreeing about where a function ends, and `lock_spans` was the walk that got missed.

    Same rule as `test_rmw_sweep.under_pid_lock`, and stricter than strictly necessary on purpose:
    a read kept outside the lock for logging would count. This function decides whether to CERTIFY,
    and the safe direction for a certifier is to refuse what it cannot prove -- *a certifier that
    reasons about which stragglers are harmless is one bad reading away from blessing one.*

    **The receiver is checked, not just the method name.** Until 2026-09-14 this matched any
    `<anything>.mutating(...)` -- so `with self.mutating(...)`, `with cursor.mutating(...)`, or a
    local object that happened to expose that method CERTIFIED every write in its body as locked.
    *A certifier that matches on a method NAME is trusting a string that anybody may define*, and it
    fails in the one direction a certifier must not: silently, and toward "yes". `lock_names` comes
    from the file's own imports, so a module with no `pid_lock` import certifies nothing at all.
    """
    outside: list[int] = []

    def is_the_lock(ctx: ast.AST) -> bool:
        if not isinstance(ctx, ast.Call):
            return False
        f = ctx.func
        if isinstance(f, ast.Attribute) and f.attr == "mutating":
            return isinstance(f.value, ast.Name) and f.value.id in lock_names
        #: Membership, not the literal `mutating`: only a name the lock's own import BOUND counts.
        return isinstance(f, ast.Name) and f.id in bare_mutating

    def walk(node: ast.AST, locked: bool) -> None:
        for ch in ast.iter_child_nodes(node):
            #: STOP at a nested function or class, exactly as `_stored_attrs` and `_bindings` do.
            #: This hand-rolled traversal descended into them, so a nested helper's UNLOCKED mention
            #: of the attribute made the ENCLOSING function's locked write report as unlocked -- and
            #: that write is what SEEDS the pair. Same seed-removal fail-open round 10 fixed in
            #: `_bindings`, in the one traversal that a grep for `ast.walk(fn)` could not find,
            #: *because this one is spelled by hand.* **Searching for a spelling is not searching for
            #: the property**, and the property is "descends into a nested scope".
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            here = locked
            if isinstance(ch, ast.With):
                here = here or any(is_the_lock(i.context_expr) for i in ch.items)
            mention = (id(ch) in nodes) if nodes is not None else (
                isinstance(ch, ast.Attribute) and ch.attr == attr)
            if mention and not here:
                outside.append(getattr(ch, "lineno", 0))
            walk(ch, here)

    walk(fn, False)
    return (not outside), outside


def touches_orm(tree: ast.AST) -> bool:
    """Could a value in this module BE a mapped instance at all?

    A module that never imports from `aec_api.models` and never takes a `Session` has no way to hold
    one, so an unresolved receiver there cannot be the protected model and must not be reported as a
    risk. Without this, `Connection.name` in the seed makes every `x.name = ...` in the IFC geometry
    code a suspect -- `aec_data.massing.stamp_conformance` and `schema_diag.__init__` both were.

    **This is a predicate that decides what to LOOK at, which is the dangerous kind** -- everything it
    excludes is invisible to the output. It is admissible only because it is DERIVED from the module's
    own imports rather than listed, and because what it excludes is provably incapable of the defect:
    no ORM import and no Session means no mapped instance. Widen it, never hand-list an exemption.
    """
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and "models" in n.module:
            return True
        if isinstance(n, ast.Name) and n.id == "Session":
            return True
        if isinstance(n, ast.Attribute) and n.attr == "Session":
            return True
    return False


def collect(roots: list[pathlib.Path]) -> list[tuple]:
    """Every `<name>.<attr> = ...` site: (path, function, model|None, attr, locked, outside_lines)."""
    files = [p for r in roots for p in r.rglob("*.py") if "__pycache__" not in str(p)]
    foreign: dict[tuple[str, str], str] = {}
    parsed: dict[pathlib.Path, ast.AST] = {}
    for p in files:
        try:
            parsed[p] = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for fname, rtype in _return_types(parsed[p]).items():
            foreign[(p.stem, fname)] = rtype

    sites: list[tuple] = []
    for p, tree in parsed.items():
        # NO MODULE-LEVEL SKIP. `touches_orm` used to stand here and it was this gate's own worst
        # defect: *a predicate that decides what to LOOK at is more dangerous than one that decides
        # what to report*, because everything it excludes is invisible to the output -- the exact
        # lesson CLAUDE.md records for `test_seeding_sweep`, quoted in that function's docstring and
        # then violated two lines below it. Its justification -- "no ORM import and no Session means
        # no mapped instance" -- is FALSE: `def stamp(p): p.source_ifc = v` holds one with neither.
        # Such a module was skipped whole, so the write never reached `verdicts` and could not be
        # reported UNKNOWN. The fail-closed rule was defeated one layer ABOVE the thing enforcing it.
        local_types = _return_types(tree)
        enclosing = {f: c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                     for f in ast.walk(c) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            #: Scoped to THIS function: module-level bindings with the function's own imports
            #: shadowing them. File-wide collection let one function's local import certify or
            #: mis-resolve another's. A function seeing no pid_lock import certifies nothing.
            alias = _alias_map(tree, fn)
            lock_names, bare_mutating = pid_lock_names(tree, fn)
            #: Bindings accumulate down the same chain, so a nested helper inherits the receiver its
            #: enclosing function fetched (`p = db.get(Project, pid)` outside, used inside).
            binds: dict[str, str] = {}
            for _scope in _scope_chain(tree, fn):
                binds.update(_bindings(_scope, alias, local_types, foreign, _rel(p)))
            #: Form 6, and the replacement for the module predicate: `self` inside a class. If the
            #: class IS mapped, `self` is that model -- which the old code could not see at all. If
            #: it is NOT mapped, `self` is provably not a mapped instance, because it is an instance
            #: of THAT class. Derived from the model registry, per receiver, and provable in both
            #: directions -- which is what the module-level predicate only claimed to be.
            if (cls := enclosing.get(fn)):
                binds["self"] = cls if cls in MODELS else NOT_A_MODEL
            #: AFTER the last merge, never inside `_bindings`. A name the inner scope rebinds must
            #: beat the enclosing scope's model even when the inner binding resolves to nothing --
            #: filtering the sentinels one scope at a time deleted exactly that information and let
            #: the outer model flow into a scope that had taken the name over.
            binds = _resolved(binds)
            seen: set[tuple[str, str]] = set()
            #: EVERY spelling of an attribute write, taken from `ctx=Store` rather than from a list
            #: of statement types -- see `_stored_attrs`. Matching `Assign` alone hid the annotated
            #: and augmented forms; matching those three hid tuple-unpacking, `for`, `with` and
            #: comprehension targets. *A population derived by matching one spelling of a thing
            #: silently excludes the others, and the exclusion never appears in the output* -- so
            #: stop spelling, and ask the grammar.
            for t in _stored_attrs(fn):
                #: A bare-Name receiver can be resolved; anything else (`ctx.project.source_ifc`,
                #: `rows[0].source_ifc`) cannot be, and is keyed by its own identity so it is
                #: reported UNKNOWN rather than dropped or merged with an unrelated site.
                if isinstance(t.value, ast.Name):
                    key, recv = t.value.id, binds.get(t.value.id)
                else:
                    key, recv = f"<expr:{id(t.value)}>", None
                if (key, t.attr) in seen:
                    continue
                seen.add((key, t.attr))
                ok, outside = lock_spans(fn, t.attr, lock_names, bare_mutating)
                sites.append((_rel(p), fn.name, recv, t.attr, ok, outside[:4]))
            #: ...and the writes the grammar does not spell as writes. `setattr(obj, k, v)` carries
            #: no `Store` and no `Attribute`, so `_stored_attrs` cannot see it however complete its
            #: reading of the grammar is -- see `dynamic_writes`. Judged by the same `lock_spans`,
            #: keyed on the CALL node rather than on an attribute name.
            for call in dynamic_writes(fn):
                tgt = call.args[0]
                recv = binds.get(tgt.id) if isinstance(tgt, ast.Name) else None
                ok, outside = lock_spans(fn, DYNAMIC_ATTR, lock_names, bare_mutating,
                                         nodes={id(call)})
                sites.append((_rel(p), fn.name, recv, DYNAMIC_ATTR, ok, outside[:4]))
    return sites


def verdicts(sites: list[tuple]) -> tuple[set, list, list]:
    """(protected pairs, violations, unknown-and-unlocked). Separate from `collect` so a mutation
    can be aimed at the JUDGEMENT without also disturbing the discovery -- the two are different
    questions, and `test_unique_read_guard` learned the hard way that asserting a site was REPORTED
    is not asserting it was CLASSIFIED."""
    #: `m != NOT_A_MODEL`: the sentinel is a non-empty string, so `if m` accepted it and a locked
    #: write through `self` in any NON-mapped class seeded a pair keyed on the sentinel. Harmless
    #: on its own -- nothing resolves TO it, so no violation could match -- but it put the sentinel's
    #: attribute into `prot_attrs`, which is what decides whether an UNRESOLVED receiver is worth
    #: reporting. *A sentinel that means "proved not a model" must not be spendable as a model.*
    protected = {(m, a) for _, _, m, a, ok, _ in sites
                 if m and m != NOT_A_MODEL and a != DYNAMIC_ATTR and ok}
    prot_attrs = {a for _, a in protected}
    prot_models = {m for m, _ in protected}
    #: A DYNAMIC write never SEEDS -- it cannot name the attribute it wrote, so `a != DYNAMIC_ATTR`
    #: above -- but it is judged against every pair something else seeded on that model. The rule is
    #: deliberately coarse in the fail-CLOSED direction: an unlocked `setattr` on a model that has
    #: ANY protected attribute is a violation, because the analyser cannot prove it wrote a
    #: different one. Measured rather than feared: this makes exactly one site in the tree a
    #: violation, `bim.patch_project`, whose `ProjectPatch` body really does declare `source_ifc`.
    violations = ([s for s in sites if s[2] and s[3] != DYNAMIC_ATTR
                   and (s[2], s[3]) in protected and not s[4]]
                  + [s for s in sites if s[3] == DYNAMIC_ATTR and s[2] in prot_models and not s[4]])
    unknown = ([s for s in sites if s[2] is None and s[3] != DYNAMIC_ATTR
                and s[3] in prot_attrs and not s[4]]
               + [s for s in sites if s[3] == DYNAMIC_ATTR and s[2] is None and not s[4]])
    return protected, violations, unknown


# --- self-tests: the analyser must find a planted defect before it may report on the tree -------

_SYNTH = ast.parse(
    #: The import is part of the fixture, not decoration: `lock_spans` resolves the `with` receiver
    #: against the file's own pid_lock bindings, so a synthetic module without this import would
    #: certify nothing and the SEED below would be empty -- which is exactly the vacuity the seed
    #: check guards against.
    "from .. import pid_lock\n"
    "def locked_writer(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = str(p.source_ifc) + '.v2'\n"
    "def sloppy_writer(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc = 'new'\n"
    "def other_model(db, k):\n"
    "    v = helper(db, SavedView)\n"
    "    v.source_ifc = 'x'\n"
    #: The receiver arrives as a bare parameter, so nothing in the function says what it is. This is
    #: `generate._finalize_generated`, reduced: it takes `p` from its caller. It exists here so the
    #: guessing mutation below has something to guess ABOUT -- the first draft of that mutation
    #: passed vacuously because every synthetic receiver resolved.
    "def opaque(thing):\n"
    "    thing.source_ifc = 'y'\n"
    #: SEVEN spellings of the same write, planted unlocked. The first two were invisible to the
    #: `ast.Assign`-only matcher; the last five were STILL invisible to the three-statement one that
    #: replaced it, because their target is not a top-level `Attribute` -- or, for `for`/`with`,
    #: is not an assignment statement at all. `AugAssign` is the sharpest of the seven: `x += y` is
    #: literally a read-modify-write, the shape this gate exists for. Narrowing `_stored_attrs`
    #: back to any statement list reds the checks below, naming the spellings it stopped seeing.
    "def annotated(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc: str = 'ann'\n"
    "def augmented(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc += '.v3'\n"
    "def unpacked(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc, _rest = 'tup', 1\n"
    "def nested_unpacked(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    (_a, (p.source_ifc, _c)) = (1, ('deep', 3))\n"
    "def starred(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc, *_tail = ['star', 1]\n"
    "def for_target(db, pid, rows):\n"
    "    p = db.get(Project, pid)\n"
    "    for p.source_ifc in rows:\n"
    "        pass\n"
    "def with_target(db, pid, ctx):\n"
    "    p = db.get(Project, pid)\n"
    "    with ctx as p.source_ifc:\n"
    "        pass\n"
    #: THE IMPOSTOR. Until 2026-09-14 `lock_spans` matched any `<anything>.mutating(...)`, so this
    #: function -- whose `session` is some unrelated object that happens to expose a method of that
    #: name -- CERTIFIED as locked and vanished from the violations. *A certifier that matches on a
    #: method NAME is trusting a string anybody may define.* It must now be reported.
    "def impostor_lock(db, pid, session):\n"
    "    p = db.get(Project, pid)\n"
    "    with session.mutating(pid):\n"
    "        p.source_ifc = 'not actually locked'\n"
    #: CHAINED RECEIVER. `ctx.project.source_ifc` carries `Store` like any write, but its receiver is
    #: an `ast.Attribute`. `_stored_attrs`' first draft required a bare `Name` and dropped it
    #: entirely -- accepted, not reported. It must now surface as UNKNOWN, which is fail-closed.
    "def chained_receiver(ctx):\n"
    "    ctx.project.source_ifc = 'chained'\n"
    #: ALIAS SCOPING, both directions. `aliased_lock` imports the lock under another name IN ITS OWN
    #: BODY and must still be certified. `impostor_alias` has a parameter of that name and no such
    #: import, so it must NOT be -- which is the leak the file-wide collection allowed: one
    #: function's local alias certifying every other function in the file.
    "def aliased_lock(db, pid):\n"
    "    from .. import pid_lock as lock\n"
    "    p = db.get(Project, pid)\n"
    "    with lock.mutating(pid):\n"
    "        p.source_ifc = 'genuinely locked, under an alias'\n"
    "def impostor_alias(db, pid, lock):\n"
    "    p = db.get(Project, pid)\n"
    "    with lock.mutating(pid):\n"
    "        p.source_ifc = 'certified by another function alias'\n"
    #: CONFLICTING BINDS. `p` means a Project for the first write and a SavedView for the second.
    #: Keeping the LAST binding reclassified the earlier `Project.source_ifc` write as a SavedView
    #: one and it left the violations. A name meaning two things now resolves to neither.
    "def rebound(db, pid, vid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.source_ifc = 'written while p is a Project'\n"
    "    p = db.get(SavedView, vid)\n"
    "    p.source_ifc = 'written while p is a SavedView'\n"
    #: SEED POISONING FROM A NESTED SCOPE. `seeder` is a correct locked writer and is the ONLY thing
    #: protecting `(Connection, config)` in this fixture. Its nested `_helper` rebinds the same name
    #: to another model. With `_bindings` walking into nested bodies, that rebinding marked `c`
    #: CONFLICT, the seed lost the pair, and `unlocked_after_seed` -- a genuine unlocked writer --
    #: stopped being a violation. **A fail-open that works by REMOVING a seed rather than by
    #: excusing a write**, which is why it survived every check aimed at the judgement.
    "def seeder(db, cid, vid):\n"
    "    c = db.get(Connection, cid)\n"
    "    with pid_lock.mutating(cid):\n"
    "        c.config = 'locked write that seeds the pair'\n"
    "    def _helper():\n"
    "        c = db.get(SavedView, vid)\n"
    "        return c\n"
    "    return _helper\n"
    "def unlocked_after_seed(db, cid):\n"
    "    c = db.get(Connection, cid)\n"
    "    c.config = 'must be a violation, and only is if the seed survived'\n"
    #: SEED LOSS THROUGH `lock_spans`, the third traversal. `span_seeder`'s own write is locked and
    #: seeds `(Project, prop_layers)`. Its nested `_leak` mentions the same attribute UNLOCKED. With
    #: `lock_spans` descending into nested bodies, that mention marked the OUTER write unlocked, the
    #: seed vanished, and `span_victim` stopped being a violation. Same shape as round 10's, in the
    #: one traversal spelled by hand rather than with `ast.walk`.
    "def span_seeder(db, pid, other):\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.prop_layers = 'locked, and this is the seed'\n"
    "    def _leak():\n"
    "        other.prop_layers = 'unlocked, and in a different scope'\n"
    "    return _leak\n"
    "def span_victim(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    p.prop_layers = 'must stay a violation'\n"
    #: SHADOWING IN THE SAME SCOPE. `impostor_alias` binds the name in a DIFFERENT function; these
    #: two bind it right here, which is the dangerous case -- the name is correct and the object is
    #: not. Python resolves both to the local binding, so neither is the project lock.
    "def param_shadow(db, pid, pid_lock):\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'a parameter is not the module'\n"
    "def local_shadow(db, pid, other):\n"
    "    p = db.get(Project, pid)\n"
    "    pid_lock = other\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'a rebinding is not the module'\n"
    #: FOUR MORE SPELLINGS OF THE SAME REBINDING, every one of them certified by the five-statement
    #: shadowing list that `param_shadow`/`local_shadow` were written against. A tuple target is not
    #: an `Assign` with a `Name` target; an import binds without any `Name` node at all; `except ...
    #: as` and a nested `def` carry their name as a plain string field. *Third time a rule here was
    #: a list of statement types and third time the list was short* -- hence `_bound_names`, which
    #: asks the grammar. Narrowing it back to statement types reds the violation list below by name.
    "def tuple_shadow(db, pid, other):\n"
    "    p = db.get(Project, pid)\n"
    "    pid_lock, _x = other, 1\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'a tuple target is still a rebinding'\n"
    "def import_shadow(db, pid):\n"
    "    from .fakes import stub as pid_lock\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'an import of something else, under the right name'\n"
    "def except_shadow(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    try:\n"
    "        pass\n"
    "    except Exception as pid_lock:\n"
    "        with pid_lock.mutating(pid):\n"
    "            p.source_ifc = 'an exception object is not the module'\n"
    "def nested_def_shadow(db, pid):\n"
    "    def pid_lock(_x):\n"
    "        return _x\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'a nested def is not the module either'\n"
    #: A MATCH CAPTURE, which is a FIFTH family and was missed by a list whose own docstring called
    #: itself closed by the language. `case pid_lock:` binds through `MatchAs.name` -- a plain `str`
    #: field, no `Name` node anywhere -- so the captured subject was certified as the project lock.
    "def match_shadow(db, pid, evt):\n"
    "    p = db.get(Project, pid)\n"
    "    match evt:\n"
    "        case pid_lock:\n"
    "            with pid_lock.mutating(pid):\n"
    "                p.source_ifc = 'a captured pattern name is not the module'\n"
    #: SUBSTITUTION WITHOUT RENAMING. `import_shadow` above imports something else UNDER the name;
    #: this imports the name itself from somewhere else. Matching on `a.name == "pid_lock"` from any
    #: module certified it. *A probe written against one spelling of a substitution does not cover
    #: the substitution* -- which is why the rule now asks where the import came FROM.
    "def fake_lock_import(db, pid):\n"
    "    from .fakes import pid_lock\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'imported from somewhere else entirely'\n"
    #: THE BARE FORM, which must be CERTIFIED. Nothing in this tree spells the lock this way, which
    #: is exactly why it needs a probe: the round-12 shadowing fix made `pid_lock_names` return
    #: `bare=False` unconditionally -- it added `"mutating"` to the shadow set because
    #: `_lock_import_names` did not recognise the import that bound it -- and the form this file's
    #: own docstring promises to accept became unreachable with nothing going red.
    "def bare_mutating(db, pid):\n"
    "    from ..pid_lock import mutating\n"
    "    p = db.get(Project, pid)\n"
    "    with mutating(pid):\n"
    "        p.source_ifc = 'the bare form, genuinely locked'\n"
    #: THE SAME SUBSTITUTION, IN THE TWO SPELLINGS ROUND 13's FIX DID NOT LOOK AT. Recognition was
    #: `endswith("pid_lock")` for the bare form and `split(".")[-1]` for `import`, so a module whose
    #: path merely ENDS in the lock's name certified: `from .fakes.pid_lock import mutating` and
    #: `import fakes.pid_lock as pid_lock`. *A fix aimed at the spelling that was reported closes
    #: that spelling* -- the docstring already said recognition is by SOURCE MODULE and the code
    #: under it went on matching a suffix, so the prose was true and the test was not.
    #: THE BARE FORM'S OWN NAME. `pid_lock_names` collected the names the lock's import bound and
    #: then answered yes/no, so `is_the_lock` fell back to the literal spelling: an ALIASED genuine
    #: import plus a PARAMETER called `mutating` certified the parameter, while the real `held`
    #: was never certified. Wrong in both directions from one discarded value.
    "def aliased_bare(db, pid):\n"
    "    from ..pid_lock import mutating as held\n"
    "    p = db.get(Project, pid)\n"
    "    with held(pid):\n"
    "        p.source_ifc = 'the aliased bare form, genuinely locked'\n"
    "def bare_alias_shadow(db, pid, mutating):\n"
    "    from ..pid_lock import mutating as held\n"
    "    p = db.get(Project, pid)\n"
    "    with mutating(pid):\n"
    "        p.source_ifc = 'a parameter named mutating is not the lock'\n"
    "def fake_bare_import(db, pid):\n"
    "    from .fakes.pid_lock import mutating\n"
    "    p = db.get(Project, pid)\n"
    "    with mutating(pid):\n"
    "        p.source_ifc = 'a module whose path merely ends in the lock name'\n"
    "def fake_module_import(db, pid):\n"
    "    import fakes.pid_lock as pid_lock\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'aliased from somewhere else entirely'\n"
    #: THE DYNAMIC WRITE, in all three of its verdicts. `setattr` carries no `Store` and no
    #: `Attribute`, so `_stored_attrs` cannot see it however completely it reads the grammar --
    #: `bim.patch_project` swapped the protected `Project.source_ifc` this way and was invisible.
    #: The locked one is here so the rule cannot pass by reporting every `setattr`, and the opaque
    #: one so an unresolvable receiver still fails CLOSED rather than being dropped.
    "def dynamic_writer(db, pid, changes):\n"
    "    p = db.get(Project, pid)\n"
    "    for k, v in changes.items():\n"
    "        setattr(p, k, v)\n"
    "def dynamic_locked(db, pid, changes):\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        for k, v in changes.items():\n"
    "            setattr(p, k, v)\n"
    "def dynamic_opaque(thing):\n"
    "    setattr(thing, 'whatever', 1)\n"
)

#: MODULE SCOPE, which needs its own fixture: a rebinding beside the import poisons every function
#: in the file, so planting one in `_SYNTH` would silently un-certify every probe above it and the
#: suite would still look green. `_scope_chain` yields functions only, so a per-function shadowing
#: scan could not see this at all.
_MOD_SHADOW = ast.parse(
    "from .. import pid_lock\n"
    "pid_lock = _install_test_double()\n"
    "def writer(db, pid):\n"
    "    p = db.get(Project, pid)\n"
    "    with pid_lock.mutating(pid):\n"
    "        p.source_ifc = 'certified by a name the module reassigned'\n"
)
_syn_types = _return_types(_SYNTH)
_syn_sites = []
for _fn in ast.walk(_SYNTH):
    if isinstance(_fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _syn_alias = _alias_map(_SYNTH, _fn)            # scoped exactly as `collect` scopes it
        _syn_lock_names, _syn_bare = pid_lock_names(_SYNTH, _fn)
        _b: dict[str, str] = {}                     # merged down the chain, filtered AFTER -- as
        for _sc in _scope_chain(_SYNTH, _fn):       # `collect` does, so the two cannot drift apart
            _b.update(_bindings(_sc, _syn_alias, _syn_types, {}, "synth.py"))
        _b = _resolved(_b)
        for _t in _stored_attrs(_fn):
            _recv = _b.get(_t.value.id) if isinstance(_t.value, ast.Name) else None
            _ok, _out = lock_spans(_fn, _t.attr, _syn_lock_names, _syn_bare)
            _syn_sites.append(("synth.py", _fn.name, _recv, _t.attr, _ok, _out))
        for _c in dynamic_writes(_fn):                  # mirrors `collect` -- see its comment
            _tgt = _c.args[0]
            _recv = _b.get(_tgt.id) if isinstance(_tgt, ast.Name) else None
            _ok, _out = lock_spans(_fn, DYNAMIC_ATTR, _syn_lock_names, _syn_bare, nodes={id(_c)})
            _syn_sites.append(("synth.py", _fn.name, _recv, DYNAMIC_ATTR, _ok, _out))

_sp, _sv, _su = verdicts(_syn_sites)
_SPELLINGS = {"annotated", "augmented", "unpacked", "nested_unpacked", "starred",
              "for_target", "with_target"}
check("self-test: a planted unlocked writer of a field locked elsewhere IS reported",
      sorted(s[1] for s in _sv) == sorted(_SPELLINGS | {
          "sloppy_writer", "impostor_lock", "impostor_alias", "unlocked_after_seed",
          "span_victim", "param_shadow", "local_shadow", "tuple_shadow", "import_shadow",
          "except_shadow", "nested_def_shadow", "match_shadow", "fake_lock_import",
          "dynamic_writer", "fake_bare_import", "fake_module_import",
          "bare_alias_shadow"}),
      f"violations={sorted(s[1] for s in _sv)}")
check("self-test: `lock_spans` stops at a nested function -- a helper's unlocked mention must not "
      "un-certify the ENCLOSING locked write and destroy the seed with it",
      ("Project", "prop_layers") in _sp, f"protected={sorted(_sp)}")
check("  and the separate unlocked writer of that pair is therefore still a VIOLATION",
      "span_victim" in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("self-test: a PARAMETER or LOCAL named `pid_lock` shadows the import and is NOT the lock -- "
      "same scope, right name, wrong object, which `impostor_alias` could not reach",
      {"param_shadow", "local_shadow"} <= {s[1] for s in _sv},
      f"violations={sorted(s[1] for s in _sv)}")
check("self-test: a TUPLE target, a non-lock IMPORT under the name, an `except ... as` and a "
      "nested `def` all shadow the import too -- the five-statement list certified every one of "
      "them, which is why `_bound_names` asks the grammar instead of naming forms",
      {"tuple_shadow", "import_shadow", "except_shadow", "nested_def_shadow"}
      <= {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
_ms_fn = next(f for f in ast.walk(_MOD_SHADOW)
              if isinstance(f, ast.FunctionDef) and f.name == "writer")
# `_rel` MUST EMIT POSIX SEPARATORS. This repository is developed on Windows, where `str(Path)`
# yields backslashes and the `/`-separated keys in `NON_MODEL_RECEIVERS` therefore never match --
# `stamp_conformance`'s receiver falls through to UNRESOLVED and the REAL-TREE verdict reds, while
# the ledger self-test above keeps passing because it normalises separators before comparing.
# `PureWindowsPath` is platform-independent, so this reproduces the Windows string on Linux rather
# than asserting something that can only be true here.
_w_root = pathlib.PureWindowsPath(r"C:\Server\modelmaker")
_w_src = pathlib.PureWindowsPath(
    r"C:\Server\modelmaker\services\data\src\aec_data\massing.py")
_w_rel = _w_src.relative_to(_w_root)
check("self-test: a repo-relative path is emitted with POSIX separators -- `str()` would emit "
      "backslashes on the platform this repo is developed on, and the declared exemption keys are "
      "slash-separated, so the ledger would silently stop matching there and only there",
      str(_w_rel) != _w_rel.as_posix()               # the platform difference is real here...
      and _posix_rel(_w_src, _w_root) in {k[0] for k in NON_MODEL_RECEIVERS}   # ...and `_rel` fixes it
      and all("\\" not in k[0] for k in NON_MODEL_RECEIVERS),
      f"str={str(_w_rel)!r} via _posix_rel={_posix_rel(_w_src, _w_root)!r}")

check("self-test: a DYNAMIC write (`setattr(p, k, v)`) of a model with a protected attribute is "
      "reported -- it carries no `Store` and no `Attribute`, so the grammar-derived matcher is "
      "blind to it by construction, and one live route swapped `Project.source_ifc` that way",
      "dynamic_writer" in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("  ...and a LOCKED one is not, so the rule is not simply reporting every `setattr`",
      "dynamic_locked" not in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("  ...and one whose receiver cannot be resolved is UNKNOWN, not dropped",
      "dynamic_opaque" in {s[1] for s in _su}, f"unknown={sorted(s[1] for s in _su)}")

check("self-test: a MATCH CAPTURE (`case pid_lock:`) shadows the import -- a FIFTH binding family, "
      "missed by a list whose own docstring called itself closed by the language",
      "match_shadow" in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("self-test: the bare form is certified by the NAME ITS IMPORT BOUND, not by the spelling "
      "`mutating` -- an aliased genuine import IS the lock, and a same-scope parameter of that "
      "literal name is NOT, which the discarded-bool version got wrong in both directions",
      "aliased_bare" not in {s[1] for s in _sv} and "bare_alias_shadow" in {s[1] for s in _sv},
      f"violations={sorted(s[1] for s in _sv)}")

check("self-test: a module whose path merely ENDS in the lock's name is not the lock -- "
      "`from .fakes.pid_lock import mutating` and `import fakes.pid_lock as pid_lock` both "
      "certified under a suffix test, in the two spellings round 13's fix did not look at",
      {"fake_bare_import", "fake_module_import"} <= {s[1] for s in _sv},
      f"violations={sorted(s[1] for s in _sv)}")

check("self-test: `from .fakes import pid_lock` is NOT the project lock -- recognition is by the "
      "SOURCE MODULE, not by the name, so substituting without renaming no longer certifies",
      "fake_lock_import" in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("self-test: ...and the BARE form `from ..pid_lock import mutating` IS certified -- the "
      "round-12 shadowing fix had made it unreachable, failing CLOSED against its own docstring "
      "with nothing in the tree spelling it that way to notice",
      "bare_mutating" not in {s[1] for s in _sv} and pid_lock_names(
          ast.parse("def w(pid):\n    from ..pid_lock import mutating\n"
                    "    with mutating(pid):\n        pass\n"),
          next(f for f in ast.walk(ast.parse(
              "def w(pid):\n    from ..pid_lock import mutating\n"
              "    with mutating(pid):\n        pass\n")) if isinstance(f, ast.FunctionDef)))[1],
      f"violations={sorted(s[1] for s in _sv)}")

check("self-test: a MODULE-LEVEL rebinding after the import shadows it for every function in the "
      "file -- `chain` holds functions only, so a per-function scan could not see the one rebinding "
      "whose blast radius is the whole module",
      pid_lock_names(_MOD_SHADOW, _ms_fn)[0] == set(),
      f"still certified: {pid_lock_names(_MOD_SHADOW, _ms_fn)[0]}")
check("  and the module scope is not simply refusing everything -- the same fixture WITHOUT the "
      "rebinding must still resolve the lock, or the check above passes by certifying nothing",
      pid_lock_names(ast.parse("from .. import pid_lock\n"
                               "def writer(db, pid):\n"
                               "    with pid_lock.mutating(pid):\n"
                               "        pass\n"),
                     next(f for f in ast.walk(ast.parse(
                         "from .. import pid_lock\n"
                         "def writer(db, pid):\n"
                         "    with pid_lock.mutating(pid):\n"
                         "        pass\n"))
                         if isinstance(f, ast.FunctionDef)))[0] == {"pid_lock"},
      "a module-scope shadow scan that removes the genuine import certifies nothing at all")

# THE SENTINEL MAY NOT BE SPENT AS A MODEL. `NOT_A_MODEL` is a non-empty string, so `if m` accepted
# it and a locked write through `self` in a NON-mapped class seeded a protected pair keyed on it.
# Nothing ever resolves TO the sentinel, so no violation could match -- but its ATTRIBUTE entered
# `prot_attrs`, which is the set deciding whether an unresolved receiver is worth reporting, so the
# unlocked write below was raised as UNKNOWN on the strength of a pair that protects nothing.
_sent_sites = [("s.py", "in_a_plain_class", NOT_A_MODEL, "source_ifc", True, []),
               ("s.py", "elsewhere", None, "source_ifc", False, [7])]
_sp2, _sv2, _su2 = verdicts(_sent_sites)
check("self-test: a receiver PROVED not to be a model does not seed a protected pair, nor put its "
      "attribute into the set that decides which unresolved writes are worth reporting",
      not _sp2 and not _su2, f"protected={_sp2} unknown={_su2}")

check("self-test: a rebinding inside a NESTED helper does not poison the enclosing function's "
      "binding map -- the outer locked write must still SEED its pair",
      ("Connection", "config") in _sp, f"protected={sorted(_sp)}")
check("  and the unlocked writer of that pair is therefore still a VIOLATION -- a fail-open that "
      "works by removing a seed is invisible to every check aimed at the judgement",
      "unlocked_after_seed" in {s[1] for s in _sv}, f"violations={sorted(s[1] for s in _sv)}")
check("self-test: one function's local `import pid_lock as lock` does NOT certify another "
      "function's unrelated `lock` -- imports resolve in the scope chain, not file-wide",
      "impostor_alias" in {s[1] for s in _sv} and "aliased_lock" not in {s[1] for s in _sv},
      f"violations={sorted(s[1] for s in _sv)}")
check("  and the genuine alias IS still certified, so the scoping did not simply stop recognising "
      "the lock -- a rule that certifies nothing would pass the check above for the wrong reason",
      ("Project", "source_ifc") in _sp and "aliased_lock" not in {s[1] for s in _sv},
      f"protected={sorted(_sp)} violations={sorted(s[1] for s in _sv)}")
check("self-test: a CHAINED receiver (`ctx.project.source_ifc`) is reported UNKNOWN, not dropped -- "
      "requiring a bare Name receiver silently removed the write from the population entirely",
      "chained_receiver" in {s[1] for s in _su}, f"unknown={sorted(s[1] for s in _su)}")
check("self-test: a name bound to TWO different models resolves to NEITHER, so the earlier write "
      "cannot be reclassified by a later rebinding and quietly leave the violations",
      "rebound" in {s[1] for s in _su}, f"unknown={sorted(s[1] for s in _su)}")
check("self-test: a `with <something-else>.mutating(...)` does NOT certify -- the receiver is "
      "resolved against the file's own pid_lock imports, not matched on the method name",
      "impostor_lock" in {s[1] for s in _sv},
      "an unrelated object exposing .mutating() was accepted as the project lock")
check("  and that INCLUDES ALL SEVEN non-plain spellings -- `ast.Assign` alone hid the first two, "
      "and the three-statement matcher that replaced it still hid the other five, because their "
      "target is a Tuple, a `For.target` or a `withitem`, not a top-level Attribute",
      _SPELLINGS <= {s[1] for s in _sv},
      f"missed={sorted(_SPELLINGS - {s[1] for s in _sv})}")
check("self-test: the SEED found the locked writer -- an empty seed would make the rule vacuous "
      "and every check below would pass by finding nothing",
      ("Project", "source_ifc") in _sp, f"protected={sorted(_sp)}")
check("self-test: a DIFFERENT model writing the same attribute name is NOT a violation -- this is "
      "the `modules.save_view` false positive that name-only matching produces",
      not any(s[2] == "SavedView" for s in _sv), f"violations={_sv}")
check("self-test: the receiver really did resolve through the model registry",
      all(s[2] in MODELS for s in _syn_sites if s[2]), f"{[s[2] for s in _syn_sites]}")

# A resolver that GUESSES instead of reporting UNKNOWN must break a self-test, or failing closed is
# decoration. Route every unresolved receiver to the protected model and the third check above --
# the one that keeps a different model out of the violation list -- has to go red.
_guessed = [(p, f, (m or "Project"), a, ok, o) for p, f, m, a, ok, o in _syn_sites]
_, _gv, _ = verdicts(_guessed)
check("self-test: a resolver that GUESSES 'Project' for every unresolved receiver produces a "
      "violation the honest one does not -- so UNKNOWN is doing work, not decoration",
      len(_gv) > len(_sv), f"guessed={len(_gv)} honest={len(_sv)}")

# THE DECLARED-EXEMPTION LEDGER, checked in BOTH directions. Round 6 inferred "not a model" from
# the shape of the binding and that inference was a tree-wide fail-open; round 8 replaced it with a
# declaration, which is only an improvement if the declaration itself cannot rot. So: empty the
# ledger and re-derive. Every entry must reappear as an UNKNOWN-and-unlocked site -- an entry that
# names code which has moved or been fixed is dead weight that silently excuses its NEXT occupant --
# and nothing may appear that is not declared, which is the fail-open the inference used to hide.
_ledger_backup = dict(NON_MODEL_RECEIVERS)
NON_MODEL_RECEIVERS.clear()
_, _, _undeclared = verdicts(collect(SRC_ROOTS))
NON_MODEL_RECEIVERS.update(_ledger_backup)
_undeclared_keys = {(u[0].replace("\\", "/"), u[1]) for u in _undeclared}
_declared_keys = {(path, func) for (path, func, _var) in NON_MODEL_RECEIVERS}
check("self-test: the exemption ledger is LOAD-BEARING -- deleting it makes every declared site "
      "come back as an unresolvable unlocked write, so no entry is there for decoration",
      _declared_keys <= _undeclared_keys,
      f"declared but not actually needed: {sorted(_declared_keys - _undeclared_keys)}")
check("  and nothing NEEDS an exemption that does not have one -- this is the direction round 6's "
      "inference failed in, by answering 'not a model' for every chain it had not been asked about",
      _undeclared_keys <= _declared_keys,
      f"undeclared unresolvable writes: {sorted(_undeclared_keys - _declared_keys)}")

check("self-test: the model registry is POPULATED -- mappers configure lazily and the first probe "
      "of this tree's registry really did return 0, which would resolve no receiver at all and "
      "leave an EMPTY seed: a gate reporting on nothing while printing a clean verdict",
      len(MODELS) > 20 and {"Project", "Connection"} <= MODELS, f"{len(MODELS)} models")

# THE REGRESSION FOR THE REMOVED MODULE PREDICATE. A module that imports neither `models` nor
# `Session` can still hold a mapped instance -- its caller passes one in. `touches_orm` skipped such
# a file WHOLE, so this write never reached `verdicts` at all and could not be reported UNKNOWN:
# the fail-closed rule was defeated one layer above the code enforcing it. Run through `collect`
# rather than `_bindings`, because the defect was in the file loop, not in the resolver.
_probe_dir = pathlib.Path(tempfile.mkdtemp(prefix="lockb_"))
(_probe_dir / "innocent.py").write_text("def stamp(p):\n    p.source_ifc = 'x'\n", encoding="utf-8")
_probe_sites = collect([_probe_dir])
_, _pv, _pu = verdicts(_probe_sites + [("seed.py", "w", "Project", "source_ifc", True, [])])
check("self-test: a module importing neither `models` nor `Session` is STILL scanned -- it can hold "
      "a mapped instance its caller passed in, which is why the module-level predicate was removed",
      any(s[3] == "source_ifc" for s in _probe_sites), f"sites={_probe_sites}")
check("  and that unresolved write is reported UNKNOWN rather than silently dropped",
      any(s[1] == "stamp" for s in _pu), f"unknown={_pu}")

# MUTATION: put the module predicate back. The probe must VANISH -- if it survives, the removal was
# not what makes the check above pass and this self-test is decoration.
_mut = [s for s in _probe_sites
        if touches_orm(ast.parse((_probe_dir / "innocent.py").read_text(encoding="utf-8")))]
check("MUTATION: reinstating the `touches_orm` module skip makes that site DISAPPEAR -- so its "
      "removal is what closes the hole, not an unrelated change",
      not _mut, f"survived the reinstated predicate: {_mut}")
shutil.rmtree(_probe_dir, ignore_errors=True)

# THE SCOPE-MERGE FAIL-OPEN, run through `collect` rather than through `_bindings` -- because the
# defect is in the MERGE and nothing calling `_bindings` alone can see it. `inner` takes the name
# `p` over: it means a Project for the write and a SavedView two lines later, so `_bind` marks it
# CONFLICT. `_bindings` then dropped the sentinel at its own return, the merge found no entry for
# `p` in the inner scope, and `outer`'s SavedView flowed in -- so an unlocked `Project.source_ifc`
# write was classified as a SavedView one and reached NEITHER the violations NOR the unknowns.
# *A name the inner scope has taken over must beat the outer binding even when the analyser cannot
# say what it now means*, which is why the sentinels survive to `_resolved` at the end of the merge.
_scope_dir = pathlib.Path(tempfile.mkdtemp(prefix="lockb_scope_"))
(_scope_dir / "shadowed.py").write_text(
    "def outer(db, vid):\n"
    "    p = db.get(SavedView, vid)\n"
    "    def inner(db, pid):\n"
    "        p = db.get(Project, pid)\n"
    "        p.source_ifc = 'unlocked, and `p` means a Project HERE'\n"
    "        p = db.get(SavedView, vid)\n"
    "        return p\n"
    "    return inner\n", encoding="utf-8")
_scope_sites = collect([_scope_dir])
_, _cv, _cu = verdicts(_scope_sites + [("seed.py", "w", "Project", "source_ifc", True, [])])
check("self-test: an inner scope that REBINDS a name does not inherit the enclosing scope's model "
      "for it -- the unlocked write must be reported, not reclassified as the outer model's",
      any(s[1] == "inner" for s in _cu),
      f"sites={_scope_sites} unknown={_cu} violations={_cv}")
check("  and specifically it must not come back as the OUTER model, which is the value that used "
      "to leak in and make the write somebody else's problem",
      not any(s[1] == "inner" and s[2] == "SavedView" for s in _scope_sites),
      f"sites={_scope_sites}")
shutil.rmtree(_scope_dir, ignore_errors=True)

if FAILED:                      # a broken analyser must not go on to report on the real tree
    print("\nself-tests failed — not reporting on the tree")
    print("test_lock_boundary FAILED")
    for f in FAILED:
        print(f"  - {f}")
    sys.exit(1)

# --- the real tree ------------------------------------------------------------------------------

SITES = collect(SRC_ROOTS)
PROTECTED, VIOLATIONS, UNKNOWN = verdicts(SITES)

check("the scan found the source tree rather than an empty directory", len(SITES) > 100, f"{len(SITES)} sites")
check("at least one field is protected somewhere -- otherwise the rule below is vacuous",
      PROTECTED, "no (model, attribute) pair is fully locked in any writer")

check("every writer of a field the lock protects elsewhere is ITSELF under the lock",
      not VIOLATIONS,
      "\n      " + "\n      ".join(f"{p}:{f} writes {m}.{a} with mentions outside the lock at {o}"
                                   for p, f, m, a, _, o in VIOLATIONS))

check("no UNLOCKED write of a protected attribute has a receiver this analyser cannot resolve -- "
      "an unresolvable receiver must never be what excuses an unlocked write",
      not UNKNOWN,
      "\n      " + "\n      ".join(f"{p}:{f} writes ?.{a} unlocked" for p, f, _, a, _, _ in UNKNOWN))

print()
print(f"  protected (model, attribute) pairs : {len(PROTECTED)}")
for _m, _a in sorted(PROTECTED):
    print(f"      {_m}.{_a}")
print(f"  attribute-write sites scanned      : {len(SITES)}")
print()
print(f"test_lock_boundary {'FAILED' if FAILED else 'OK'}"
      + ("" if FAILED else f" - {len(PROTECTED)} protected fields, every writer of each under the lock"))
for f in FAILED:
    print(f"  - {f}")
sys.exit(1 if FAILED else 0)
