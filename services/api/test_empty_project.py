"""Hardening: every analytics / real-estate surface must degrade cleanly on a brand-new project
with no records — 200 with a sane zeroed structure (and valid PDFs), never a 500 or a blank crash.
Guards the "no data yet" path for the newer Finance/construction/RE features.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_empty_project.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_empty.db"
os.environ["STORAGE_DIR"] = "./test_storage_empty"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_empty.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Empty"}).json()["id"]

    # --- read-side analytics: all 200 on an empty project --------------------
    gets = ["/quality/summary", "/rfi/register", "/submittals/register", "/tm-summary",
            "/tm-by-change-event", "/daily-reports/summary", "/safety/summary", "/closeout/summary",
            "/leases/management", "/change-orders/log", "/action-items/tracker", "/cap-table",
            "/rent-roll", "/health"]
    for g in gets:
        url = f"/projects/{pid}{g}" if g != "/health" else g
        r = c.get(url)
        assert r.status_code == 200, (g, r.status_code, r.text[:200])

    # spot-check zeroed structure (no KeyErrors / Nones where a number is expected)
    q = c.get(f"/projects/{pid}/quality/summary").json()
    assert q["inspections"]["total"] == 0 and q["ncrs"]["ncr_count"] == 0, q
    saf = c.get(f"/projects/{pid}/safety/summary").json()
    assert saf["incidents"]["incident_count"] == 0 and saf["incidents"]["trir"] is None, saf
    lm = c.get(f"/projects/{pid}/leases/management").json()
    assert lm["lease_count"] == 0 and lm["escalations"]["current_base_rent"] == 0, lm
    ph = c.get(f"/projects/{pid}/health").json()
    assert "health_score" in ph and isinstance(ph["domains"], list), ph

    # --- write-side endpoints tolerate empty inputs --------------------------
    wf = c.post(f"/projects/{pid}/waterfall", json={"exit_amount": 1_000_000}).json()
    assert wf["lp_distributions"] == 0 and wf["per_investor"] == [], wf      # no investors -> no allocation
    imp = c.post(f"/projects/{pid}/comparables/import", json={"csv": "address\n"}).json()
    assert imp["imported"] == 0, imp                                          # header only -> nothing

    # --- every report renders a valid PDF with no data -----------------------
    for rid in ("quality", "rfi_register", "safety_dashboard", "closeout", "lease_management",
                "field_log", "project_health", "tm_log", "submittal_register", "cap_table",
                "rent_roll", "marketing_flyer", "listing_factsheet"):
        pdf = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF", (rid, pdf.status_code)
        xls = c.get(f"/projects/{pid}/reports/{rid}.xlsx")
        assert xls.status_code == 200 and len(xls.content) > 100, (rid, "xlsx", xls.status_code)

print("EMPTY-PROJECT OK - all 14 analytics endpoints 200 + zeroed; waterfall/comps tolerate empty; "
      "13 reports render valid PDF + xlsx with no data (no 500s, no blank crashes)")
