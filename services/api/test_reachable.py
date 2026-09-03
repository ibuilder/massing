"""ARCH-REACH — every engine must be reachable from a route, or say why not.

This is the executable form of the lesson that cost the most this cycle. Across v0.3.701–710, eleven
things were built and **seven shipped with no route**: fully tested, CI-green, and impossible to
call. From the outside that is indistinguishable from a working feature, and it survived ten releases
because every gate was green — the engine's own suite, the full suite, CI, CodeQL. None of them asks
whether a request can arrive.

The idea of turning an architectural claim into something that fails a build rather than ageing into
fiction is borrowed from the companion kernel repo's `check:architecture`. Prose in a README cannot
hold an invariant; a check can. That mattered here specifically because two codebases were being
built in parallel against shared assumptions, and every assumption that was written down in prose
instead of asserted had drifted by the time anyone looked.

**What is checked.** Build the import graph over `aec_api`, seed it from everything the routers, the
MCP tool surface and `main` import, and walk it transitively. A module reached that way is callable
by a request. Anything else must appear in `ENTRY_POINTS` (reached another way, with the way named)
or `KNOWN_UNREACHABLE` (a real gap, dated and tracked). Anything else at all fails.

Two directions, both deliberate:
  * a NEW unreachable module fails — that is the regression this exists to stop;
  * a KNOWN_UNREACHABLE that becomes reachable ALSO fails — so the list cannot quietly rot into a
    place where things are parked and forgotten. Fixing one means deleting its entry.

Transitive, not direct: routers overwhelmingly import engines lazily inside handlers, and an engine
called by another engine that has a route is reachable. A direct-reference check would report ~250
false positives and be switched off within a week.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_reachable.py
"""
from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).parent / "src" / "aec_api"

# Reached by something other than an HTTP route. The VALUE is the way in — an entry named without a
# way in is just an allowlist, and an allowlist without reasons is where unreachable code goes to
# hide (which is the very failure this file exists to catch).
ENTRY_POINTS = {
    "main": "the FastAPI app itself — the root every route hangs off, so it seeds the walk",
    "desktop": "separate process entry point: `desktop_entry.py` and `python -m aec_api.desktop`",
    "demo_seed": "build-time script, invoked by build_demo_data.py to capture the demo snapshot",
    "worker": "separate process entry point: `python -m aec_api.worker`, run as the compose `worker` "
              "service when the API sets AEC_JOB_WORKER=off (JOB-WORKER-SPLIT). Reachable by being "
              "*launched*, not by being imported — which is exactly why this list has to name the way "
              "in: `docker-compose.yml` is the caller, and no amount of walking Python imports from a "
              "route will ever find it",
    "plugin_host": "separate process entry point: `python -m aec_api.plugin_host`, launched by "
                   "`plugin_registry._host` for every plugin discovery and every plugin recipe run. "
                   "SEC-PLUGIN-LOADER put a process boundary between third-party code and the API, so "
                   "the module being unreachable BY IMPORT is the point rather than an oversight — an "
                   "import edge from here to there would mean the boundary had a hole in it. "
                   "Unlike `worker`, whose caller is docker-compose, this one's caller is first-party "
                   "Python and the launch is proven end to end: `test_plugin_isolation.py` asserts the "
                   "plugin's import and its recipe both report a pid different from the API's, which "
                   "cannot happen unless this module really ran",
}

# Real gaps: tested, shipped, and callable by nothing. Each carries the date it was found so an entry
# that lingers is visibly lingering. Fixing one means DELETING its line — the test enforces that.
#
# `money` was here from 2026-07-27 and is GONE as of v0.3.718: `capital.allocate` now uses it, so the
# entry had to be removed or `test_the_known_gap_list_cannot_rot` fails. That is the mechanism doing
# its job — the list describes the present, not the past.
KNOWN_UNREACHABLE = {
}


