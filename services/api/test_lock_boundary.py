"""A field the project lock protects SOMEWHERE must be protected EVERYWHERE.

## Why this exists, and why `test_rmw_sweep` could not have found it

`test_rmw_sweep` derives **read-modify-writes** and asks whether each is serialised. That population
is the right one for the defect it was built for, and it is structurally blind to this one.
`p.source_ifc = str(ifc_path)` READS NOTHING — it installs a new pointer — so it is not a
read-modify-write and never enters the sweep. Neither does the conditional-create shape
`if not p.source_ifc: ... p.source_ifc = ...`.

The consequence, measured rather than feared: G-11 was closed on 2026-09-13 by locking every
`source_ifc` read-modify-write in `routers/authoring.py`, and **four writers of that same column were
left unlocked**, two of them in `authoring.py` itself. A pointer swap that reads nothing still
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
paper over — it is why this file and `test_rmw_sweep` are both necessary.** `Project.dev_budget` has
four writers and *no* lock anywhere, so it never enters the seed and this gate is silent on it; the
sweep names two of those four as open read-modify-writes, which is the reach this one lacks. Each
derivation is blind where the other sees. A future instance must now evade both.

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

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_lock_boundary.py
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

os.environ["DATABASE_URL"] = "sqlite:///./_lockboundary_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_lockboundary")

HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "data" / "src"))

import aec_api.models  # noqa: E402,F401  -- importing it is what populates the mapper registry
from aec_api.db import Base  # noqa: E402

#: Every mapped class name, read from SQLAlchemy's registry rather than listed here. A list would be
#: a copy, and a copy is what drifts.
MODELS: set[str] = {m.class_.__name__ for m in Base.registry.mappers}

SRC_ROOTS = [HERE / "src", HERE.parent / "data" / "src"]

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail if not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the analyser -----------------------------------------------------------------------------

def _alias_map(tree: ast.AST) -> dict[str, tuple[str, str]]:
    """local name -> (module, original name), for `from m import x as y` and `import x as y`."""
    out: dict[str, tuple[str, str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out[a.asname or a.name] = (n.module or "", a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                out[a.asname or a.name] = ("", a.name)
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


def _bindings(fn: ast.AST, alias: dict, local_types: dict, foreign_types: dict) -> dict[str, str]:
    """local variable -> mapped model name, for the four forms the module docstring lists."""
    out: dict[str, str] = {}
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign) or not isinstance(n.value, ast.Call):
            continue
        names = [t.id for t in n.targets if isinstance(t, ast.Name)]
        if not names and isinstance(n.targets[0], ast.Tuple):       # `v, _created = helper(...)`
            names = [e.id for e in n.targets[0].elts if isinstance(e, ast.Name)][:1]
        if not names:
            continue
        if (model := _model_of_call(n.value, alias)):
            out[names[0]] = model
            continue
        fnc = n.value.func                       # ...otherwise a helper whose RETURN TYPE names one
        if isinstance(fnc, ast.Name):
            if (t := local_types.get(fnc.id)) and t in MODELS:
                out[names[0]] = t
            elif fnc.id in alias:
                mod, real = alias[fnc.id]
                if (t := foreign_types.get((mod.rsplit(".", 1)[-1], real))) and t in MODELS:
                    out[names[0]] = t
    return out


def lock_spans(fn: ast.AST, attr: str) -> tuple[bool, list[int]]:
    """Is EVERY mention of `attr` in this function inside `with pid_lock.mutating(...)`?

    Same rule as `test_rmw_sweep.under_pid_lock`, and stricter than strictly necessary on purpose:
    a read kept outside the lock for logging would count. This function decides whether to CERTIFY,
    and the safe direction for a certifier is to refuse what it cannot prove -- *a certifier that
    reasons about which stragglers are harmless is one bad reading away from blessing one.*
    """
    outside: list[int] = []

    def walk(node: ast.AST, locked: bool) -> None:
        for ch in ast.iter_child_nodes(node):
            here = locked
            if isinstance(ch, ast.With):
                for item in ch.items:
                    ctx = item.context_expr
                    if (isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute)
                            and ctx.func.attr == "mutating"):
                        here = True
            if isinstance(ch, ast.Attribute) and ch.attr == attr and not here:
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
        if not touches_orm(tree):
            continue
        alias, local_types = _alias_map(tree), _return_types(tree)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            binds = _bindings(fn, alias, local_types, foreign)
            seen: set[tuple[str, str]] = set()
            for n in ast.walk(fn):
                if not isinstance(n, ast.Assign):
                    continue
                for t in n.targets:
                    if not (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)):
                        continue
                    if (t.value.id, t.attr) in seen:
                        continue
                    seen.add((t.value.id, t.attr))
                    ok, outside = lock_spans(fn, t.attr)
                    sites.append((str(p.relative_to(HERE.parent.parent)), fn.name,
                                  binds.get(t.value.id), t.attr, ok, outside[:4]))
    return sites


def verdicts(sites: list[tuple]) -> tuple[set, list, list]:
    """(protected pairs, violations, unknown-and-unlocked). Separate from `collect` so a mutation
    can be aimed at the JUDGEMENT without also disturbing the discovery -- the two are different
    questions, and `test_unique_read_guard` learned the hard way that asserting a site was REPORTED
    is not asserting it was CLASSIFIED."""
    protected = {(m, a) for _, _, m, a, ok, _ in sites if m and ok}
    prot_attrs = {a for _, a in protected}
    violations = [s for s in sites if s[2] and (s[2], s[3]) in protected and not s[4]]
    unknown = [s for s in sites if s[2] is None and s[3] in prot_attrs and not s[4]]
    return protected, violations, unknown


# --- self-tests: the analyser must find a planted defect before it may report on the tree -------

_SYNTH = ast.parse(
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
)
_syn_alias, _syn_types = _alias_map(_SYNTH), _return_types(_SYNTH)
_syn_sites = []
for _fn in ast.walk(_SYNTH):
    if isinstance(_fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _b = _bindings(_fn, _syn_alias, _syn_types, {})
        for _n in ast.walk(_fn):
            if isinstance(_n, ast.Assign):
                for _t in _n.targets:
                    if isinstance(_t, ast.Attribute) and isinstance(_t.value, ast.Name):
                        _ok, _out = lock_spans(_fn, _t.attr)
                        _syn_sites.append(("synth.py", _fn.name, _b.get(_t.value.id), _t.attr, _ok, _out))

_sp, _sv, _su = verdicts(_syn_sites)
check("self-test: a planted unlocked writer of a field locked elsewhere IS reported",
      [s[1] for s in _sv] == ["sloppy_writer"], f"violations={[s[1] for s in _sv]}")
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
