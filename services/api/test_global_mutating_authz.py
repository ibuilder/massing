"""Platform-global routes that `test_global_authz` could only FREEZE must actually refuse anonymity.

`test_global_authz.py` enumerates global mutating routes with no authorising dependency and FREEZES
the count so it cannot grow. Freezing is not fixing. Three entries in that baseline were annotated
"the entries in this list I would not defend if asked", and they were right to be:

    POST   /templates              Depends(current_user)  -> identifies, does not authorise
    DELETE /templates/{tid}        Depends(current_user)  -> unauthenticated delete of SHARED state
    POST   /samples/{id}/open      no identity dependency at all -> 201, project created, no actor

`/templates` and `/samples` are both outside `_PROTECTED_PREFIXES`, so the RBAC middleware never
challenged them either. Templates are cross-project: deleting one affects every project that uses it.

Then the `/pdf/*` cluster, found the same way and worse (see the comment beside those checks):
eight routes including `/pdf/seal`, which returned a rendered PE/RA seal bearing a caller-chosen name
and licence number to an unauthenticated request.

Then `/firm/rules`, which was gated `require_role("admin")` — a PROJECT gate on a FIRM-WIDE route.
Its dependency signature is `dep(pid: str, ...)`, so with no `{pid}` in the path FastAPI made `pid` a
caller-supplied query parameter: name any project you are admin of (your own throwaway one will do)
and you may replace the firm's entire standards library. Measured under control — ordinary account,
`role="user"`, admin only of a project it had just created: `200 {"saved": 1}` before, `403` after.

These now take `rbac.require_identified` (global reads), or `rbac.require_platform_admin` (firm-wide
writes). This file is the live probe that says so — the static walker can only see that *a* dependency
is present, and the whole defect was a dependency that looks like a gate and is not.

The last check is the one that generalises: no global route may expose a `pid` query parameter. That
is a property of the schema rather than a list of known-bad routes, so it catches the NEXT one.

Keep the closing summary counting `len` rather than naming a number: this file said "the three
routes" while asserting eleven, which is the same staleness bug the sibling file had.

RBAC-ON is the only configuration in which the bug exists, which is why this is its own file: the
repo convention pops `AEC_RBAC`, and with RBAC off `current_user` returns the X-User header and
everything is authenticated by construction. A suite that could not see the failure was how these
shipped.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_global_mutating_authz.py
"""
import json
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


_TOTAL = 0


def check(label, ok, detail=""):
    global _TOTAL
    _TOTAL += 1
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


TEMPLATE = {"module": "rfi", "name": "authz-probe", "data": {}}

import aec_api.rbac as _rbac  # noqa: E402

with TestClient(app) as c:
    # The CONTROL first: if RBAC is not really on, every assertion below passes for the wrong reason.
    #
    # Assert the FLAG, not just a 403. An earlier version used `GET /admin/errors == 403` alone, which
    # is a weaker control than it looks: that route gates on `require_admin_user`, which refuses any
    # caller who is not a platform admin — and with RBAC *off* the identity is "dev", which is not a
    # platform admin either. So it returns 403 in both configurations and cannot distinguish them.
    check("CONTROL: RBAC is actually ON in this process", _rbac.RBAC_ON is True, _rbac.RBAC_ON)
    check("CONTROL: not in LOCAL_MODE (which opens the admin gates by design)",
          _rbac.LOCAL_MODE is False, _rbac.LOCAL_MODE)
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

    # ---- the /pdf/* cluster: the worst instance of the same defect ------------------------------
    # These were in `test_global_authz`'s frozen baseline too, and /pdf is not in
    # _PROTECTED_PREFIXES, so an anonymous caller reached them all. `/pdf/seal` is the one that
    # matters: it renders a Professional Engineer / Registered Architect seal, and the identity it
    # stamps comes from a caller-supplied `profile` blob. Verified end to end before the fix — an
    # unauthenticated POST returned a 2,068-byte PDF and the name, licence number and state read back
    # out of the returned document. That is a forged professional credential, not a permission slip:
    # a sealed drawing is the artefact a plan reviewer accepts and an engineer is personally liable
    # for. `seal-pe` and `seal-ra` are hidden from `GET /stamps/library`, but the repo is public, so
    # obscurity was never the control.
    #
    # A one-byte body is deliberate: authorisation must refuse before the upload is parsed, so an
    # invalid PDF must still give 403 and never 400/422.
    #
    # Read a 422 as "inconclusive, go look", NOT as "ungated". FastAPI reports request-validation
    # errors ahead of a dependency's exception, and the missing field can belong to the GATE rather
    # than the body: `require_role` on a path with no `{pid}` makes `pid` a required query parameter,
    # so `PUT /firm/rules` answered 422 to an anonymous caller while being wide open to any
    # authenticated one. A 422 was also what this very check returned when `/pdf/seal` was reverted to
    # `current_user` during a mutation test — same status, opposite meaning.
    PDF_FILES = {"file": ("probe.pdf", b"x", "application/pdf")}
    SEAL_ID = json.dumps({"name": "Not This Person, PE", "license_no": "PE-000000", "state": "NY"})

    for label, path, data in [
        ("SEAL a PDF with an arbitrary PE identity", "/pdf/seal",
         {"template_id": "seal-pe", "profile": SEAL_ID, "sign": "false", "page": "1"}),
        ("SEAL a PDF with an arbitrary RA identity", "/pdf/seal",
         {"template_id": "seal-ra", "profile": SEAL_ID, "sign": "false", "page": "1"}),
        ("STAMP a PDF", "/pdf/stamp", {"template_id": "review-ejcdc", "page": "1"}),
        ("read a PDF's structure", "/pdf/info", {}),
        ("MERGE PDFs", "/pdf/merge", {}),
        ("SPLIT a PDF", "/pdf/split", {}),
        ("EXTRACT pages from a PDF", "/pdf/extract", {"pages": "1"}),
        ("ROTATE a PDF's pages", "/pdf/rotate", {"degrees": "90"}),
    ]:
        r = c.post(path, files=PDF_FILES, data=data)
        check(f"anonymous cannot {label}", r.status_code == 403,
              f"{r.status_code} on {path} — 422 would mean the gate sits BEHIND the PDF parser")

    # The stamp catalogue is gated with them: if you cannot stamp, you cannot enumerate the templates.
    check("anonymous cannot enumerate the stamp/seal catalogue",
          c.get("/stamps/library").status_code == 403, c.get("/stamps/library").status_code)

    check("anonymous cannot READ the firm's standards library",
          c.get("/firm/rules").status_code == 403, c.get("/firm/rules").status_code)
    check("anonymous cannot REPLACE the firm's standards library",
          c.put("/firm/rules", json={"rules": []}).status_code == 403,
          c.put("/firm/rules", json={"rules": []}).status_code)

