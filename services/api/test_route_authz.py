"""Route-authorization guard: every project-scoped ("/projects/{pid}/...") route MUST enforce project
membership via a rbac.require_role(...) dependency (tagged `_role_gate`) — identity-only Depends(current_user)
is NOT sufficient and silently breaks the tenant boundary. This test enumerates the live app and fails on
any {pid} route lacking a role gate, so the cross-tenant hole cannot regress.

A small allowlist covers routes that are intentionally public or that do their own in-body membership check.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_route_authz.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_route_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_route_authz"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_route_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import APIRouter  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

import aec_api.main as M  # noqa: E402  (importing main registers + includes every router)

# (METHOD, PATH) pairs that are legitimately exempt from the membership gate:
#   - public/shared read endpoints (signed links, public listings, embeds)
#   - endpoints that perform their own in-body membership check (documented at the call site)
ALLOW: set[tuple[str, str]] = {
    # self-info: reports the caller's own membership (must return role=null, not 403, for non-members)
    ("GET", "/projects/{pid}/me"),
    # public share links (marketing listing + investor statement) — intentionally unauthenticated
    ("GET", "/projects/{pid}/listings/{lid}/public"),
    ("GET", "/projects/{pid}/investors/{iid}/statement.public.pdf"),
}


def _has_role_gate(dependant) -> bool:
    if getattr(getattr(dependant, "call", None), "_role_gate", None) is not None:
        return True
    return any(_has_role_gate(sub) for sub in getattr(dependant, "dependencies", []))


# Iterate every included router's own routes (robust; app.routes wrapping varies by import context).
_routers = {n: getattr(M, n) for n in dir(M)
            if isinstance(getattr(getattr(M, n, None), "router", None), APIRouter)}
offenders: list[str] = []
checked = 0
for _name, _mod in _routers.items():
    for r in _mod.router.routes:
        if not isinstance(r, APIRoute) or "{pid}" not in r.path:
            continue
        methods = (r.methods or set()) & {"GET", "POST", "PUT", "PATCH", "DELETE"}
        if not methods:
            continue
        checked += 1
        if _has_role_gate(r.dependant):
            continue
        if all((m, r.path) in ALLOW for m in methods):
            continue
        offenders.append(f"[{_name}] {'/'.join(sorted(methods))}  {r.path}")

if offenders:
    print(f"FAIL — {len(offenders)} project-scoped route(s) missing a require_role membership gate:")
    for o in sorted(offenders):
        print("   " + o)
    raise SystemExit(1)

print(f"ROUTE-AUTHZ OK - all {checked} /projects/{{pid}} routes enforce project membership via "
      f"require_role (or are explicitly allowlisted); cross-tenant access is gated.")
