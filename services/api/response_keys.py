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


def collect() -> dict[str, dict]:
    """Every decorated route under `routers/`, keyed `METHOD /normalised/path`."""
    routes: dict[str, dict] = {}
    for path in sorted(ROUTERS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = router_prefix(tree)
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
                        shapes.add("other")
                rec = routes.setdefault(key, {"keys": set(), "complete": True, "literal": False,
                                              "shapes": set(), "sites": []})
                rec["keys"].update(keys)
                rec["complete"] = rec["complete"] and complete
                rec["literal"] = rec["literal"] or literal
                rec["shapes"] |= shapes
                rec["sites"].append(f"{path.name}:{node.lineno}:{node.name}")
    return routes


def main() -> int:
    routes = collect()
    json.dump({k: {"keys": sorted(v["keys"]), "complete": v["complete"], "literal": v["literal"],
                   "shapes": sorted(v["shapes"]), "sites": v["sites"]}
               for k, v in routes.items()}, sys.stdout, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
