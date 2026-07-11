"""Session revocation: a token carries an issued-at (iat); the account's token_epoch is a
watermark bumped on password change / admin reset / "sign out everywhere". Tokens issued before
the watermark are rejected immediately (not only after the 7-day expiry) — so a leaked bearer
token dies the moment the password is rotated or sessions are revoked.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sessions.py"""
import os
import time

os.environ["DATABASE_URL"] = "sqlite:///./test_sessions.db"
os.environ["STORAGE_DIR"] = "./test_storage_sessions"
os.environ["AEC_RBAC"] = "1"                   # production posture: tokens are the identity
os.environ.pop("AEC_TRUST_XUSER", None)        # don't let the dev X-User header stand in for a token
for _f in ("./test_sessions.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import auth  # noqa: E402
from aec_api.main import app  # noqa: E402

B = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


def me_ok(c, tok):
    r = c.get("/auth/me", headers=B(tok))
    return r.status_code == 200 and r.json().get("authenticated") is True


with TestClient(app) as c:
    # alice (first account → admin) logs in for a real signed token
    c.post("/auth/register", json={"username": "alice", "password": "supersecret"})
    tok1 = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()["token"]
    assert me_ok(c, tok1), "fresh token should authenticate"

    # the token carries an issued-at claim (the revocation anchor)
    claims = auth.verify_token_claims(tok1)
    assert claims and claims["sub"] == "alice" and isinstance(claims.get("iat"), int), claims
    assert auth.verify_token(tok1) == "alice"                     # back-compat accessor still works

    # --- password change revokes every other session ---------------------------
    time.sleep(1.1)   # ensure the epoch lands strictly after tok1's iat (1-second granularity)
    chg = c.post("/auth/password", headers=B(tok1),
                 json={"current": "supersecret", "new": "newpassword1"})
    assert chg.status_code == 200, chg.text
    tok2 = chg.json()["token"]                                    # fresh token keeps THIS tab in
    assert not me_ok(c, tok1), "old token must be revoked after password change"
    assert me_ok(c, tok2), "the re-issued token must still authenticate"
    # the unit-level gate also rejects the stale token (signature still valid, but epoch-revoked)
    assert c.get("/auth/me", headers=B(tok1)).status_code == 401

    # --- 'sign out everywhere' revokes all but the re-issued session -----------
    tok3 = c.post("/auth/login", json={"username": "alice", "password": "newpassword1"}).json()["token"]
    assert me_ok(c, tok3)
    time.sleep(1.1)
    out = c.post("/auth/logout-all", headers=B(tok3))
    assert out.status_code == 200, out.text
    tok4 = out.json()["token"]
    assert not me_ok(c, tok3), "logout-all must revoke prior sessions"
    assert me_ok(c, tok4), "logout-all re-issues the current session"

    # --- admin force-revoke of another user's sessions -------------------------
    c.post("/auth/users", headers=B(tok4),
           json={"username": "bob", "password": "bobpassword", "role": "user"})
    tokB = c.post("/auth/login", json={"username": "bob", "password": "bobpassword"}).json()["token"]
    assert me_ok(c, tokB)
    time.sleep(1.1)
    rev = c.post("/auth/users/bob/revoke-sessions", headers=B(tok4))
    assert rev.status_code == 200, rev.text
    assert not me_ok(c, tokB), "admin revoke-sessions must invalidate the user's live tokens"
    # bob can still sign in again (revoke != deactivate)
    tokB2 = c.post("/auth/login", json={"username": "bob", "password": "bobpassword"}).json()["token"]
    assert me_ok(c, tokB2)

    # admin reset of a password also revokes that user's sessions
    time.sleep(1.1)
    c.post("/auth/users/bob/password", headers=B(tok4), json={"password": "bobpassword2"})
    assert not me_ok(c, tokB2), "admin password reset must revoke the user's sessions"

print("SESSIONS OK - tokens carry iat; token_epoch watermark revokes pre-issue tokens on password "
      "change / logout-all / admin revoke-sessions / admin reset; re-issued token keeps the caller "
      "signed in; revoke != deactivate (user can sign in again)")
