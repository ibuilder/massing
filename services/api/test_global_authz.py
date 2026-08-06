"""SEC-GLOBAL-AUTHZ — no NEW platform-global mutating route may ship without a gate.

`test_route_authz` walks `/projects/{pid}` routes and asserts each carries `require_role`. A route
with no `{pid}` is outside its remit entirely — so on 2026-07-29 it passed on 695 routes while three
brand-new routes, `GET`/`POST`/`DELETE /jurisdiction/packs`, were reachable **unauthenticated**
(measured with RBAC on and no credentials: 200 / **201** / 200, with `GET /admin/errors` correctly
403 in the same run). Packs are global, so anyone could have changed compliance results for every
project in a matching jurisdiction.

TWO MECHANISMS PROTECT THESE ROUTES, and a route needs one of them:

1. `main._PROTECTED_PREFIXES` — middleware that refuses anonymous callers on listed path prefixes
   when RBAC is on. **It is a hand-maintained list of top-level prefixes**, which is the actual
   defect: adding a new prefix (`/jurisdiction`) silently opts out of the safety net and nothing
   fails. That is exactly what happened.
2. The route's own dependency chain carrying something that AUTHORISES — `require_role` (tagged
   `_role_gate`), `require_admin_user`, `require_platform_admin` /
   `_require_platform_admin`, `require_identified`,
   `require_scim`.

`Depends(current_user)` is neither. It **identifies**; with RBAC on and no credential it returns the
literal string "anonymous", so a route guarded only by it has a name attached and no gate — and the
signature reads like a gate, which is how it survives review.

WHY THIS IS A RATCHET AND NOT A PASS/FAIL. There are 43 such routes on main today. Most are
legitimately open — auth entry points, token-scoped `/shared/{token}` links, SCIM's own bearer gate,
webhooks, and the stateless-compute paths the middleware comment explicitly exempts. Triaging all 43
is real work and this test does not pretend to have done it. What it does is freeze the set: **a new
unguarded global mutating route fails the build**, and the baseline can only go down. Same shape as
the innerHTML ratchet.

If you are removing one, delete its line from BASELINE. If you are ADDING a route and this fails,
the fix is almost never to add it here — it is to add your prefix to `_PROTECTED_PREFIXES` or give
the route a real dependency.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_global_authz.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_global_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_global_authz"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_global_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import APIRouter  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

import aec_api.main as M  # noqa: E402

#: Dependencies that AUTHORISE. `current_user` is deliberately absent — that is the whole point.
#:
#: Every name here MUST resolve to a real dependency (asserted below). `require_license` and
#: `require_plan` were listed until 2026-07-29 and do not exist anywhere in `src/`. Dead today, since
#: no route depends on them — but matching is BY NAME, so the day someone writes a `require_license`
#: that checks a subscription *tier* rather than authorisation, every route using it leaves this
#: ratchet silently and nothing fails. That is the `current_user` trap one level up: a name that
#: reads like a gate. An allowlist entry with no referent is a pre-authorised hole waiting for a
#: matching name, so the set is now verified against the source rather than trusted.
# `require_platform_admin` is the shared rbac.py gate for firm-wide writes; `_require_platform_admin`
# is the private name in routers/cost.py that now delegates to it. Both names are kept because this
# matches by NAME and both still appear as dependencies.
AUTHORISING = {"require_admin_user", "require_platform_admin", "_require_platform_admin",
               "require_identified", "require_scim"}

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _defined_in_source() -> set:
    """Names in AUTHORISING that have a definition under `src/`.

    Accepts a `def` **or** a module-level assignment. A `def`-only match was the first version and it
    is too narrow: a dependency built by a factory — `require_x = _make_gate(...)`, a normal FastAPI
    idiom — has no `def` and would be reported as resolving to nothing. That direction of error is
    the damaging one here: the guard would fail a build over a dependency that exists, and a gate
    that cries wolf teaches people to suppress it. This file's failure text argues against
    suppression; it must not manufacture reasons to reach for it.

    Text matching rather than importing, deliberately: the question is "does this name have a
    referent in the source", and importing every module to answer it would run application code and
    make a security gate depend on import side effects.
    """
    found = set()
    for root, _dirs, files in os.walk(os.path.join(os.path.dirname(__file__), "src")):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
            for name in AUTHORISING:
                for ln in lines:
                    stripped = ln.lstrip()
                    if stripped.startswith((f"def {name}(", f"async def {name}(")):
                        found.add(name)
                        break
                    # module-level binding: `name = ...` at column 0, not `something = name`
                    if ln.startswith((f"{name} =", f"{name}:")):
                        found.add(name)
                        break
    return found


_missing = AUTHORISING - _defined_in_source()
if _missing:
    print(f"FAIL - {len(_missing)} name(s) in AUTHORISING resolve to nothing in src/: "
          f"{sorted(_missing)}")
    print("  Matching is BY NAME. A name with no referent silently becomes an authoriser the day")
    print("  someone happens to define it - which may be a subscription check, not a gate.")
    print("  Either delete the name, or point it at a dependency that actually authorises.")
    sys.exit(1)

#: Known routes that are mutating, global, outside `_PROTECTED_PREFIXES`, and carry no authorising
#: dependency. Frozen 2026-07-29 at v0.3.790. NOT a statement that each is safe — a statement that
#: each is KNOWN. Adding here should be rare and argued; removing is always welcome.
BASELINE = {
    # public auth surface — necessarily reachable without an identity
    ("POST", "/auth/login"), ("POST", "/auth/logout"), ("POST", "/auth/register"),
    ("POST", "/auth/reset"), ("POST", "/auth/mfa/verify"), ("POST", "/auth/saml/acs"),
    # authenticated self-service: operates on the CALLER's own record, and 401s anonymously
    ("POST", "/auth/logout-all"), ("POST", "/auth/password"),
    ("POST", "/auth/mfa/setup"), ("POST", "/auth/mfa/enable"), ("POST", "/auth/mfa/disable"),
    # token-scoped share links — the token IS the credential
    ("POST", "/shared/{token}/comment"), ("POST", "/shared/{token}/decision"),
    # signed webhook
    ("POST", "/esign/webhook"),
    # stateless compute — no stored state; the middleware comment exempts this class explicitly
    ("POST", "/compute/graph"), ("POST", "/generate/massing/preview"),
    ("POST", "/massing/optioneer"), ("POST", "/massing/optioneer/recipes"),
    ("POST", "/structure/recommend"), ("POST", "/test-fit/compare"),
    # (POST /test-fit/optimize was removed on 2026-08-06: FIXED, not re-frozen. It was the ONLY one
    #  of the five routes under this "stateless compute" label that takes a `Session` — it read an
    #  arbitrary project's purchase_price and hard $/sf from a `pid` in the request BODY, which
    #  `require_role` structurally cannot cover (its dep resolves `pid` from path/query) and
    #  `test_route_authz` never walks (no `{pid}` in the path). It now calls `rbac.authorize_pid`.
    #  The lesson is about THIS LIST rather than that route: the entry was not an oversight, it was
    #  a triage decision made by association with its neighbours — same file, same shape, and four
    #  of the five genuinely are calculators. A frozen baseline preserves the reasoning of the day
    #  it was written, including the parts that were wrong. The predicate that isolates the real
    #  cases is not "no authz" but "no authz AND takes a DB session". Guarded by
    #  `test_body_pid_authz.py`, which fails if it is ever re-added here.)
    ("POST", "/schedule/takt"), ("POST", "/schedule/takt/progress"),
    ("POST", "/estimate/assembly/price"), ("POST", "/parcels/analyze"), ("POST", "/parcels/screen"),
    ("POST", "/ids/build"), ("POST", "/ids/eir"),
    ("POST", "/client-errors"),
    # (SCIM is NOT here: `require_scim` is in AUTHORISING, so the enumerator already clears those
    #  four routes. Listing them anyway would have been a silent lie about why they are safe — the
    #  first run of this test reported them as stale baseline entries, which is the check working.)
    # (The seven POST /pdf/* routes were removed on 2026-07-29: FIXED, not re-frozen. They guarded with
    #  `Depends(current_user)` and /pdf is outside _PROTECTED_PREFIXES, so an anonymous caller could
    #  reach them. /pdf/seal was the serious one — verified end to end, an unauthenticated request
    #  returned a PDF bearing a rendered PE seal with an attacker-chosen name and licence number.
    #  All now take require_identified, and sealing writes an audit row naming the actor.)
    # (The three entries that used to sit here — POST /templates, DELETE /templates/{tid} and
    #  POST /samples/{sample_id}/open — were removed on 2026-07-29 because they were FIXED rather than
    #  re-frozen. They were flagged in this file as "the entries in this list I would not defend if
    #  asked", which was accurate: /templates is outside _PROTECTED_PREFIXES and both routes guarded
    #  with `Depends(current_user)`, so an anonymous caller could delete a template every project
    #  shares; open_sample carried no identity dependency at all and returned 201. All three now take
    #  `require_identified`. Freezing a count stops it growing; it does not close the hole, and this
    #  file existing is what made them findable.)
}


def _chain(dep, out):
    call = getattr(dep, "call", None)
    if call is not None:
        out.append(getattr(call, "__name__", str(call)))
        if getattr(call, "_role_gate", None) is not None:
            out.append("__ROLE_GATE__")
    for sub in getattr(dep, "dependencies", []):
        _chain(sub, out)
    return out


def unguarded() -> set:
    """Mutating, non-`{pid}`, outside `_PROTECTED_PREFIXES`, and with no authorising dependency."""
    routers = {n: getattr(M, n) for n in dir(M)
               if isinstance(getattr(getattr(M, n, None), "router", None), APIRouter)}
    found = set()
    for _name, mod in routers.items():
        for r in mod.router.routes:
            if not isinstance(r, APIRoute) or "{pid}" in r.path:
                continue
            methods = (r.methods or set()) & MUTATING
            if not methods or r.path.startswith(M._PROTECTED_PREFIXES):
                continue
            names = set(_chain(r.dependant, []))
            if "__ROLE_GATE__" in names or (AUTHORISING & names):
                continue
            for m in methods:
                found.add((m, r.path))
    return found


live = unguarded()
new = sorted(live - BASELINE)
gone = sorted(BASELINE - live)

if new:
    print(f"FAIL - {len(new)} NEW platform-global mutating route(s) with no gate:")
    for m, p in new:
        print(f"    {m:6} {p}")
    print()
    print("  Depends(current_user) IDENTIFIES; it does not AUTHORISE. With RBAC on and no")
    print("  credential it returns the literal string 'anonymous', so it is not a gate.")
    print("  Fix by adding the prefix to main._PROTECTED_PREFIXES, or by giving the route a real")
    print("  dependency (require_role / require_admin_user / require_identified).")
    print("  Adding it to BASELINE is almost never the right answer.")
    sys.exit(1)

print(f"GLOBAL-AUTHZ OK - {len(live)} platform-global mutating route(s) carry no authorising "
      f"dependency of their own and sit outside the RBAC middleware's prefix list; all are known. "
      f"test_route_authz covers /projects/{{pid}} routes and is SILENT about these, which is how "
      f"three unauthenticated /jurisdiction/packs routes reached a PR on 2026-07-29 (200/201/200 "
      f"with no credentials, while /admin/errors correctly returned 403 in the same run). The root "
      f"cause is that _PROTECTED_PREFIXES is hand-maintained, so a NEW top-level prefix silently "
      f"opts out of the safety net and nothing fails. This freezes the set: a new one fails the "
      f"build. It is not a claim that each of the {len(live)} is safe - it is a claim that each is "
      f"KNOWN, and the number can only go down. Twelve routes were FIXED rather than re-frozen on "
      f"2026-07-29: POST/DELETE /templates and POST /samples/{{id}}/open (the three this file had "
      f"flagged as indefensible), the seven POST /pdf/* routes - /pdf/seal returned a rendered PE "
      f"seal bearing a caller-chosen name and licence number to an UNAUTHENTICATED request - and "
      f"GET/PUT /firm/rules, where require_role on a path with no {{pid}} made `pid` a caller-supplied "
      f"query parameter, so any project-admin could replace the firm's standards by naming their own "
      f"project. A frozen count stops a hole multiplying; it does not close one.")
if gone:
    print(f"  ({len(gone)} baseline entr(ies) no longer present - delete from BASELINE: {gone})")
