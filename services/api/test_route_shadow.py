"""Is any route registered on a (path, method) another route already owns? — ROUTE-SHADOW.

Starlette matches the FIRST route whose path and method fit. A second registration on the same pair
is therefore not an override and not an error: it is **dead code that looks live**, and it takes the
published contract with it, because FastAPI builds the OpenAPI document into a dict keyed by path and
method, so the LAST registration is the one that ends up described. The server runs one handler and
`/docs`, the OpenAPI JSON and the generated `apps/web/src/api/schema.d.ts` all describe the other.

FOUR SHIPPED INSTANCES, all found on 2026-09-24 and all fixed in the change that added this file:

    GET /projects/{pid}/drawings/plan.svg    drawings.py::plan       shadowed authoring_docs.py::plan_svg
    GET /projects/{pid}/drawings/sheet.svg   drawings.py::sheet_svg  shadowed authoring_docs.py::sheet_svg
    GET /projects/{pid}/drawings/sheet.pdf   drawings.py::sheet_pdf  shadowed authoring_docs.py::sheet_pdf
    GET /projects/{pid}/mep                  analysis.py::mep        shadowed authoring_analysis.py::mep_summary

**FastAPI's own warning saw two of the four, and the two it saw are the least interesting.** It warns
on a duplicate *operationId*, which is built from the FUNCTION NAME plus the path — so it fires when
two handlers are spelled the same (`sheet_svg`, `sheet_pdf`) and stays silent when they are not
(`plan` vs `plan_svg`, `mep` vs `mep_summary`). *A warning keyed on the name cannot see a collision
that is about the path*, and half a population reported confidently reads exactly like all of it.

**The live defect was the pair the warning could not see.** `api/mep.ts` declared TWO shapes for
`/projects/{pid}/mep`: `mepSummary()` (systems as a LIST, with per-system counts) and `mep()` (systems
as a Record). `mep_inventory` served, so the MEP systems panel read `s.systems.length` off a Record,
got `undefined`, and printed "No distribution systems yet" on every model that has ever had one —
then returned, hiding the discipline rollup, the fire-protection check and the sizing checks below it.

**Why no test went red.** Every MEP assertion in `test_mep_systems.py` calls `mep.mep_summary(m)`, the
engine, directly; not one goes through the route. The engine was thoroughly right and unreachable.
*A test of the engine is not a test of the door* — the same shape as the routines sweep, where every
test asserted the enqueue and none asserted the run.

THE DERIVATION, AND THE TWO WAYS IT COULD LIE
    The population is every APIRoute the app actually holds, which means walking `_IncludedRouter`
    placeholders that FastAPI leaves in `app.routes` until inclusion is materialised. Two failure
    modes, and both produce "0 duplicates":

    1. **The walk stops finding things.** A FastAPI upgrade renames `_IncludedRouter` or moves its
       sub-router attribute and the expansion yields a handful of routes; a clean tree is reported in
       the words of a clean tree. Guarded by a floor on the expanded count AND by requiring the named
       routers that carried the shipped collisions to be present in the result.
    2. **The walk quietly drops what it cannot classify.** Guarded by FAILING CLOSED: any object in a
       router's `routes` that is neither an APIRoute, an includable router, nor a plain Starlette
       Route reds the build rather than being skipped.

PROOF OF REACH
    The four shipped registrations are replayed as a router tree built here — not fetched from git,
    because CI's checkout is shallow and `test_gap_records.py` failed closed on every build learning
    that. The replay must find **all four and nothing else**. It also runs the analyser with the
    expansion narrowed to top-level routes only — the mutation matching failure mode 1 — and requires
    that to MISS all four, so the floor checks above are demonstrably doing work.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_route_shadow.py
"""
import collections
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./_route_shadow.db"
os.environ.setdefault("STORAGE_DIR", "./_route_shadow_store")

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from starlette.routing import BaseRoute, Match, Route  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


#: Objects that legitimately appear in `app.routes` and carry no (path, method) of their own.
#: Anything NOT here and not a route reds the build — see failure mode 2 in the docstring.
_IGNORABLE = ("Mount", "WebSocketRoute", "Host")


