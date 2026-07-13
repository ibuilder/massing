"""APS (Autodesk) RVT->IFC bridge — the feature-flag / cost-confirmation / input-validation GATES.
The paid Design-Automation conversion itself needs live credentials + a provisioned Activity and is
not exercised here; these tests lock down the gates that protect a user from an accidental (billed)
conversion and from a misconfigured bridge. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_aps.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_aps.db"
os.environ["STORAGE_DIR"] = "./test_storage_aps"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_aps.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import aps  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- engine-level gates (no network) ---------------------------------------------------------------
# Off by default (no APS_CLIENT_ID/SECRET in the test env).
assert aps.is_enabled() is False, "APS must be off without credentials"

st = aps.status()
assert st["enabled"] is False
assert "cost" in st["cost_warning"].lower()
assert "export ifc" in st["free_alternative"].lower()          # points to the free path
assert "APS_CLIENT_ID" in st["message"]                        # tells the operator what to set

# translate refuses cleanly (RuntimeError, not a silent None) when the bridge is off.
try:
    aps.translate_rvt_to_ifc(b"not-a-real-rvt", "model.rvt")
    raise AssertionError("translate should refuse when the bridge is disabled")
except RuntimeError as e:
    assert "APS" in str(e) or "configured" in str(e)

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "APS Bridge Test"}).json()["id"]

    # public status endpoint reflects the disabled bridge (what the UI checks before offering import).
    r = c.get("/bridge/rvt/status")
    assert r.status_code == 200 and r.json()["enabled"] is False, r.text

    # bridge OFF -> 501 (route the user to the free IFC export), regardless of confirm_cost.
    r = c.post(f"/projects/{pid}/import/rvt?confirm_cost=true",
               files={"file": ("model.rvt", b"rvtbytes", "application/octet-stream")})
    assert r.status_code == 501, f"expected 501 when bridge off, got {r.status_code}: {r.text[:160]}"

    # --- pretend the bridge is provisioned so the later gates are reachable (per-process monkeypatch;
    #     the router calls aps.is_enabled() at request time, so reassigning the module attr takes) ---
    aps.is_enabled = lambda: True                              # type: ignore[assignment]

    # wrong file type -> 400 BEFORE any cost is confirmed (don't bill for a file we'll reject).
    r = c.post(f"/projects/{pid}/import/rvt?confirm_cost=true",
               files={"file": ("model.ifc", b"not-rvt", "application/octet-stream")})
    assert r.status_code == 400 and "rvt" in r.json()["detail"].lower(), r.text

    # right file type but cost NOT confirmed -> 402 (explicit money gate).
    r = c.post(f"/projects/{pid}/import/rvt",
               files={"file": ("model.rvt", b"rvtbytes", "application/octet-stream")})
    assert r.status_code == 402, f"expected 402 without confirm_cost, got {r.status_code}: {r.text[:160]}"

    # empty file -> 400.
    r = c.post(f"/projects/{pid}/import/rvt?confirm_cost=true",
               files={"file": ("model.rvt", b"", "application/octet-stream")})
    assert r.status_code == 400 and "empty" in r.json()["detail"].lower(), r.text

    # confirmed + valid file, but the DA Activity is a stub -> 502 with an actionable message
    # (the real conversion runs only in a credentialed deployment; it must fail loud, not fake IFC).
    r = c.post(f"/projects/{pid}/import/rvt?confirm_cost=true",
               files={"file": ("model.rvt", b"rvtbytes", "application/octet-stream")})
    assert r.status_code == 502 and "bridge" in r.json()["detail"].lower(), r.text

print("APS OK - bridge off by default; status advertises cost + free alternative; import gates: "
      "501 (off) -> 400 (wrong type) -> 402 (unconfirmed cost) -> 400 (empty) -> 502 (stub activity, "
      "actionable). No conversion is faked without credentials.")
