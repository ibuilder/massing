"""Can anybody SEE the verdict? — PROVENANCE-DARK.

Ten modules across the two engine roots compute a **verdict**: a dict carrying a `"verdict"` key, the
output of an engine whose whole job is to reach a conclusion somebody acts on. They are the most
carefully written code in this tree — `provenance_report.report` keeps four states and makes
`not_captured` deliberately distinct from `no_data`, because *"'you have not filled this in' and
'this system has nowhere to put it' send a reader to completely different places"* — and a verdict
nobody can read is the one kind of dead code that costs a decision rather than a byte.

**Two of the ten are dark, and the pair of gates that should have caught them are silent for two
DIFFERENT reasons, neither of which is a bug.**

* `test_route_reachability.py` **declines to rule** on `GET /projects/{pid}/drawing-set/qa`: its
  `MIN_SEGMENT = 5` and the leaf is `qa`, two characters, so the route sits in that file's bounded
  sub-`MIN_SEGMENT` population — the set it honestly says it cannot judge, rather than one it judged
  clean.
* `clientCallers.test.ts` **cannot see any of them**, because a route with no client method cannot
  appear on a list of unreachable client *methods*. That is the `workflow_config` lesson again, now
  with three more instances: *a register reports on what it contains, and the absence of a member
  reads exactly like a clean bill.*

The capability falls through the gap between a documented coarseness and a structural blind spot.
This file is the third question — not "is the route called" and not "is the method called", but **is
this engine's conclusion reachable from a screen at all.**

### The predicate is MODULE-level, and that was measured rather than assumed

The first draft asked whether a route handler calls the engine's **verdict function** by name. That
reported `condition_checks` and `vendor_memory` as having no route at all — because `design.py` calls
`condition_checks.check_all` (which calls `check_condition`) and `benchmarking.py` calls
`vendor_memory.vendor_memory`, a sibling of the function holding the dict. **A function-level
predicate under-counted the reachable set by two and would have reported two healthy capabilities as
dark**, which is the flattering direction for a checker: it invents work. Both predicates are
implemented below and the self-test asserts they DISAGREE on exactly those two, so the module-level
rule cannot be quietly narrowed back.

### A module with one live door and one dark one is a different finding

`rfi_qa` serves `POST …/rfi/qa` (reachable, `rfiQa`) and `POST …/ai/audit` (no client method). The
engine's conclusion IS reachable; one of its two doors is not. That is dead surface rather than a
dark capability, and folding the two together would let a genuinely dark engine hide behind a
sibling route — so they are counted and reported apart.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_verdict_reachable.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Anchored on `__file__`, never the working directory — `run_tests.py` chdirs into `services/api`
#: and `ci.yml` invokes it from the repo root, and a glob over a missing directory yields nothing and
#: raises nothing. `test_schema_types_agree` shipped that bug and reported a clean tree under CI only.
ROOT = HERE.parent.parent
ENGINE_ROOTS = [HERE / "src" / "aec_api", ROOT / "services" / "data" / "src" / "aec_data"]
ROUTERS = HERE / "src" / "aec_api" / "routers"
WEB_API = ROOT / "apps" / "web" / "src" / "api"
CALLERS = WEB_API / "clientCallers.test.ts"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


class Unclassified(Exception):
    """A join this cannot resolve. Never caught into a skip."""


#: Engines whose verdict no screen can reach. DOWN-ONLY: delete a line when you wire one.
OPEN_VERDICTS: dict[str, str] = {
    "drawing_qa": "GET /projects/{pid}/drawing-set/qa has no client method — the drawing-set QA "
                  "review and its verdict are computed for nobody",
}
#: `provenance_report` was here until PROVENANCE-DARK wired `projectAdmissibility`; it moved to
#: OPEN_DOORS, which is the move this file's two lists exist to distinguish.
#: Routes that reach a reachable engine by a door nothing calls. Dead surface, not a dark capability.
OPEN_DOORS: dict[str, str] = {
    "rfi_qa": "POST /projects/{pid}/ai/audit has no client method; the engine is reachable through "
              "POST /projects/{pid}/rfi/qa (rfiQa)",
    #: The STATELESS sibling, and it stays dark deliberately rather than for want of effort: its body
    #: is `{assumptions_provenance, estimate_ledger, agent_answers}`, each the OUTPUT of another
    #: engine, and the SPA has no reason to assemble three leg results client-side when
    #: `GET /projects/{pid}/provenance/admissibility` gathers them on the server. A client method for
    #: it would be a caller invented to satisfy a gate.
    "provenance_report": "POST /proforma/provenance/admissibility has no client method; the engine is "
                         "reachable through GET /projects/{pid}/provenance/admissibility "
                         "(projectAdmissibility), which gathers the three legs server-side",
}


# ---------------------------------------------------------------------------------------------
# 1. the population — modules that compute a verdict

def verdict_modules(roots: list[Path]) -> dict[str, Path]:
    """module stem -> path, for every module with a dict literal carrying a `"verdict"` key."""
    out: dict[str, Path] = {}
    for root in roots:
        if not root.exists():
            continue
        for f in sorted(root.rglob("*.py")):
            if "/routers/" in f.as_posix() or f.name.startswith("test_"):
                continue
            src = f.read_text(encoding="utf-8")
            if '"verdict"' not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError as e:                       # pragma: no cover
                raise Unclassified(f"{f.name} does not parse: {e}") from None
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict) and any(
                        isinstance(k, ast.Constant) and k.value == "verdict"
                        for k in node.keys if k is not None):
                    out[f.stem] = f
                    break
    return out


# ---------------------------------------------------------------------------------------------
# 2. the routes that reach them

def _aliases(scope: ast.AST, top_only: bool = False) -> dict[str, str]:
    body = getattr(scope, "body", []) if top_only else ast.walk(scope)
    out: dict[str, str] = {}
    for n in body:
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out[a.asname or a.name] = a.name
    return out


def routes_for(modules: set[str], *, functions: dict[str, set[str]] | None = None
               ) -> dict[str, set[tuple[str, str]]]:
    """module -> {(METHOD, path)} for every route handler that reaches it.

    `functions` is the NARROW variant kept only so the self-test can prove the two disagree: when
    given, a handler counts only if it calls one of the named functions of that module.
    """
    found: dict[str, set[tuple[str, str]]] = {}
    for f in sorted(ROUTERS.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        outer = _aliases(tree, top_only=True)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            amap = {**outer, **_aliases(fn)}
            touched: set[str] = set()
            for c in ast.walk(fn):
                if not (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and isinstance(c.func.value, ast.Name)):
                    continue
                mod = amap.get(c.func.value.id)
                if mod not in modules:
                    continue
                if functions is not None and c.func.attr not in functions.get(mod, set()):
                    continue
                touched.add(mod)
            if not touched:
                continue
            for dec in fn.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if not dec.args:
                    continue
                if not isinstance(dec.args[0], ast.Constant):
                    raise Unclassified(f"{f.name}:{fn.name}: route path is not a literal")
                for mod in touched:
                    found.setdefault(mod, set()).add((dec.func.attr.upper(), dec.args[0].value))
    return found


def verdict_functions(path: Path) -> set[str]:
    """The functions of one module that build a dict with a `"verdict"` key — the NARROW population."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in ast.walk(fn):
            if isinstance(d, ast.Dict) and any(
                    isinstance(k, ast.Constant) and k.value == "verdict"
                    for k in d.keys if k is not None):
                out.add(fn.name)
                break
    return out


