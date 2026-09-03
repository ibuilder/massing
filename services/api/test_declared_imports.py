"""
Every third-party package our source imports at module scope must be DECLARED, not inherited.

Found on 2026-08-28 while bumping `anthropic` across its 0.x -> 1.x major. Two packages that shipped
code imports directly were declared in no requirements file at all, and reached the lock on a single
transitive edge each:

    httpx    <- only `# via anthropic`     (bsdd.py, site_context.py)
    pillow   <- only `# via reportlab`     (photo_cv.py, and photo_detect.py calls it "a hard dep")

The anthropic bump is exactly the event that collects on that debt: 1.x moved its HTTP layer from
`httpx` to `httpx2`, so recompiling the lock would have removed `httpx` from the install set while
two modules still did `import httpx` at the top of the file.

**The failure would have been quiet, which is the part worth a gate.** Both consumers are imported
inside functions, so the service boots normally, the health check passes, and the whole suite is
green -- right up until someone opens the bSDD lookup or a site-context route and gets a 500. Nothing
about "we upgraded an unrelated AI SDK" points at those routes.

So the rule is not "pin more things". It is: **a package that appears in our own `import` statements
is a direct dependency, whatever else happens to pull it in.** Transitive availability is a fact
about somebody else's metadata, and it can change in a release we do not review.

WHAT IS DELIBERATELY NOT COVERED -- the exemptions are structural, not a name list:

  * **function-local imports.** `from massingifc_ifc import convert_ifc` inside a function, or
    `import pye57` under `try/except ImportError`, is the established way this codebase says
    "optional, supplied by the deployment". Those must stay legal, and they fail loudly at call time
    rather than silently, which is the difference that matters.
  * **first-party**, including the vendored trees on `src/` (`massingplan`, `massingcapture`) and
    `aec_data` -- derived from the source layout, never listed here, so vendoring a fourth package
    does not need an edit to this file.
  * **stdlib**, from `sys.stdlib_module_names`.

An import that is neither installed nor exempt fails too. At module scope that is not a style
question: the module cannot be imported at all, and something else is hiding it.
"""
import ast
import os
import re
import sys
from importlib.metadata import packages_distributions

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FAILED = []


def check(label, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + label + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(label)


def norm(name):
    """PEP 503 normalisation, so `Pillow`, `pillow` and `sentry_sdk` compare equal to their pins."""
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_in(path):
    """Top-level requirement names from a pip-compile input, extras and specifiers stripped."""
    out = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9._-]+)", line)
            if m:
                out.add(norm(m.group(1)))
    return out