class Unclassified(Exception):
    """Raised when the walk meets something it cannot rule on. Never caught into a skip."""


def _sub_router(placeholder):
    """The router behind a FastAPI `_IncludedRouter` placeholder.

    FastAPI defers `include_router` work, leaving a placeholder in `app.routes` that holds the real
    router and the prefix it was mounted under. The attribute name is not public API, so this looks
    for `router` first and then for any attribute exposing `.routes` — and raises rather than
    returning None if neither exists, because a silent None here is failure mode 1.
    """
    sub = getattr(placeholder, "router", None)
    if sub is not None and hasattr(sub, "routes"):
        return sub
    for name in dir(placeholder):
        if name.startswith("__"):
            continue
        value = getattr(placeholder, name, None)
        if hasattr(value, "routes") and not isinstance(value, BaseRoute):
            return value
    raise Unclassified(
        f"{type(placeholder).__name__} exposes no sub-router; the walk would silently stop here")


def expand(routes, prefix="", _depth=0):
    """Every APIRoute reachable from `routes`, paired with the prefix it is mounted under.

    Yields `(full_path, method, route)` triples. Fails closed: an object it cannot classify raises.
    """
    if _depth > 20:
        raise Unclassified("router nesting deeper than 20 — refusing to guess")
    for r in routes:
        name = type(r).__name__
        if isinstance(r, APIRoute):
            for m in sorted(r.methods or ()):
                if m in ("HEAD", "OPTIONS"):
                    continue
                yield prefix + r.path, m, r
        elif name.endswith("IncludedRouter"):
            sub = _sub_router(r)
            yield from expand(sub.routes, prefix + (getattr(r, "prefix", "") or ""), _depth + 1)
        elif isinstance(r, Route) or name in _IGNORABLE:
            continue
        else:
            raise Unclassified(f"unclassified route object {name!r} at prefix {prefix!r}")


def _concrete(path):
    """A URL the declaring route certainly matches: each `{param}` filled with a placeholder.

    Sound because no route in this tree uses a `:path` converter (asserted below) — with one, a
    single segment would not stand in for the rest of the URL and this would under-report.
    """
    out, n = [], 0
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            n += 1
            out.append(f"v{n}")
        else:
            out.append(seg)
    return "/" + "/".join(out)


def shadowed(routes):
    """Every registration an EARLIER one already answers, keyed by the shadowed (path, method).

    **Asks Starlette, rather than comparing strings.** The four shipped instances were identical
    paths, and an equality test would find all four — but equality is a precondition, not the rule:
    Starlette matches by regex, so `/projects/{pid}/drawings/{name}` registered first swallows a
    later `/projects/{pid}/drawings/sheet.svg` just as completely, and a gate written to the four
    known spellings would report that tree clean. *A predicate that decides what to LOOK at is more
    dangerous than one that decides what to report.* Measured before widening: the live tree holds
    **0** of the non-identical form, so this costs no exemptions and no noise today — it removes a
    precondition rather than chasing a finding.

    Separate from the walk on purpose. `test_unique_read_guard`'s first draft asserted that its
    analyser still *reported* a site, so a mutation routing every site to "safe" passed — reporting
    and ruling are two different questions, and a mutation has to be able to aim at the ruling.
    """
    ordered = list(routes)
    hits: dict[tuple[str, str], list] = collections.defaultdict(list)
    for j, (path, method, route) in enumerate(ordered):
        scope = {"type": "http", "method": method, "path": _concrete(path),
                 "path_params": {}, "headers": [], "root_path": ""}
        for _path_i, method_i, route_i in ordered[:j]:
            if method_i != method:
                continue
            if route_i.matches(scope)[0] is Match.FULL:
                # The first match wins at runtime, so `route_i` serves and `route` never runs.
                hits[(path, method)] = [route_i, route]
                break
    return dict(hits)


def _fn(route):
    return getattr(route.endpoint, "__name__", "?")


# ---------------------------------------------------------------------------------------------
# THE POPULATION — derived from the live app, with the floors that stop a silent empty walk.

