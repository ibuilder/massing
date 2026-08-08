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

    # ---- a 0.0 IRR is a RESULT, not a missing value ------------------------------------------
    # The row sort keyed on `-(x["equity_irr"] or -9e9)`, and 0.0 is falsy — so a break-even deal
    # took the sort key reserved for a project whose scenario never solved, and sank to the bottom
    # of a returns table among the blanks. The spread six lines below already filtered on
    # `is not None`. Two lines in one function disagreed about what 0.0 meant, and that
    # disagreement is the evidence: read alone, neither looks wrong.
    #
    # THE FIXTURE IS SHAPED SO THE OLD CODE FAILS DETERMINISTICALLY. Under the bug a break-even
    # deal and an unsolved one BOTH key to 9e9, and Python's sort is stable — comparing those two
    # would pass or fail on insertion order, which is a coin toss dressed as a test. Comparing
    # against a LOSS-MAKING deal breaks the tie: with the bug -0.05 keys to +0.05 and sorts above
    # break-even's 9e9; with the fix break-even outranks it. It is also the claim worth asserting —
    # breaking even beats losing money, and a returns table that says otherwise is lying.
    from aec_api.db import SessionLocal
    from aec_api.models import Scenario
    p_zero = c.post("/projects", json={"name": "Break Even"}).json()["id"]
    p_loss = c.post("/projects", json={"name": "Loss Maker"}).json()["id"]
    with SessionLocal() as db:
        db.add(Scenario(name="zero", project_id=p_zero, assumptions={},
                        result={"returns": {"equity_irr": 0.0}}))
        db.add(Scenario(name="loss", project_id=p_loss, assumptions={},
                        result={"returns": {"equity_irr": -0.05}}))
        db.commit()
    cmp2 = c.get("/proforma/portfolio/compare").json()
    order = [r["project_name"] for r in cmp2["rows"]]
    assert order.index("Break Even") < order.index("Loss Maker"), (
        f"a 0% deal ranked below a loss-making one — 0.0 was read as 'no result': {order}")
    sp0 = cmp2["spread"]["equity_irr"]
    assert sp0["worst"] == "Loss Maker" and sp0["min"] == -0.05, sp0

print("FIN-PORTFOLIO OK - /proforma/portfolio/compare lays the two towers side by side (published "
      "vs draft governance state rides each row, the richer-rent deal wins equity IRR, the spread "
      "names Tower B best); the investor_pack Report-Center preset builds (return KPIs + Sources & "
      "Uses + scenario returns tables) and renders to a real PDF.")