def module_scope_imports(tree):
    """Top-level import names, skipping function/class bodies and try/except ImportError guards.

    Walking with `ast.walk` would be shorter and wrong: it flattens the tree, so a deliberate lazy
    import inside a function is indistinguishable from one at the top of the file -- and that
    distinction is the entire point of this gate.
    """
    names = []

    def guarded(node):
        for h in node.handlers:
            t = h.type
            if isinstance(t, ast.Name) and t.id == "ImportError":
                return True
            if isinstance(t, ast.Tuple) and any(
                    isinstance(e, ast.Name) and e.id == "ImportError" for e in t.elts):
                return True
        return False

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue                                  # lazy/optional by construction
            if isinstance(node, ast.Try):
                if guarded(node):
                    continue                              # declared-optional by construction
                visit(node.body)
                for h in node.handlers:
                    visit(h.body)
                visit(node.orelse)
                visit(node.finalbody)
            elif isinstance(node, ast.Import):
                names.extend(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if not node.level and node.module:        # level>0 is a relative (first-party) import
                    names.append(node.module.split(".")[0])
            elif isinstance(node, (ast.If, ast.With, ast.For, ast.While)):
                visit(node.body)
                visit(getattr(node, "orelse", []))
    visit(tree.body)
    return names


API_SRC = os.path.join(ROOT, "services", "api", "src")
DATA_SRC = os.path.join(ROOT, "services", "data", "src")
# First-party is DERIVED from the layout, not listed: every top-level package on either src root.
FIRST_PARTY = {d for root in (API_SRC, DATA_SRC) if os.path.isdir(root) for d in os.listdir(root)
               if os.path.isdir(os.path.join(root, d))}

#: LOCAL MODULES the gate files import as bare names. Widening the scan to the gate files (2026-09-03)
#: immediately produced five "not installed" failures — `run_tests`, `mcp_server`, `vendor_drift`,
#: `massing_api`, `massing_export` — none of which is a package at all. They are sibling `.py` files,
#: and the pyRevit bridge library that `test_revit_bridge.py` puts on `sys.path`. A first-party set
#: derived from `src/` package DIRECTORIES cannot see a module that is a bare file.
#:
#: Enumerated from disk rather than listed, for the same reason FIRST_PARTY is: a hand-list goes stale
#: the first time someone adds a gate. Scoped to the directories that actually get imported from, not
#: to every `.py` in the repository — a repo-wide basename sweep would silently forgive a real
#: third-party import that happened to share a name with one of our files, and forgiving is the
#: failure mode this whole test exists to prevent.
_LOCAL_ROOTS = [os.path.join(ROOT, "services", "api"), os.path.join(ROOT, "services", "data")] + [
    os.path.join(ROOT, "integrations", "pyrevit", "Massing.extension", "lib"),
]
LOCAL_MODULES = {
    f[:-3]
    for root in _LOCAL_ROOTS if os.path.isdir(root)
    for f in os.listdir(root)
    if f.endswith(".py") and os.path.isfile(os.path.join(root, f))
}
FIRST_PARTY |= LOCAL_MODULES

# One lock covers both services -- requirements.in says so in its own header ("the data service's
# runtime deps are a strict subset"). So both trees are measured against that one file, which also
# keeps the header's claim honest rather than merely written down.
DECLARED = declared_in(os.path.join(ROOT, "services", "api", "requirements.in"))
#: Test-only declarations. A GATE may import from either file; a SHIPPED module may import only from
#: `requirements.in`, because that is what compiles into the runtime image — a runtime import backed
#: solely by a dev pin is a module that works in CI and ImportErrors in production. The two scopes
#: below encode exactly that difference, and it is the reason this widening needed two sets rather
#: than one bigger one.
DECLARED_DEV = DECLARED | declared_in(os.path.join(ROOT, "services", "api", "requirements-dev.txt"))
PKG2DIST = packages_distributions()

#: The GATE FILES — everything directly under a service root that is not inside `src/`. Added
#: 2026-09-03, and it was NOT a hypothetical gap: `test_ruff_scope.py` landed with `import yaml`
#: declared in NEITHER requirements file, reaching the lock only `# via` fastapi/uvicorn/pyHanko/
#: bandit/starlette/markdown-it-py — and this test stayed green, because it walked `src/` only.
#: The gate written to catch "a package our own source imports is a DIRECT dependency however else
#: it happens to arrive" could not see the ~30 files that live beside it. Same scope hole RUFF-SCOPE
#: fixed for the linter that same day, one directory over: *the checker was real, its reach was the
#: fiction.* Non-recursive on purpose — `migrations/`, `_models/` and `scripts/` are separate
#: populations with their own answers, and sweeping them in silently would repeat the mistake of
#: widening a scope without reading what it caught.
GATE_DIRS = (os.path.join(ROOT, "services", "api"), os.path.join(ROOT, "services", "data"))

#: PACKAGING MANIFESTS — the files that decide what actually leaves this repository. Anything they
#: name is SHIPPED and must clear the stricter scope, wherever it happens to sit on disk.
#:
#: CodeRabbit found this on the PR that introduced the two-scope split, and it is worth stating
#: plainly: the first version swept every direct `.py` under `services/api` into the DEV scope, and
#: two of those files ship. `desktop_entry.py` is the executable in `desktop.spec` and
#: `sidecar.spec`; `seed_demo.py` is COPYed into the runtime image by `Dockerfile` and run by
#: `docker-compose.yml`'s seed profile. A dev-only import in either would have passed this gate and
#: failed in the packaged artifact — which is the EXACT failure the split exists to prevent, so the
#: split had reintroduced its own defect by assuming "directly under services/api" means "test".
#:
#: DERIVED, not listed. Naming those two files would fix today and leave the next packaged entry
#: point to land in the loose bucket silently — the same "a hand-list goes stale" argument as
#: FIRST_PARTY and LOCAL_MODULES, and the reason this whole sequence keeps deriving populations
#: instead of enumerating them.
PACKAGING = [
    os.path.join(ROOT, "services", "api", "desktop.spec"),
    os.path.join(ROOT, "services", "api", "sidecar.spec"),
    os.path.join(ROOT, "services", "api", "Dockerfile"),
    os.path.join(ROOT, "services", "data", "Dockerfile"),
    os.path.join(ROOT, "docker-compose.yml"),
]


def _packaged_filenames():
    """`{'seed_demo.py', ...}` — every .py basename any packaging manifest mentions."""
    named = set()
    for path in PACKAGING:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        named |= set(re.findall(r"([A-Za-z0-9_]+\.py)", text))
    return named


PACKAGED = _packaged_filenames()


def _walk_py(root, recursive=True):
    if recursive:
        for dirpath, _, files in os.walk(root):
            for fname in files:
                if fname.endswith(".py"):
                    yield os.path.join(dirpath, fname)
    else:
        for fname in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            full = os.path.join(root, fname)
            if fname.endswith(".py") and os.path.isfile(full):
                yield full


def _scan(paths):
    """{module: {relative path, ...}} for every module-scope third-party import in `paths`."""
    found = {}
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            try:
                parsed = ast.parse(fh.read())
            except SyntaxError:
                continue
        for mod in module_scope_imports(parsed):
            if mod and mod not in FIRST_PARTY and mod not in sys.stdlib_module_names:
                found.setdefault(mod, set()).add(os.path.relpath(path, ROOT).replace("\\", "/"))
    return found


print(f"first-party packages (derived from src roots): {', '.join(sorted(FIRST_PARTY))}")
print(f"declared in services/api/requirements.in: {len(DECLARED)}")
print(f"          + requirements-dev.txt (gates only): {len(DECLARED_DEV)}")

_direct = [p for root in GATE_DIRS for p in _walk_py(root, recursive=False)]
_ships = [p for p in _direct if os.path.basename(p) in PACKAGED]
_gate_only = [p for p in _direct if os.path.basename(p) not in PACKAGED]

shipped = _scan(list(_walk_py(API_SRC)) + list(_walk_py(DATA_SRC)) + _ships)
gates = _scan(_gate_only)

check("a packaging manifest still names at least one direct entry point", bool(_ships),
      ", ".join(sorted(os.path.relpath(p, ROOT).replace("\\", "/") for p in _ships))
      or "none — if the specs/Dockerfile/compose stopped naming any direct .py, PACKAGING is stale "
         "and every entry point has silently dropped into the looser dev scope")

# A gate importing something a shipped module also imports is already covered by the stricter scope;
# reporting it twice would just make a failure read as two problems.
gates = {m: w for m, w in gates.items() if m not in shipped}

print(f"distinct third-party module-scope imports: {len(shipped)} shipped, {len(gates)} gate-only")
_gate_files = sum(1 for root in GATE_DIRS for _ in _walk_py(root, recursive=False))
check("the gate-file scan actually reached the files beside this one", _gate_files >= 20,
      f"{_gate_files} .py directly under {len(GATE_DIRS)} service root(s) — a scan that reaches "
      f"nothing passes vacuously, which is the failure this widening exists to correct")
print()

for label, sites, allowed, where_to_add in (
    ("shipped", shipped, DECLARED, "requirements.in"),
    ("gate", gates, DECLARED_DEV, "requirements-dev.txt (or requirements.in if it also ships)"),
):
    for mod in sorted(sites):
        where = sorted(sites[mod])
        extra = f" (+{len(where) - 1} more)" if len(where) > 1 else ""
        dists = PKG2DIST.get(mod, [])
        if not dists:
            check(f"[{label}] `import {mod}` resolves to an installed distribution", False,
                  f"not installed, yet imported at module scope by {where[0]}{extra}")
            continue
        provider = "/".join(dists)
        check(f"[{label}] `import {mod}` is declared ({provider})",
              any(norm(d) in allowed for d in dists),
              f"provided by {provider}, declared nowhere -- imported at module scope by "
              f"{where[0]}{extra}. Add it to {where_to_add}, or make the import function-local "
              f"if it is genuinely optional")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_declared_imports OK")
