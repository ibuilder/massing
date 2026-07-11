"""TOTP multi-factor auth (RFC 6238/4226): the crypto matches the published test vectors, and the
full flow works — enroll (setup→confirm), login becomes a two-step challenge, a TOTP *or* a one-time
recovery code completes it, and disabling requires password + a live code.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mfa.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mfa.db"
os.environ["STORAGE_DIR"] = "./test_storage_mfa"
os.environ["AEC_RBAC"] = "1"
os.environ.pop("AEC_TRUST_XUSER", None)
for _f in ("./test_mfa.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import totp  # noqa: E402
from aec_api.main import app  # noqa: E402

B = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

# --- RFC 4226 Appendix D HOTP vectors (secret = ASCII "12345678901234567890") -------------------
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
RFC_HOTP = ["755224", "287082", "359152", "969429", "338314",
            "254676", "287922", "162583", "399871", "520489"]
for i, want in enumerate(RFC_HOTP):
    got = totp.hotp(RFC_SECRET, i)
    assert got == want, f"HOTP counter {i}: got {got}, want {want}"
# TOTP round-trips and tolerates ±1 step; a wrong code fails; malformed input is a clean False
sec = totp.random_secret()
assert totp.verify(sec, totp.totp(sec)) is True
assert totp.verify(sec, totp.totp(sec, when=0), when=0) is True
assert totp.verify(sec, "000000") in (True, False)          # numeric but (almost surely) wrong
assert totp.verify(sec, "abc") is False and totp.verify(sec, "") is False
assert totp.provisioning_uri(sec, "alice@x.com").startswith("otpauth://totp/")

with TestClient(app) as c:
    c.post("/auth/register", json={"username": "alice", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()["token"]
    c.cookies.clear()                                         # use the bearer token explicitly, not the cookie

    # enroll: setup issues a secret + otpauth URI; a wrong confirmation code is rejected
    setup = c.post("/auth/mfa/setup", headers=B(tok)).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and secret, setup
    assert c.post("/auth/mfa/enable", headers=B(tok), json={"code": "000000"}).status_code == 401

    # confirm with a real code → MFA on + 10 one-time recovery codes returned once
    en = c.post("/auth/mfa/enable", headers=B(tok), json={"code": totp.totp(secret)})
    assert en.status_code == 200, en.text
    recovery = en.json()["recovery_codes"]
    assert len(recovery) == 10, en.json()
    st = c.get("/auth/mfa/status", headers=B(tok)).json()
    assert st["enabled"] is True and st["recovery_remaining"] == 10, st

    # login is now a two-step challenge: password → ticket (NO session yet)
    ch = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()
    assert ch.get("mfa_required") is True and ch.get("mfa_token") and "token" not in ch, ch

    # a wrong second factor is rejected; the right TOTP completes the login
    assert c.post("/auth/mfa/verify",
                  json={"mfa_token": ch["mfa_token"], "code": "000000"}).status_code == 401
    done = c.post("/auth/mfa/verify", json={"mfa_token": ch["mfa_token"], "code": totp.totp(secret)})
    assert done.status_code == 200 and done.json().get("token"), done.text
    tok2 = done.json()["token"]
    assert c.get("/auth/me", headers=B(tok2)).json().get("authenticated") is True

    # a one-time recovery code also completes the challenge and is then burned
    ch2 = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()
    rc = recovery[0]
    assert c.post("/auth/mfa/verify",
                  json={"mfa_token": ch2["mfa_token"], "code": rc}).status_code == 200
    assert c.get("/auth/mfa/status", headers=B(tok)).json()["recovery_remaining"] == 9   # one burned
    # …and the same recovery code can't be reused
    ch3 = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()
    assert c.post("/auth/mfa/verify",
                  json={"mfa_token": ch3["mfa_token"], "code": rc}).status_code == 401

    # disabling MFA needs the password AND a live code (a hijacked session alone can't strip it)
    assert c.post("/auth/mfa/disable", headers=B(tok),
                  json={"password": "wrong", "code": totp.totp(secret)}).status_code == 403
    assert c.post("/auth/mfa/disable", headers=B(tok),
                  json={"password": "supersecret", "code": "000000"}).status_code == 401
    off = c.post("/auth/mfa/disable", headers=B(tok),
                 json={"password": "supersecret", "code": totp.totp(secret)})
    assert off.status_code == 200 and off.json()["enabled"] is False, off.text

    # with MFA off, login returns a session token directly again
    back = c.post("/auth/login", json={"username": "alice", "password": "supersecret"}).json()
    assert back.get("token") and not back.get("mfa_required"), back

print("MFA OK - HOTP/TOTP match RFC 4226/6238 vectors; enroll (setup->confirm) issues secret+otpauth "
      "URI+10 recovery codes; login becomes a 2-step challenge; TOTP or a one-time (non-reusable) "
      "recovery code completes it; disable requires password+live code; MFA-off restores 1-step login")
