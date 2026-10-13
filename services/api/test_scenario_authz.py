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

**SEC-SCENARIO-LIST, 2026-10-13: THE POPULATION WAS THE DEFECT.** The walk in section 1 reads
`if "{sid}" not in str(path): continue` — so `GET /proforma/scenarios`, which serves **the same data
for every scenario at once**, was outside this gate by construction, and it had no authorisation of
any kind. `?project_id=<someone else's>` returned their scenario names, review states and solved
returns (equity IRR, multiple, yield on cost, NPV) to any authenticated caller; with no
`project_id` at all it returned **the entire table**. `create_scenario` was wrong in the other
direction: no `current_user` dependency at all, so it had no notion of who was calling while taking
`project_id` from the body — any authenticated caller could write a scenario into any project.

*A predicate that decides what to LOOK at is more dangerous than one that decides what to report* —
and the paragraph above celebrates "2 of the 8 `{sid}` routes", where the 8 is this predicate's own
output.

**Four gates, and not one could see it:**

| gate | why not |
|---|---|
| this file | `{sid}` routes only — a collection route is not one |
| `test_route_authz.py` | `/projects/{pid}` routes only; there is no `{pid}` in this path |
| `test_global_authz.py` | skips anything under `main._PROTECTED_PREFIXES`, and `/proforma` is in it — but that list enforces **authentication** only, which is why every route *looked* guarded. It also considers MUTATING methods, so the GET was outside twice |
| `test_body_pid_authz.py` | a behavioural test for one route, `/test-fit/optimize` |

*Three exclusions that are each individually reasonable compose into a hole nobody owns* — the shape
`test_schema_types_agree.py` recorded as *"seven exemptions and no owner is how an artifact stops
being checked by anybody."* Section 5 replaces the path-shape predicate with **every route in this
file that reads or writes the `Scenario` model**, derived from the AST, so the next collection route
is in scope the day it is added.

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

# --- 5. EVERY scenario route is authorised, not only the {sid} ones -------------------------------
# Population by what the handler TOUCHES, not by what its path looks like. A route that reads or
# writes `Scenario` is handling scenario data whatever its URL shape, and that is the only property
# the leak above had in common with the eight routes this file already covered.

#: Every mechanism in this router that scopes scenario data to the caller.
#:
#: **`member_project_ids` was missing from the first draft, and measuring is what found it.** The
#: rule then reported FOUR unauthorised routes, and two of them — `GET /proforma/portfolio` and
#: `/proforma/portfolio/compare` — are correctly scoped: both take `rbac.member_project_ids(db,
#: user)` and skip every scenario outside it, which is a *stricter* filter than `_can_read` because
#: it does not admit `shared_with`. *A gate that names its authorisers can only see the ones somebody
#: remembered*, and the two it would have condemned are the ones R46 ⑥ built
#: `test_portfolio_authz.py` for. Had the list shipped as drafted, its instruction would have been
#: "add a guard here" to two routes that have one.
#:
#: `role_for` joined for the same reason one step later: `create_scenario`'s `project_id` comes from
#: the BODY, so `rbac.require_role` is structurally unavailable to it — its inner signature is
#: `dep(pid: str, ...)`, which FastAPI resolves from the path or query — and the check has to be
#: written out against `rbac.role_for`. **Found by this gate reporting the REPAIRED route as
#: unauthorised**, which is the right answer from a list that did not yet name the mechanism the
#: repair was forced to use.
AUTHORISERS = ("_scenario_for", "_can_read", "_can_write", "require_role", "_readable_scenarios",
               "member_project_ids", "role_for")


def _code_of(fn) -> str:
    """The function's source with its DOCSTRING REMOVED.

    **Section 3 above records this exact defect and section 5 reproduced it anyway.** That section
    says: *"The unparsed source includes the DOCSTRING, and this function's docstring says 'there
    was no `current_user` dependency at all' — so a substring check for 'current_user' passes on a
    route that has none… The gate was reading its own documentation."*

    The first draft of section 5 checked `ast.unparse(fn)`, and mutation found it: reinstating the
    shipped `list_scenarios` and the shipped `create_scenario` **in the fixed tree** left this gate
    GREEN both times, because the repaired routes' docstrings explain the fix and name `_can_read`
    and `role_for` while doing so. **The better the comment, the more thoroughly it defeats the
    check** — a prose explanation of a guard is indistinguishable, to a substring, from the guard.

    *A lesson written four sections above the code that needs it is not applied by being true.*
    """
    body = fn.body
    if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    stripped = type(fn)(name=fn.name, args=fn.args, body=body or [ast.Pass()],
                        decorator_list=fn.decorator_list, returns=fn.returns,
                        type_comment=None, type_params=[])
    return ast.unparse(ast.fix_missing_locations(stripped))


