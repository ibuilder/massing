"""Massing licensing — key-format validation, per-tier feature entitlements, the /license + /capabilities
endpoints, and the Settings activation flow (record key + plan, reject malformed keys).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_licensing.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_licensing.db"
os.environ["STORAGE_DIR"] = "./test_storage_licensing"
os.environ["AEC_LOCAL_MODE"] = "1"           # single-operator: the local user is admin (Settings PUT allowed)
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_licensing.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import licensing            # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app              # noqa: E402

# --- engine: key format ------------------------------------------------------
assert licensing.valid_key_format("MASS-AB12-CD34-EF56-GH78")
assert licensing.valid_key_format("mass-ab12-cd34-ef56-gh78")     # case-insensitive
assert not licensing.valid_key_format("MASS-AB12-CD34-EF56")      # too short
assert not licensing.valid_key_format("NOPE-AB12-CD34-EF56-GH78") # wrong prefix
assert not licensing.valid_key_format("")
assert not licensing.valid_key_format(None)

# --- engine: tier features cumulative ----------------------------------------
assert licensing.allows_export("png", "home") and not licensing.allows_export("png", "free")
assert licensing.allows_export("ifc", "commercial") and not licensing.allows_export("ifc", "home")
assert licensing.allows("api_access", "commercial") and not licensing.allows("api_access", "home")
assert licensing.allows("navisworks", "enterprise") and not licensing.allows("navisworks", "commercial")
assert licensing.allows("sso", "enterprise") and not licensing.allows("sso", "commercial")
assert licensing.tier_at_least("home", "commercial") and not licensing.tier_at_least("commercial", "home")

with TestClient(app) as c:
    # --- default state: no key -> Free tier ----------------------------------
    st = c.get("/license").json()
    assert st["tier"] == "free" and st["key_configured"] is False, st
    assert st["features"]["api_access"] is False, st
    cap = c.get("/capabilities").json()
    assert cap["license_tier"] == "free", cap

    # --- activate a Commercial licence via Settings --------------------------
    bad = c.put("/settings/integrations", json={"values": {"MASSING_LICENSE_KEY": "NOT-A-KEY"}})
    assert bad.status_code == 400, bad.status_code                 # malformed key rejected
    badtier = c.put("/settings/integrations", json={"values": {"MASSING_LICENSE_TIER": "platinum"}})
    assert badtier.status_code == 400, badtier.status_code        # unknown plan rejected

    ok = c.put("/settings/integrations", json={"values": {
        "MASSING_LICENSE_KEY": "MASS-AB12-CD34-EF56-GH78", "MASSING_LICENSE_TIER": "commercial"}})
    assert ok.status_code == 200, ok.text[:200]

    st2 = c.get("/license").json()
    assert st2["tier"] == "commercial" and st2["tier_label"] == "Commercial", st2
    assert st2["key_configured"] is True and st2["key_format_valid"] is True, st2
    assert st2["key_masked"] == "MASS-****-****-****-GH78", st2    # key masked, never returned in full
    assert st2["features"]["api_access"] is True and "ifc" in st2["features"]["exports"], st2
    assert st2["features"]["navisworks"] is False, st2            # commercial < enterprise
    assert c.get("/capabilities").json()["license_tier"] == "commercial"

    # --- the full key is never exposed by the settings catalog ----------------
    cat = c.get("/settings/integrations").json()
    blob = str(cat)
    assert "GH78" not in blob and "AB12" not in blob, "licence key must not be echoed in the catalog"

print("LICENSING OK - key format validated (MASS-XXXX-XXXX-XXXX-XXXX); tiers free<home<commercial<"
      "enterprise gate exports/API/SSO/Navisworks; /license + /capabilities report tier; Settings activates "
      "a plan, rejects malformed key/plan, masks the key and never echoes it")
