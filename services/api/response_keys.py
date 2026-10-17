"""Which response keys does each route return? — the SERVER half of RESPONSE-UNDECLARED.

Emits JSON on stdout so the gate that consumes it can live where the TypeScript checker runs
(`apps/web/src/api/responseUndeclared.test.ts`). **Stdlib only, deliberately**: that gate runs in the
web CI job, which installs node and web dependencies and no Python ones, so anything imported here
would have to be installed somewhere it currently is not.

WHAT IT ANSWERS, and the boundary. For every route handler under `routers/`, the top-level string
keys of every dict literal it returns, plus those of any dict literal reachable through up to
`MAX_HOPS` delegations. Routes returning a list, an ORM object or a Pydantic model are reported with
their shape and NO keys, because this cannot know what those serialise to — that is a different
derivation and pretending otherwise would understate what the server sends.

**AND IT NOW SAYS WHEN IT COULD NOT LOOK.** A route whose return is a call this cannot follow is
reported with a `call-unresolved` or `call-no-dict` shape and a `stops` entry naming where resolution
gave up. It used to be published as `{"complete": true, "keys": []}` — byte-identical to a file
download — so a consumer could not distinguish "this route sends no dict" from "nobody read this
route". `complete` means *the key set is the whole truth*, and asserting it over a key set nothing
had looked for is the one claim a derivation must never make. RESPKEY-HOP2 found 265 routes in that
state, 108 of them with a typed client call site; `apps/web/src/api/responseUndeclared.test.ts` pins
that number as a ceiling.

THREE THINGS ITS FIRST DRAFT GOT WRONG, each found by reading a reported row rather than by trusting
a count. They are recorded here because each is a way for the next version to go quietly wrong:

1. **`ast.walk` descends into nested `def`s.** A helper's `return {...}` was attributed to the route
   around it — `/codecheck/egress/bcf` reported `x, y, z`, which belong to its `_anchor` helper.
   `own_returns` walks children and stops at any nested function or lambda.

2. **A path is not a route identity; a method and a path are.** `GET` and `POST
   /projects/{pid}/models` are different routes sharing one path, and keying on the path alone
   unioned their key sets — inventing keys in both directions. Keying on `METHOD /path` moved the
   discovered population from 944 to 1018.

3. **A route returning a LIST of dicts has no top-level dict**, and must not be counted as
   dict-returning merely because dicts appear inside it.

`complete` is False when a literal carries a `**spread` or a computed key: the key set is then a
LOWER BOUND rather than the whole truth, and a consumer that treats it as exhaustive would understate
the gap. Reported, never silently dropped.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ROUTERS = pathlib.Path(__file__).resolve().parent / "src" / "aec_api" / "routers"
METHODS = {"get", "post", "put", "patch", "delete"}


def normalise(path: str) -> str:
    """`/projects/{pid}/x` -> `/projects/{}/x`, and the query string dropped.

    The client builds its paths from template literals, so the two sides can only be compared once
    every parameter is reduced to the same placeholder. Nested braces are counted rather than
    matched pairwise so a converter like `{pid:path}` collapses to one `{}` and not two.
    """
    out: list[str] = []
    depth = 0
    for ch in path.split("?")[0]:
        if ch == "{":
            depth += 1
            if depth == 1:
                out.append("{}")
        elif ch == "}":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def router_prefix(tree: ast.AST) -> str:
    """The `APIRouter(prefix=...)` a module declares. Without it every path in that module is wrong,
    and wrong in the direction that silently fails to match a client call site — which reads as
    `no client` rather than as a broken derivation."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "APIRouter":
            for kw in node.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return ""


def own_returns(fn: ast.AST) -> list[ast.Return]:
    """Return statements belonging to THIS function — not to a nested def, async def or lambda.

    See lesson 1 in the module docstring: `ast.walk` does not stop at a function boundary, so a
    helper defined inside a route handler had its return value reported as the route's response.
    """
    out: list[ast.Return] = []

    def walk(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Return):
                out.append(child)
            walk(child)

    walk(fn)
    return out