def _touches_model(body: str) -> bool:
    return ("Scenario(" in body or "Scenario)" in body or "Scenario." in body
            or "_scenario_for" in body)


def _route_decorators(fn) -> list:
    return [d for d in fn.decorator_list
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and d.func.attr in ("get", "post", "put", "patch", "delete")]


scenario_routes: list[tuple[str, str, str, bool]] = []
for fn in ast.walk(tree):
    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    routes = _route_decorators(fn)
    if not routes:
        continue
    body = _code_of(fn)                      # NEVER `ast.unparse(fn)` — see `_code_of`
    if not _touches_model(body):
        continue
    arg = routes[0].args[0] if routes[0].args else None
    path = str(getattr(arg, "value", ""))
    scenario_routes.append((routes[0].func.attr.upper(), path, fn.name,
                            any(a in body for a in AUTHORISERS)))

# Silence is not a signal, twice over: this derivation must find MORE routes than the {sid} one, or
# it has reproduced the predicate it exists to replace.
check("the model-touching walk found the scenario routes", len(scenario_routes) >= 10,
      f"{len(scenario_routes)} route(s) read or write Scenario")
check("...and it is STRICTLY WIDER than the {sid} predicate — otherwise it is the same gate "
      "wearing a new docstring",
      len(scenario_routes) > len(sid_routes),
      f"{len(scenario_routes)} model-touching vs {len(sid_routes)} with a sid in the path")

unauth = [f"{m} {p} ({fn})" for m, p, fn, ok in scenario_routes if not ok]
check("every route that reads or writes a Scenario authorises the caller", not unauth,
      "; ".join(unauth) or f"all {len(scenario_routes)} authorised")

# PROOF OF REACH: the two shipped defects, reinstated as source, must BOTH be re-found. Without
# this the check above is a claim about a tree that has already been fixed. Frozen as text rather
# than fetched from history — `test_gap_records.py` paid for a replay that used `git show` and
# failed only in CI, whose checkout is shallow.
_PRE_FIX_LIST = "\n".join([
    '@router.get("/proforma/scenarios")',
    "def list_scenarios(project_id: str | None = None, db: Session = Depends(get_db)):",
    "    q = db.query(Scenario)",
    "    if project_id:",
    "        q = q.filter(Scenario.project_id == project_id)",
    '    return [{"id": s.id, "name": s.name} for s in q.all()]',
])
_PRE_FIX_CREATE = "\n".join([
    '@router.post("/proforma/scenarios", status_code=201)',
    "def create_scenario(body: ScenarioIn, db: Session = Depends(get_db)):",
    "    s = Scenario(name=body.name, project_id=body.project_id, assumptions={})",
    "    db.add(s)",
    "    db.commit()",
    '    return {"id": s.id}',
])
_GUARDED = "\n".join([
    '@router.get("/proforma/scenarios/{sid}")',
    "def get_scenario(sid: str, db: Session = Depends(get_db), user: str = Depends(current_user)):",
    "    return _scenario_for(sid, db, user)",
])
#: Scoped by `member_project_ids` rather than `_can_read` — the two portfolio routes the first draft
#: of AUTHORISERS would have told somebody to "fix".
_PORTFOLIO_SHAPE = "\n".join([
    '@router.get("/proforma/portfolio")',
    "def portfolio(db: Session = Depends(get_db), user: str = Depends(rbac.current_user)):",
    "    allowed = rbac.member_project_ids(db, user)",
    "    scens = [s for s in db.query(Scenario).all()",
    "             if s.result and (allowed is None or s.project_id in allowed)]",
    '    return {"deals": len(scens)}',
])
#: The docstring trap, as a fixture. A route with NO guard whose prose NAMES one must be reported.
#: This is what `_code_of` exists for, and without it this file goes blind on exactly the commit
#: that documents a fix — the better the comment, the worse the blindness.
_PROSE_ONLY = "\n".join([
    '@router.get("/proforma/scenarios")',
    "def list_scenarios(project_id: str | None = None, db: Session = Depends(get_db)):",
    '    """Scenarios for a project.',
    "",
    "    `_can_read` guards the eight {sid} routes and `rbac.role_for` backs it; this route is",
    "    deliberately open because the middleware already 401s an anonymous caller.",
    '    """',
    "    return [{} for s in db.query(Scenario).all()]",
])


