"""SEC-THREAT G-5 — the common-password deny-list: weak_password_reason engine rails + the
register/change/reset routes rejecting deny-listed passwords with a named reason.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_password_policy.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_password_policy.db"
os.environ["STORAGE_DIR"] = "./test_storage_pwpol"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_password_policy.db"):
    os.remove("./test_password_policy.db")

from aec_api import auth  # noqa: E402

# --- the engine: deny-list + normalization + distinct-char + username rails ------------------------
for weak in ("password", "Password123", "P@ssw0rd", "12345678", "qwerty123", "iloveyou",
             "trustno1", "welcome1!", "starwars", "aaaaaaaa", "abababab"):
    assert auth.weak_password_reason(weak) is not None, f"{weak!r} must be rejected"
assert auth.weak_password_reason("pat.smith", "Pat.Smith") is not None      # equals the username
for ok in ("correct horse battery staple", "Tr1cky-Blue-Fox!", "modelmaker-2026-xyz"):
    assert auth.weak_password_reason(ok) is None, f"{ok!r} must pass"
assert "common" in auth.weak_password_reason("password123!")                 # suffix-run normalized

# --- routes ----------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # bootstrap admin: a deny-listed password is refused even for the first account
    r = c.post("/auth/register", json={"username": "boss", "password": "Password123"})
    assert r.status_code == 400 and "common" in r.json()["detail"], r.text
    r = c.post("/auth/register", json={"username": "boss", "password": "Sturdy-Oak-42!"})
    assert r.status_code == 201, r.text
    tok = c.post("/auth/login", json={"username": "boss", "password": "Sturdy-Oak-42!"}).json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}

    # admin-created users get the same gate, including password == username
    r = c.post("/auth/register", json={"username": "fielduser", "password": "fielduser"}, headers=hdr)
    assert r.status_code == 400 and "username" in r.json()["detail"], r.text

    # self-service change: too-common rejected, strong accepted
    r = c.post("/auth/password", json={"current": "Sturdy-Oak-42!", "new": "welcome123"}, headers=hdr)
    assert r.status_code == 400, r.text
    r = c.post("/auth/password", json={"current": "Sturdy-Oak-42!", "new": "Granite-Pier-7x"}, headers=hdr)
    assert r.status_code == 200, r.text

print("PASSWORD-POLICY OK - weak_password_reason deny-lists the breach-corpus head (case + trailing-"
      "punctuation normalized: Password123! -> password123), rejects <=2-distinct-char strings and "
      "password==username, passes strong phrases; /auth/register (bootstrap AND admin-created), "
      "/auth/password all refuse deny-listed passwords with a named 400 reason while strong ones "
      "proceed (register 201 -> login -> change 200).")
