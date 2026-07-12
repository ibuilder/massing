"""Capital-markets / syndication connector — package export (always on) + feature-flagged push
(ledger sync only, never moves money). Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_securities_bridge.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_securities.db"
os.environ["STORAGE_DIR"] = "./test_storage_sec"
os.environ.pop("AEC_RBAC", None)
# ensure the bridge starts DISABLED regardless of the ambient environment
for _k in ("SECURITIES_PLATFORM_URL", "SECURITIES_API_KEY", "SECURITIES_TARGET"):
    os.environ.pop(_k, None)
for _f in ("./test_securities.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import securities_bridge  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- 1. pure payload builder ---------------------------------------------------
ct = {
    "investor_count": 2, "total_commitment": 1_000_000.0, "total_contributed": 400_000.0,
    "total_distributed": 50_000.0, "total_unreturned": 350_000.0, "by_class": {"LP": 800_000.0, "GP": 200_000.0},
    "rows": [
        {"investor": "Acme Fund LP", "investor_class": "LP", "entity_type": "LP", "ref": "INV-1",
         "commitment": 800_000.0, "ownership_pct": 80.0, "contributed": 320_000.0, "distributed": 40_000.0,
         "unreturned": 280_000.0, "status": "committed"},
        {"investor": "Sponsor GP", "investor_class": "GP", "entity_type": "LLC", "ref": "INV-2",
         "commitment": 200_000.0, "ownership_pct": 20.0, "contributed": 80_000.0, "distributed": 10_000.0,
         "unreturned": 70_000.0, "status": "committed"},
    ],
}
pkg = securities_bridge.syndication_payload("Riverside Tower", ct, {"exemption": "506(c)"})
assert pkg["schema"] == "massing.syndication.v1", pkg
assert pkg["fund"]["total_commitment"] == 1_000_000.0 and pkg["fund"]["investor_count"] == 2, pkg
assert len(pkg["positions"]) == 2 and pkg["positions"][0]["external_ref"] == "INV-1", pkg
assert pkg["disclosures"]["exemption"] == "506(c)", pkg
assert "does not instruct" in pkg["disclaimer"], pkg  # money-handling guard is stated

# --- 2. status is disabled by default, and says so + confirms it never moves money -------------
st = securities_bridge.status()
assert st["enabled"] is False and st["moves_money"] is False, st
assert "not configured" in st["message"] and "never moves money" in st["message"], st

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "Riverside Tower"}).json()["id"]
    # two investors so the package has real positions
    tc.post(f"/projects/{pid}/modules/investor",
            json={"data": {"investor": "Acme Fund LP", "investor_class": "LP", "commitment": 800000, "contributed": 320000}})
    tc.post(f"/projects/{pid}/modules/investor",
            json={"data": {"investor": "Sponsor GP", "investor_class": "GP", "commitment": 200000, "contributed": 80000}})

    # --- 3. package export is available with the bridge OFF --------------------
    r = tc.get(f"/projects/{pid}/securities/package")
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["schema"] == "massing.syndication.v1" and len(body["positions"]) == 2, body
    assert body["fund"]["total_commitment"] == 1_000_000.0, body

    # --- 4. status endpoint reports disabled ----------------------------------
    s = tc.get("/securities-syndication/status").json()
    assert s["enabled"] is False and s["moves_money"] is False, s

    # --- 5. syndicate with the bridge OFF → 422 actionable, no fabricated success ----
    r = tc.post(f"/projects/{pid}/securities/syndicate")
    assert r.status_code == 422 and "SECURITIES_PLATFORM_URL" in r.json()["detail"], r.text[:200]

    # --- 6. configure the generic target + stub the transport → real push, ledger only ----
    os.environ["SECURITIES_PLATFORM_URL"] = "https://investors.example.com"
    os.environ["SECURITIES_API_KEY"] = "test-key"
    os.environ["SECURITIES_TARGET"] = "generic"
    captured = {}

    def _fake_post(url, headers, payload):
        captured["url"] = url
        captured["auth"] = headers.get("Authorization")
        captured["positions"] = len(payload.get("positions", []))
        captured["project_ref"] = payload.get("project_ref")
        return {"id": "rmt-123"}

    _orig = securities_bridge.post_json
    securities_bridge.post_json = _fake_post
    try:
        assert securities_bridge.is_enabled() is True, securities_bridge.status()
        r = tc.post(f"/projects/{pid}/securities/syndicate")
        assert r.status_code == 200, r.text[:200]
        out = r.json()
        assert out["status"] == "synced" and out["remote_id"] == "rmt-123", out
        assert out["moves_money"] is False and out["positions_pushed"] == 2, out
        assert captured["url"].endswith("/api/syndications"), captured
        assert captured["auth"] == "Bearer test-key" and captured["positions"] == 2, captured
        assert captured["project_ref"] == pid, captured
    finally:
        securities_bridge.post_json = _orig

    # --- 7. an unimplemented named target raises an actionable 422 (never fakes) ----
    os.environ["SECURITIES_TARGET"] = "securitize"
    r = tc.post(f"/projects/{pid}/securities/syndicate")
    assert r.status_code == 422 and "credentialed deployment" in r.json()["detail"], r.text[:200]

print("SECURITIES-BRIDGE OK - syndication package (cap table -> neutral investor-platform schema) exports "
      "with the bridge OFF; status/syndicate report disabled + a 422 actionable message and never fabricate "
      "success; a configured generic REST target pushes positions only (Bearer auth, /api/syndications, "
      "moves_money=False); a named target raises until wired. Ledger sync never moves money.")
