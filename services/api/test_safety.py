"""Safety analytics: incidents by OSHA class, recordable/lost-time, TRIR/DART per 200k hours.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_safety.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./safety_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_safety"
os.environ.pop("AEC_RBAC", None)
for f in ("./safety_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Safety"}).json()["id"]
    for cls, days in [("Near Miss", 0), ("Recordable", 0), ("Lost Time", 5), ("First Aid", 0)]:
        r = c.post(f"/projects/{pid}/modules/incident",
                   json={"data": {"subject": cls, "classification": cls, "lost_days": days,
                                  "severity": "Medium", "date": "2026-06-01"}})
        assert r.status_code == 201, r.text

    # explicit hours -> deterministic TRIR/DART:  2 recordables (Recordable + Lost Time), 1 lost-time
    m = c.get(f"/projects/{pid}/safety/metrics?hours=100000").json()
    assert m["incident_count"] == 4, m
    assert m["recordable_count"] == 2 and m["lost_time_count"] == 1 and m["lost_days"] == 5, m
    assert m["trir"] == round(2 * 200000 / 100000, 2) == 4.0, m["trir"]      # 2 recordables / 100k hrs
    assert m["dart"] == round(1 * 200000 / 100000, 2) == 2.0, m["dart"]
    assert m["by_class"]["Lost Time"] == 1 and m["by_class"]["Near Miss"] == 1

    # hours derived from logs when not passed (none here) -> trir None, not a crash
    m2 = c.get(f"/projects/{pid}/safety/metrics").json()
    assert m2["hours_worked"] == 0 and m2["trir"] is None, m2

    print("SAFETY OK - OSHA class counts, recordable/lost-time, TRIR 4.0 / DART 2.0 @100k hrs, no-hours safe")
