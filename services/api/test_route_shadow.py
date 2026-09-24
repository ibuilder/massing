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
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./_route_shadow.db"
os.environ.setdefault("STORAGE_DIR", "./_route_shadow_store")

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from starlette.routing import Route  # noqa: E402

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


class Reg:
    """One route registration, resolved: the URL it really answers and the regex that decides it.

    Built from FastAPI's own `_EffectiveRouteContext` where one exists, because the inclusion prefix
    lives only there. The first draft reached into the placeholder's `original_router` and read a
    `prefix` attribute — which **does not exist** on this FastAPI version, so it silently used the
    UN-prefixed router: `include_router(r, prefix="/p")` was reported as `/x/thing`, not
    `/p/x/thing`, and two handlers colliding at the prefixed URL passed the gate clean. *Guessing at
    another library's internals is a precondition you did not write down* — asking it instead
    removes the guess.
    """

    __slots__ = ("path", "method", "regex", "convertors", "endpoint")

    def __init__(self, path, method, regex, convertors, endpoint):
        self.path, self.method = path, method
        self.regex, self.convertors, self.endpoint = regex, convertors, endpoint


def expand(routes, _depth=0):
    """Every route registration the app holds, in match order. Fails closed on anything unclassified."""
    if _depth > 20:
        raise Unclassified("router nesting deeper than 20 — refusing to guess")
    for r in routes:
        name = type(r).__name__
        if isinstance(r, APIRoute):
            for m in sorted(r.methods or ()):
                if m not in ("HEAD", "OPTIONS"):
                    yield Reg(r.path, m, r.path_regex, r.param_convertors, r.endpoint)
        elif name.endswith("IncludedRouter"):
            contexts = getattr(r, "effective_route_contexts", None)
            if contexts is None:
                raise Unclassified(
                    f"{name} exposes no effective_route_contexts; the prefix cannot be resolved and "
                    "the walk would report un-prefixed paths")
            for ctx in contexts():
                for m in sorted(getattr(ctx, "methods", None) or ()):
                    if m not in ("HEAD", "OPTIONS"):
                        yield Reg(ctx.path, m, ctx.path_regex, ctx.param_convertors,
                                  ctx.original_route.endpoint)
        elif isinstance(r, Route) or name in _IGNORABLE:
            continue
        else:
            raise Unclassified(f"unclassified route object {name!r}")


#: One probe value per Starlette convertor. `str` is the default; the others exist because a probe
#: that does not satisfy the convertor cannot match its own route, and a collision on such a route
#: would be reported clean — CodeRabbit's finding on the first draft, which handled only `str` and
#: asserted merely that no `:path` existed.
_PROBE = {"str": "v", "int": "1", "float": "1.5", "uuid": "3f2504e0-4f89-11d3-9a0c-0305e82c3301"}


def probe_url(reg):
    """A URL `reg` certainly answers, with each parameter filled to satisfy its own convertor.

    **The soundness check is not this table, it is `probe_matches_own_route` below.** A convertor
    absent from `_PROBE` yields a probe its own route rejects, and that is asserted rather than
    assumed — so a Starlette release adding a convertor, or a route declaring a custom one, reds the
    build instead of quietly shrinking the population. *A list of known cases is a list somebody
    stopped widening; a self-check is not.*
    """
    out = []
    for seg in reg.path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            inner = seg[1:-1]
            name, _, conv = inner.partition(":")
            out.append(_PROBE.get(conv or "str", "\x00unprobeable"))
        else:
            out.append(seg)
    return "/" + "/".join(out)


def probe_matches_own_route(reg):
    """Does the probe actually match the route it was built from? If not, the probe proves nothing."""
    return reg.regex.match(probe_url(reg)) is not None


