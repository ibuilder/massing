"""The platform-global mutating routes `test_global_authz` flagged as indefensible must refuse anonymity.

`test_global_authz.py` enumerates global mutating routes with no authorising dependency and FREEZES
the count so it cannot grow. Freezing is not fixing. Three entries in that baseline were annotated
"the entries in this list I would not defend if asked", and they were right to be:

    POST   /templates              Depends(current_user)  -> identifies, does not authorise
    DELETE /templates/{tid}        Depends(current_user)  -> unauthenticated delete of SHARED state
    POST   /samples/{id}/open      no identity dependency at all -> 201, project created, no actor

`/templates` and `/samples` are both outside `_PROTECTED_PREFIXES`, so the RBAC middleware never
challenged them either. Templates are cross-project: deleting one affects every project that uses it.

All three now take `rbac.require_identified`. This file is the live probe that says so — the static
walker can only see that *a* dependency is present, and the whole defect was a dependency that looks
like a gate and is not.

RBAC-ON is the only configuration in which the bug exists, which is why this is its own file: the
repo convention pops `AEC_RBAC`, and with RBAC off `current_user` returns the X-User header and
everything is authenticated by construction. A suite that could not see the failure was how these
shipped.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_global_mutating_authz.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_glob_mut_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_glob_mut_authz"
os.environ["AEC_RBAC"] = "1"                 # the whole point — RBAC ON
os.environ.pop("AEC_TRUST_XUSER", None)      # ...and the dev header NOT trusted
os.environ["AEC_AUTH_SECRET"] = "test-secret-that-is-long-enough-to-be-accepted"
for _f in ("./test_glob_mut_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TEMPLATE = {"module": "rfi", "name": "authz-probe", "data": {}}

with TestClient(app) as c:
    # The CONTROL first. If this is not 403 the harness is not actually running with RBAC on, and
    # every assertion below would pass for the wrong reason. A probe that cannot fail proves nothing.
    ctl = c.get("/admin/errors")
    check("CONTROL: a known-protected route refuses an anonymous caller",
          ctl.status_code == 403, ctl.status_code)

    r = c.post("/templates", json=TEMPLATE)
    check("anonymous cannot CREATE a template", r.status_code == 403, r.status_code)

    r = c.delete("/templates/any-id")
    check("anonymous cannot DELETE a template — shared across every project",
          r.status_code == 403, r.status_code)

    # Form-encoded, not JSON: `name` is a Form field. Authorisation must refuse before the body or the
    # sample id is ever looked at, so a nonexistent sample must still give 403 and not 404.
    r = c.post("/samples/nonexistent/open", data={})
    check("anonymous cannot OPEN a sample as a new project", r.status_code == 403, r.status_code)
    check("...and it refuses on AUTH, not on a missing sample (403 before 404)",
          r.status_code == 403, r.status_code)

    # A bare X-User header must not be enough — that is the dev path, gated by TRUST_XUSER. If this
    # passes, the header is being honoured in a production posture.
    c2 = TestClient(app)
    c2.headers.update({"X-User": "someone@example.com"})
    with c2:
        check("an untrusted X-User header does not grant template creation",
              c2.post("/templates", json=TEMPLATE).status_code == 403,
              c2.post("/templates", json=TEMPLATE).status_code)
        check("an untrusted X-User header does not grant sample opening",
              c2.post("/samples/nonexistent/open", data={}).status_code == 403,
              c2.post("/samples/nonexistent/open", data={}).status_code)

    # The READ route beside them is deliberately NOT asserted as 403: `GET /templates` is a list of
    # shared templates and is not in this file's remit. Stating that rather than silently omitting it,
    # because a reader should not infer that every /templates route was reviewed here.

print()
if FAILED:
    print(f"global_mutating_authz: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("global_mutating_authz: all checks passed — the three routes test_global_authz flagged as "
      "indefensible now refuse an anonymous caller, and the control proves RBAC was actually on.")