def module_refs(path: pathlib.Path, names: set[str]) -> set[str]:
    """First-party module names this file imports, at any nesting depth.

    `from .. import audit` carries `module=None` and puts the module name in `names` — missing that
    case makes every router look as though it imports nothing, which on the first run of this walk
    reported 252 unreachable modules out of 300. A check that wrong is worse than no check, because
    the number is specific enough to be believed.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module.split(".")[-1])
            for alias in node.names:
                out.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[-1])
    return out & names


def reachable() -> tuple[set[str], set[str]]:
    modules = {p.stem for p in SRC.glob("*.py")} - {"__init__"}
    graph = {m: module_refs(SRC / f"{m}.py", modules) for m in modules}

    seeds: set[str] = set()
    for path in list((SRC / "routers").glob("*.py")) + [SRC / "mcp_tools.py", SRC / "main.py"]:
        if path.exists():
            seeds |= module_refs(path, modules)

    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        stack.extend(graph.get(m, set()) - seen)
    return modules, seen


def test_every_module_is_reachable_or_declared():
    modules, seen = reachable()
    declared = set(ENTRY_POINTS) | set(KNOWN_UNREACHABLE)
    orphans = sorted(modules - seen - declared)
    assert not orphans, (
        "These modules cannot be reached from any route, MCP tool or entry point. A tested module "
        "behind no route looks exactly like a shipped feature from the outside.\n  "
        + "\n  ".join(orphans)
        + "\n\nWire it, or add it to ENTRY_POINTS/KNOWN_UNREACHABLE in this file WITH A REASON."
    )


def test_the_known_gap_list_cannot_rot():
    # A gap that got fixed must leave the list. Otherwise the list slowly becomes a description of
    # nothing, and the next person reads it as "these are known-bad" long after they are fine.
    _, seen = reachable()
    fixed = sorted(set(KNOWN_UNREACHABLE) & seen)
    assert not fixed, (
        f"{fixed} are now reachable — delete them from KNOWN_UNREACHABLE. Leaving a fixed entry "
        "there makes the list describe the past rather than the present."
    )


def test_entry_points_still_exist():
    modules = {p.stem for p in SRC.glob("*.py")}
    missing = sorted((set(ENTRY_POINTS) | set(KNOWN_UNREACHABLE)) - modules)
    assert not missing, f"declared but no longer present: {missing} — stale entries, delete them"


def test_every_declared_module_states_its_reason():
    for name, why in {**ENTRY_POINTS, **KNOWN_UNREACHABLE}.items():
        assert len(why) > 25, f"{name} needs a real reason, not a placeholder"


def test_the_walk_actually_found_something():
    # The failure mode this whole file is about: a check that examined nothing reporting clean. If
    # the source layout moves and the glob comes back empty, every assertion above passes vacuously.
    modules, seen = reachable()
    assert len(modules) > 200, f"only {len(modules)} modules found — the source layout moved"
    assert len(seen) > 0.8 * len(modules), (
        f"only {len(seen)}/{len(modules)} reachable — the graph walk is broken, not the codebase"
    )


# --- ARCH-REACH-2: the SUBPACKAGES, which the scan above cannot see -------------------------------
#
# `reachable()` enumerates `SRC.glob("*.py")` — **non-recursive**. So `proforma/` (15 modules of money
# maths) and `report_builders/` were never orphan *candidates*: an engine could ship there behind no
# route and this gate would still report OK. Found while adding a proforma module and noticing the
# count did not move.
#
# It needs QUALIFIED names, not stems. **31 stems collide** between the top level and these packages
# (`operations`, `schedule`, `cost`, `reports`, …), so matching on a bare stem would mark
# `proforma.operations` reachable because the unrelated top-level `operations` is imported somewhere —
# a gate reporting OK for the wrong reason, which is worse than the blind spot it replaces.
SUBPACKAGES = ("proforma", "report_builders")


def _qualified_refs(path) -> set[str]:
    """Every `pkg.module` this file imports, resolved through Python's relative-import forms."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    here = path.parent.name
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            parts = (node.module or "").split(".") if node.module else []
            if parts and parts[-1] in SUBPACKAGES:                 # from ..proforma import X
                out |= {f"{parts[-1]}.{a.name}" for a in node.names}
            elif len(parts) >= 2 and parts[-2] in SUBPACKAGES:     # from ..proforma.X import y
                out.add(f"{parts[-2]}.{parts[-1]}")
            elif here in SUBPACKAGES and node.level:
                if not parts:                                      # from . import X
                    out |= {f"{here}.{a.name}" for a in node.names}
                elif len(parts) == 1:                              # from .X import y
                    out.add(f"{here}.{parts[0]}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                p = a.name.split(".")
                if len(p) >= 2 and p[-2] in SUBPACKAGES:
                    out.add(f"{p[-2]}.{p[-1]}")
    return out


def test_subpackage_modules_are_reachable():
    candidates = {f"{pkg}.{m.stem}"
                  for pkg in SUBPACKAGES
                  for m in (SRC / pkg).glob("*.py") if m.stem != "__init__"}
    assert candidates, "no subpackage modules found — the check would pass vacuously"

    graph = {c: _qualified_refs(SRC / c.split(".")[0] / f"{c.split('.')[1]}.py") for c in candidates}

    seeds: set[str] = set()
    for path in list((SRC / "routers").glob("*.py")) + [SRC / "mcp_tools.py", SRC / "main.py"]:
        if path.exists():
            seeds |= _qualified_refs(path)
    for top in SRC.glob("*.py"):
        seeds |= _qualified_refs(top)
    # A package's own `__init__.py` is a seed: importing the package RUNS it, so everything it
    # re-exports is reached. `reports.py` does `from .report_builders import …`, which executes that
    # `__init__` and pulls in `.bim`, `.finance` and the rest. Omitting this hop reported five
    # perfectly reachable builders as orphans — a gate failing the build on its own blind spot,
    # which is a worse outcome than the gap it was written to close.
    for pkg in SUBPACKAGES:
        seeds |= _qualified_refs(SRC / pkg / "__init__.py")

    seen: set[str] = set()
    stack = list(seeds & candidates)
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        stack.extend((graph.get(c, set()) & candidates) - seen)

    orphans = sorted(candidates - seen)
    joined = ", ".join(orphans)
    assert not orphans, (
        "These subpackage modules cannot be reached from any route, MCP tool or top-level module: "
        + joined
        + ". A proforma engine behind no route is money maths nobody can call. Wire it, or move it."
    )
    print(f"ARCH-REACH-2 OK - {len(seen)}/{len(candidates)} modules in {list(SUBPACKAGES)} are "
          "reachable. This check exists because the walk above globs *.py non-recursively, so these "
          "packages were never orphan candidates at all.")


for _name, _fn in sorted(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        _fn()

_mods, _seen = reachable()
print(
    f"ARCH-REACH OK - {len(_seen)}/{len(_mods)} modules are reachable from a route, an MCP tool or "
    f"main; {len(ENTRY_POINTS)} are entry points reached another way and {len(KNOWN_UNREACHABLE)} "
    "are declared gaps. This is the executable form of the lesson that cost the most this cycle: "
    "across v0.3.701-710, SEVEN of eleven things built shipped with NO ROUTE - fully tested, "
    "CI-green, and impossible to call - because every gate measures the module and none measures "
    "whether a request can arrive. The idea of turning an architectural claim into something that "
    "fails a build rather than ageing into fiction is borrowed from the companion kernel repo's "
    "check:architecture, and it mattered here because two codebases were being built in parallel "
    "and every shared assumption written in prose instead of asserted had drifted by the time "
    "anyone looked. It found two more on its first run: `money`, decimal-precise currency helpers "
    "with their own suite and zero importers - so the float-drift they exist to prevent is still "
    "present everywhere money is computed - and `supply_chain`, security hardening that nothing "
    "invoked. **`supply_chain` was fixed on 2026-08-29 and its entry deleted**, which is this "
    "check working in the second direction: `pdf_sanity` called itself a pre-ingest gate for a "
    "month while nothing called it, and wiring it into the PDF upload chokepoint made the module "
    "reachable and this assertion fail until the stale entry went. Both directions fail: a NEW orphan is the regression this stops, and a declared gap "
    "that becomes reachable ALSO fails, so the list cannot rot into a place where things are "
    "parked and forgotten."
)
