"""Which response keys does each route return? — the SERVER half of RESPONSE-UNDECLARED.

Emits JSON on stdout so the gate that consumes it can live where the TypeScript checker runs
(`apps/web/src/api/responseUndeclared.test.ts`). **Stdlib only, deliberately**: that gate runs in the
web CI job, which installs node and web dependencies and no Python ones, so anything imported here
would have to be installed somewhere it currently is not.

WHAT IT ANSWERS, and the boundary. For every route handler under `routers/`, the top-level string
keys of every dict literal it returns. Routes returning a list, an ORM object or a Pydantic model are
reported with their shape and NO keys, because this cannot know what those serialise to — that is a
different derivation and pretending otherwise would understate what the server sends.

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


def engine_index() -> dict[str, dict[str, tuple[list[str], bool]]]:
    """Every module-level function in the package that returns a dict literal, by module identity.

    Module-level only: a nested helper is not reachable as `module.func`, so indexing one would
    offer a resolution that cannot happen.
    """
    out: dict[str, dict[str, tuple[list[str], bool]]] = {}
    for path in sorted(PKG.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                                # a module this Python cannot parse
            continue
        fns: dict[str, tuple[list[str], bool]] = {}
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            keys: list[str] = []
            complete = True
            for ret in own_returns(node):
                if isinstance(ret.value, ast.Dict):
                    k, c = dict_keys(ret.value)
                    keys.extend(k)
                    complete = complete and c
            if keys:
                fns[node.name] = (keys, complete)
        if fns:
            out[module_id(path)] = fns
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


def one_hop(ret: ast.Return, aliases: dict[str, str],
            index: dict[str, dict[str, tuple[list[str], bool]]]) -> tuple[list[str], bool, str] | None:
    """`return engine.func(...)` -> that function's dict-literal keys, or None.

    EXACTLY ONE HOP, and only through an alias this router itself imported relatively. A deeper
    chain is reported as unresolved rather than followed: each extra hop multiplies the ways to
    attribute keys to the wrong function, and `complete: False` on a route nobody can check is a
    worse answer than no keys at all.
    """
    call = ret.value
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)):
        return None
    mod = aliases.get(call.func.value.id)
    if mod is None:
        return None
    hit = index.get(mod, {}).get(call.func.attr)
    if hit is None:
        return None
    keys, complete = hit
    return keys, complete, f"{mod}.{call.func.attr}"


def collect() -> dict[str, dict]:
    """Every decorated route under `routers/`, keyed `METHOD /normalised/path`."""
    routes: dict[str, dict] = {}
    index = engine_index()
    for path in sorted(ROUTERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = router_prefix(tree)
        aliases = relative_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            returns = own_returns(node)
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in METHODS and dec.args
                        and isinstance(dec.args[0], ast.Constant)):
                    continue
                key = f"{dec.func.attr.upper()} {normalise(prefix + str(dec.args[0].value))}"
                keys: set[str] = set()
                complete, literal = True, False
                shapes: set[str] = set()
                hops: set[str] = set()
                for ret in returns:
                    if isinstance(ret.value, ast.Dict):
                        literal = True
                        shapes.add("dict")
                        k, c = dict_keys(ret.value)
                        keys.update(k)
                        complete = complete and c
                    elif isinstance(ret.value, (ast.List, ast.ListComp)):
                        shapes.add("list")                 # lesson 3
                    elif ret.value is not None:
                        # RESPKEY-DELEGATED. A route that hands off to an engine used to land here
                        # as `other` with no keys, and 605 of 1016 routes do exactly that — so the
                        # gate consuming this had no view of the MAJORITY of the surface. The
                        # module docstring named its boundary as "a list, an ORM object or a
                        # Pydantic model"; the commonest case was none of those.
                        hop = one_hop(ret, aliases, index)
                        if hop is None:
                            shapes.add("other")
                        else:
                            k, c, target = hop
                            shapes.add("delegated")
                            keys.update(k)
                            complete = complete and c
                            hops.add(target)
                rec = routes.setdefault(key, {"keys": set(), "complete": True, "literal": False,
                                              "shapes": set(), "sites": [], "hops": set()})
                rec["keys"].update(keys)
                rec["complete"] = rec["complete"] and complete
                rec["literal"] = rec["literal"] or literal
                rec["shapes"] |= shapes
                rec["hops"] |= hops
                rec["sites"].append(f"{path.name}:{node.lineno}:{node.name}")
    return routes


#: The one-hop resolution measured when it landed. A FLOOR, not a target: it may rise freely, and a
#: fall means the resolver has quietly stopped resolving — which looks exactly like a tree that
#: happens to delegate less, and is the failure mode a count cannot distinguish from progress.
MIN_DELEGATED = 260


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

    index = {"widget": {"f": (["engine_key"], True)},
             "routers.widget": {"f": (["router_key"], True)}}
    got = {}
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hop = one_hop(own_returns(fn)[0], aliases, index)
            got[fn.name] = None if hop is None else (hop[0], hop[2])
    want = {"a": (["engine_key"], "widget.f"), "b": (["router_key"], "routers.widget.f")}
    if got != want:
        raise AssertionError(f"same-stem modules conflated: {got} != {want}")

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

    # A function the resolver must REFUSE: a bare local call is not `module.func`, and guessing at
    # one by name is how the wrong engine's keys get attributed.
    bare = ast.parse("def c():\n    return f()\n").body[0]
    if one_hop(own_returns(bare)[0], aliases, index) is not None:
        raise AssertionError("a bare call resolved — the resolver is matching by NAME")


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
                   "hops": sorted(v["hops"])}
               for k, v in routes.items()}, sys.stdout, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
