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

    # --- enforcement is OPTIONAL — OFF by default = everything open ------------
    assert licensing.enforcement_enabled() is False, "enforcement must default OFF (no forced registration)"
    assert licensing.allows("api_access") and licensing.allows_export("nwd"), "open mode grants everything"
    assert c.get("/license").json()["enforced"] is False
    pid = c.post("/projects", json={"name": "Lic"}).json()["id"]
    # IFC download not licence-gated in open mode (no project IFC -> 409, never 402)
    assert c.get("/projects/%s/source.ifc" % pid).status_code == 409

    # --- turn enforcement ON on the Free tier -> entitlements bite ------------
    c.put("/settings/integrations", json={"values": {
        "MASSING_LICENSE_ENFORCE": "1", "MASSING_LICENSE_TIER": "free", "MASSING_LICENSE_KEY": ""}})
    assert licensing.enforcement_enabled() is True
    assert not licensing.allows("api_access") and not licensing.allows_export("ifc")
    from fastapi import HTTPException
    try:
        licensing.require("api_access")
        raise AssertionError("expected 402 when enforced + free")
    except HTTPException as e:
        assert e.status_code == 402, e.status_code
    ls = c.get("/license").json()
    assert ls["enforced"] is True and ls["tier"] == "free", ls
    assert c.get("/projects/%s/source.ifc" % pid).status_code == 402   # IFC export blocked before 409

    # --- upgrade to Commercial -> IFC export + API allowed again --------------
    c.put("/settings/integrations", json={"values": {
        "MASSING_LICENSE_KEY": "MASS-AB12-CD34-EF56-GH78", "MASSING_LICENSE_TIER": "commercial"}})
    assert licensing.allows("api_access") and licensing.allows_export("ifc")
    assert c.get("/projects/%s/source.ifc" % pid).status_code == 409   # allowed -> just no IFC yet

    # --- back to open mode (default) ------------------------------------------
    c.put("/settings/integrations", json={"values": {"MASSING_LICENSE_ENFORCE": "0"}})
    assert licensing.enforcement_enabled() is False
    assert c.get("/projects/%s/source.ifc" % pid).status_code == 409   # open again, never 402

    # --- the full key is never exposed by the settings catalog ----------------
    cat = c.get("/settings/integrations").json()
    blob = str(cat)
    assert "GH78" not in blob and "AB12" not in blob, "licence key must not be echoed in the catalog"

print("LICENSING OK - key format validated; tiers free<home<commercial<enterprise; enforcement is "
      "OPTIONAL + OFF by default (open mode grants everything, licence not required); when enabled it "
      "gates IFC export (402) + programmatic API by tier and clears on upgrade; /license reports enforced; "
      "Settings activates/rejects/masks the key and never echoes it")
