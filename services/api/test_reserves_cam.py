"""Reserve study / capital plan + CAM reconciliation (hold-phase asset management).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_reserves_cam.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_reserves_cam.db"
os.environ["STORAGE_DIR"] = "./test_storage_reserves_cam"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_reserves_cam.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _create(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:160]}"
    return r.json()


Y = date.today().year
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    # --- reserve study: RTU due in 4 yrs (recurring), roof CIP item, one asset w/o data ----------
    _create(c, pid, "asset_register", {"name": "RTU-1 rooftop unit",
        "install_date": f"{Y - 16}-06-01", "expected_life_years": 20, "replacement_cost": 80000})
    _create(c, pid, "asset_register", {"name": "Elevator cab"})   # no life/cost -> counted missing
    _create(c, pid, "capital_plan", {"subject": "Roof membrane replacement",
        "category": "Roof", "planned_year": Y + 2, "cost": 250000,
        "priority": "Recommended (end of life)", "funding_source": "Reserves"})

    rs = c.get(f"/projects/{pid}/reserves/study",
               params={"horizon_years": 25, "opening_balance": 50000,
                       "annual_contribution": 10000}).json()
    assert rs["components"] == 1 and rs["components_missing_data"] == 1, rs
    yrs = [e["year"] for e in rs["events"]]
    assert (Y + 4) in yrs and (Y + 24) in yrs, f"RTU should recur at +4 and +24: {yrs}"
    assert (Y + 2) in yrs, f"CIP roof at +2 missing: {yrs}"
    assert rs["total_outflows"] == 80000 * 2 + 250000, rs["total_outflows"]
    assert rs["adequately_funded"] is False and rs["first_underfunded_year"] == Y + 2, \
        (rs["first_underfunded_year"], rs["adequately_funded"])
    # The suggestion is now solved exactly, so assert the VALUE, not a range. `> 10000` passed for
    # any of ~10^5 wrong answers, including every one produced by the binary search this replaced.
    # The binding year is Y+2 (k=3): the 250k roof must be covered by three contributions plus the
    # 50k opening balance -> ceil((250000 - 50000) / 3) == 66667. The later 80k events need less per
    # year because they have more years to accumulate against, so k=3 is the maximum.
    assert rs["suggested_level_contribution"] == 66667, rs["suggested_level_contribution"]
    assert rs["suggestion_clears_horizon"] is True, rs
    # the suggested contribution actually clears the horizon
    rs2 = c.get(f"/projects/{pid}/reserves/study",
                params={"horizon_years": 25, "opening_balance": 50000,
                        "annual_contribution": rs["suggested_level_contribution"]}).json()
    assert rs2["adequately_funded"] is True, rs2["first_underfunded_year"]
    # ...and one dollar less does NOT. Without this the assertion above is satisfied by any
    # over-estimate, which is exactly what the old upper-bound-returning search produced.
    rs3 = c.get(f"/projects/{pid}/reserves/study",
                params={"horizon_years": 25, "opening_balance": 50000,
                        "annual_contribution": rs["suggested_level_contribution"] - 1}).json()
    assert rs3["adequately_funded"] is False, "the suggestion is not MINIMAL — one dollar less still clears"

    # --- two blind spots the fixture above cannot reach ------------------------------------------
    # (1) An opening DEFICIT. The old search bracketed the answer in [0, max_annual * years + 1] and
    #     returned the upper bound after 40 halvings without checking that bound was feasible. With a
    #     negative opening balance it is not, so the study returned a confident number that did not
    #     clear its own horizon. Nothing in the fixture above has a negative opening balance.
    pid_neg = c.post("/projects", json={"name": "deficit"}).json()["id"]
    _create(c, pid_neg, "asset_register", {"name": "Chiller", "install_date": f"{Y - 1}-01-01",
                                           "expected_life_years": 20, "replacement_cost": 80000})
    neg = c.get(f"/projects/{pid_neg}/reserves/study",
                params={"horizon_years": 25, "opening_balance": -500000,
                        "annual_contribution": 0}).json()
    # The deficit must be cleared in year one, so the requirement is the deficit itself.
    assert neg["suggested_level_contribution"] == 500000, neg["suggested_level_contribution"]
    assert neg["suggestion_clears_horizon"] is True, neg
    neg2 = c.get(f"/projects/{pid_neg}/reserves/study",
                 params={"horizon_years": 25, "opening_balance": -500000,
                         "annual_contribution": neg["suggested_level_contribution"]}).json()
    assert neg2["adequately_funded"] is True, ("a suggestion that does not clear its own horizon is "
                                               "worse than none — it is the number somebody funds to",
                                               neg2["first_underfunded_year"])

    # (2) A component with a cost and a life but NO install date. It is projected as if installed
    #     today — the most optimistic reading — so a 20-year component contributes nothing to a
    #     25-year study while still being counted as a complete component. `components_missing_data`
    #     stayed 0 and nothing named the assumption.
    pid_und = c.post("/projects", json={"name": "undated"}).json()["id"]
    _create(c, pid_und, "asset_register", {"name": "RTU-9 undated",
                                           "expected_life_years": 20, "replacement_cost": 80000})
    und = c.get(f"/projects/{pid_und}/reserves/study", params={"horizon_years": 25}).json()
    assert und["components"] == 1 and und["components_missing_data"] == 0, und
    assert und["components_without_install_date"] == 1, und
    assert und["components_without_install_date_names"] == ["RTU-9 undated"], und
    assert "install date" in und["note"], und["note"]
    # and the optimism is real, not theoretical: the first replacement is a full life away
    assert [e["year"] for e in und["events"]] == [Y + 20], und["events"]

    # --- CAM reconciliation: variable-only gross-up + per-tenant true-up ------------------------
    _create(c, pid, "lease", {"tenant": "Acme Corp", "suite": "100", "rentable_sf": 10000,
        "base_rent_annual": 300000, "lease_type": "NNN", "recovery_psf": 5})
    _create(c, pid, "lease", {"tenant": "Beta LLC", "suite": "200", "rentable_sf": 5000,
        "base_rent_annual": 140000, "lease_type": "NNN", "recovery_psf": 4})
    _create(c, pid, "cam_expense", {"subject": "Janitorial contract", "category": "Cleaning / Janitorial",
        "year": Y, "budget_annual": 90000, "actual_annual": 100000, "variable": "Yes", "recoverable": "Yes"})
    _create(c, pid, "cam_expense", {"subject": "Property insurance", "category": "Insurance",
        "year": Y, "budget_annual": 45000, "actual_annual": 50000, "variable": "No", "recoverable": "Yes"})
    _create(c, pid, "cam_expense", {"subject": "Owner legal", "category": "Administrative",
        "year": Y, "budget_annual": 8000, "actual_annual": 10000, "variable": "No", "recoverable": "No"})

    rec = c.get(f"/projects/{pid}/cam/reconciliation",
                params={"building_sf": 20000, "gross_up_to_pct": 95}).json()
    assert rec["occupancy_pct"] == 75.0, rec["occupancy_pct"]
    # variable janitorial grossed 100k * 95/75; fixed insurance passes at actual; legal excluded
    assert rec["recoverable_pool"] == round(100000 * 95 / 75 + 50000, 2), rec["recoverable_pool"]
    acme = next(t for t in rec["tenants"] if t["tenant"] == "Acme Corp")
    assert acme["share_pct"] == 50.0 and acme["estimated_paid"] == 50000, acme
    assert abs(acme["balance_due"] - (rec["recoverable_pool"] * 0.5 - 50000)) < 0.02, acme

    # --- per-tenant statement PDF ----------------------------------------------------------------
    r = c.get(f"/projects/{pid}/cam/statement/{acme['id']}.pdf",
              params={"building_sf": 20000, "gross_up_to_pct": 95})
    assert r.status_code == 200 and r.content[:4] == b"%PDF", (r.status_code, r.content[:8])
    assert r.status_code == 200 and len(r.content) > 1200

print(f"RESERVES+CAM OK - reserve study: RTU recurs +4/+24 + CIP roof (total {rs['total_outflows']:,}), "
      f"underfunded {rs['first_underfunded_year']} at $10k/yr, suggested "
      f"${rs['suggested_level_contribution']:,.0f}/yr clears; CAM: 75% occ, variable-only gross-up pool "
      f"${rec['recoverable_pool']:,.0f}, Acme 50% share balance ${acme['balance_due']:,.0f}; statement PDF served")
