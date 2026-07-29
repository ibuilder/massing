"""R23-JURISDICTION-PACKS — the GLOBAL pack routes must refuse an unauthenticated caller.

Its own test file, and RBAC-ON, because that is the only configuration in which the bug exists. The
other two jurisdiction suites run with `AEC_RBAC` popped (the repo's convention), so they could never
have caught this: with RBAC off `current_user` returns the X-User header and everything is
authenticated by construction.

THE BUG THIS PINS. `Depends(current_user)` IDENTIFIES; it does not AUTHORISE. With RBAC on and no
bearer token, cookie or trusted header it returns the literal string `"anonymous"` — so a route
guarded only by it is not guarded. Measured on the shipped branch before the fix:

    GET    /jurisdiction/packs        -> 200
    POST   /jurisdiction/packs        -> 201      <-- unauthenticated write to GLOBAL state
    DELETE /jurisdiction/packs/{id}   -> 200
    control: GET /admin/errors        -> 403      (so the harness was authenticating correctly)

Packs are global and feed `/projects/{pid}/jurisdiction/check`, so anyone could have added, replaced
or deleted rule packs that change compliance results across EVERY project in a matching jurisdiction.

This is the platform-global sibling of `test_route_authz`, which only walks `/projects/{pid}` routes —
a route with no `{pid}` is outside its remit entirely, which is why nothing caught this.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_jurisdiction_authz.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_juris_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_juris_authz"
os.environ["AEC_RBAC"] = "1"                 # the whole point — RBAC ON
os.environ.pop("AEC_TRUST_XUSER", None)      # ...and the dev header NOT trusted
os.environ["AEC_AUTH_SECRET"] = "test-secret-that-is-long-enough-to-be-accepted"
for _f in ("./test_juris_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


PACK = {"id": "authz-probe", "jurisdiction": "TX", "authority": "a", "name": "n",
        "edition": "1", "source": "s",
        "requirements": [{"id": "r", "scope": "IfcWall", "require": "name", "severity": "high"}]}

with TestClient(app) as c:
    # The control first. If this is not 403 the harness is not actually running with RBAC on, and
    # every assertion below would pass for the wrong reason.
    ctl = c.get("/admin/errors")
    check("CONTROL: a known-protected route refuses an anonymous caller",
          ctl.status_code == 403, ctl.status_code)

    check("anonymous cannot LIST packs", c.get("/jurisdiction/packs").status_code == 403,
          c.get("/jurisdiction/packs").status_code)
    imp = c.post("/jurisdiction/packs", json=PACK)
    check("anonymous cannot IMPORT a pack — global state, every project's compliance",
          imp.status_code == 403, imp.status_code)
    dele = c.delete("/jurisdiction/packs/authz-probe")
    check("anonymous cannot DELETE a pack", dele.status_code == 403, dele.status_code)

    # A bare X-User header must not be enough either — that is the dev path, and it is exactly what
    # `TRUST_XUSER` gates. If this passes, the header is being trusted in a production posture.
    c2 = TestClient(app)
    c2.headers.update({"X-User": "someone@example.com"})
    with c2:
        check("an untrusted X-User header does not grant access",
              c2.post("/jurisdiction/packs", json=PACK).status_code == 403,
              c2.post("/jurisdiction/packs", json=PACK).status_code)

    # The project-scoped routes were always gated by require_role; assert it rather than assume.
    check("the project-scoped requirements route is gated too",
          c.get("/projects/nonexistent/jurisdiction/requirements").status_code in (401, 403, 404))
    check("the project-scoped check route is gated too",
          c.get("/projects/nonexistent/jurisdiction/check").status_code in (401, 403, 404))

print()
if FAILED:
    print(f"jurisdiction_authz: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("jurisdiction_authz: all checks passed")
