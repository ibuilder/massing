"""Optional paid Revit (.rvt)→IFC bridge — the feature-flag + cost-warning gates (no APS creds /
network needed; the gates short-circuit before any APS call).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rvt_bridge.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_rvt.db"
os.environ["STORAGE_DIR"] = "./test_storage_rvt"
os.environ["IFC_DIR"] = "./test_ifc_rvt"
os.environ.pop("AEC_RBAC", None)
for k in ("APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_DA_ACTIVITY"):
    os.environ.pop(k, None)
if os.path.exists("./test_rvt.db"):
    os.remove("./test_rvt.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

RVT = ("m.rvt", b"fake-rvt-bytes", "application/octet-stream")

with TestClient(app) as c:
    # --- bridge OFF (no credentials): status reports disabled + the free alternative -----------
    s = c.get("/bridge/rvt/status").json()
    assert s["enabled"] is False and "export IFC from Revit" in s["free_alternative"], s
    pid = c.post("/projects", json={"name": "RVT Bridge"}).json()["id"]
    r = c.post(f"/projects/{pid}/import/rvt", files={"file": RVT})
    assert r.status_code == 501 and "not configured" in r.json()["detail"].lower(), r.text   # → 501, points to free path

    # --- bridge ON (creds present) but no Design-Automation activity yet ------------------------
    os.environ["APS_CLIENT_ID"], os.environ["APS_CLIENT_SECRET"] = "dummy-id", "dummy-secret"
    assert c.get("/bridge/rvt/status").json()["enabled"] is True

    # cost gate: must confirm the paid conversion first (no APS call happens)
    r = c.post(f"/projects/{pid}/import/rvt", files={"file": RVT})
    assert r.status_code == 402 and "cost" in r.json()["detail"].lower(), r.text

    # confirmed, but the DA activity isn't provisioned → a clear, actionable 502 (still no network)
    r = c.post(f"/projects/{pid}/import/rvt?confirm_cost=true", files={"file": RVT})
    assert r.status_code == 502 and "APS_DA_ACTIVITY" in r.json()["detail"], r.text

    # with an activity set, status flips to ready (the WorkItem itself needs live APS to run)
    os.environ["APS_DA_ACTIVITY"] = "me.IfcExport+prod"
    assert c.get("/bridge/rvt/status").json()["message"].startswith("RVT→IFC bridge ready"), c.get("/bridge/rvt/status").json()

    for k in ("APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_DA_ACTIVITY"):
        os.environ.pop(k, None)

print("RVT BRIDGE OK - off->501 (free alternative); on but unconfirmed->402 cost gate; "
      "confirmed but no DA activity->502 actionable; activity set->ready")
