"""SSO (OAuth) login + free-tier + ops-only platform admin.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sso.py

Covers: providers list reflects configured creds; the OAuth callback (driven through the
exchange/userinfo test seams) creates a plain free-tier user — NOT an admin; /auth/me reports
tier + features; platform-admin is ops-only via AEC_ADMIN_EMAILS (no end-user admin tier)."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./sso_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_sso"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_API_KEY", None)
os.environ.pop("AEC_LOCAL_MODE", None)
# enable Google + Microsoft by configuring (fake) creds; Procore left unconfigured
os.environ["AEC_OAUTH_GOOGLE_CLIENT_ID"] = "gid"
os.environ["AEC_OAUTH_GOOGLE_CLIENT_SECRET"] = "gsecret"
os.environ["AEC_OAUTH_MICROSOFT_CLIENT_ID"] = "mid"
os.environ["AEC_OAUTH_MICROSOFT_CLIENT_SECRET"] = "msecret"
os.environ.pop("AEC_OAUTH_PROCORE_CLIENT_ID", None)
os.environ.pop("AEC_ADMIN_EMAILS", None)
for f in ("./sso_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import auth, oauth  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # --- providers list: enabled = those with creds (google, microsoft; not procore) ---------
    provs = {p["id"] for p in c.get("/auth/providers").json()["providers"]}
    assert provs == {"google", "microsoft"}, provs

    # --- drive the callback through the test seams (no real provider) -------------------------
    oauth.exchange_code = lambda provider, code, redirect_uri: {"access_token": "fake"}
    oauth.fetch_userinfo = lambda provider, token: {"email": "Alice@Example.com"}

    state = auth.create_oauth_state("google")
    r = c.get(f"/auth/oauth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 303, (r.status_code, r.text)
    assert "aec_token" in r.cookies, r.headers

    # the account exists, is a plain free-tier USER (not admin), email normalized lower-case
    me = c.get("/auth/me").json()          # TestClient carries the Set-Cookie automatically
    assert me["username"] == "alice@example.com", me
    assert me["authenticated"] is True and me["role"] == "user", me
    assert me["tier"] == "free" and me["features"]["viewer"] is True, me
    assert me["platform_admin"] is False, me        # SSO users are never platform admins

    # --- a second SSO user is also a plain user (no first-account-admin bootstrap) ------------
    oauth.fetch_userinfo = lambda provider, token: {"email": "bob@example.com"}
    c.cookies.clear()
    state2 = auth.create_oauth_state("microsoft")
    oauth.exchange_code = lambda provider, code, redirect_uri: {"access_token": "fake2"}
    r2 = c.get(f"/auth/oauth/microsoft/callback?code=xyz&state={state2}", follow_redirects=False)
    assert r2.status_code == 303
    assert c.get("/auth/me").json()["role"] == "user"

    # --- bad state is rejected (CSRF) --------------------------------------------------------
    bad = c.get("/auth/oauth/google/callback?code=abc&state=tampered", follow_redirects=False)
    assert bad.status_code == 400, bad.text

    # --- a disabled provider 404s ------------------------------------------------------------
    assert c.get("/auth/oauth/procore/login", follow_redirects=False).status_code == 404

    # --- platform admin is ops-only via AEC_ADMIN_EMAILS ------------------------------------
    # alice is a normal user -> can't touch platform settings
    c.cookies.clear()
    st3 = auth.create_oauth_state("google")
    oauth.exchange_code = lambda provider, code, redirect_uri: {"access_token": "fake"}
    oauth.fetch_userinfo = lambda provider, token: {"email": "alice@example.com"}
    c.get(f"/auth/oauth/google/callback?code=abc&state={st3}", follow_redirects=False)
    assert c.get("/auth/users").status_code == 403, "regular SSO user must not access user admin"
    # promote via the ops env allowlist -> now platform admin
    os.environ["AEC_ADMIN_EMAILS"] = "alice@example.com"
    assert c.get("/auth/me").json()["platform_admin"] is True
    assert c.get("/auth/users").status_code == 200, "AEC_ADMIN_EMAILS should grant platform admin"
    os.environ.pop("AEC_ADMIN_EMAILS", None)

print("SSO OK - providers reflect creds; callback makes plain free-tier users (no admin "
      "bootstrap); bad-state rejected; platform admin is ops-only via AEC_ADMIN_EMAILS")
