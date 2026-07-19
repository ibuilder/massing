"""DEV-2 (REL-8): import-cycle guard — no circular imports at MODULE TOP LEVEL across the first-party
packages `aec_api` + `aec_data`. The modularization work (REL-3) repeatedly tripped over *false-positive*
cycle reports (imports that are actually function-local / deferred); this locks in the real invariant so a
genuine top-level cycle — the kind that breaks at import time and blocks a clean façade extraction — can't
regress in silently. Pure stdlib `ast`, no third-party linter, runs inside the fast test gate.

Only TOP-LEVEL `import` / `from … import` statements count: a function-local import (the deliberate way
this codebase breaks would-be cycles, e.g. routers importing engines lazily) does not create an
import-time cycle and is correctly ignored.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_import_cycles.py"""
from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTS = {
    "aec_api": os.path.join(HERE, "src", "aec_api"),
    "aec_data": os.path.join(HERE, "..", "data", "src", "aec_data"),
}


def _discover() -> dict[str, str]:
    """Map fully-qualified first-party module name -> file path."""
    mods: dict[str, str] = {}
    for pkg, root in ROOTS.items():
        root = os.path.normpath(root)
        for dp, _, fs in os.walk(root):
            for f in fs:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root).replace(os.sep, ".")[:-3]
                name = pkg if rel == "__init__" else f"{pkg}.{rel.removesuffix('.__init__')}"
                mods[name] = p
    return mods


def _edges(mods: dict[str, str]) -> tuple[dict[str, set[str]], list[str]]:
    """First-party top-level import edges (module -> modules it imports) + any unparseable files."""
    firstparty = set(mods)
    edges: dict[str, set[str]] = defaultdict(set)
    unparseable: list[str] = []

    def add(src: str, target: str) -> None:
        # a `from pkg.mod import name` may reference either the module `pkg.mod` or `pkg.mod.name`
        if target in firstparty:
            edges[src].add(target)

    for name, path in mods.items():
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            unparseable.append(name)
            continue
        pkg = name.split(".")[0]
        for node in tree.body:                      # TOP-LEVEL statements only
            if isinstance(node, ast.Import):
                for a in node.names:
                    add(name, a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:                      # relative import: resolve against this module's package
                    base = name.rsplit(".", node.level)[0] if name.count(".") >= node.level else pkg
                    mod = f"{base}.{node.module}" if node.module else base
                else:
                    mod = node.module or ""
                add(name, mod)
                for a in node.names:
                    add(name, f"{mod}.{a.name}")
    return edges, unparseable


def _cycles(edges: dict[str, set[str]], nodes: list[str]) -> list[list[str]]:
    """Tarjan SCCs; any component with >1 member (or a self-loop) is an import cycle."""
    idx: dict[str, int] = {}
    low: dict[str, int] = {}
    on: dict[str, bool] = {}
    stack: list[str] = []
    counter = [0]
    out: list[list[str]] = []
    sys.setrecursionlimit(20000)

    def strongconnect(v: str) -> None:
        idx[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on[v] = True
        for w in edges.get(v, ()):
            if w not in idx:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif on.get(w):
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stack.pop()
                on[w] = False
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in edges.get(v, ()):
                out.append(sorted(comp))

    for v in nodes:
        if v not in idx:
            strongconnect(v)
    return out


mods = _discover()
assert len(mods) > 100, f"discovery looks broken — only found {len(mods)} modules"
edges, unparseable = _edges(mods)
assert not unparseable, f"first-party modules failed to parse: {unparseable}"

cycles = _cycles(edges, list(mods))
if cycles:
    lines = "\n".join("  CYCLE: " + " -> ".join(c) for c in cycles)
    raise AssertionError(f"{len(cycles)} top-level import cycle(s) found:\n{lines}")

# REL-8: every first-party module opens with a header docstring — the one-paragraph "what this is"
# a newcomer reads before the code. Enforced so it stays true as modules are added.
undocumented = []
for name, path in mods.items():
    if name.endswith("__init__") or os.path.basename(path) == "__init__.py":
        continue
    with open(path, encoding="utf-8") as fh:
        first = fh.readline()
    if not first.lstrip().startswith(('"""', "'''", 'r"""', 'f"""')):
        undocumented.append(name)
assert not undocumented, f"module(s) missing a header docstring (REL-8): {undocumented}"

edge_count = sum(len(v) for v in edges.values())
print(f"test_import_cycles OK - no top-level import cycles across {len(mods)} first-party modules "
      f"(aec_api + aec_data), {edge_count} intra-package import edges. Function-local/deferred imports are "
      f"correctly ignored (they don't cycle at import time). Guards the REL-3 façade layering. "
      f"REL-8: every module opens with a header docstring (enforced).")
