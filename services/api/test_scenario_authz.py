"""SEC-SCENARIO-AUTHZ — every `{sid}` scenario route authorises the caller, and write ≠ read.

Aikido reported "IDOR in proforma.py". The real shape was narrower and worse: `_can_read` **already
existed** and was called by **2 of the 8** `{sid}` routes. Six — share, update, clone, review,
forecast, draw-package — fetched by id and acted with no ownership check at all.

Not an unauthenticated hole: `/proforma` is in `main.py`'s `_PROTECTED_PREFIXES`, so the global
security middleware 401s anonymous callers and every route *looked* guarded. **A generic gate hiding
a missing specific one** — authentication was enforced, authorisation was not.

The worst was `share_scenario`, which took `user: str = Body(...)` as the person being granted
access and had **no `current_user` dependency at all**. It had no notion of who was calling, so any
authenticated caller could share any scenario with anyone.

**Three claims, each asserted rather than described:**

1. Every `{sid}` route is guarded — enumerated from the AST, so a ninth route added without a guard
   fails here rather than being noticed later.
2. Read permission is NOT write permission. Someone in `shared_with` (an LP sent a scenario) can
   read it and must not be able to edit, clone, approve, forecast or pull a draw package from it.
   This is the assertion that a single reused `_can_read` would quietly fail.
3. The guards permit as well as refuse. A guard that refuses everyone satisfies every negative test
   ever written, so each route has a positive case too.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROUTER = pathlib.Path(__file__).parent / "src" / "aec_api" / "routers" / "proforma.py"

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# --- 1. structural: no {sid} route may skip the guard --------------------------------------------
tree = ast.parse(open(ROUTER, encoding="utf-8").read())
sid_routes: list[tuple[str, str, bool, bool]] = []
for fn in ast.walk(tree):
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    routes = [d for d in fn.decorator_list
              if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
              and d.func.attr in ("get", "post", "put", "patch", "delete")]
    if not routes:
        continue
    arg = routes[0].args[0] if routes[0].args else None
    path = arg.value if isinstance(arg, ast.Constant) else ""
    if "{sid}" not in str(path):
        continue
    body = ast.unparse(fn)
    sid_routes.append((routes[0].func.attr.upper(), path,
                       "_scenario_for" in body or "_can_read" in body or "_can_write" in body,
                       routes[0].func.attr in ("post", "put", "patch", "delete")))

# Silence is not a signal: if the AST walk stops matching, every assertion below evaporates.
check("the scan found the scenario routes at all", len(sid_routes) >= 8,
      f"{len(sid_routes)} route(s) with a {{sid}} path")

unguarded = [f"{m} {p}" for m, p, g, _ in sid_routes if not g]
check("every {sid} route authorises the caller", not unguarded,
      "; ".join(unguarded) or f"all {len(sid_routes)} guarded")

# --- 2. write routes must use the WRITE guard, not the read one -----------------------------------
# `_can_read` admits anyone in `shared_with`. If a mutating route used it, an LP with read access
# could edit assumptions or approve a review. This asserts the distinction the fix exists to make.
read_only_on_write = []
for fn in ast.walk(tree):
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    routes = [d for d in fn.decorator_list
              if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
              and d.func.attr in ("post", "put", "patch", "delete")]
    if not routes:
        continue
    arg = routes[0].args[0] if routes[0].args else None
    if "{sid}" not in str(getattr(arg, "value", "")):
        continue
    body = ast.unparse(fn)
    if "_scenario_for" in body and "write=True" not in body:
        read_only_on_write.append(fn.name)
check("mutating scenario routes take the WRITE guard, not the read guard", not read_only_on_write,
      "; ".join(read_only_on_write) or "share/update/clone/review/forecast/draw-package all write=True")

# --- 3. share_scenario distinguishes the ACTOR from the SHARE TARGET -------------------------------
share = next((fn for fn in ast.walk(tree)
              if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == "share_scenario"),
             None)
check("share_scenario exists", share is not None)
if share is not None:
    # Inspect the DEFAULTS via the AST, not `ast.unparse(share)`. The unparsed source includes the
    # DOCSTRING, and this function's docstring says "there was no `current_user` dependency at all"
    # — so a substring check for "current_user" passes on a route that has none. Proven: replacing
    # `Depends(current_user)` with a literal left this check green. The gate was reading its own
    # documentation, which is the third time that shape has appeared in this repo today.
    defaults = [ast.unparse(d) for d in share.args.defaults]
    names = [a.arg for a in share.args.args]
    actor_dep = any("Depends(current_user)" in d for d in defaults)
    check("share_scenario has a real current_user DEPENDENCY — it knows WHO is calling", actor_dep,
          "defaults=" + "; ".join(defaults) if not actor_dep else "Depends(current_user) present")
    check("...and the grantee is a parameter distinct from the actor",
          "target" in names and "actor" in names,
          "params=" + ", ".join(names))
    check("...while the wire key stays `user`, so no caller breaks",
          any('alias=' in d and "'user'" in d.replace('"', "'") for d in defaults),
          "; ".join(defaults))

# --- 4. behavioural: the guards permit AND refuse --------------------------------------------------
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
from aec_api import rbac  # noqa: E402
from aec_api.routers.proforma import _can_read, _can_write  # noqa: E402


class _S:
    """Minimal Scenario stand-in — the guards only read `shared_with` and `project_id`."""

    def __init__(self, shared_with=None, project_id="p1"):
        self.shared_with = shared_with or []
        self.project_id = project_id


class _DB:
    pass


_orig_on, _orig_role = rbac.RBAC_ON, rbac.role_for
try:
    rbac.RBAC_ON = True
    rbac.role_for = lambda db, pid, user: "editor" if user == "member" else None  # type: ignore

    lp = _S(shared_with=["lp"])
    check("an LP in shared_with CAN read", _can_read(_DB(), lp, "lp") is True)
    check("an LP in shared_with CANNOT write — read is not write",
          _can_write(_DB(), lp, "lp") is False,
          "this is the whole reason _can_write exists separately")
    check("a project member CAN write", _can_write(_DB(), _S(), "member") is True)
    check("a stranger can neither read nor write",
          _can_read(_DB(), _S(), "nobody") is False and _can_write(_DB(), _S(), "nobody") is False)

    # The twin for the guards themselves: with RBAC off they must be permissive, or every
    # single-tenant and desktop deployment breaks.
    rbac.RBAC_ON = False
    check("with RBAC off both guards are open — desktop/local deployments unaffected",
          _can_read(_DB(), _S(), "anyone") is True and _can_write(_DB(), _S(), "anyone") is True)
finally:
    rbac.RBAC_ON, rbac.role_for = _orig_on, _orig_role

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_scenario_authz OK")
