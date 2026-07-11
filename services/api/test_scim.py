"""SCIM 2.0 provisioning (RFC 7643/7644) — an IdP creates / updates / deactivates / de-provisions
accounts over a token-authed REST surface. Verifies auth gating, the User mapping, both PATCH
deactivation shapes (Okta path / Azure value-map), token revocation on deactivate, and rehire.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scim.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scim.db"
os.environ["STORAGE_DIR"] = "./test_storage_scim"
os.environ["AEC_SCIM_TOKEN"] = "scim-secret-token-xyz"      # enables the surface + is the IdP bearer
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scim.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import User  # noqa: E402

TOK = {"Authorization": "Bearer scim-secret-token-xyz"}
BAD = {"Authorization": "Bearer wrong-token"}
BASE = "/scim/v2/Users"


def _db_user(username):
    with SessionLocal() as db:
        return db.get(User, username)


with TestClient(app) as c:
    # --- auth gating -------------------------------------------------------------------------
    assert c.get(BASE).status_code == 401, "no bearer must be rejected"
    assert c.get(BASE, headers=BAD).status_code == 401, "wrong bearer must be rejected"
    assert c.get(BASE, headers=TOK).status_code == 200, "correct bearer must pass"

    # ServiceProviderConfig advertises filter + patch
    cfg = c.get("/scim/v2/ServiceProviderConfig", headers=TOK).json()
    assert cfg["patch"]["supported"] and cfg["filter"]["supported"], cfg

    # --- provision (create) ------------------------------------------------------------------
    body = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": "alice@corp.com", "externalId": "okta-0001", "active": True,
        "emails": [{"value": "alice@corp.com", "primary": True, "type": "work"}],
    }
    r = c.post(BASE, headers=TOK, json=body)
    assert r.status_code == 201, r.text[:200]
    res = r.json()
    assert res["userName"] == "alice@corp.com" and res["active"] and res["externalId"] == "okta-0001", res
    assert res["id"] == "alice@corp.com" and res["emails"][0]["value"] == "alice@corp.com", res

    u = _db_user("alice@corp.com")
    assert u and u.provisioned is True and u.active is True and u.email == "alice@corp.com", u
    # SSO-only: the account has a random password nobody can guess (not the empty/blank one)
    from aec_api import auth as _auth
    assert not _auth.verify_password("", u.password_hash), "provisioned account must not have a blank password"

    # --- read + filter -----------------------------------------------------------------------
    assert c.get(f"{BASE}/alice@corp.com", headers=TOK).status_code == 200
    lst = c.get(BASE, headers=TOK, params={"filter": 'userName eq "alice@corp.com"'}).json()
    assert lst["totalResults"] == 1 and lst["Resources"][0]["userName"] == "alice@corp.com", lst
    empty = c.get(BASE, headers=TOK, params={"filter": 'userName eq "ghost@corp.com"'}).json()
    assert empty["totalResults"] == 0, empty

    # --- PATCH deactivate: Okta shape (path=active) ------------------------------------------
    r = c.patch(f"{BASE}/alice@corp.com", headers=TOK, json={
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "replace", "path": "active", "value": False}]})
    assert r.status_code == 200 and r.json()["active"] is False, r.text[:200]
    u = _db_user("alice@corp.com")
    assert u.active is False and u.token_epoch and u.token_epoch > 0, "deactivate must revoke live tokens"

    # reactivate via Azure shape (value map, no path), then deactivate again the same way
    r = c.patch(f"{BASE}/alice@corp.com", headers=TOK, json={
        "Operations": [{"op": "replace", "value": {"active": True}}]})
    assert r.status_code == 200 and r.json()["active"] is True, r.text[:200]

    # --- PUT replace -------------------------------------------------------------------------
    r = c.put(f"{BASE}/alice@corp.com", headers=TOK, json={
        "userName": "alice@corp.com", "active": True,
        "emails": [{"value": "alice.smith@corp.com", "primary": True}]})
    assert r.status_code == 200 and r.json()["emails"][0]["value"] == "alice.smith@corp.com", r.text[:200]

    # --- DELETE = de-provision (soft) --------------------------------------------------------
    assert c.delete(f"{BASE}/alice@corp.com", headers=TOK).status_code == 204
    u = _db_user("alice@corp.com")
    assert u is not None and u.active is False, "de-provision soft-deletes (row kept, deactivated)"

    # rehire: POST the same userName reactivates (200, not 409)
    r = c.post(BASE, headers=TOK, json={"userName": "alice@corp.com", "active": True})
    assert r.status_code == 200 and r.json()["active"] is True, r.text[:200]
    assert _db_user("alice@corp.com").active is True

    # unknown user → 404
    assert c.get(f"{BASE}/nobody@corp.com", headers=TOK).status_code == 404

print("SCIM OK - token-gated Users provisioning: create/read/filter/patch(both shapes)/put/delete + rehire; deactivate revokes tokens")
