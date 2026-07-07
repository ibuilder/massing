"""Field AI (Phase E): labor productivity analytics (E1) + the feature-flagged CV progress bridge (E2).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_field_ai.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_field_ai.db"
os.environ["STORAGE_DIR"] = "./test_storage_field_ai"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_CV_BRIDGE", None)          # bridge off by default
for _f in ("./test_field_ai.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import cv_bridge, reports  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- E1: labor productivity ------------------------------------------------------------------
    def log(data):
        r = c.post(f"/projects/{pid}/modules/productivity_log", json={"data": data})
        assert r.status_code == 201, r.text[:160]

    log({"date": "2026-03-02", "activity": "SOG pour", "trade": "Concrete",
         "quantity": 120, "unit": "cy", "workers": 6, "hours": 8})     # 120 / 48 mh = 2.5 cy/mh
    log({"date": "2026-03-03", "activity": "SOG pour", "trade": "Concrete",
         "quantity": 90, "unit": "cy", "workers": 6, "hours": 8})      # 90 / 48 mh = 1.875 cy/mh
    log({"date": "2026-03-02", "activity": "Layout", "trade": "Carpentry"})  # no production -> excluded

    s = c.get(f"/projects/{pid}/productivity/summary").json()
    assert s["count"] == 3, s
    conc = next(t for t in s["by_trade"] if t["trade"] == "Concrete")
    assert conc["quantity"] == 210.0 and conc["man_hours"] == 96.0, conc
    assert conc["units_per_manhour"] == round(210 / 96, 3), conc          # ~2.188 cy/man-hr
    assert {t["trade"] for t in s["by_trade"]} == {"Concrete"}, s["by_trade"]   # carpentry has no man-hrs

    rep = c.get(f"/projects/{pid}/reports/productivity.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code
    assert "productivity" in {x["id"] for x in reports.catalog()}

    # --- E2: CV progress bridge is off by default; ingest is a no-op -----------------------------
    st = c.get(f"/projects/{pid}/cv-progress/status").json()
    assert st["enabled"] is False and st["feature"] == "cv_progress_bridge", st
    ing = c.post(f"/projects/{pid}/cv-progress/ingest",
                 json={"activity": "A1", "percent": 65, "source": "vision-svc"}).json()
    assert ing["accepted"] is False, ing                                 # nothing fabricated when disabled

# --- E2 engine: when the operator enables the flag, estimates are accepted (clamped) --------------
os.environ["AEC_CV_BRIDGE"] = "1"
assert cv_bridge.enabled() is True
acc = cv_bridge.ingest({"activity": "A1", "percent": 140, "source": "vision-svc"})
assert acc["accepted"] is True and acc["percent"] == 100.0, acc          # clamped to 0–100
os.environ.pop("AEC_CV_BRIDGE", None)

print("FIELD AI OK - E1: productivity log -> units/man-hr per entry + by-trade rollup (Concrete "
      "210 cy / 96 mh = 2.188 cy/man-hr; no-production entry excluded); report PDF served. E2: CV "
      "bridge disabled by default (ingest = no-op, nothing fabricated); enabling AEC_CV_BRIDGE accepts "
      "estimates, clamped 0–100")
