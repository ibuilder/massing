"""CLOUD-SSO / CLOUD-LIBRARY test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_massing_cloud_sso.py

Covers the massing.cloud broker integration end to end with the network stubbed at the two seams
`massing_cloud_auth` exposes (`exchange_code` / `fetch_userinfo` / `refresh_token`) and the one
`massing_cloud_vault` exposes (`call`):

  * PKCE: the verifier is sealed into a cookie and **never** appears in `state` (the property the
    whole flow rests on), the challenge is S256, and a seal is bound to its own state.
  * the callback links the account, mints a session, and maps tier + role;
  * `administrator`/`editor` on massing.cloud ⇒ platform admin here — and **losing** the role on a
    later sync drops the elevation again, which is the half a one-way mapping would leave behind;
  * the tier vocabularies do not get crossed: `commercial` is a paying plan, not `free`;
  * the library is tier-gated — a free user gets 402 naming the upgrade, not an empty list;
  * a 409 plan-limit message from the site is passed through verbatim;
  * disconnect revokes and deletes, and takes the cloud-granted elevation with it.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./cloud_sso_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_cloud_sso"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_API_KEY", None)
os.environ.pop("AEC_ADMIN_EMAILS", None)
# Enable the broker via the ENVIRONMENT, not `settings_store._cache`: the app's lifespan calls
# `settings_store.load()`, which **clears** the cache — so anything pre-seeded there is gone by the
# time the first request runs. `get()` falls back to env, which survives startup.
os.environ["MASSING_CLOUD_SSO_ENABLED"] = "1"
os.environ["MASSING_CLOUD_SITE_URL"] = "https://www.massing.cloud"
os.environ["MASSING_CLOUD_ROLE_SYNC"] = "1"
for f in ("./cloud_sso_test.db",):
    if os.path.exists(f):
        os.remove(f)

import urllib.parse  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import auth as auth_mod  # noqa: E402
from aec_api import massing_cloud_auth as cloud  # noqa: E402
from aec_api import massing_cloud_vault as vault  # noqa: E402
from aec_api import settings_store  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

# ── unit: PKCE + role/tier shaping ────────────────────────────────────────────────────────────
flow = cloud.new_flow_id()
v = cloud.verifier_for(flow)
assert 43 <= len(v) <= 128, len(v)                       # RFC 7636 §4.1
assert cloud.verifier_for(flow) == v, "derivation must be deterministic — the callback recomputes it"
assert cloud.verifier_for(cloud.new_flow_id()) != v, "different flows get different verifiers"
assert cloud.challenge_for("abc") == cloud.challenge_for("abc")
assert cloud.challenge_for("abc") != "abc"               # S256, not plain
assert "=" not in cloud.challenge_for(v)                 # base64url, unpadded

state = auth_mod.create_oauth_state("massing-cloud")
sealed = auth_mod.seal_pkce(flow, state)
assert auth_mod.open_pkce(sealed, state) == flow
assert auth_mod.open_pkce(sealed, "someone-elses-state") is None, "seal must bind to its state"
assert auth_mod.open_pkce("garbage", state) is None
# THE property the whole flow rests on: the verifier exists in NEITHER thing the browser touches.
# The seal is signed but not encrypted, so "the verifier is not in it" has to be asserted against
# the decoded bytes, not assumed from the fact that it is signed.
assert v not in sealed, "the cookie must carry an opaque flow id, never the verifier itself"
import base64 as _b64mod  # noqa: E402

_decoded = _b64mod.urlsafe_b64decode(sealed.split(".")[0] + "==").decode()
assert v not in _decoded, "the verifier must not be recoverable by decoding the cookie"
assert flow in _decoded, "...and the flow id is what IS in there"
# ...and the authorize URL carries the challenge and the state, and NOT the verifier.
url = cloud.authorize_url("http://127.0.0.1:8093/auth/cloud/callback", state, v)
assert v not in url, "the code_verifier must never travel to the broker"
q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
assert q["code_challenge_method"] == ["S256"] and q["code_challenge"] == [cloud.challenge_for(v)]
assert q["client_id"] == ["massing-desktop"] and q["response_type"] == ["code"]

# tier vocabularies must not be crossed: massing.cloud speaks free|home|commercial|enterprise.
assert cloud.normalize_tier("commercial") == "commercial", "commercial is a PAYING plan"
assert cloud.app_tier_for("commercial") == "pro" and cloud.app_tier_for("home") == "pro"
assert cloud.app_tier_for("enterprise") == "enterprise"
assert cloud.normalize_tier("platinum") == "free" and cloud.app_tier_for("platinum") == "free"
assert cloud.has_library_access("home") and cloud.has_library_access("enterprise")
assert not cloud.has_library_access("free")

assert cloud.roles_from_userinfo({"roles": ["Editor"]}) == ["editor"]
assert cloud.roles_from_userinfo({"role": "administrator,subscriber"}) == ["administrator", "subscriber"]
assert cloud.roles_from_userinfo({"tier": "pro"}) == [], "no role key ⇒ no roles"
assert cloud.is_cloud_admin(["editor"]) and cloud.is_cloud_admin(["administrator"])
assert not cloud.is_cloud_admin([]), "empty roles must fail CLOSED"
assert not cloud.is_cloud_admin(["subscriber"])

# ── stub the broker + vault ───────────────────────────────────────────────────────────────────
STATE = {"tier": "commercial", "roles": ["editor"], "exchanges": 0, "revoked": []}

cloud.exchange_code = lambda code, verifier, redirect_uri: (
    STATE.__setitem__("exchanges", STATE["exchanges"] + 1),
    STATE.__setitem__("last_verifier", verifier),
    {"access_token": "acc-1", "refresh_token": "ref-1", "expires_in": 28800},
)[-1]
cloud.fetch_userinfo = lambda token: {
    "sub": "1042", "name": "Ada Lovelace", "email": "Ada@Example.com",
    "avatar_url": "https://www.massing.cloud/wp-content/uploads/avatar-1042.jpg",
    "tier": STATE["tier"], "providers": ["google"], "roles": STATE["roles"],
}
cloud.refresh_token = lambda r: {"access_token": "acc-2", "refresh_token": "ref-2", "expires_in": 28800}
cloud.revoke_token = lambda t: STATE["revoked"].append(t)

VAULT_PROJECTS = {"user_id": 1042, "projects": [
    {"id": 123, "title": "1428 Maple Ave", "cloud_project_id": "proj_ab12",
     "status": "active", "model_count": 3, "updated": "2026-08-24T10:00:00Z", "secret_site_field": "nope"},
]}
VAULT_MODEL = {"id": 456, "title": "Scheme C", "project_id": 123, "format": "mass",
               "size_bytes": 91234, "version": 2, "cloud_model_id": "mdl_77",
               "download_url": "https://www.massing.cloud/wp-admin/admin-post.php?action=massing_vault_download&model=456&token=sig"}


def fake_call(path, token, method="GET", body=None):
    assert token in ("acc-1", "acc-2"), f"vault called with a bad token: {token}"
    if path == "/projects":
        return VAULT_PROJECTS
    if path == "/models/456":
        return VAULT_MODEL
    if path == "/models/999":
        raise vault.VaultError(409, "Vault limit reached on the Home plan (3 of 3 models).")
    raise vault.VaultError(404, "not found")


vault.call = fake_call

with TestClient(app) as c:
    # ── the authorize redirect sets the sealed cookie and points at the broker ────────────────
    r = c.get("/auth/cloud/login", follow_redirects=False)
    assert r.status_code == 307, r.text
    loc = r.headers["location"]
    assert loc.startswith("https://www.massing.cloud/massing-sso/authorize?"), loc
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    sent_state = q["state"][0]
    assert q["code_challenge_method"] == ["S256"]
    jar_seal = c.cookies.get("mc_pkce")
    assert jar_seal, "the verifier seal must be set as a cookie"
    sent_flow = auth_mod.open_pkce(jar_seal, sent_state)
    assert sent_flow, "the cookie must seal a flow id"
    real_verifier = cloud.verifier_for(sent_flow)
    assert real_verifier not in loc, "verifier must not be in the authorize URL"
    assert real_verifier not in jar_seal, "...nor recoverable from the cookie"

    # a callback whose state does not match the seal is refused (CSRF / mix-up)
    bad = c.get("/auth/cloud/callback", params={"code": "abc", "state": "forged"},
                follow_redirects=False)
    assert bad.status_code == 400, bad.text

    # ── the real callback links the account and signs the user in ────────────────────────────
    r = c.get("/auth/cloud/callback", params={"code": "the-code", "state": sent_state},
              follow_redirects=False)
    assert r.status_code == 303, r.text
    assert STATE["exchanges"] == 1
    assert STATE["last_verifier"] == real_verifier, "the DERIVED verifier is what gets exchanged"
    tok = c.cookies.get("aec_token")
    assert tok, "the callback must mint an app session"

    me = c.get("/auth/me", headers=BEARER(tok)).json()
    assert me["authenticated"] and me["username"] == "ada@example.com", me
    assert me["display_name"] == "Ada Lovelace", me
    assert me["avatar_url"].endswith("avatar-1042.jpg"), me
    # editor on massing.cloud ⇒ admin here
    assert me["role"] == "admin" and me["platform_admin"] is True, me
    # commercial ⇒ a paid entitlement tier, NOT free
    assert me["tier"] == "pro", me
    assert me["cloud"]["linked"] is True and me["cloud"]["library_access"] is True, me

    st = c.get("/auth/cloud/status", headers=BEARER(tok)).json()
    assert st["linked"] and st["tier"] == "commercial" and st["tier_label"] == "Commercial", st
    assert st["is_admin"] is True and st["library_access"] is True, st
    assert "access_token" not in st and "refresh_token" not in st, "status must never leak a token"

    # ── the library ──────────────────────────────────────────────────────────────────────────
    lib = c.get("/cloud/library/projects", headers=BEARER(tok))
    assert lib.status_code == 200, lib.text
    projects = lib.json()["projects"]
    assert len(projects) == 1 and projects[0]["title"] == "1428 Maple Ave", projects
    assert "secret_site_field" not in projects[0], "unknown site keys must not be forwarded"

    m = c.get("/cloud/library/models/456", headers=BEARER(tok))
    assert m.status_code == 200 and "download_url" in m.json(), m.text

    # a site-side plan limit is surfaced verbatim, with its own status
    lim = c.get("/cloud/library/models/999", headers=BEARER(tok))
    assert lim.status_code == 409 and "3 of 3 models" in lim.text, lim.text

    # ── losing the cloud role drops the elevation (the half a one-way map would miss) ─────────
    STATE["roles"] = ["subscriber"]
    STATE["tier"] = "free"
    r = c.post("/auth/cloud/refresh", headers=BEARER(tok))
    assert r.status_code == 200, r.text
    me2 = c.get("/auth/me", headers=BEARER(tok)).json()
    assert me2["role"] == "user" and me2["platform_admin"] is False, me2
    assert me2["tier"] == "free", me2

    # ...and a free account is refused the library with an upgrade pointer, not an empty list
    lib2 = c.get("/cloud/library/projects", headers=BEARER(tok))
    assert lib2.status_code == 402, lib2.text
    assert "/pricing/" in lib2.text, lib2.text

    # ── disconnect revokes at the broker and deletes the link ────────────────────────────────
    d = c.post("/auth/cloud/disconnect", headers=BEARER(tok))
    assert d.status_code == 200 and d.json()["linked"] is False, d.text
    assert "acc-1" in STATE["revoked"] or "acc-2" in STATE["revoked"], STATE["revoked"]
    st2 = c.get("/auth/cloud/status", headers=BEARER(tok)).json()
    assert st2["linked"] is False, st2
    # the library is gone with the link, and says so as "not linked" rather than "not entitled"
    assert c.get("/cloud/library/projects", headers=BEARER(tok)).status_code == 403

    # ── PROVENANCE OF THE ADMIN BIT: promote freely, demote only what this path granted ───────
    # Three lockouts came from not recording where the admin bit came from, all reproduced first:
    # a first link demoted a pre-existing local admin; a first-link-only guard merely DELAYED that
    # to the second sign-in; and `disconnect` demoted them on the way out. `/auth/cloud/refresh`
    # had it too. All four are asserted below, in BOTH directions — asserting only "never demotes"
    # would pass on a build with role sync switched off entirely, which is the refusal-test trap.
    from aec_api.db import SessionLocal             # noqa: E402
    from aec_api.models import CloudIdentity, User  # noqa: E402

    def role_of(name):
        with SessionLocal() as s:
            u = s.get(User, name)
            return u.role if u else None

    def cloud_signin(nonce):
        lg = c.get("/auth/cloud/login", follow_redirects=False)
        st = urllib.parse.parse_qs(urllib.parse.urlparse(lg.headers["location"]).query)["state"][0]
        r = c.get("/auth/cloud/callback", params={"code": nonce, "state": st}, follow_redirects=False)
        assert r.status_code == 303, r.text

    # (A) a PRE-EXISTING LOCAL admin, against a broker that publishes no roles (today's live shape)
    STATE["roles"], STATE["tier"] = [], "commercial"
    with SessionLocal() as s:
        s.add(User(username="boss@example.com", password_hash="x", role="admin", active=True))
        s.commit()
    cloud.fetch_userinfo = lambda token: {
        "sub": "9001", "name": "Boss", "email": "boss@example.com",
        "tier": STATE["tier"], "providers": [], "roles": STATE["roles"]}
    c.cookies.clear()
    cloud_signin("a1")
    assert role_of("boss@example.com") == "admin", "a FIRST link must not demote a local admin"
    with SessionLocal() as s:
        assert s.get(CloudIdentity, "boss@example.com").local_admin_at_link is True
    cloud_signin("a2")
    assert role_of("boss@example.com") == "admin", "...nor may the SECOND sign-in"
    boss_tok = c.cookies.get("aec_token")
    assert c.post("/auth/cloud/refresh", headers=BEARER(boss_tok)).status_code == 200
    assert role_of("boss@example.com") == "admin", "...nor may an explicit Refresh"
    assert c.post("/auth/cloud/disconnect", headers=BEARER(boss_tok)).status_code == 200
    assert role_of("boss@example.com") == "admin", "...nor may Disconnect"

    # (B) an account elevated BY the cloud — the demotions that must still happen
    with SessionLocal() as s:
        s.add(User(username="chief@example.com", password_hash="x", role="user", active=True))
        s.commit()
    STATE["roles"] = ["administrator"]
    cloud.fetch_userinfo = lambda token: {
        "sub": "9002", "name": "Chief", "email": "chief@example.com",
        "tier": "commercial", "providers": [], "roles": STATE["roles"]}
    c.cookies.clear()
    cloud_signin("b1")
    assert role_of("chief@example.com") == "admin", "a first link SHOULD promote a cloud admin"
    with SessionLocal() as s:
        assert s.get(CloudIdentity, "chief@example.com").local_admin_at_link is False
    STATE["roles"] = ["subscriber"]                 # the site revokes the role
    cloud_signin("b2")
    assert role_of("chief@example.com") == "user",         "losing the cloud role MUST drop a cloud-granted elevation"

    # ...and disconnect strips a cloud-granted elevation too
    STATE["roles"] = ["administrator"]
    c.cookies.clear()
    cloud_signin("b3")
    assert role_of("chief@example.com") == "admin"
    chief_tok = c.cookies.get("aec_token")
    assert c.post("/auth/cloud/disconnect", headers=BEARER(chief_tok)).status_code == 200
    assert role_of("chief@example.com") == "user",         "disconnect MUST strip an elevation this path granted"

    # ── AEC_OAUTH_ALLOWED_DOMAINS applies to THIS door too ───────────────────────────────────
    # It did not originally. The flag reads as if it were scoped to the four direct IdPs, so this
    # path was written from that callback without carrying it — an operator who had restricted
    # sign-in to their own domain got it enforced on four doors and bypassed by the fifth. A control
    # that is true for four paths and false for the fifth is worse than none, because it is believed.
    os.environ["AEC_OAUTH_ALLOWED_DOMAINS"] = "acme.com"
    try:
        cloud.fetch_userinfo = lambda token: {
            "sub": "9100", "name": "Outsider", "email": "someone@evil.example",
            "tier": "commercial", "providers": [], "roles": []}
        c.cookies.clear()
        lg = c.get("/auth/cloud/login", follow_redirects=False)
        st5 = urllib.parse.parse_qs(urllib.parse.urlparse(lg.headers["location"]).query)["state"][0]
        r = c.get("/auth/cloud/callback", params={"code": "d1", "state": st5}, follow_redirects=False)
        assert r.status_code == 403 and "domain is not permitted" in r.text, r.text
        assert role_of("someone@evil.example") is None, "...and no account was provisioned"

        # ...and the twin: an ALLOWED domain still gets in, or "it refuses" is satisfied by a door
        # that refuses everyone.
        cloud.fetch_userinfo = lambda token: {
            "sub": "9101", "name": "Insider", "email": "someone@acme.com",
            "tier": "commercial", "providers": [], "roles": []}
        c.cookies.clear()
        lg = c.get("/auth/cloud/login", follow_redirects=False)
        st6 = urllib.parse.parse_qs(urllib.parse.urlparse(lg.headers["location"]).query)["state"][0]
        r = c.get("/auth/cloud/callback", params={"code": "d2", "state": st6}, follow_redirects=False)
        assert r.status_code == 303, r.text
        assert role_of("someone@acme.com") == "user"
    finally:
        os.environ.pop("AEC_OAUTH_ALLOWED_DOMAINS", None)

    # ── the feature is off by default: no flag ⇒ the routes are not there at all ─────────────
    settings_store._cache["MASSING_CLOUD_SSO_ENABLED"] = "0"
    assert c.get("/auth/cloud/login", follow_redirects=False).status_code == 404
    settings_store._cache["MASSING_CLOUD_SSO_ENABLED"] = "1"

print("massing.cloud SSO + library: OK")