def dict_keys(node: ast.Dict) -> tuple[list[str], bool]:
    """Top-level string keys, and whether the set is COMPLETE. A `**spread` or a computed key means
    the route may send more than this names, so the caller must treat the list as a lower bound."""
    keys: list[str] = []
    complete = True
    for k in node.keys:
        if k is None:                                      # **spread
            complete = False
        elif isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
        else:                                              # computed key
            complete = False
    return keys, complete


#: The package root, so a module's identity can be its dotted path rather than its file name.
PKG = ROUTERS.parent


def module_id(path: pathlib.Path) -> str:
    """`aec_api/closeout.py` -> `closeout`; `aec_api/routers/closeout.py` -> `routers.closeout`.

    **A STEM IS NOT AN IDENTITY, and this function exists because the first draft assumed it was.**
    26 stems collide between `aec_api/` and `aec_api/routers/` — `closeout`, `cost`, `modules`,
    `reports`, `accounting`, `contracts`, `responsibility`, `procurement` among them — so an index
    keyed by file name resolved a router's `from .. import closeout` to `routers/closeout.py` and
    attributed the WRONG engine's keys to the route. *Reporting confidently wrong keys is worse than
    reporting none*, which is the same reason `one_hop` below refuses to match an engine function by
    name. The hazard was identified at the FUNCTION-name level, designed around, and then rebuilt
    one layer down at the MODULE-name level.
    """
    return ".".join(path.relative_to(PKG).with_suffix("").parts)


#: How many hops from a route the resolver follows. TWO, measured rather than chosen: at ONE hop,
#: 34 routes that do reach a dict literal resolved to nothing, and the commonest shape was a
#: register engine whose public entry point is itself a one-line delegation --
#: `drawingset.drawing_set` is `return register(drawings)`. A third hop was measured as reaching
#: nothing further, and each extra level multiplies the ways to attribute keys to the wrong
#: function, which is the hazard `module_id` exists for.
MAX_HOPS = 2