def _unauthorised_in(src: str) -> list[str]:
    """The VERDICT over arbitrary source, separate from the walk so it can be mutated directly.

    `test_unique_read_guard.py` had to learn this one layer up: asserting that the analyser still
    REPORTS a site is not asserting how it classifies it, so a mutation routing everything to
    "safe" passed. The classification is this function, and the self-checks below mutate it.
    """
    out: list[str] = []
    for f in ast.walk(ast.parse(src)):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not _route_decorators(f):
            continue
        b = _code_of(f)
        if not _touches_model(b):
            continue
        if not any(a in b for a in AUTHORISERS):
            out.append(f.name)
    return out


check("PROOF OF REACH: the shipped `list_scenarios` is re-found as unauthorised",
      _unauthorised_in(_PRE_FIX_LIST) == ["list_scenarios"], str(_unauthorised_in(_PRE_FIX_LIST)))
check("PROOF OF REACH: ...and the shipped `create_scenario` too — a collection READ and a "
      "cross-project WRITE are two defects, and re-finding one is not re-finding both",
      _unauthorised_in(_PRE_FIX_CREATE) == ["create_scenario"],
      str(_unauthorised_in(_PRE_FIX_CREATE)))
check("PROOF OF REACH: ...and a route whose DOCSTRING names a guard it does not use is still "
      "reported — the regression this file already paid for once, now pinned",
      _unauthorised_in(_PROSE_ONLY) == ["list_scenarios"], str(_unauthorised_in(_PROSE_ONLY)))
check("...and a route that DOES authorise comes back clean, so the rule is not simply 'everything'",
      _unauthorised_in(_GUARDED) == [], "a guarded route must not be reported")
check("...and so does one scoped by `member_project_ids` rather than `_can_read`",
      _unauthorised_in(_PORTFOLIO_SHAPE) == [], "a differently-scoped route must not be reported")

# --- 6. behavioural: the collection filter actually refuses a stranger -----------------------------
# The static rule above checks that an authoriser is MENTIONED in code. That is not the same as it
# being applied to every row — `test_pid_lock_pgxproc.py`'s lesson one layer up: a check that the
# lock is taken is not a check that it excludes anybody. So the filter is exercised directly.
from aec_api.routers.proforma import _readable_scenarios  # noqa: E402

_orig_on2, _orig_role2 = rbac.RBAC_ON, rbac.role_for
try:
    rbac.RBAC_ON = True
    rbac.role_for = lambda db, pid, user: "editor" if (user, pid) == ("member", "p1") else None  # type: ignore
    mine, theirs = _S(project_id="p1"), _S(project_id="p2")
    shared = _S(project_id="p3", shared_with=["lp"])
    for _s, _i in ((mine, "s1"), (theirs, "s2"), (shared, "s3")):
        _s.id = _i
    rows = [mine, theirs, shared]
    check("a member sees only their own project's scenarios",
          [s.id for s in _readable_scenarios(_DB(), rows, "member")] == ["s1"])
    check("a stranger sees NONE — this is the leak, asserted rather than described",
          _readable_scenarios(_DB(), rows, "nobody") == [])
    check("an LP sees the one shared with them, and no other",
          [s.id for s in _readable_scenarios(_DB(), rows, "lp")] == ["s3"])
    # The api-key claim needs the REAL `role_for`, not the stub three lines up. Asserted against
    # the stub it FAILED — correctly: the stub returns None for every user but `member`, so it was
    # measuring the stand-in rather than the composition. *A test that supplies the thing under test
    # cannot notice it being wrong*, and the inverse bites just as hard: a stub can refute a true
    # claim about the real function. `role_for` short-circuits to "admin" for `api-key` before any
    # query, so the real one is safe to call with a stub session here.
    rbac.role_for = _orig_role2
    check("the api-key identity still sees everything — `role_for` returns admin for it, as it "
          "already did for the eight {sid} routes, so server-to-server callers are unaffected",
          len(_readable_scenarios(_DB(), rows, "api-key")) == 3)
    rbac.RBAC_ON = False
    check("with RBAC off the filter is open — desktop/local deployments unaffected",
          len(_readable_scenarios(_DB(), rows, "anyone")) == 3)
finally:
    rbac.RBAC_ON, rbac.role_for = _orig_on2, _orig_role2

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_scenario_authz OK - {len(scenario_routes)} scenario routes authorised "
      f"({len(sid_routes)} of them carry a sid)")