# ---- the structural invariant: a global route must not let the CALLER choose the project ----------
# `require_role(min_role)`'s dependency is `dep(pid: str, ...)`. On a path containing `{pid}` that is
# bound from the path and is correct. On a path WITHOUT `{pid}`, FastAPI has nowhere to bind it from,
# so it becomes a required *query* parameter — supplied by the caller, who thereby chooses which
# project's role is checked. `PUT /firm/rules` shipped that way and the escalation was complete.
#
# This is the check that would have caught it without anyone thinking of it, so it is the one worth
# keeping: it is a property of the schema, not a list of known-bad routes.
with TestClient(app) as c:
    _offenders = []
    for _p, _ops in sorted(app.openapi()["paths"].items()):
        if "{pid}" in _p:
            continue
        for _m, _op in _ops.items():
            for _prm in _op.get("parameters") or []:
                if _prm.get("name") == "pid" and _prm.get("in") == "query":
                    _offenders.append(f"{_m.upper()} {_p}")
    check("no global route takes a caller-supplied `pid` query parameter",
          not _offenders,
          f"{_offenders} — these gate on a project the CALLER names. Use rbac.require_platform_admin "
          f"(firm-wide writes) or rbac.require_identified (global reads) instead of require_role.")

# ---- the escalation itself, end to end -----------------------------------------------------------
# A SEPARATE client, and deliberately so: `TestClient` keeps a cookie jar, and `/auth/login` sets
# `aec_token`. Once anything logs in on a client, no later request on it is anonymous — which briefly
# made the anonymous checks above look like they were passing 200s. Any probe that mixes a login with
# an "anonymous" assertion on one client is measuring the wrong thing.
with TestClient(app) as c3:
    c3.post("/auth/register", json={"username": "boss@authz.test", "password": "Correct-Horse-9!"})
    _at = (c3.post("/auth/login", json={"username": "boss@authz.test",
                                        "password": "Correct-Horse-9!"}).json() or {}).get("token")
    # An ORDINARY account (role "user"), not the bootstrap admin. Testing this with the first account
    # in an empty DB proves nothing: that one is legitimately a platform admin by design.
    c3.post("/auth/register", json={"username": "bob@authz.test", "password": "Correct-Horse-9!",
                                    "role": "user"}, headers={"Authorization": f"Bearer {_at}"})
    _bt = (c3.post("/auth/login", json={"username": "bob@authz.test",
                                        "password": "Correct-Horse-9!"}).json() or {}).get("token")
    check("the probe actually obtained an ordinary user's token", bool(_bt), "no token — probe is inert")
    _H = {"Authorization": f"Bearer {_bt}"}
    _pid = (c3.post("/projects", json={"name": "bobs-sandbox"}, headers=_H).json() or {}).get("id")
    # Bob is admin OF HIS OWN PROJECT — that is normal and stays true. The bug was that this satisfied
    # a firm-wide gate. Verified: under `require_role("admin")` this returned 200 {"saved": 1} and
    # replaced the firm library; `save_rules` replaces, so it erased the firm's real standards too.
    _r = c3.put(f"/firm/rules?pid={_pid}", json={
        "rules": [{"id": "EVIL", "scope": {"class": "IfcWall"}, "require": {"class": "IfcWall"}}]},
        headers=_H)
    check("a project-admin cannot replace the FIRM's standards by naming their own project",
          _r.status_code == 403, f"{_r.status_code} {str(_r.json())[:90]}")

print()
if FAILED:
    print(f"global_mutating_authz: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"global_mutating_authz: all {_TOTAL} checks passed — every global route this file names "
      "refuses an anonymous caller, and the control proves RBAC was actually on.")