# ---------------------------------------------------------------------------------------------
# 3. is a route reachable from a screen?

def uncalled_record(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(r"const UNCALLED: readonly string\[\] = \[(.*?)\n\];", src, re.S)
    if m is None:
        raise Unclassified("clientCallers.test.ts no longer declares UNCALLED in the expected form")
    return set(re.findall(r'"([A-Za-z_]\w*)"', re.sub(r"//[^\n]*", "", m.group(1))))


_MSTART = re.compile(r"^\s{2,6}(?:async )?([a-zA-Z_]\w*)\(")
#: Lexical, not domain: the JavaScript keywords a `name(` line can begin with.
_NOT_A_METHOD = {"if", "for", "while", "switch", "catch", "return", "function", "do", "else"}


def path_regex(path: str) -> re.Pattern[str]:
    return re.compile(r"\$\{[^}]*\}".join(re.escape(p) for p in re.split(r"\{[^}]*\}", path)))


def client_methods(path: str) -> set[str]:
    """Client methods whose body builds `path`. Verb-agnostic deliberately: this asks whether the URL
    is reachable at all, and a method that reads it is as good as one that writes it."""
    pat = path_regex(path)
    out: set[str] = set()
    for f in sorted(WEB_API.glob("*.ts")):
        if f.name.endswith((".test.ts", ".d.ts")):
            continue
        current: str | None = None
        for line in f.read_text(encoding="utf-8").split("\n"):
            m = _MSTART.match(line)
            if m and m.group(1) not in _NOT_A_METHOD:
                current = m.group(1)
            if pat.search(line):
                if current is None:
                    raise Unclassified(f"{f.name}: {path} is built outside any method")
                out.add(current)
    return out


def verdict(mods: dict[str, set[tuple[str, str]]], uncalled: set[str],
            methods=client_methods) -> tuple[dict[str, str], dict[str, str]]:
    """(dark engines, dead doors). Separate from the reporting so a mutation can aim at the RULE."""
    dark: dict[str, str] = {}
    doors: dict[str, str] = {}
    for mod, rs in sorted(mods.items()):
        if not rs:
            raise Unclassified(f"{mod} computes a verdict and no route reaches it at all")
        live, blocked = [], []
        for verb, path in sorted(rs):
            found = methods(path)
            if any(n not in uncalled for n in found):
                live.append(path)
            else:
                blocked.append(f"{verb} {path}" + (f" ({', '.join(sorted(found))} uncalled)"
                                                   if found else " (no client method)"))
        if not live:
            dark[mod] = "; ".join(blocked)
        elif blocked:
            doors[mod] = "; ".join(blocked)
    return dark, doors


# ---------------------------------------------------------------------------------------------
# PRECONDITIONS AND MUTATIONS — before any verdict is printed

_MODULES = verdict_modules(ENGINE_ROOTS)
_UNCALLED = uncalled_record(CALLERS)
_WIDE = routes_for(set(_MODULES))

check("the walk found the verdict engines it exists to watch",
      len(_MODULES) >= 10,
      f"only {len(_MODULES)} found: {sorted(_MODULES)} — a population this small means the walk "
      "broke, and its verdict below would read 'clean' either way")
check("the UNCALLED record parsed, so reachability is read rather than assumed",
      len(_UNCALLED) >= 40 and "colorFacets" in _UNCALLED,
      f"{len(_UNCALLED)} names parsed — `colorFacets` is asserted there as a method with NO app call "
      "site, so its absence means this parse is wrong, not that the app grew a caller")
check("every verdict engine is reached by at least one route",
      all(_WIDE.get(m) for m in _MODULES),
      f"no route reaches {[m for m in _MODULES if not _WIDE.get(m)]} — an engine with no door at all "
      "is a different finding and must not pass through here silently")

# THE PREDICATE SELF-TEST. A function-level rule under-counts, and the two must be shown to disagree
# or the module-level rule can be narrowed back by anybody who finds it loose.
_NARROW = routes_for(set(_MODULES), functions={m: verdict_functions(p) for m, p in _MODULES.items()})
_MISSED = sorted(m for m in _MODULES if _WIDE.get(m) and not _NARROW.get(m))
check("the MODULE-level predicate is load-bearing: a function-level one loses engines",
      _MISSED == ["condition_checks", "vendor_memory"],
      f"the narrow predicate misses {_MISSED}, expected ['condition_checks', 'vendor_memory'] — "
      "`design.py` calls `condition_checks.check_all` and `benchmarking.py` "
      "`vendor_memory.vendor_memory`, both siblings of the function holding the dict. If this list "
      "changed, re-derive which rule is right before touching the one below; a checker that reports "
      "a healthy capability as dark invents work")

_DARK, _DOORS = verdict(_WIDE, _UNCALLED)

# MUTATION 1 — an engine whose every door loses its client method must be reported DARK.
check("an engine with no reachable door is reported dark",
      verdict({"synthetic": {("GET", "/projects/{pid}/nothing-builds-this")}}, _UNCALLED)
      == ({"synthetic": "GET /projects/{pid}/nothing-builds-this (no client method)"}, {}),
      str(verdict({"synthetic": {("GET", "/projects/{pid}/nothing-builds-this")}}, _UNCALLED)))

# MUTATION 2 — one LIVE door is enough, and a dead sibling is reported apart rather than folded in.
# Without this, a genuinely dark engine could hide behind a reachable sibling route.
_two = {"synthetic": {("GET", "/projects/{pid}/ai-readiness"),
                      ("GET", "/projects/{pid}/nothing-builds-this")}}
_d2, _o2 = verdict(_two, _UNCALLED)
check("one live door spares the engine, and the dead sibling is still named",
      not _d2 and "synthetic" in _o2 and "nothing-builds-this" in _o2["synthetic"],
      f"dark={_d2}, doors={_o2}")

# MUTATION 3 — a method that EXISTS but is itself unreachable does not count as a door.
# This is the whole reason the UNCALLED record is read: `clause_playbook`'s GET and PUT were
# declared for months and called by nothing, and a presence check would have called them live.
_frozen = _UNCALLED | {"clausePlaybook", "saveClausePlaybook", "reviewContractClauses"}
_d3, _ = verdict({"clause_playbook": _WIDE["clause_playbook"]}, _frozen)
check("a DECLARED but uncalled client method is not a door",
      "clause_playbook" in _d3 and "uncalled" in _d3["clause_playbook"],
      f"{_d3} — replaying CLAUSE-DARK as it shipped must report the engine dark")

# …and with only the review route restored, the engine is reachable again: the discrimination.
_d4, _o4 = verdict({"clause_playbook": _WIDE["clause_playbook"]},
                   _UNCALLED | {"clausePlaybook", "saveClausePlaybook"})
check("…and one restored caller is enough to clear it",
      not _d4 and "clause_playbook" in _o4,
      f"dark={_d4}, doors={_o4}")

# FAIL CLOSED — an engine with no route must raise, never pass as fine.
try:
    verdict({"orphan": set()}, _UNCALLED)
    _closed = False
except Unclassified:
    _closed = True
check("an engine no route reaches reds the build instead of leaving the population", _closed,
      "verdict() accepted an engine with no route")

# The path matcher, both directions.
check("the path matcher resolves a real route and refuses a near-miss",
      client_methods("/projects/{pid}/ai-readiness") and not client_methods("/projects/{pid}/ai-readinesses"),
      f"ai-readiness -> {sorted(client_methods('/projects/{pid}/ai-readiness'))}, "
      f"near-miss -> {sorted(client_methods('/projects/{pid}/ai-readinesss'))}")


# ---------------------------------------------------------------------------------------------
# THE VERDICT

_NEW_DARK = {m: why for m, why in _DARK.items() if m not in OPEN_VERDICTS}
_NEW_DOORS = {m: why for m, why in _DOORS.items() if m not in OPEN_DOORS}
_WIRED = sorted(set(OPEN_VERDICTS) - set(_DARK))
_WIRED_DOORS = sorted(set(OPEN_DOORS) - set(_DOORS))

check(f"no engine's verdict became unreachable ({len(_MODULES)} verdict engines)",
      not _NEW_DARK,
      f"{len(_NEW_DARK)} newly dark: " + "; ".join(f"{m}: {w}" for m, w in sorted(_NEW_DARK.items()))
      + " — an engine that reaches a conclusion nobody can read. Give its route a client method and "
        "a screen, or add it to OPEN_VERDICTS and say in the commit why shipping another unreadable "
        "verdict is worth it")
check("no reachable engine grew a door nothing calls",
      not _NEW_DOORS,
      f"{len(_NEW_DOORS)} new dead door(s): "
      + "; ".join(f"{m}: {w}" for m, w in sorted(_NEW_DOORS.items()))
      + " — the engine is reachable, so this is dead surface rather than a dark capability; wire it "
        "or delete the route")
check("OPEN_VERDICTS names only engines that are still dark", not _WIRED,
      f"{_WIRED} can now be read — delete those line(s). A stale entry is slack the next person "
      "spends without knowing")
check("OPEN_DOORS names only doors that are still dead", not _WIRED_DOORS, f"{_WIRED_DOORS}")

print()
for m in sorted(_MODULES):
    state = "DARK" if m in _DARK else ("door" if m in _DOORS else " ok ")
    print(f"  {state}  {m:20} " + "; ".join(f"{v} {p}" for v, p in sorted(_WIDE[m])))
if FAILED:
    print(f"verdict_reachable: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"verdict_reachable: all checks passed — {len(_MODULES)} verdict engines, {len(_DARK)} dark "
      f"and {len(_DOORS)} with a dead door (all named)")