try:
    LIVE = list(expand(app.routes))
except Unclassified as exc:                                    # pragma: no cover - fail closed
    print(f"FAIL  the walk could not classify the live app — {exc}")
    sys.exit(1)

_MODULES = {getattr(r.endpoint, "__module__", "") for _, _, r in LIVE}

#: Floor, not a pin. The tree held 1,023 routes when this was written; a walk that returns a
#: handful has broken, and a check whose expected answer is zero is the easiest kind to break
#: silently. Deliberately far below the real count so ordinary growth never touches it.
_FLOOR = 600

check(f"the walk still reaches the app's routes ({len(LIVE)} >= {_FLOOR})",
      len(LIVE) >= _FLOOR,
      f"only {len(LIVE)} — the expansion has stopped following included routers, and every "
      "'no duplicates' verdict below is vacuous")

#: The four routers that carried the shipped collisions. If the walk no longer reaches one of them,
#: it cannot see a recurrence there, whatever the total says.
_MUST_REACH = ["aec_api.routers.drawings", "aec_api.routers.authoring_docs",
               "aec_api.routers.analysis", "aec_api.routers.authoring_analysis"]
_MISSING = [m for m in _MUST_REACH if m not in _MODULES]
check("the walk reaches every router that carried a shipped collision",
      not _MISSING,
      f"absent from the expansion: {_MISSING} — a recurrence in one of these would be invisible")

#: `_concrete()` fills each `{param}` with ONE segment, which stands in for the real value only
#: while no route declares a `:path` converter — that one swallows the rest of the URL, so a
#: single placeholder would under-match and the verdict would silently narrow.
_PATH_CONV = sorted({p for p, _, _ in LIVE if ":path}" in p})
check("no route uses a `:path` converter, so a one-segment placeholder is a sound probe",
      not _PATH_CONV,
      f"{len(_PATH_CONV)} do: {_PATH_CONV[:4]} — `_concrete()` under-matches for these and the "
      "verdict below is narrower than it reads; give them a multi-segment placeholder first")

# ---------------------------------------------------------------------------------------------
# PROOF OF REACH — the four as they shipped, rebuilt rather than fetched.


def _shipped_collision_app():
    """The four registrations as they stood at `dc222fff~1`, in their shipped inclusion order.

    Frozen here rather than read out of git: CI checks out shallow, so `git show` of a parent commit
    is a build failure, and every neighbouring gate embeds its pre-fix subject for that reason. Only
    the paths, methods and inclusion order matter to the analyser, so the handlers are stubs.
    """
    drawings, authoring_docs = APIRouter(), APIRouter()
    analysis, authoring_analysis = APIRouter(), APIRouter()

    def stub(router, path, name):
        """Register `path` on `router` under `name` — the handler body is irrelevant to the walk."""
        def handler(pid: str):
            return None
        handler.__name__ = name
        router.get(path)(handler)

    # `drawings.py` and `analysis.py` are included first, so THEY served.
    stub(drawings, "/projects/{pid}/drawings/plan.svg", "plan")
    stub(drawings, "/projects/{pid}/drawings/sheet.svg", "sheet_svg")
    stub(drawings, "/projects/{pid}/drawings/sheet.pdf", "sheet_pdf")
    stub(analysis, "/projects/{pid}/mep", "mep")

    # `authoring_docs.py` and `authoring_analysis.py` are included after, so they were shadowed.
    stub(authoring_docs, "/projects/{pid}/drawings/plan.svg", "plan_svg")
    stub(authoring_docs, "/projects/{pid}/drawings/sheet.svg", "sheet_svg")
    stub(authoring_docs, "/projects/{pid}/drawings/sheet.pdf", "sheet_pdf")
    stub(authoring_analysis, "/projects/{pid}/mep", "mep_summary")

    # A route unique to one router, so "found four" is not "found everything".
    stub(authoring_docs, "/projects/{pid}/spec/manual", "spec_manual")

    replay = FastAPI()
    for r in (drawings, analysis, authoring_docs, authoring_analysis):
        replay.include_router(r)
    return replay


