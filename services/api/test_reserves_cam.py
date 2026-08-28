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
    # EXECUTED, not just created. The `lease` workflow starts at `draft` and the draft -> active
    # transition's action is literally `execute` — a draft lease is one nobody has signed. This
    # fixture used to leave both in draft and then assert they were billed CAM, which is what let
    # `cam.reconciliation` bill an unsigned tenant: a 20,000 sf prospect came back with a
    # `balance_due` of $70,000 on a reconciliation. The engine now filters to in-place leases, so
    # the fixture has to say what it always meant.
    for _t, _suite, _sf, _rent, _rec in (("Acme Corp", "100", 10000, 300000, 5),
                                         ("Beta LLC", "200", 5000, 140000, 4)):
        _ls = _create(c, pid, "lease", {"tenant": _t, "suite": _suite, "rentable_sf": _sf,
            "base_rent_annual": _rent, "lease_type": "NNN", "recovery_psf": _rec,
            "start_date": "2025-01-01", "end_date": "2029-12-31"})
        _tr = c.post(f"/projects/{pid}/modules/lease/{_ls['id']}/transition",
                     json={"action": "execute"})
        assert _tr.status_code == 200, f"execute {_t}: {_tr.text[:160]}"
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

    # AN UNSIGNED LEASE IS NOT BILLED — and is NAMED rather than silently dropped.
    #
    # `cam.reconciliation` filtered leases on `rentable_sf > 0` alone, so a DRAFT lease was billed:
    # a 20,000 sf prospect came back with `balance_due: 70000.0`, and moved reported occupancy from
    # 35% to 85% — the same figure the gross-up is struck against. The `lease` workflow starts at
    # `draft` and its draft -> active action is literally `execute`, so a draft lease is one nobody
    # has signed. `ACTIVE_STATES` is imported from `rentroll`, not restated, because that is already
    # the definition of "counts as income" and a tenant with no income cannot owe a recovery.
    prospect = _create(c, pid, "lease", {"tenant": "Prospect Co", "suite": "300",
        "rentable_sf": 20000, "base_rent_annual": 480000, "lease_type": "NNN", "recovery_psf": 4,
        "start_date": "2026-01-01", "end_date": "2031-12-31"})
    rec2 = c.get(f"/projects/{pid}/cam/reconciliation",
                 params={"year": date.today().year, "building_sf": 20000}).json()
    assert all(t["tenant"] != "Prospect Co" for t in rec2["tenants"]),         f"an unexecuted lease was billed CAM: {[t['tenant'] for t in rec2['tenants']]}"
    excluded = rec2.get("tenants_not_in_place") or []
    assert any(t["tenant"] == "Prospect Co" and t["workflow_state"] == "draft" for t in excluded),         f"the excluded tenant must be NAMED — removing a payer shifts everyone else's share: {excluded}"

    # THE TWIN: executing that same lease puts it back on the statement. Without this the assertion
    # above passes on an engine that bills nobody.
    ex = c.post(f"/projects/{pid}/modules/lease/{prospect['id']}/transition", json={"action": "execute"})
    assert ex.status_code == 200, ex.text[:160]
    rec3 = c.get(f"/projects/{pid}/cam/reconciliation",
                 params={"year": date.today().year, "building_sf": 20000}).json()
    assert any(t["tenant"] == "Prospect Co" for t in rec3["tenants"]),         "an EXECUTED lease must be billed — the filter excludes drafts, not everyone"
    assert not (rec3.get("tenants_not_in_place") or []), rec3.get("tenants_not_in_place")


    # --- per-tenant statement PDF ----------------------------------------------------------------
    r = c.post(f"/projects/{pid}/cam/statement/{acme['id']}.pdf",
               params={"building_sf": 20000, "gross_up_to_pct": 95})
    assert r.status_code == 200 and r.content[:4] == b"%PDF", (r.status_code, r.content[:8])
    assert r.status_code == 200 and len(r.content) > 1200

print(f"RESERVES+CAM OK - reserve study: RTU recurs +4/+24 + CIP roof (total {rs['total_outflows']:,}), "
      f"underfunded {rs['first_underfunded_year']} at $10k/yr, suggested "
      f"${rs['suggested_level_contribution']:,.0f}/yr clears; CAM: 75% occ, variable-only gross-up pool "
      f"${rec['recoverable_pool']:,.0f}, Acme 50% share balance ${acme['balance_due']:,.0f}; statement PDF served")