def shadowed(routes):
    """Every registration an EARLIER one already answers, keyed by the shadowed (path, method).

    **Asks the resolved regex, rather than comparing strings.** The four shipped instances were
    identical paths, and an equality test would find all four — but equality is a precondition, not
    the rule: Starlette matches by regex, so `/projects/{pid}/drawings/{name}` registered first
    swallows a later `/projects/{pid}/drawings/sheet.svg` just as completely, and a gate written to
    the four known spellings would report that tree clean. *A predicate that decides what to LOOK at
    is more dangerous than one that decides what to report.* Measured before widening: the live tree
    holds **0** of the non-identical form, so this costs no exemptions and no noise today — it
    removes a precondition rather than chasing a finding.

    Separate from the walk on purpose. `test_unique_read_guard`'s first draft asserted that its
    analyser still *reported* a site, so a mutation routing every site to "safe" passed — reporting
    and ruling are two different questions, and a mutation has to be able to aim at the ruling.
    """
    ordered = list(routes)
    hits: dict[tuple[str, str], list] = {}
    for j, reg in enumerate(ordered):
        url = probe_url(reg)
        for earlier in ordered[:j]:
            if earlier.method != reg.method:
                continue
            if earlier.regex.match(url) is not None:
                # The first match wins at runtime, so `earlier` serves and `reg` never runs.
                hits[(reg.path, reg.method)] = [earlier, reg]
                break
    return hits


def _fn(reg):
    return getattr(reg.endpoint, "__name__", "?")


# ---------------------------------------------------------------------------------------------
# THE POPULATION — derived from the live app, with the floors that stop a silent empty walk.

try:
    LIVE = list(expand(app.routes))
except Unclassified as exc:                                    # pragma: no cover - fail closed
    print(f"FAIL  the walk could not classify the live app — {exc}")
    sys.exit(1)

_MODULES = {getattr(r.endpoint, "__module__", "") for r in LIVE}

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

#: EVERY probe must match the route it was built from. This replaces the first draft's narrower
#: assertion that no route declares a `:path` converter — which was true, and left `:int`, `:float`,
#: `:uuid` and any custom convertor unhandled: a probe those routes reject cannot collide with
#: anything, so a duplicate on one would have been reported clean. *Asserting the one case you
#: thought of is not asserting the property.* Raised by review on the first draft.
_UNPROBEABLE = [r for r in LIVE if not probe_matches_own_route(r)]
check(f"every probe matches its own route, so a probe can detect a collision ({len(LIVE)} routes)",
      not _UNPROBEABLE,
      f"{len(_UNPROBEABLE)} probe(s) their own route rejects, e.g. "
      f"{[r.path for r in _UNPROBEABLE[:4]]} — add the convertor to `_PROBE`. Until then a "
      "collision on these paths is invisible and the verdict below is narrower than it reads")

# ---------------------------------------------------------------------------------------------
# PROOF OF REACH — the shipped four, plus the two forms review showed the first draft could not see.


def _stub(router, path, name):
    """Register `path` on `router` under `name`; the handler body is irrelevant to the walk."""
    def handler(pid: str):
        return None
    handler.__name__ = name
    router.get(path)(handler)


def _shipped_collision_app():
    """The four registrations as they stood at `dc222fff~1`, in their shipped inclusion order.

    Frozen here rather than read out of git: CI checks out shallow, so `git show` of a parent commit
    is a build failure, and every neighbouring gate embeds its pre-fix subject for that reason.
    """
    drawings, authoring_docs = APIRouter(), APIRouter()
    analysis, authoring_analysis = APIRouter(), APIRouter()

    # `drawings.py` and `analysis.py` are included first, so THEY served.
    _stub(drawings, "/projects/{pid}/drawings/plan.svg", "plan")
    _stub(drawings, "/projects/{pid}/drawings/sheet.svg", "sheet_svg")
    _stub(drawings, "/projects/{pid}/drawings/sheet.pdf", "sheet_pdf")
    _stub(analysis, "/projects/{pid}/mep", "mep")

    # `authoring_docs.py` and `authoring_analysis.py` are included after, so they were shadowed.
    _stub(authoring_docs, "/projects/{pid}/drawings/plan.svg", "plan_svg")
    _stub(authoring_docs, "/projects/{pid}/drawings/sheet.svg", "sheet_svg")
    _stub(authoring_docs, "/projects/{pid}/drawings/sheet.pdf", "sheet_pdf")
    _stub(authoring_analysis, "/projects/{pid}/mep", "mep_summary")

    # A route unique to one router, so "found four" is not "found everything".
    _stub(authoring_docs, "/projects/{pid}/spec/manual", "spec_manual")

    replay = FastAPI()
    for r in (drawings, analysis, authoring_docs, authoring_analysis):
        replay.include_router(r)
    return replay