_REPLAY = _shipped_collision_app()
_REPLAY_HITS = shadowed(list(expand(_REPLAY.routes)))
_EXPECTED = {("/projects/{pid}/drawings/plan.svg", "GET"),
             ("/projects/{pid}/drawings/sheet.svg", "GET"),
             ("/projects/{pid}/drawings/sheet.pdf", "GET"),
             ("/projects/{pid}/mep", "GET")}

check("the analyser re-finds all four shipped collisions, and only those four",
      set(_REPLAY_HITS) == _EXPECTED,
      f"found {sorted(_REPLAY_HITS)} — expected exactly {sorted(_EXPECTED)}")

# The mutation for failure mode 1: narrow the walk to top-level routes, as a broken expansion would.
_NARROWED = shadowed([(r.path, m, r) for r in _REPLAY.routes if isinstance(r, APIRoute)
                      for m in sorted(r.methods or ()) if m not in ("HEAD", "OPTIONS")])
check("  and a walk that stops at the top level MISSES all four (mutation)",
      not _NARROWED,
      f"the narrowed walk still found {sorted(_NARROWED)} — the replay is not exercising the "
      "included-router path, so it proves nothing about the live derivation")


def _param_before_literal_app():
    """A parameterised route registered BEFORE the literal one it swallows — no equal paths.

    The four shipped instances were identical spellings, so a gate built from them alone would pass
    a tree holding this. The live tree holds **0** of these (measured), and *a check whose expected
    answer is zero is the easiest kind to break silently*, so the predicate has to be shown finding
    one before that zero means anything.
    """
    first, second = APIRouter(), APIRouter()

    def general(pid: str, name: str):
        return None

    def specific(pid: str):
        return None

    general.__name__, specific.__name__ = "any_drawing", "sheet_svg"
    first.get("/projects/{pid}/drawings/{name}")(general)
    second.get("/projects/{pid}/drawings/sheet.svg")(specific)
    app_ = FastAPI()
    app_.include_router(first)
    app_.include_router(second)
    return app_


_PARAM_HITS = shadowed(list(expand(_param_before_literal_app().routes)))
check("the predicate finds a NON-identical shadow (param route registered before a literal one)",
      set(_PARAM_HITS) == {("/projects/{pid}/drawings/sheet.svg", "GET")},
      f"found {sorted(_PARAM_HITS)} — it is still comparing path strings, so a collision spelled "
      "two different ways reads as a clean tree")


def _literal_first_app():
    """The same two routes in the CORRECT order. Must be clean, or the rule forbids ordinary code."""
    first, second = APIRouter(), APIRouter()

    def specific(pid: str):
        return None

    def general(pid: str, name: str):
        return None

    specific.__name__, general.__name__ = "sheet_svg", "any_drawing"
    first.get("/projects/{pid}/drawings/sheet.svg")(specific)
    second.get("/projects/{pid}/drawings/{name}")(general)
    app_ = FastAPI()
    app_.include_router(first)
    app_.include_router(second)
    return app_


check("  and the same pair in the RIGHT order is clean (the rule is about order, not shape)",
      not shadowed(list(expand(_literal_first_app().routes))),
      "literal-before-parameterised was flagged — that is the correct way to write these two, and "
      "a rule that forbids it would be unusable")

# ---------------------------------------------------------------------------------------------
# THE VERDICT

_HITS = shadowed(LIVE)
_DETAIL = "; ".join(
    f"{m} {p}: {_fn(v[1])} never runs — {_fn(v[0])} is registered earlier and answers this URL"
    for (p, m), v in sorted(_HITS.items()))
check(f"no route is shadowed by an earlier one that already answers its URL ({len(LIVE)} routes)",
      not _HITS,
      f"{len(_HITS)} shadowed: {_DETAIL} — the first registration serves and the LAST one is what "
      "OpenAPI (and so schema.d.ts) describes, so the published contract is the handler that never "
      "runs. Decide which one the consumers want and delete the other; do not re-home a route "
      "without checking who calls it")

print()
if FAILED:
    print(f"route_shadow: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"route_shadow: all checks passed — {len(LIVE)} routes, 0 shadowed")
