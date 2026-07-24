"""FIN-PORTFOLIO — the investor reporting pack (Report Center preset) + portfolio-level scenario
comparison across projects.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fin_portfolio.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_fin_portfolio.db"
os.environ["STORAGE_DIR"] = "./test_storage_finport"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_fin_portfolio.db"):
    os.remove("./test_fin_portfolio.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

DEAL = {
    "timing": {"construction_months": 6, "leaseup_months": 3, "hold_years": 2,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 1_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Build", "amount": 4_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 5},
    ],
    "debt": {"ltc": 0.6, "rate": 0.08, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 700_000, "other_income_annual": 0,
                   "opex_annual": 250_000, "stabilized_occ": 0.95, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.06, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
}

with TestClient(app) as c:
    p1 = c.post("/projects", json={"name": "Tower A"}).json()["id"]
    p2 = c.post("/projects", json={"name": "Tower B"}).json()["id"]
    richer = {**DEAL, "operations": {**DEAL["operations"], "potential_rent_annual": 850_000}}
    s1 = c.post("/proforma/scenarios", json={"name": "A Base", "project_id": p1,
                                             "assumptions": DEAL}).json()["id"]
    c.post("/proforma/scenarios", json={"name": "B Base", "project_id": p2,
                                        "assumptions": richer})
    # publish A's scenario so the compare can show governance state
    for a in ("submit", "approve", "publish"):
        assert c.post(f"/proforma/scenarios/{s1}/review", json={"action": a}).status_code == 200

    # ---- portfolio scenario compare: one row per project, side-by-side returns + the spread
    r = c.get("/proforma/portfolio/compare")
    assert r.status_code == 200, r.text
    cmp_ = r.json()
    assert cmp_["project_count"] == 2, cmp_
    by_name = {row["project_name"]: row for row in cmp_["rows"]}
    assert by_name["Tower A"]["review_status"] == "published"
    assert by_name["Tower B"]["review_status"] == "draft"
    assert by_name["Tower B"]["equity_irr"] > by_name["Tower A"]["equity_irr"]  # richer rents win
    assert cmp_["spread"]["equity_irr"]["best"] == "Tower B", cmp_["spread"]

    # ---- the investor pack report builds and renders to PDF like any Report Center preset
    from aec_api import reports
    from aec_api.db import SessionLocal
    assert any(x["id"] == "investor_pack" for x in reports.catalog()), "not in the catalog"
    with SessionLocal() as db:
        rep = reports.build(db, p1, "investor_pack")
    assert rep.title.lower().startswith("investor")
    assert any("IRR" in k or "Equity" in k for k, _ in rep.kpis), rep.kpis
    names = [t["name"] for t in rep.tables]
    assert any("Sources" in n for n in names) and any("Returns" in n or "Scenario" in n
                                                      for n in names), names
    pdf = c.get(f"/projects/{p1}/reports/investor_pack.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

print("FIN-PORTFOLIO OK - /proforma/portfolio/compare lays the two towers side by side (published "
      "vs draft governance state rides each row, the richer-rent deal wins equity IRR, the spread "
      "names Tower B best); the investor_pack Report-Center preset builds (return KPIs + Sources & "
      "Uses + scenario returns tables) and renders to a real PDF.")
