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

# One lock covers both services -- requirements.in says so in its own header ("the data service's
# runtime deps are a strict subset"). So both trees are measured against that one file, which also
# keeps the header's claim honest rather than merely written down.
DECLARED = declared_in(os.path.join(ROOT, "services", "api", "requirements.in"))
PKG2DIST = packages_distributions()

print(f"first-party packages (derived from src roots): {', '.join(sorted(FIRST_PARTY))}")
print(f"declared in services/api/requirements.in: {len(DECLARED)}")

sites = {}
for tree_root in (API_SRC, DATA_SRC):
    for dirpath, _, files in os.walk(tree_root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            with open(path, encoding="utf-8") as fh:
                try:
                    parsed = ast.parse(fh.read())
                except SyntaxError:
                    continue
            for mod in module_scope_imports(parsed):
                if mod and mod not in FIRST_PARTY and mod not in sys.stdlib_module_names:
                    sites.setdefault(mod, set()).add(os.path.relpath(path, ROOT).replace("\\", "/"))

print(f"distinct third-party module-scope imports: {len(sites)}\n")

for mod in sorted(sites):
    where = sorted(sites[mod])
    extra = f" (+{len(where) - 1} more)" if len(where) > 1 else ""
    dists = PKG2DIST.get(mod, [])
    if not dists:
        check(f"`import {mod}` resolves to an installed distribution", False,
              f"not installed, yet imported at module scope by {where[0]}{extra}")
        continue
    provider = "/".join(dists)
    check(f"`import {mod}` is declared ({provider})",
          any(norm(d) in DECLARED for d in dists),
          f"provided by {provider}, which requirements.in does not declare -- imported at module "
          f"scope by {where[0]}{extra}. Add it to requirements.in, or make the import "
          f"function-local if it is genuinely optional")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_declared_imports OK")
