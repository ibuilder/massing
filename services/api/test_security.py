"""Production-hardening: the X-User header must NOT be trusted as identity in production (RBAC on,
no AEC_TRUST_XUSER), and the auth signing secret defaults are detectable.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_security.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_sec.db"
os.environ["STORAGE_DIR"] = "./test_storage_sec"
os.environ["AEC_RBAC"] = "1"                  # production posture
os.environ.pop("AEC_TRUST_XUSER", None)      # do NOT trust the dev impersonation header
os.environ.pop("AEC_AUTH_SECRET", None)
os.environ.pop("AEC_API_KEY", None)
for f in ("./test_sec.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import auth  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    # the public dev signing secret is detected (production must set AEC_AUTH_SECRET)
    assert auth.secret_is_default() is True, "expected default-secret detection"

    # alice signs up (first account → admin) and logs in for a real signed token
    c.post("/auth/register", json={"username": "alice", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()["token"]
    pid = c.post("/projects", json={"name": "Sec"}, headers=BEARER(tok)).json()["id"]

    # with her token, alice (project admin) can read members
    members = c.get(f"/projects/{pid}/members", headers=BEARER(tok))
    assert members.status_code == 200
    # hardening response headers are present on every response
    h = members.headers
    assert h.get("X-Content-Type-Options") == "nosniff", h
    assert h.get("X-Frame-Options") == "DENY" and "frame-ancestors" in h.get("Content-Security-Policy", ""), h

    c.cookies.clear()    # drop alice's login cookie so the next calls carry no real identity
    # an attacker tries to impersonate alice with just the X-User header (no token) → ignored in
    # production → no valid identity → denied (401 from the RBAC gate, was a spoofing hole before)
    spoof = c.get(f"/projects/{pid}/members", headers={"X-User": "alice"})
    assert spoof.status_code in (401, 403), f"X-User must not be trusted, got {spoof.status_code}"
    assert c.get(f"/projects/{pid}/members").status_code in (401, 403)   # bare request denied too

    # FAIL-CLOSED: a malformed / tampered bearer token must be REJECTED, never fall open to access.
    # (regression guard — verify_token & the RBAC gate must deny on any bad token, not error-into-allow)
    assert c.get(f"/projects/{pid}/members", headers=BEARER("garbage.token")).status_code in (401, 403)
    assert c.get(f"/projects/{pid}/members", headers=BEARER("not-even-dotted")).status_code in (401, 403)
    tampered = tok[:-2] + ("aa" if not tok.endswith("aa") else "bb")     # flip the signature bytes
    assert tampered != tok
    assert c.get(f"/projects/{pid}/members", headers=BEARER(tampered)).status_code in (401, 403), \
        "tampered token must be rejected"
    # unit-level: verify_token yields None (deny) for garbage/tampered/empty — the fail-closed contract
    assert auth.verify_token("garbage.token") is None
    assert auth.verify_token(tampered) is None
    assert auth.verify_token("") is None
    assert auth.verify_token(tok) == "alice"                             # the genuine token still works

    # RBAC defense-in-depth gate: the (otherwise un-guarded) finance + properties surfaces are NOT
    # reachable anonymously when RBAC is on — previously these had no auth dependency at all.
    assert c.get(f"/projects/{pid}/dev-budget").status_code == 401, "finance must require auth under RBAC"
    assert c.get(f"/projects/{pid}/financials").status_code == 401
    assert c.post(f"/projects/{pid}/properties/index", files={"file": ("p.json", b"{}", "application/json")}).status_code == 401
    # …but with a valid token the owner reaches them (gate passes; 200 or a clean 404 when no data)
    assert c.get(f"/projects/{pid}/dev-budget", headers=BEARER(tok)).status_code == 200

    # oversized uploads are rejected by the body-size cap (Content-Length check → 413)
    big = c.post(f"/projects/{pid}/properties/index", headers={**BEARER(tok), "Content-Length": str(99 * 1024**3)},
                 files={"file": ("p.json", b"{}", "application/json")})
    assert big.status_code == 413, f"oversized upload should be 413, got {big.status_code}"

    # the rest of the project-data surface is gated too (drawings / exports were unauthenticated before)
    assert c.get(f"/projects/{pid}/exports/qto.xlsx").status_code == 401
    assert c.get(f"/projects/{pid}/drawings/plan.svg").status_code == 401

    # the projects list is filtered to the caller's memberships (alice sees her one project)
    mine = c.get("/projects", headers=BEARER(tok)).json()
    assert isinstance(mine, list) and any(p["id"] == pid for p in mine), mine

    # login brute-force throttle: repeated bad passwords for a username get locked out (429)
    statuses = [c.post("/auth/login", json={"username": "mallory", "password": f"wrong{i}"}).status_code
                for i in range(12)]
    assert 429 in statuses, f"expected a 429 lockout after repeated failures, got {statuses}"

    # path-traversal: the storage layer rejects keys that escape the root (defense for upload keys)
    from aec_api import storage as _storage
    try:
        _storage.put("../../escape.txt", b"x"); assert False, "traversal key must be rejected"
    except ValueError:
        pass
    assert _storage.put("ok/inside.txt", b"x") == "ok/inside.txt"   # normal keys still work

    # signed/expiring URLs: a member mints one; it then authorizes the download without a session,
    # while a forged or absent signature is still blocked by the RBAC gate.
    minted = c.get(f"/projects/{pid}/model.frag/signed-url", headers=BEARER(tok))
    assert minted.status_code == 200, minted.text[:160]
    signed_url = minted.json()["url"]
    c.cookies.clear()
    assert c.get(signed_url).status_code != 401, "valid signed URL must pass the gate"   # 404 ok (no model)
    assert c.get(f"/projects/{pid}/model.frag").status_code == 401                        # no sig → blocked
    assert c.get(f"/projects/{pid}/model.frag?sig=forged&exp=9999999999").status_code == 401
    from aec_api import signing as _sig
    assert _sig.verify_path("/x", None, None) is False                 # missing sig/exp
    bad = _sig.sign_path("/x", ttl=-10)                                # already expired
    assert _sig.verify_path("/x", bad["sig"], bad["exp"]) is False
    good = _sig.sign_path("/x", ttl=60)
    assert _sig.verify_path("/x", good["sig"], good["exp"]) is True    # valid round-trip

    # liveness vs readiness: /health is shallow; /ready pings the DB and is reachable without auth
    # (probes carry no session) and reports the DB up. Orchestrator aliases resolve too.
    assert c.get("/health").json()["status"] == "ok"
    rdy = c.get("/ready")
    assert rdy.status_code == 200 and rdy.json()["db"] == "up", rdy.text[:160]
    assert c.get("/healthz").status_code == 200 and c.get("/readyz").status_code == 200

print("SECURITY OK - X-User not trusted; malformed/tampered bearer tokens fail CLOSED (verify_token->None, "
      "gate 401); hardening headers; RBAC gate blocks anonymous finance/properties/exports/drawings (401); "
      "projects list scoped to members; oversized upload -> 413; login brute-force lockout -> 429; "
      "default signing-secret detected")