_REPLAY = _shipped_collision_app()
_REPLAY_HITS = shadowed(expand(_REPLAY.routes))
_EXPECTED = {("/projects/{pid}/drawings/plan.svg", "GET"),
             ("/projects/{pid}/drawings/sheet.svg", "GET"),
             ("/projects/{pid}/drawings/sheet.pdf", "GET"),
             ("/projects/{pid}/mep", "GET")}

check("the analyser re-finds all four shipped collisions, and only those four",
      set(_REPLAY_HITS) == _EXPECTED,
      f"found {sorted(_REPLAY_HITS)} — expected exactly {sorted(_EXPECTED)}")

# The mutation for failure mode 1: narrow the walk to top-level routes, as a broken expansion would.
_NARROWED = shadowed([Reg(r.path, m, r.path_regex, r.param_convertors, r.endpoint)
                      for r in _REPLAY.routes if isinstance(r, APIRoute)
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


_PARAM_HITS = shadowed(expand(_param_before_literal_app().routes))
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


def _typed_converter_app():
    """An identical collision on an `:int` path. The first draft probed `/items/v1`, which an `:int`
    route rejects, so this duplicate came back CLEAN — measured, not supposed."""
    first, second = APIRouter(), APIRouter()
    _stub(first, "/items/{item_id:int}", "first")
    _stub(second, "/items/{item_id:int}", "second")
    app_ = FastAPI()
    app_.include_router(first)
    app_.include_router(second)
    return app_


check("a collision on a TYPED path is found (`:int`; the first draft probed a value it rejects)",
      set(shadowed(expand(_typed_converter_app().routes))) == {("/items/{item_id:int}", "GET")},
      f"found {sorted(shadowed(expand(_typed_converter_app().routes)))} — the probe does not "
      "satisfy the convertor, so nothing can collide on any typed path in the tree")


def _prefixed_app():
    """A collision that exists only at the PREFIXED URL.

    The first draft read a `prefix` attribute off the router placeholder. This FastAPI has none, so
    `getattr(..., "prefix", "")` returned empty and the walk reported `/x/thing` for a router
    included at `/p` — two handlers on `/p/x/thing` passed clean. Every replay above uses an empty
    prefix, so **no fixture here could have caught it**: the gap was invisible to its own tests.
    """
    under_prefix, at_root = APIRouter(), APIRouter()
    _stub(under_prefix, "/x/thing", "under_prefix")
    _stub(at_root, "/p/x/thing", "at_root")
    app_ = FastAPI()
    app_.include_router(under_prefix, prefix="/p")
    app_.include_router(at_root)
    return app_


_PREFIXED = list(expand(_prefixed_app().routes))
check("an inclusion PREFIX is resolved, so a collision at the prefixed URL is found",
      [r.path for r in _PREFIXED] == ["/p/x/thing", "/p/x/thing"]
      and set(shadowed(_PREFIXED)) == {("/p/x/thing", "GET")},
      f"paths seen {[r.path for r in _PREFIXED]}, hits {sorted(shadowed(_PREFIXED))} — the walk is "
      "reporting un-prefixed paths, so every collision behind a prefix is invisible")

check("  and the same pair in the RIGHT order is clean (the rule is about order, not shape)",
      not shadowed(expand(_literal_first_app().routes)),
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
