"""Certified payroll (WH-347) from timesheets x labor rates, and the drawing-set revision register.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_payroll_drawings.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_paydraw.db"
os.environ["STORAGE_DIR"] = "./test_storage_paydraw"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_paydraw.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Federal Job"}).json()["id"]

    # --- G3: certified payroll ------------------------------------------------
    mk(c, pid, "labor_rate", {"trade": "Carpenter", "rate": 50, "unit": "hr"})
    mk(c, pid, "labor_rate", {"trade": "Laborer", "rate": 30, "unit": "hr"})
    # Carpenter: 9h Mon-Fri = 45h (40 ST + 5 OT). Laborer: 8h x4 = 32h.
    for d in ("2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26"):
        mk(c, pid, "timesheet", {"worker": "Sam Carpenter", "date": d, "hours": 9, "trade": "Carpenter"})
    for d in ("2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25"):
        mk(c, pid, "timesheet", {"worker": "Lee Laborer", "date": d, "hours": 8, "trade": "Laborer"})
    # a timesheet OUTSIDE the week should be excluded
    mk(c, pid, "timesheet", {"worker": "Sam Carpenter", "date": "2026-06-15", "hours": 8, "trade": "Carpenter"})

    pr = c.get(f"/projects/{pid}/payroll?week_ending=2026-06-28").json()
    assert pr["worker_count"] == 2, pr
    assert pr["total_hours"] == 77, pr                              # 45 + 32 (excludes prior week)
    sam = next(r for r in pr["rows"] if r["worker"] == "Sam Carpenter")
    assert sam["straight_hours"] == 40 and sam["ot_hours"] == 5, sam
    assert abs(sam["gross"] - (40 * 50 + 5 * 75)) < 0.01, sam      # 2000 + 375 = 2375
    lee = next(r for r in pr["rows"] if r["worker"] == "Lee Laborer")
    assert abs(lee["gross"] - 32 * 30) < 0.01, lee                 # 960
    assert abs(pr["total_gross"] - (2375 + 960)) < 0.01, pr

    pdf = c.get(f"/projects/{pid}/payroll/wh347.pdf?week_ending=2026-06-28")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, pdf.status_code

    # --- G5: drawing-set register --------------------------------------------
    # A-101 has revs 0,1,2 → current is 2; A-102 has rev A → current A
    for rev in ("0", "1", "2"):
        mk(c, pid, "drawing", {"number": f"A-101-{rev}", "sheet_number": "A-101", "title": "Level 1 Plan",
                               "discipline": "Architectural", "revision": rev})
    mk(c, pid, "drawing", {"number": "A-102-A", "sheet_number": "A-102", "title": "Level 2 Plan",
                           "discipline": "Architectural", "revision": "A"})
    mk(c, pid, "drawing", {"number": "S-201-0", "sheet_number": "S-201", "title": "Framing",
                           "discipline": "Structural", "revision": "0"})

    ds = c.get(f"/projects/{pid}/drawing-set").json()
    assert ds["sheet_count"] == 3, ds
    assert ds["current_count"] == 3 and ds["superseded_count"] == 2, ds   # A-101 revs 0,1 superseded
    a101 = next(s for s in ds["sheet_index"] if s["sheet_number"] == "A-101")
    assert a101["current_revision"] == "2" and a101["revisions"] == 3, a101
    assert ds["by_discipline"].get("Architectural") == 2 and ds["by_discipline"].get("Structural") == 1, ds["by_discipline"]
    assert all(s["superseded_by"] == "2" for s in ds["superseded"] if s["sheet_number"] == "A-101"), ds["superseded"]
    # issuance classification: A-101 (3 revs) revised; A-102 & S-201 (1 rev each) new
    assert ds["new_count"] == 2 and ds["revised_count"] == 1, ds
    assert a101["change"] == "revised", a101
    # drawing transmittal PDF renders
    xmit = c.get(f"/projects/{pid}/drawing-set/transmittal.pdf?to=ACME,Owner&note=For%20construction")
    assert xmit.status_code == 200 and xmit.content[:4] == b"%PDF" and len(xmit.content) > 1200, xmit.status_code

print("PAYROLL+DRAWINGS OK - WH-347: 2 workers, 77h, OT past 40 (Sam 40ST+5OT=$2,375), PDF renders; "
      "drawing-set: 3 sheets, current=latest rev (A-101 r2), 2 superseded, discipline rollup")