def module_tables() -> tuple[dict[str, dict[str, ast.AST]], dict[str, dict[str, str]]]:
    """Every module-level function in the package, and every module's own relative aliases.

    Module-level only: a nested helper is not reachable as `module.func`, so indexing one would
    offer a resolution that cannot happen.

    **Both are keyed PER MODULE, and that is the load-bearing part of this function.** A hop into an
    engine must resolve THAT engine's own calls through ITS imports; resolving a second hop through
    the ROUTER's aliases would rebuild the stem collision `module_id` exists to prevent, one level
    further down, where nothing would notice.
    """
    funcs: dict[str, dict[str, ast.AST]] = {}
    aliases: dict[str, dict[str, str]] = {}
    for path in sorted(PKG.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                                # a module this Python cannot parse
            continue
        mid = module_id(path)
        fns = {n.name: n for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if fns:
            funcs[mid] = fns
        aliases[mid] = relative_aliases(tree)
    return funcs, aliases


def resolve_target(call: ast.AST, mid: str, funcs: dict[str, dict[str, ast.AST]],
                   aliases: dict[str, dict[str, str]]) -> str | None:
    """Where `call` points -- `"module.func"` -- or None.

    TWO shapes, and the second is the one the resolver used to refuse:

    - `engine.func(...)`, through an alias the CONTAINING module imported relatively.
    - a BARE `func(...)` that the containing module itself defines at module level.

    **The self-test below pinned the bare form as a refusal, and its stated reason named the wrong
    hazard.** It said "a bare call resolved -- the resolver is matching by NAME". Matching a name
    across MODULES is indeed a guess, and 26 stems collide here, which is what `module_id` is for.
    But a bare call inside a module that DEFINES that function is not a guess: it is the lookup
    Python itself performs, and it cannot reach another module. The refusal is still correct when
    the containing module has no such function -- and the self-test's fixture defined none, so it
    could not tell the two cases apart. *Asserting the one case you thought of is not asserting the
    property*, so it now asserts both directions.
    """
    if not isinstance(call, ast.Call):
        return None
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        mod = aliases.get(mid, {}).get(call.func.value.id)
        # EXISTENCE IS PART OF RESOLUTION. An alias can name a module that holds no such function —
        # `from . import ai` binds `routers.ai`, and the engine is `aec_api/ai.py`. The old
        # `one_hop` happened to be safe here because it looked the name up in the index and got
        # None; reading the function's AST does not get that check for free, and the first draft of
        # this crashed on exactly that pair rather than refusing it.
        return f"{mod}.{call.func.attr}" if call.func.attr in funcs.get(mod or "", {}) else None
    if isinstance(call.func, ast.Name) and call.func.id in funcs.get(mid, {}):
        return f"{mid}.{call.func.id}"
    return None


#: What one return statement puts on the wire: its keys, whether that set is the whole truth, the
#: hop targets the keys came from, the shape vocabulary for the report, and -- `stops` -- where
#: resolution gave up. `stops` is the half that did not exist before: a route that returns a call
#: nobody can follow used to be reported `{"complete": true, "keys": []}`, which is the same output
#: as a file download, so the consumer could not tell "did not look" from "nothing to find".
def return_facts(fn: ast.AST, mid: str, funcs: dict[str, dict[str, ast.AST]],
                 aliases: dict[str, dict[str, str]], hops_left: int,
                 ) -> tuple[set[str], bool, set[str], set[str], set[str]]:
    """(keys, complete, hops, shapes, stops) for ONE function's own returns, following `hops_left`.

    `complete` is False as soon as any return path cannot be read: an unresolvable call, a variable,
    a conditional expression, a comprehension. **That is a correction, not a tightening.** The old
    index collected the dict-literal returns of a function and ignored its other return paths
    entirely, reporting `complete: True` -- so a function written as `if x: return {...}` /
    `return build()` had its key set published as the whole truth. 106 module-level functions here
    have such a mixed return set and 24 of them are reachable from a route in one hop, among them
    `/schedule/health`, `/schedule/flowline`, `/feasibility` and `/contracts/review`.

    A `return`, `return None` or a scalar constant adds no keys and does NOT make the set
    incomplete: `null` on the wire is not a dict with fields nobody declared.
    """
    keys: set[str] = set()
    hops: set[str] = set()
    shapes: set[str] = set()
    stops: set[str] = set()
    complete = True
    for ret in own_returns(fn):
        if ret.value is None or isinstance(ret.value, ast.Constant):
            shapes.add("other")
        elif isinstance(ret.value, ast.Dict):
            shapes.add("dict")
            k, c = dict_keys(ret.value)
            keys.update(k)
            complete = complete and c
        elif isinstance(ret.value, (ast.List, ast.ListComp)):
            shapes.add("list")                             # lesson 3
        elif isinstance(ret.value, ast.Call):
            # NAMING IS INDEPENDENT OF THE BUDGET. A call this runs out of hops on is still worth
            # naming, because the point of `stops` is to say WHERE to look; only the recursion is
            # bounded. An earlier draft folded the two together and reported `?` for a call it
            # could name perfectly well.
            target = resolve_target(ret.value, mid, funcs, aliases)
            if target is None:
                # A call this cannot follow: a method on an expression, an absolute import, a local
                # name. Named as a CALL rather than as "other", because a call is a delegation and
                # may become followable later — `other` is for a shape that never will be.
                shapes.add("call-unresolved")
                stops.add("?")
                complete = False
                continue
            if hops_left <= 0:
                shapes.add("call-no-dict")
                stops.add(target)
                complete = False
                continue
            tmid, tname = target.rsplit(".", 1)
            sub = return_facts(funcs[tmid][tname], tmid, funcs, aliases, hops_left - 1)
            sub_keys, sub_complete, sub_hops, _sub_shapes, sub_stops = sub
            if sub_keys:
                shapes.add("delegated")
                keys |= sub_keys
                hops.add(target)
                hops |= sub_hops
                complete = complete and sub_complete
            else:
                # The callee was FOUND and reaches no dict literal. Different from
                # `call-unresolved` on purpose: this one knows where to send a reader. When the
                # callee reported its OWN stop, that deeper one is the real cause and this one
                # would bury it — a stop list naming every link of a chain says nothing about
                # which link to open.
                shapes.add("call-no-dict")
                complete = False
                if not sub_stops:
                    stops.add(target)
            stops |= sub_stops
        else:
            # A variable, a conditional expression, a dict comprehension, an await. No keys are
            # readable, so whatever this route sends is outside the comparison.
            shapes.add("other")
            complete = False
    return keys, complete, hops, shapes, stops


def engine_index(funcs: dict[str, dict[str, ast.AST]],
                 aliases: dict[str, dict[str, str]],
                 ) -> dict[str, dict[str, tuple[list[str], bool]]]:
    """Every module-level function that reaches a dict literal, by module identity.

    Kept as a function of its own because `_selftest` drives `resolve_target` through it, and
    because the FLOOR below is measured against what it resolves.
    """
    out: dict[str, dict[str, tuple[list[str], bool]]] = {}
    for mid, fns in funcs.items():
        got: dict[str, tuple[list[str], bool]] = {}
        for name, node in fns.items():
            keys, complete, _hops, _shapes, _stops = return_facts(
                node, mid, funcs, aliases, MAX_HOPS - 1)
            if keys:
                got[name] = (sorted(keys), complete)
        if got:
            out[mid] = got
    return out


def relative_aliases(tree: ast.AST) -> dict[str, str]:
    """`from .. import closeout as closeout_engine` -> {"closeout_engine": "closeout"}.

    **The LEVEL is half the answer**: `from ..` names a module of the package, `from .` one of
    `routers/`. Dropping the level is how the stem collision above becomes invisible again.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and not node.module:
            base = "" if node.level >= 2 else "routers."
            for alias in node.names:
                out[alias.asname or alias.name] = base + alias.name
    return out


def collect() -> dict[str, dict]:
    """Every decorated route under `routers/`, keyed `METHOD /normalised/path`.

    RESPKEY-DELEGATED. A route that hands off to an engine used to land here as `other` with no
    keys, and 605 of 1016 routes do exactly that — so the gate consuming this had no view of the
    MAJORITY of the surface. The module docstring named its boundary as "a list, an ORM object or a
    Pydantic model"; the commonest case was none of those.

    RESPKEY-HOP2. The per-return switch that used to live here is now `return_facts`, shared with
    the engine index, so a route's returns and an engine's returns are read by ONE function at two
    depths rather than by two functions that could drift. A route is read with the full hop budget.
    """
    routes: dict[str, dict] = {}
    funcs, aliases = module_tables()
    for path in sorted(ROUTERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = router_prefix(tree)
        rmid = module_id(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in METHODS and dec.args
                        and isinstance(dec.args[0], ast.Constant)):
                    continue
                key = f"{dec.func.attr.upper()} {normalise(prefix + str(dec.args[0].value))}"
                keys, complete, hops, shapes, stops = return_facts(
                    node, rmid, funcs, aliases, MAX_HOPS)
                rec = routes.setdefault(key, {"keys": set(), "complete": True, "literal": False,
                                              "shapes": set(), "sites": [], "hops": set(),
                                              "stops": set()})
                rec["keys"].update(keys)
                rec["complete"] = rec["complete"] and complete
                rec["literal"] = rec["literal"] or "dict" in shapes
                rec["shapes"] |= shapes
                rec["hops"] |= hops
                rec["stops"] |= stops
                rec["sites"].append(f"{path.name}:{node.lineno}:{node.name}")
    return routes


#: The delegated resolution measured when it landed. A FLOOR, not a target: it may rise freely, and a
#: fall means the resolver has quietly stopped resolving — which looks exactly like a tree that
#: happens to delegate less, and is the failure mode a count cannot distinguish from progress.
#:
#: RESPKEY-HOP2 raised the measurement from 301 to 341 (a second hop, and the bare same-module call
#: shape). The floor keeps the same headroom the one-hop version chose — ~15% below the measurement,
#: not equal to it — because a delegation REWRITTEN as a dict literal in the route is an improvement
#: and must not red the build. *A ratchet set equal to the measurement fails on the work it exists
#: to encourage.*
MIN_DELEGATED = 300


def _selftest() -> None:
    """Prove the resolver distinguishes two modules with the SAME STEM, before it reports anything.

    This is the mistake the first draft shipped with, and it is synthetic on purpose: pinning a live
    route would make the proof depend on today's tree, so a refactor could remove the evidence
    without removing the hazard. *A proof of reach that a rename can delete is not a proof.*
    """
    tree = ast.parse("from .. import widget as w\n"
                     "from . import widget as rw\n"
                     "def a():\n"
                     "    return w.f()\n"
                     "def b():\n"
                     "    return rw.f()\n")
    aliases = relative_aliases(tree)
    if aliases != {"w": "widget", "rw": "routers.widget"}:
        raise AssertionError(f"relative import LEVEL is lost: {aliases}")

    widget = ast.parse('def f():\n    return {"engine_key": 1}\n')
    rwidget = ast.parse('def f():\n    return {"router_key": 1}\n')
    funcs = {"widget": {"f": widget.body[0]}, "routers.widget": {"f": rwidget.body[0]},
             "caller": {n.name: n for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}}
    all_aliases = {"caller": aliases, "widget": {}, "routers.widget": {}}
    got = {}
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            k, _c, hops, _sh, _st = return_facts(fn, "caller", funcs, all_aliases, MAX_HOPS)
            got[fn.name] = (sorted(k), sorted(hops))
    want = {"a": (["engine_key"], ["widget.f"]), "b": (["router_key"], ["routers.widget.f"])}
    if got != want:
        raise AssertionError(f"same-stem modules conflated: {got} != {want}")

    # THE SECOND HOP, asserted rather than assumed. `drawingset.drawing_set` is
    # `return register(drawings)`, so at one hop it resolved to nothing and the route was reported
    # as sending NO keys — indistinguishable from a file download. 20 routes were in that hole,
    # including every GC register (`/rfi/register`, `/submittals/register`, `/rent-roll`).
    # ATTRIBUTE calls on purpose, not bare ones. The bare-call form is asserted separately below,
    # and a fixture that needed both would make one regression red two checks with the wrong
    # message — *two checks that share a failure mode are one check.*
    top = ast.parse('from .. import mid as m\ndef outer():\n    return m.middle()\n')
    midm = ast.parse('from .. import deep as d\ndef middle():\n    return d.inner()\n')
    deep = ast.parse('def inner():\n    return {"deep_key": 1}\n')
    cfuncs = {"top": {"outer": top.body[-1]}, "mid": {"middle": midm.body[-1]},
              "deep": {"inner": deep.body[-1]}}
    calias = {"top": relative_aliases(top), "mid": relative_aliases(midm), "deep": {}}
    k2, _c2, hops2, _s2, _t2 = return_facts(cfuncs["top"]["outer"], "top", cfuncs, calias, MAX_HOPS)
    if sorted(k2) != ["deep_key"] or sorted(hops2) != ["deep.inner", "mid.middle"]:
        raise AssertionError(f"a two-hop delegation did not resolve: {sorted(k2)} {sorted(hops2)}")
    # ...and the budget is a BOUND, not a decoration: the same chain read with ONE hop must report
    # that it STOPPED, and say where, rather than that there was nothing there. `stops` is the half
    # that did not exist: an empty key set used to be published as `complete: true`.
    k1, c1, _h1, sh1, st1 = return_facts(cfuncs["top"]["outer"], "top", cfuncs, calias, 1)
    if k1 or c1 or "call-no-dict" not in sh1 or st1 != {"deep.inner"}:
        raise AssertionError("running out of hops must report a STOP, not an empty key set: "
                             f"keys={sorted(k1)} complete={c1} shapes={sorted(sh1)} stops={st1}")

    # A MIXED return set is a LOWER BOUND, not the whole truth. The old index read a function's
    # dict-literal returns and ignored its other return paths, publishing `complete: True`.
    mixed = ast.parse('def m(x):\n'
                      '    if x:\n'
                      '        return {"named": 1}\n'
                      '    return whatever\n')
    mfuncs = {"mix": {n.name: n for n in mixed.body}}
    km, cm, _hm, _sm, _tm = return_facts(mfuncs["mix"]["m"], "mix", mfuncs, {"mix": {}}, MAX_HOPS)
    if sorted(km) != ["named"] or cm is not False:
        raise AssertionError(f"a mixed return set reported as complete: {sorted(km)} {cm}")

    # ...AND `module_id` ITSELF IS EXERCISED ON THE REAL PAIR. The synthetic case above builds its
    # own index, so it cannot notice `module_id` being wrong — the first version of this self-test
    # caught a stem-keyed `module_id` only through the collision count below, and reported it as
    # "no colliding stems remain", which blames the tree for a broken function. *A check whose
    # failure message can misdiagnose is worse than one that stays silent, because somebody acts
    # on it.* The collision set is therefore derived from PATHS, which are unambiguous by
    # construction, and `module_id` is then asserted to separate them.
    stems: dict[str, set[str]] = {}
    for path in PKG.rglob("*.py"):
        stems.setdefault(path.stem, set()).add(str(path.relative_to(PKG)))
    collisions = {k: sorted(v) for k, v in stems.items() if len(v) > 1}
    if not collisions:
        raise AssertionError("no two modules share a stem any more, so `module_id` is no longer "
                             "load-bearing — re-measure before simplifying it away")
    for stem, rels in collisions.items():
        ids = {module_id(PKG / r) for r in rels}
        if len(ids) != len(rels):
            raise AssertionError(f"`module_id` conflates {rels} (stem {stem!r}) into {sorted(ids)} "
                                 f"— an index keyed on this attributes one module's keys to another")

    # THE BARE CALL, BOTH WAYS — and the old version of this check asserted only one of them.
    #
    # It refused `return f()` outright, with the reason "guessing at one by name is how the wrong
    # engine's keys get attributed". The hazard is real but it is about crossing MODULES: 26 stems
    # collide here. A bare call inside a module that DEFINES that function is the lookup Python
    # itself performs and cannot reach another module — and 14 routes delegate to a helper in their
    # own router file, every one of them invisible for as long as this refusal was unconditional.
    # The fixture below defined no `f`, so it could not tell the two cases apart; *asserting the
    # one case you thought of is not asserting the property.*
    bare = ast.parse("def c():\n    return f()\n")
    nf = {"lonely": {"c": bare.body[0]}}
    if resolve_target(own_returns(bare.body[0])[0].value, "lonely", nf, {"lonely": {}}) is not None:
        raise AssertionError("a bare call resolved in a module that defines no such function — "
                             "the resolver is matching by NAME across modules")
    local = ast.parse('def c():\n    return f()\n'
                      'def f():\n    return {"local_key": 1}\n')
    lf = {"same": {n.name: n for n in local.body}}
    kl, _cl, hl, _sl, _tl = return_facts(lf["same"]["c"], "same", lf, {"same": {}}, MAX_HOPS)
    if sorted(kl) != ["local_key"] or sorted(hl) != ["same.f"]:
        raise AssertionError(f"a bare call to the module's OWN function did not resolve: "
                             f"{sorted(kl)} {sorted(hl)}")


def main() -> int:
    try:
        _selftest()
    except AssertionError as e:
        # FAIL CLOSED. Emitting keys from a resolver that cannot be trusted is worse than emitting
        # none: the gate downstream pins its gaps exactly, so a wrong key set becomes a wrong
        # instruction to whoever acts on it.
        print(f"response_keys self-test FAILED: {e}", file=sys.stderr)
        return 2
    routes = collect()
    delegated = sum(1 for v in routes.values() if "delegated" in v["shapes"])
    if delegated < MIN_DELEGATED:
        print(f"response_keys: one-hop resolution fell to {delegated} routes, below the "
              f"{MIN_DELEGATED} measured when it landed — the resolver has stopped resolving, "
              f"which reads the same as a tree that delegates less", file=sys.stderr)
        return 2
    json.dump({k: {"keys": sorted(v["keys"]), "complete": v["complete"], "literal": v["literal"],
                   "shapes": sorted(v["shapes"]), "sites": v["sites"],
                   # Where the keys came from. A consumer treating a delegated key set as a
                   # hand-written literal would be wrong about who to go and fix.
                   "hops": sorted(v["hops"]),
                   # RESPKEY-HOP2. Where resolution GAVE UP, which is the field whose absence was
                   # the defect: a route returning a call nobody could follow was published as
                   # `{"complete": true, "keys": []}` — the same bytes as a file download — so the
                   # consumer could not tell "did not look" from "nothing to find". `"?"` means the
                   # call could not even be named; anything else names the function to go and read.
                   "stops": sorted(v["stops"])}
               for k, v in routes.items()}, sys.stdout, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
