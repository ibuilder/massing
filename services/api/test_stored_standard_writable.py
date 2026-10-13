"""Can the firm WRITE the standard the server refuses without? — CLAUSE-DARK.

Eight modules under `src/aec_api/` are the same shape: a project's stored **standard**, with a
module-level `load(pid)` / `save(pid, …)` pair over `storage`. An engine reads it, and when the store
is empty the engine does not guess — it refuses, by name, and several of them tell the reader to go
and write one. `clause_playbook.from_project` is the clearest:

    {"verdict": "no_playbook", "reason": "no clause playbook stored for contract type 'subcontract'",
     "note": "Store a playbook first — reviewing without a written standard is the problem this
              feature exists to fix."}

**That refusal was unanswerable for the whole life of the feature.** `reviewContractClauses` HAS a
caller, so the review ran; `saveClausePlaybook` had none, so `no_playbook` was the only answer the
screen could ever print, on every project that has ever existed. *A refusal is only honest if its
remedy is reachable* — and nothing checked the remedy, because every gate here asks about one side:
`test_route_reachability` asks whether a route is called, `clientCallers.test.ts` asks whether a
client method is called, and neither asks whether a capability's READ and WRITE halves are both
reachable. A standard you can consult and cannot author is not a feature with a missing button; it
is an engine whose input can never arrive.

### What this derives

The population is the `load`/`save`-over-`storage` modules, by AST — not a list in this file, so a
ninth standard added tomorrow is in scope the day it lands. For each one the write route is found by
walking the routers for a call to `<module>.save(`, and the client method by matching that route's
path against the template literals in `apps/web/src/api/`. Reachability of that method is read from
`clientCallers.test.ts`'s `UNCALLED` record, which is **not prose**: that file asserts the list is
EXACTLY the measured set in both directions and mutation-proves the assertion, so reading it here is
reading a gate's output rather than a comment. The alternative — a second TypeScript scanner in
Python — is the drift `web_source.py`'s own docstring warns about, and it would drift in the
direction that invents work.

It FAILS CLOSED at every join: a module whose `save` no router calls, a route path no client
template matches, a client method whose enclosing name cannot be determined — each is UNKNOWN and
reds the build. All three were candidates to be silently dropped, and *a predicate that decides what
to LOOK at is more dangerous than one that decides what to report.*

### Three are still unwritable, and they are NAMED rather than exempted

| module | write route | client method | state |
|---|---|---|---|
| `clause_playbook` | PUT …/contracts/playbook | `saveClausePlaybook` | **FIXED 2026-10-13** — the editor is the fourth tab of Risk Review |
| `macros` | PUT …/macros | `saveMacros` | **OPEN** |
| `view_templates` | PUT …/view-templates | `saveViewTemplates` | **OPEN** |
| `workflow_config` | PUT …/workflow/{key} | *none declared* | **OPEN** — and invisible to the gate next door |

`OPEN_STANDARDS` below is a **down-only record**, the same shape and for the same reason as
`UNCALLED`: this file's job is to stop the set growing silently, not to forbid the commit that lands
an engine before its editor. Removing a line is the fix; adding one is a deliberate act that says "I
am shipping another standard nobody can write", and it belongs in the commit message.

**`workflow_config` is the instance worth the most.** It has **no client method at all**, so it
cannot appear on `UNCALLED` — you cannot be on a list of unreachable client methods if nobody ever
declared one. *A register reports on what it contains, and the absence of a member reads exactly like
a clean bill.* `test_route_reachability.py` does freeze that URL, which is the other half of the same
question asked from the server side, and the two together are why this one is recorded rather than
newly discovered. It is in this table because the GROUPING is the finding: four of eight project
standards could not be written, and read one at a time they are four unrelated missing buttons.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_stored_standard_writable.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: Anchored on `__file__`. `run_tests.py` chdirs into `services/api` and `ci.yml` runs
#: `python services/api/run_tests.py` from the repo root — and a glob over a directory that is not
#: there yields nothing and raises nothing, which is how `test_schema_types_agree` shipped a gate
#: that reported a clean tree under CI and nowhere else.
ROOT = HERE.parent.parent
PKG = HERE / "src" / "aec_api"
ROUTERS = PKG / "routers"
WEB_API = ROOT / "apps" / "web" / "src" / "api"
CALLERS = WEB_API / "clientCallers.test.ts"

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


class Unclassified(Exception):
    """A join this cannot resolve. Never caught into a skip — see FAILS CLOSED above."""


#: Standards whose write half has no reachable caller. DOWN-ONLY: delete a line when you wire one.
OPEN_STANDARDS: dict[str, str] = {
    "macros": "saveMacros has no app caller — the recipe-macro library falls back to a starter set "
              "and nothing can save over it",
    "view_templates": "saveViewTemplates has no app caller — view templates can be listed and never "
                      "authored",
    "workflow_config": "no client method declares PUT /projects/{pid}/workflow/{key} at all, so the "
                       "per-module workflow is server-only (also frozen in test_route_reachability)",
}


# ---------------------------------------------------------------------------------------------
# 1. the population — a stored per-project standard

def stored_standards(pkg: Path) -> list[str]:
    """Modules with a module-level `load` AND `save` that touch `storage`.

    Module-level on purpose: a `save` method on a class is a different thing, and the shape this is
    about is the leaf that owns one blob per project.
    """
    out = []
    for f in sorted(pkg.glob("*.py")):
        src = f.read_text(encoding="utf-8")
        top = {n.name for n in ast.parse(src).body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if {"load", "save"} <= top and "storage." in src:
            out.append(f.stem)
    return out


# ---------------------------------------------------------------------------------------------
# 2. the write route

_WRITE_VERBS = ("put", "post", "patch")


def _aliases_module_level(tree: ast.Module) -> dict[str, str]:
    """Top-level `from .. import X [as Y]` only — a nested import belongs to its own function."""
    out: dict[str, str] = {}
    for n in tree.body:
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out[a.asname or a.name] = a.name
    return out


def _aliases(scope: ast.AST) -> dict[str, str]:
    """Local name -> module name, for every `from .. import X [as Y]` in this scope.

    **The first draft matched `<module>.save(` on the bare module name and MISSED TWO of eight.**
    `authoring.py` writes `from .. import macros as mac` and `standards.py`
    `from .. import view_templates as vt`, both inside the handler, so the attribute's value is
    `mac` / `vt` and nothing named `macros` or `view_templates` appears in the call at all. *A
    defect the analyser cannot spell is invisible to it and reads exactly like an absent one* —
    which is the same spelling failure `test_gap_records` paid for twice.

    It failed CLOSED, and that is the only reason this note exists rather than a clean verdict over
    six of eight: the join raised `Unclassified` and named the two modules. A version that had
    returned "no write route, so nothing to check" would have reported the tree clean and taken
    `macros` and `view_templates` out of the population on the way.
    """
    out: dict[str, str] = {}
    for n in ast.walk(scope):
        if isinstance(n, ast.ImportFrom):
            for a in n.names:
                out[a.asname or a.name] = a.name
    return out


def write_routes(routers: Path, module: str) -> list[tuple[str, str]]:
    """(METHOD, path) for every route handler that calls `<module>.save(...)`, alias included."""
    found: list[tuple[str, str]] = []
    for f in sorted(routers.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        outer = _aliases_module_level(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            names = {k for k, v in {**outer, **_aliases(node)}.items() if v == module}
            calls_save = any(
                isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr == "save" and isinstance(c.func.value, ast.Name)
                and c.func.value.id in names
                for c in ast.walk(node))
            if not calls_save:
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                if dec.func.attr not in _WRITE_VERBS:
                    continue
                if not (dec.args and isinstance(dec.args[0], ast.Constant)
                        and isinstance(dec.args[0].value, str)):
                    raise Unclassified(f"{f.name}:{node.name}: route path is not a literal")
                found.append((dec.func.attr.upper(), dec.args[0].value))
    return found


# ---------------------------------------------------------------------------------------------
# 3. the client method that posts to it

#: A path template `/projects/{pid}/x` as the client writes it: `/projects/${pid}/x`.
def path_regex(path: str) -> re.Pattern[str]:
    parts = re.split(r"\{[^}]*\}", path)
    return re.compile(r"\$\{[^}]*\}".join(re.escape(p) for p in parts))


#: Lexical, not domain: these are the JavaScript keywords a `name(` line can start with. There is no
#: judgement in this list, which is why it is allowed to be a list at all.
_NOT_A_METHOD = {"if", "for", "while", "switch", "catch", "return", "function", "do", "else"}
_METHOD_START = re.compile(r"^\s{2,6}(?:async )?([a-zA-Z_]\w*)\(")


def client_writers(web_api: Path, method: str, path: str) -> list[str]:
    """Client methods whose body builds `path` and sends `method`.

    FAILS CLOSED: a matching template literal whose enclosing method name cannot be determined
    raises, rather than being dropped — a path matched and attributed to nobody is exactly the
    silent narrowing this file exists not to do.
    """
    pat = path_regex(path)
    out: list[str] = []
    for f in sorted(web_api.glob("*.ts")):
        if f.name.endswith((".test.ts", ".d.ts")):
            continue
        lines = f.read_text(encoding="utf-8").split("\n")
        current: str | None = None
        for i, line in enumerate(lines):
            m = _METHOD_START.match(line)
            if m and m.group(1) not in _NOT_A_METHOD:
                current = m.group(1)
            if not pat.search(line):
                continue
            # BOUNDED AT THE NEXT METHOD, not at a fixed five lines. `api/client.ts` declares
            # `sharedParams` immediately above `saveSharedParams`, so a five-line window from the
            # GET's path literal reaches the PUT's `method: "PUT"` and reported the READER as a
            # writer. Harmless there because the real writer is also found — which is the point: a
            # window that spills into the next declaration produces a confident wrong attribution
            # that only looks right while something else happens to be correct.
            stop = i + 1
            while stop < len(lines) and stop < i + 6:
                nxt = _METHOD_START.match(lines[stop])
                if nxt and nxt.group(1) not in _NOT_A_METHOD:
                    break
                stop += 1
            window = "\n".join(lines[i:stop])
            verb = re.search(r'method:\s*"(\w+)"', window)
            if not verb or verb.group(1).upper() != method:
                continue
            if current is None:
                raise Unclassified(f"{f.name}:{i + 1}: {method} {path} is built outside any method")
            out.append(current)
    return out


# ---------------------------------------------------------------------------------------------
# 4. is that method reached? — read from the gate that proves its own list exact

def uncalled_record(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    m = re.search(r"const UNCALLED: readonly string\[\] = \[(.*?)\n\];", src, re.S)
    if m is None:
        raise Unclassified("clientCallers.test.ts no longer declares UNCALLED in the expected form")
    body = re.sub(r"//[^\n]*", "", m.group(1))
    return set(re.findall(r'"([A-Za-z_]\w*)"', body))


def verdict(standards: list[str], resolve) -> dict[str, str]:
    """module -> why it is unwritable, for every standard that is.

    Separate from the reporting so a mutation can be aimed at the RULE. `test_unique_read_guard`'s
    own first draft asserted that its analyser still REPORTED a site, so a mutation routing every
    verdict to "safe" passed; reporting a site and ruling on it are two different questions.
    """
    bad: dict[str, str] = {}
    for mod in standards:
        routes, methods, uncalled = resolve(mod)
        if not routes:
            raise Unclassified(f"{mod}: load/save over storage, and no router calls {mod}.save()")
        if not methods:
            bad[mod] = f"no client method declares {routes[0][0]} {routes[0][1]}"
            continue
        reached = [n for n in methods if n not in uncalled]
        if not reached:
            bad[mod] = f"{', '.join(sorted(set(methods)))} has no app caller"
    return bad


# ---------------------------------------------------------------------------------------------
# PRECONDITIONS AND MUTATIONS — before any verdict

_STANDARDS = stored_standards(PKG)
_UNCALLED = uncalled_record(CALLERS)

check("the AST walk found the stored-standard population it exists to watch",
      len(_STANDARDS) >= 8,
      f"only {len(_STANDARDS)} found: {_STANDARDS} — a population this small means the walk broke, "
      "and its verdict would read 'clean' either way")
check("the UNCALLED record parsed, so reachability is read rather than assumed",
      len(_UNCALLED) >= 40 and "colorFacets" in _UNCALLED,
      f"{len(_UNCALLED)} names parsed from clientCallers.test.ts — `colorFacets` is asserted present "
      "there as a method with NO app call site, so its absence here means this parse is wrong, not "
      "that the app grew a caller")

_ROUTES = {m: write_routes(ROUTERS, m) for m in _STANDARDS}
_METHODS = {m: client_writers(WEB_API, *_ROUTES[m][0]) if _ROUTES[m] else [] for m in _STANDARDS}
check("every standard's save() is reached by a router, and every route by at most one path shape",
      all(_ROUTES[m] for m in _STANDARDS),
      f"no write route found for {[m for m in _STANDARDS if not _ROUTES[m]]}")


def _resolve(mod: str):
    return _ROUTES[mod], _METHODS[mod], _UNCALLED


_BAD = verdict(_STANDARDS, _resolve)

# REPLAY — the shipped defect must be re-found. `saveClausePlaybook` was on UNCALLED until this
# change; put it back and `clause_playbook` must be reported, or the rule is not testing the rule.
def _replay(mod: str):
    return _ROUTES[mod], _METHODS[mod], _UNCALLED | {"saveClausePlaybook"}


_REPLAYED = verdict(_STANDARDS, _replay)
check("replays CLAUSE-DARK as shipped and re-finds it",
      "clause_playbook" in _REPLAYED
      and set(_REPLAYED) == set(_BAD) | {"clause_playbook"},
      f"replay found {sorted(_REPLAYED)}; today's verdict is {sorted(_BAD)} — the replay must add "
      "exactly clause_playbook and nothing else")

# MUTATION — a standard whose client method vanishes entirely must be reported for the OTHER reason,
# because "declared and uncalled" and "never declared" are different findings and `workflow_config`
# is the live instance of the second.
def _no_methods(mod: str):
    return _ROUTES[mod], ([] if mod == "deal_authority" else _METHODS[mod]), _UNCALLED


_GONE = verdict(_STANDARDS, _no_methods)
check("an undeclared write route is reported, and not as an uncalled method",
      "deal_authority" in _GONE and "no client method declares" in _GONE["deal_authority"],
      f"mutation reported {_GONE.get('deal_authority')!r}")

# FAIL CLOSED — a standard no router writes must raise, never pass as 'fine'.
try:
    verdict(["clause_playbook"], lambda m: ([], [], _UNCALLED))
    _closed = False
except Unclassified:
    _closed = True
check("a standard whose save() no router calls reds the build instead of leaving the population",
      _closed, "verdict() accepted a standard with no write route")

# The path matcher, both directions — a matcher that answers yes to everything proves nothing.
check("the path matcher resolves a real route and refuses a near-miss",
      client_writers(WEB_API, "PUT", "/projects/{pid}/contracts/playbook") == ["saveClausePlaybook"]
      and client_writers(WEB_API, "PUT", "/projects/{pid}/contracts/playbooks") == []
      and client_writers(WEB_API, "POST", "/projects/{pid}/contracts/playbook") == [],
      f"PUT playbook -> {client_writers(WEB_API, 'PUT', '/projects/{pid}/contracts/playbook')}, "
      f"near-miss -> {client_writers(WEB_API, 'PUT', '/projects/{pid}/contracts/playbooks')}, "
      f"wrong verb -> {client_writers(WEB_API, 'POST', '/projects/{pid}/contracts/playbook')}")


# ---------------------------------------------------------------------------------------------
# THE VERDICT

_NEW = {m: why for m, why in _BAD.items() if m not in OPEN_STANDARDS}
_WIRED = sorted(set(OPEN_STANDARDS) - set(_BAD))

check(f"no project standard became unwritable ({len(_STANDARDS)} standards)",
      not _NEW,
      f"{len(_NEW)} newly unwritable: "
      + "; ".join(f"{m}: {why}" for m, why in sorted(_NEW.items()))
      + " — an engine that refuses for want of a stored standard, and no way to store one. Wire the "
        "write half to a screen, or add it to OPEN_STANDARDS and say in the commit why shipping "
        "another standard nobody can author is worth it")

check("OPEN_STANDARDS names only standards that are still unwritable",
      not _WIRED,
      f"{_WIRED} can now be written — delete those line(s). A stale entry is slack the next person "
      "spends without knowing, and this list is the RECORD of what cannot be authored")

print()
print(f"  population ({len(_STANDARDS)}): " + ", ".join(_STANDARDS))
for m in _STANDARDS:
    verb, path = _ROUTES[m][0]
    who = ", ".join(sorted(set(_METHODS[m]))) or "no client method"
    print(f"    {'OPEN' if m in _BAD else ' ok '}  {m:16} {verb} {path:38} {who}")
if FAILED:
    print(f"stored_standard_writable: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"stored_standard_writable: all checks passed — {len(_STANDARDS)} standards, "
      f"{len(_BAD)} unwritable (all named in OPEN_STANDARDS)")
