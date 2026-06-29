"""Operate & Capital (G1+G2): rent roll (occupancy, WALT, expirations, in-place income → appraisal)
and the investor cap table + pro-rata capital-call / distribution allocation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_operate_capital.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_opcap.db"
os.environ["STORAGE_DIR"] = "./test_storage_opcap"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_opcap.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()["id"]


def trans(c, pid, key, rid, action):
    return c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Riverside Op"}).json()["id"]
    c.put(f"/projects/{pid}/property", json={"sqft": 50000})        # building rentable area

    # --- G1: leases → rent roll -----------------------------------------------
    l1 = mk(c, pid, "lease", {"tenant": "Acme", "suite": "100", "rentable_sf": 20000,
                              "base_rent_annual": 600000, "lease_type": "NNN",
                              "start_date": "2026-01-01", "end_date": "2031-12-31", "recovery_psf": 5})
    l2 = mk(c, pid, "lease", {"tenant": "Globex", "suite": "200", "rentable_sf": 10000,
                              "base_rent_annual": 250000, "lease_type": "Gross",
                              "start_date": "2026-01-01", "end_date": "2028-12-31"})
    for lid in (l1, l2):
        assert trans(c, pid, "lease", lid, "execute").json()["workflow_state"] == "active"

    rr = c.get(f"/projects/{pid}/rent-roll").json()
    assert rr["lease_count"] == 2, rr
    assert rr["occupied_sf"] == 30000 and rr["total_rentable_sf"] == 50000, rr
    assert rr["occupancy_pct"] == 60.0, rr["occupancy_pct"]         # 30k / 50k
    assert rr["base_rent_annual"] == 850000, rr
    assert rr["recoveries_annual"] == 100000, rr                   # 5 $/SF * 20000
    assert rr["in_place_gross_income"] == 950000, rr
    assert "2028" in rr["expirations_by_year"] and "2031" in rr["expirations_by_year"], rr["expirations_by_year"]
    assert rr["walt_years"] > 0, rr

    # appraisal income approach can value off the actual rent roll
    base = c.get(f"/projects/{pid}/appraisal").json()
    onrr = c.get(f"/projects/{pid}/appraisal?rentroll=1").json()
    assert abs(onrr["income"]["stabilized_noi"] - 950000) < 1, onrr["income"]
    assert onrr["income"]["stabilized_noi"] != base["income"]["stabilized_noi"], "rentroll should override NOI"

    # --- G1b: lease-management depth (renewals / escalations / CAM) -----------
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=60)).isoformat()       # within the <=90d bucket
    l3 = mk(c, pid, "lease", {"tenant": "Initech", "suite": "300", "rentable_sf": 10000,
                              "base_rent_annual": 300000, "lease_type": "NNN", "escalation_pct": 3,
                              "start_date": "2023-01-01", "end_date": soon, "recovery_psf": 4,
                              "renewal_options": "1 x 5yr"})
    trans(c, pid, "lease", l3, "execute")
    lm = c.get(f"/projects/{pid}/leases/management?years=5&recoverable_opex=150000").json()
    assert lm["lease_count"] == 3, lm
    # escalations: l1/l2 flat (no esc), l3 grows 3%/yr; current = 600k+250k+300k
    assert lm["escalations"]["current_base_rent"] == 1_150_000, lm["escalations"]
    # projected yr5 = 850k flat + 300k*1.03^5 (=347,782.43)
    assert abs(lm["escalations"]["projected_base_rent"] - (850_000 + 300_000 * 1.03 ** 5)) < 1.0, lm["escalations"]
    # renewals: l3 expires in ~60d -> <=90d bucket + at-risk rent (l1/l2 end years away)
    assert lm["renewals"]["expiring"]["<=90d"]["count"] == 1, lm["renewals"]
    assert lm["renewals"]["at_risk_rent"] == 300_000, lm["renewals"]
    assert lm["renewals"]["options_outstanding"] == 1, lm["renewals"]
    # CAM: NNN leases with recovery_psf -> l1 (5*20k) + l3 (4*10k) = 140k; Gross l2 excluded
    assert lm["cam"]["recoverable_income"] == 140_000, lm["cam"]
    assert lm["cam"]["recovery_ratio"] == 0.933, lm["cam"]       # round(140k/150k, 3)
    assert lm["cam"]["under_recovery"] == 10_000, lm["cam"]      # 150k pool - 140k recovered

    # --- G2: investors → cap table + allocations ------------------------------
    investors = [("LP One", "LP", 6_000_000), ("LP Two", "LP", 3_000_000), ("GP", "GP", 1_000_000)]
    for name, cls, commit in investors:
        iid = mk(c, pid, "investor", {"investor": name, "investor_class": cls, "commitment": commit})
        trans(c, pid, "investor", iid, "commit")

    ct = c.get(f"/projects/{pid}/cap-table").json()
    assert ct["investor_count"] == 3 and ct["total_commitment"] == 10_000_000, ct
    lp1 = next(r for r in ct["rows"] if r["investor"] == "LP One")
    assert lp1["ownership_pct"] == 60.0, lp1                        # 6M / 10M
    assert ct["by_class"]["LP"] == 9_000_000 and ct["by_class"]["GP"] == 1_000_000, ct["by_class"]

    call = c.post(f"/projects/{pid}/capital-call", json={"amount": 1_000_000}).json()
    assert call["kind"] == "call" and abs(sum(a["amount"] for a in call["allocations"]) - 1_000_000) < 0.01, call
    a_lp1 = next(a for a in call["allocations"] if a["investor"] == "LP One")
    assert abs(a_lp1["amount"] - 600000) < 1, a_lp1                 # 60% pro-rata

    dist = c.post(f"/projects/{pid}/distribution", json={"amount": 500_000}).json()
    assert dist["kind"] == "distribution" and abs(sum(a["amount"] for a in dist["allocations"]) - 500_000) < 0.01, dist

    # persisted capital call posts to each investor's contributed total → cap table updates
    before = c.get(f"/projects/{pid}/cap-table").json()["total_contributed"]
    pc = c.post(f"/projects/{pid}/capital-call", json={"amount": 2_000_000, "persist": True}).json()
    assert pc.get("persisted") is True, pc
    after = c.get(f"/projects/{pid}/cap-table").json()
    assert abs(after["total_contributed"] - (before + 2_000_000)) < 1.0, after
    lp1c = next(r for r in after["rows"] if r["investor"] == "LP One")
    assert abs(lp1c["contributed"] - 1_200_000) < 1.0, lp1c       # 60% of 2M

    # per-investor capital-account statement PDF
    iid = next(r["id"] for r in ct["rows"] if r["investor"] == "LP One")
    stmt = c.get(f"/projects/{pid}/investors/{iid}/statement.pdf")
    assert stmt.status_code == 200 and stmt.content[:4] == b"%PDF" and len(stmt.content) > 1000, stmt.status_code

    # --- reports render ------------------------------------------------------
    cat = {x["id"] for x in c.get("/reports").json()["reports"]}
    assert {"rent_roll", "cap_table", "lease_management"} <= cat, cat
    for rid in ("rent_roll", "cap_table", "lease_management"):
        pdf = c.get(f"/projects/{pid}/reports/{rid}.pdf")
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 1200, (rid, pdf.status_code)

print("OPERATE+CAPITAL OK - rent roll 60% occ / $950k in-place income (feeds appraisal); lease mgmt: "
      "1 expiring <=90d / $300k at-risk, 3%/yr escalation to yr5, CAM recovers $140k (93% of pool, $10k "
      "under); cap table ownership (LP One 60%); capital call + distribution pro-rata; "
      "rent_roll + cap_table + lease_management PDFs render")
