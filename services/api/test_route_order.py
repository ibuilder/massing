"""Route-order guard — catches path shadowing at build time.

FastAPI/Starlette match routes in *registration order*, first match wins. So a generic route like
`GET /elements/{guid}` registered BEFORE a specific sibling `GET /elements/color-by` makes the
specific one unreachable (the `{guid}` route swallows `color-by`). That exact bug bit us this session.
This test fails the build if, within any router, an earlier route shadows a more-specific later route
on a shared method — so the fix (register specific-before-generic) is enforced, not remembered.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_route_order.py"""
import os
import re

os.environ["DATABASE_URL"] = "sqlite:///./test_route_order.db"
os.environ["STORAGE_DIR"] = "./test_storage_route_order"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_route_order.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.routing import APIRoute                         # noqa: E402
from aec_api.main import app                                 # noqa: E402

_PARAM = re.compile(r"\{[^}]+\}")


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def _is_param(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def _more_specific_at_some_segment(generic: str, specific: str) -> bool:
    """True if `specific` has a literal where `generic` has a path param at the same position (same
    segment count, all other literals equal) — i.e. `specific` is the one that must be registered
    first, and being registered later makes it unreachable behind `generic`."""
    g, s = _segments(generic), _segments(specific)
    if len(g) != len(s):
        return False
    saw = False
    for gi, si in zip(g, s):
        if _is_param(gi) and not _is_param(si):
            saw = True                    # generic wildcard vs specific literal here
        elif not _is_param(gi) and gi != si:
            return False                  # differing literals -> genuinely different routes
    return saw


def _api_routes(router) -> list[APIRoute]:
    return [r for r in getattr(router, "routes", []) if isinstance(r, APIRoute)]


def find_shadows(routes: list[APIRoute]) -> list[tuple[list[str], str, str]]:
    """Within one ordered router, find (methods, specific_path, generic_path) where an earlier
    generic route makes a later, more-specific route unreachable on a shared method."""
    out = []
    for j, later in enumerate(routes):
        later_methods = later.methods or set()
        sample = _PARAM.sub("sample", later.path)             # concrete path for the later route
        for earlier in routes[:j]:
            if not (later_methods & (earlier.methods or set())):
                continue                                      # no shared HTTP method -> no conflict
            if earlier.path == later.path:
                continue                                      # same template (duplicate, not shadow)
            if earlier.path_regex.match(sample) and _more_specific_at_some_segment(earlier.path, later.path):
                out.append((sorted(later_methods & earlier.methods), later.path, earlier.path))
    return out


# Self-test: prove the detector actually fires on a known shadow (guard against a vacuous check).
from fastapi import APIRouter as _APIRouter                   # noqa: E402
_probe = _APIRouter()
_probe.add_api_route("/elements/{guid}", lambda: None, methods=["GET"])   # generic FIRST -> shadows
_probe.add_api_route("/elements/color-by", lambda: None, methods=["GET"])
assert len(find_shadows(_api_routes(_probe))) == 1, "detector failed to catch a known shadow"
_ok = _APIRouter()
_ok.add_api_route("/elements/color-by", lambda: None, methods=["GET"])    # specific FIRST -> fine
_ok.add_api_route("/elements/{guid}", lambda: None, methods=["GET"])
assert find_shadows(_api_routes(_ok)) == [], "detector produced a false positive on correct order"


# Collect each router's ordered APIRoutes. This app wraps every included router in an
# `_IncludedRouter` exposing the real router via `.original_router`; also include any routes
# registered directly on the app.
groups: list[tuple[str, list[APIRoute]]] = []
for r in app.routes:
    orig = getattr(r, "original_router", None)
    if orig is not None:
        rs = _api_routes(orig)
        if rs:
            groups.append((type(r).__name__, rs))
top = _api_routes(app.router)
if top:
    groups.append(("app", top))

total = sum(len(rs) for _, rs in groups)
shadows = []
for _label, routes in groups:
    shadows.extend(find_shadows(routes))

if shadows:
    print("ROUTE ORDER FAIL - a generic route shadows a more-specific one registered after it:")
    for methods, specific, generic in shadows:
        print(f"  {','.join(methods):8} {specific}  is unreachable behind earlier  {generic}")
    print("Fix: register the specific /verb route(s) BEFORE the /{param} route in that router.")
    raise SystemExit(1)

print(f"ROUTE ORDER OK - {total} routes across {len(groups)} routers, no specific route shadowed by an "
      "earlier /{param} route")
