"""Auth + user-management test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_auth.py

Covers token + cookie identity, the admin bootstrap, admin user management (create / list /
role / (de)activate / password reset), self-service password change, the last-admin guard,
and that deactivation revokes both new logins and existing tokens."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./auth_test.db"
os.environ["STORAGE_DIR"] = "./test_storage"
os.environ.pop("AEC_RBAC", None)          # user management is independent of project RBAC
os.environ.pop("AEC_API_KEY", None)
for f in ("./auth_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    # --- bootstrap: the first registered account becomes admin -----------------
    r = c.post("/auth/register", json={"username": "admin", "password": "supersecret"})
    assert r.status_code == 201 and r.json()["role"] == "admin", r.text

    admin_tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]

    # cookie-only identity (the SSE / direct-download path that can't send a header)
    c.cookies.clear()
    login = c.post("/auth/login", json={"username": "admin", "password": "supersecret"})
    assert login.status_code == 200
    me = c.get("/auth/me")                 # no Authorization header → cookie carries it
    mj = me.json()
    assert (mj["username"], mj["role"], mj["authenticated"]) == ("admin", "admin", True), me.text
    assert mj["tier"] == "free" and mj["platform_admin"] is True, mj   # legacy admin role → platform admin
    c.cookies.clear()

    # --- admin creates a regular user -----------------------------------------
    r = c.post("/auth/users", json={"username": "bob", "password": "bobspassword"}, headers=BEARER(admin_tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "bob" and body["role"] == "user" and body["active"] is True, body
    bob_tok = c.post("/auth/login", json={"username": "bob", "password": "bobspassword"}).json()["token"]
    c.cookies.clear()

    # non-admin cannot list or manage users
    assert c.get("/auth/users", headers=BEARER(bob_tok)).status_code == 403
    assert c.post("/auth/users", json={"username": "x", "password": "yyyyyyyy"},
                  headers=BEARER(bob_tok)).status_code == 403

    # admin can list — sees both accounts
    users = {u["username"]: u for u in c.get("/auth/users", headers=BEARER(admin_tok)).json()}
    assert set(users) == {"admin", "bob"} and users["bob"]["role"] == "user", users

    # short passwords rejected
    assert c.post("/auth/users", json={"username": "z", "password": "short"},
                  headers=BEARER(admin_tok)).status_code == 400
    # duplicate username rejected
    assert c.post("/auth/users", json={"username": "bob", "password": "bobspassword"},
                  headers=BEARER(admin_tok)).status_code == 409

    # --- self-service password change -----------------------------------------
    assert c.post("/auth/password", json={"current": "wrong", "new": "newbobpass"},
                  headers=BEARER(bob_tok)).status_code == 403
    assert c.post("/auth/password", json={"current": "bobspassword", "new": "newbobpass"},
                  headers=BEARER(bob_tok)).status_code == 200
    assert c.post("/auth/login", json={"username": "bob", "password": "bobspassword"}).status_code == 401
    assert c.post("/auth/login", json={"username": "bob", "password": "newbobpass"}).status_code == 200
    c.cookies.clear()

    # --- admin password reset --------------------------------------------------
    assert c.post("/auth/users/bob/password", json={"password": "resetbobpass"},
                  headers=BEARER(admin_tok)).status_code == 200
    assert c.post("/auth/login", json={"username": "bob", "password": "resetbobpass"}).status_code == 200
    c.cookies.clear()

    # --- deactivation revokes new logins AND existing tokens -------------------
    assert c.patch("/auth/users/bob", json={"active": False}, headers=BEARER(admin_tok)).status_code == 200
    assert c.post("/auth/login", json={"username": "bob", "password": "resetbobpass"}).status_code == 403
    assert c.get("/auth/me", headers=BEARER(bob_tok)).status_code == 401   # token stops authenticating
    c.cookies.clear()
    # reactivate
    assert c.patch("/auth/users/bob", json={"active": True}, headers=BEARER(admin_tok)).status_code == 200
    assert c.post("/auth/login", json={"username": "bob", "password": "resetbobpass"}).status_code == 200
    c.cookies.clear()

    # --- admin-issued reset token (self-service password set, no email) --------
    tok = c.post("/auth/users/bob/reset-token", headers=BEARER(admin_tok)).json()["reset_token"]
    # a reset token must NOT work as a bearer token (purpose-separated)
    assert c.get("/auth/me", headers=BEARER(tok)).json()["authenticated"] is False
    # too-short new password rejected
    assert c.post("/auth/reset", json={"token": tok, "new": "short"}).status_code == 400
    # consume the token → new password works
    assert c.post("/auth/reset", json={"token": tok, "new": "brandnewpass"}).status_code == 200
    _bob = c.post("/auth/login", json={"username": "bob", "password": "brandnewpass"})
    assert _bob.status_code == 200
    bob_tok = _bob.json()["token"]   # refresh: every password change/reset revokes bob's prior sessions
    c.cookies.clear()
    # single-use: the same token no longer validates (password hash changed)
    assert c.post("/auth/reset", json={"token": tok, "new": "anotherpass1"}).status_code == 403
    # a garbage token is rejected
    assert c.post("/auth/reset", json={"token": "not.a.token", "new": "whatever8"}).status_code == 403

    # --- audit log: admin actions are recorded + readable ----------------------
    assert c.get("/audit", headers=BEARER(bob_tok)).status_code == 403   # non-admin can't read
    audit = c.get("/audit", headers=BEARER(admin_tok)).json()
    actions = {a["action"] for a in audit}
    assert {"user.create", "user.update", "user.password_reset"} <= actions, actions
    # newest-first ordering + actor recorded
    assert all(a["actor"] == "admin" for a in audit if a["action"].startswith("user."))
    create_rows = c.get("/audit", params={"action": "user.create"}, headers=BEARER(admin_tok)).json()
    assert create_rows and all(a["action"] == "user.create" for a in create_rows)
    assert any(a["detail"].get("username") == "bob" for a in create_rows)
    assert c.get("/audit", params={"since": "not-a-date"}, headers=BEARER(admin_tok)).status_code == 400

    # --- email field + mailer (no-op when SMTP unconfigured) -------------------
    assert c.patch("/auth/users/bob", json={"email": "bob@example.com"},
                   headers=BEARER(admin_tok)).json()["email"] == "bob@example.com"
    from aec_api import mailer  # noqa: E402
    assert mailer.smtp_configured() is False                         # no AEC_SMTP_HOST in tests
    assert mailer.send_email("x@example.com", "Hi", "body") == "disabled"   # no-op, doesn't raise
    m = mailer.build_message("x@example.com", "Subj", "text body", "<p>html</p>")
    assert m["To"] == "x@example.com" and m["Subject"] == "Subj" and m.is_multipart()

    # --- admin: integration settings (API keys; secrets write-only) ------------
    from aec_api import ai, settings_store  # noqa: E402
    assert c.get("/settings/integrations", headers=BEARER(bob_tok)).status_code == 403   # non-admin
    groups = c.get("/settings/integrations", headers=BEARER(admin_tok)).json()["groups"]
    flat = {k["key"]: k for grp in groups for k in grp["keys"]}
    assert flat["ANTHROPIC_API_KEY"]["secret"] and "value" not in flat["ANTHROPIC_API_KEY"]   # secret hidden
    assert flat["AEC_AI_MODEL"]["secret"] is False and "value" in flat["AEC_AI_MODEL"]        # non-secret shown
    assert flat["ANTHROPIC_API_KEY"]["configured"] is False and ai.ai_enabled() is False
    # set the key via the admin API → AI enables; the secret is never echoed back
    r = c.put("/settings/integrations", headers=BEARER(admin_tok),
              json={"values": {"ANTHROPIC_API_KEY": "sk-test-123"}}).json()
    flat2 = {k["key"]: k for grp in r["groups"] for k in grp["keys"]}
    assert flat2["ANTHROPIC_API_KEY"]["configured"] is True and "value" not in flat2["ANTHROPIC_API_KEY"]
    assert ai.ai_enabled() is True and settings_store.get("ANTHROPIC_API_KEY") == "sk-test-123"
    assert c.put("/settings/integrations", headers=BEARER(admin_tok),
                 json={"values": {"BOGUS": "x"}}).status_code == 400                          # unknown key
    c.put("/settings/integrations", headers=BEARER(admin_tok), json={"values": {"ANTHROPIC_API_KEY": ""}})
    assert ai.ai_enabled() is False                                                           # cleared

    # --- last-admin guard ------------------------------------------------------
    assert c.patch("/auth/users/admin", json={"active": False}, headers=BEARER(admin_tok)).status_code == 400
    assert c.patch("/auth/users/admin", json={"role": "user"}, headers=BEARER(admin_tok)).status_code == 400
    # promote bob to admin, then the first admin can be demoted
    assert c.patch("/auth/users/bob", json={"role": "admin"}, headers=BEARER(admin_tok)).status_code == 200
    assert c.patch("/auth/users/admin", json={"role": "user"}, headers=BEARER(admin_tok)).status_code == 200

    # --- SSO / OAuth (Google/Microsoft/Procore) --------------------------------
    from aec_api import auth as _auth, oauth  # noqa: E402
    assert c.get("/auth/providers").json()["providers"] == []          # none configured
    assert c.get("/auth/oauth/google/login", follow_redirects=False).status_code == 404
    os.environ["AEC_OAUTH_GOOGLE_CLIENT_ID"] = "cid"
    os.environ["AEC_OAUTH_GOOGLE_CLIENT_SECRET"] = "secret"
    assert {"id": "google", "label": "Google"} in c.get("/auth/providers").json()["providers"]
    lg = c.get("/auth/oauth/google/login", follow_redirects=False)
    assert lg.status_code == 307 and "accounts.google.com" in lg.headers["location"], lg.headers.get("location")
    # bad state is rejected
    assert c.get("/auth/oauth/google/callback", params={"code": "x", "state": "bad"},
                 follow_redirects=False).status_code == 400
    # stub the provider exchange + drive the callback → account created, session minted
    oauth.exchange_code = lambda p, code, ru: {"access_token": "tok"}
    oauth.fetch_userinfo = lambda p, t: {"email": "Sso.User@Example.com"}
    cb = c.get("/auth/oauth/google/callback",
               params={"code": "abc", "state": _auth.create_oauth_state("google")}, follow_redirects=False)
    assert cb.status_code == 303 and cb.cookies.get("aec_token"), cb.status_code
    who = c.get("/auth/me").json()                                     # cookie carries identity
    assert who["username"] == "sso.user@example.com" and who["authenticated"], who
    assert who["role"] == "user"                                       # not bootstrap (users exist)
    c.cookies.clear()

    print("AUTH OK — token+cookie identity, admin user mgmt, self password change, "
          "deactivation revokes tokens, last-admin guard, reset token, audit, email/mailer, SSO")
