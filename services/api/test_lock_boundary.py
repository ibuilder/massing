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
MODELS: set[str] = {m.class_.__name__ for m in Base.registry.mappers}

#: A receiver PROVED not to be a mapped instance -- distinct from `None`, which means "unresolved"
#: and fails closed. Only a derivation that cannot be wrong may use this.
NOT_A_MODEL = "<not-a-model>"

#: Every attribute name mapped on ANY model -- columns AND relationships. `configure_mappers()` is
#: REQUIRED: mappers are configured lazily, and `m.attrs` on an unconfigured registry returns an
#: EMPTY set. Measured, not assumed -- the first probe of this returned 0 of 183. An empty set here
#: would mark every attribute chain "provably not a model", which is a fail-OPEN across the whole
#: tree, so the self-tests below assert it is populated before any verdict is printed.
configure_mappers()
MAPPED_ATTRS: set[str] = {a for m in Base.registry.mappers for a in m.attrs.keys()}

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


def _rel(p: pathlib.Path) -> str:
    """Repo-relative path, or the bare path when `p` is outside the tree (the self-test probe)."""
    try:
        return str(p.relative_to(HERE.parent.parent))
    except ValueError:
        return str(p)


def _chain_attrs(node: ast.AST) -> list[str] | None:
    """The attribute names in `a.b.c`, root-last, or None when the node is not a pure chain."""
    names: list[str] = []
    while isinstance(node, ast.Attribute):
        names.append(node.attr)
        node = node.value
    return names if names and isinstance(node, ast.Name) else None


def _bindings(fn: ast.AST, alias: dict, local_types: dict, foreign_types: dict) -> dict[str, str]:
    """local variable -> mapped model name, for the five forms the module docstring lists."""
    out: dict[str, str] = {}
    #: Form 7: bound from an ATTRIBUTE CHAIN whose every name is unmapped anywhere. To reach a mapped
    #: instance by attribute access you must traverse a mapped RELATIONSHIP, and every relationship
    #: name is in `MAPPED_ATTRS` -- so a chain that touches none of them cannot yield one. This is
    #: what resolves `massing.stamp_conformance` (`fn = header.file_name`, an ifcopenshell header)
    #: WITHOUT the module-level predicate that used to hide the whole file. Deliberately NOT "bound
    #: from an attribute chain is not a model": `project.owner` would be, which is why the test is
    #: against the registry rather than against the shape.
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            chain = _chain_attrs(n.value)
            if chain and not (set(chain) & MAPPED_ATTRS):
                out.setdefault(n.targets[0].id, NOT_A_MODEL)
    #: Form 5: a PARAMETER whose annotation names a model. Added to close this gate's own seed blind
    #: spot: `generate._finalize_generated` locks `.dev_budget` but received `p` unannotated, so the
    #: pair never entered the seed and three unlocked writers of it went unreported. A helper that
    #: takes an already-fetched row is a normal shape, and without this every one of them is UNKNOWN.
    for arg in [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]:
        if isinstance(arg.annotation, ast.Name):
            resolved = alias.get(arg.annotation.id, ("", arg.annotation.id))[1]
            if resolved in MODELS:
                out[arg.arg] = resolved
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
        # NO MODULE-LEVEL SKIP. `touches_orm` used to stand here and it was this gate's own worst
        # defect: *a predicate that decides what to LOOK at is more dangerous than one that decides
        # what to report*, because everything it excludes is invisible to the output -- the exact
        # lesson CLAUDE.md records for `test_seeding_sweep`, quoted in that function's docstring and
        # then violated two lines below it. Its justification -- "no ORM import and no Session means
        # no mapped instance" -- is FALSE: `def stamp(p): p.source_ifc = v` holds one with neither.
        # Such a module was skipped whole, so the write never reached `verdicts` and could not be
        # reported UNKNOWN. The fail-closed rule was defeated one layer ABOVE the thing enforcing it.
        alias, local_types = _alias_map(tree), _return_types(tree)
        enclosing = {f: c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)
                     for f in ast.walk(c) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            binds = _bindings(fn, alias, local_types, foreign)
            #: Form 6, and the replacement for the module predicate: `self` inside a class. If the
            #: class IS mapped, `self` is that model -- which the old code could not see at all. If
            #: it is NOT mapped, `self` is provably not a mapped instance, because it is an instance
            #: of THAT class. Derived from the model registry, per receiver, and provable in both
            #: directions -- which is what the module-level predicate only claimed to be.
            if (cls := enclosing.get(fn)):
                binds["self"] = cls if cls in MODELS else NOT_A_MODEL
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
                    sites.append((_rel(p), fn.name,
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

check("self-test: the mapped-attribute set is POPULATED -- an empty one would mark every attribute "
      "chain 'provably not a model', a fail-OPEN across the whole tree, and the first probe of it "
      "really did return 0 because mappers configure lazily",
      len(MAPPED_ATTRS) > 50 and "source_ifc" in MAPPED_ATTRS, f"{len(MAPPED_ATTRS)} attrs")

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
