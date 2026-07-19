"""CLOUD-BRIDGE — massing.cloud online licence validation. Offline by default; when enabled, the
transport seam is monkeypatched (no real network in the suite) to prove the validate → normalize →
apply-tier flow, and that the shared secret is NEVER exposed by status/state.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_license_cloud.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_license_cloud.db"
os.environ["STORAGE_DIR"] = "./test_storage_license_cloud"
os.environ["AEC_LOCAL_MODE"] = "1"           # local user is admin (cloud-check is admin-gated)
os.environ.pop("AEC_RBAC", None)
# make sure no ambient env leaks into the offline-default assertions
for _k in ("MASSING_CLOUD_ONLINE", "MASSING_CLOUD_SECRET", "MASSING_CLOUD_URL",
           "MASSING_LICENSE_KEY", "MASSING_LICENSE_TIER", "MASSING_LICENSE_ENFORCE"):
    os.environ.pop(_k, None)
if os.path.exists("./test_license_cloud.db"):
    os.remove("./test_license_cloud.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import license_cloud  # noqa: E402
from aec_api.main import app  # noqa: E402

SECRET = "test-shared-secret-never-echoed"
KEY = "MASS-AB12-CD34-EF56-GH78"

# --- offline by default: no network, no-op, secret not required ------------------------------------
assert license_cloud.online_enabled() is False
st0 = license_cloud.status()
assert st0["online"] is False and st0["secret_configured"] is False, st0
assert SECRET not in str(st0)                                    # never leaks the (unset) secret
v0 = license_cloud.validate(KEY)
assert v0["checked_online"] is False and "disabled" in v0["error"], v0

# --- record the transport seam so the "network" is deterministic -----------------------------------
_calls = []


def _fake_http(url, secret, payload):
    _calls.append({"url": url, "secret": secret, "payload": payload})
    # the massing.cloud contract: echo a verdict based on the key we send
    if payload["key"] == KEY:
        return {"valid": True, "tier": "commercial", "seats": 5, "expires": "2027-01-01"}
    return {"valid": False, "reason": "unknown"}


license_cloud._http_json = _fake_http

with TestClient(app) as c:
    # enable online validation + configure the secret via Settings (admin, local mode)
    r = c.put("/settings/integrations", json={"values": {
        "MASSING_LICENSE_KEY": KEY, "MASSING_LICENSE_TIER": "free",
        "MASSING_CLOUD_ONLINE": "1", "MASSING_CLOUD_SECRET": SECRET,
        "MASSING_CLOUD_URL": "https://www.massing.cloud/wp-json/massing/v1"}})
    assert r.status_code == 200, r.text[:200]

    # the settings catalog GET must NEVER echo the secret (masked/omitted like the licence key)
    cat = c.get("/settings/integrations").json()
    assert SECRET not in str(cat), "shared secret must never be returned by the settings catalog"

    # /license now reports the cloud bridge as online, still without the secret
    lic = c.get("/license").json()
    assert lic["cloud"]["online"] is True and lic["cloud"]["secret_configured"] is True, lic["cloud"]
    assert SECRET not in str(lic)

    assert license_cloud.online_enabled() is True

    # engine: a valid key normalizes to the cloud's tier; the request carried the secret header value
    res = license_cloud.validate(KEY)
    assert res["checked_online"] is True and res["valid"] is True and res["tier"] == "commercial", res
    assert res["seats"] == 5 and res["expires"] == "2027-01-01", res
    assert _calls[-1]["secret"] == SECRET and _calls[-1]["url"].endswith("/validate"), _calls[-1]
    assert _calls[-1]["payload"]["key"] == KEY and _calls[-1]["payload"]["app"] == "massing", _calls[-1]

    # cloud-check endpoint (admin) validates + APPLIES the returned tier to Settings
    chk = c.post("/license/cloud-check").json()
    assert chk["checked_online"] and chk["valid"] and chk["applied"] is True, chk
    assert chk["tier_before"] == "free" and chk["tier_after"] == "commercial", chk
    assert c.get("/license").json()["tier"] == "commercial"     # persisted

    # a re-check when already on the right tier is a no-op apply
    chk2 = c.post("/license/cloud-check").json()
    assert chk2["valid"] and chk2["applied"] is False and chk2["tier_after"] == "commercial", chk2

    # an unknown tier in the response degrades to free (never trusts a bogus tier)
    license_cloud._http_json = lambda u, s, p: {"valid": True, "tier": "platinum"}
    assert license_cloud.validate(KEY)["tier"] == "free"

    # an explicit invalid verdict (revoked) downgrades the local tier to free
    license_cloud._http_json = lambda u, s, p: {"valid": False, "reason": "revoked"}
    dn = c.post("/license/cloud-check").json()
    assert dn["valid"] is False and dn["applied"] is True and dn["tier_after"] == "free", dn
    assert c.get("/license").json()["tier"] == "free"

    # a network error is an OFFLINE result — never raises, never downgrades a paying operator
    c.put("/settings/integrations", json={"values": {"MASSING_LICENSE_TIER": "commercial"}})

    def _boom(u, s, p):
        raise OSError("connection refused")

    license_cloud._http_json = _boom
    off = c.post("/license/cloud-check").json()
    assert off["checked_online"] is False and off["applied"] is False, off
    assert c.get("/license").json()["tier"] == "commercial", "unreachable cloud must not downgrade"

print("LICENSE-CLOUD OK - offline by default (validate is a no-op, secret never required); the shared "
      "secret is never echoed by /settings/integrations or /license; when enabled, validate() sends the "
      "X-Massing-Secret + {key,app} to {base}/validate and normalizes the verdict (unknown tier→free); "
      "the admin cloud-check applies a valid tier, downgrades on an explicit revoked verdict, and treats "
      "a network error as offline (no downgrade of a paying operator).")
