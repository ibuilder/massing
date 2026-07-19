"""distwaterfall.scenario — the investor-allocation wrapper over run_waterfall (the last of the
audit-flagged untested engines; run_waterfall's math itself is pinned in test_waterfall).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_distwaterfall.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_distwf.db"
os.environ["STORAGE_DIR"] = "./test_storage_distwf"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_distwf.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Waterfall"}).json()["id"]

    # empty cap table → clean zeroed scenario with a note, never a phantom split
    z = c.post(f"/projects/{pid}/waterfall", json={"exit_amount": 1_000_000}).json()
    assert z["total_distributable"] == 0.0 and z["per_investor"] == [], z
    assert "No investors" in z["note"], z

    # cap table: two LPs (600k + 300k) + a GP (100k)
    for name, cls, commit in (("Alpha LP", "LP", 600_000), ("Beta LP", "LP", 300_000),
                              ("Sponsor", "GP", 100_000)):
        r = c.post(f"/projects/{pid}/modules/investor",
                   json={"data": {"investor": name, "investor_class": cls, "commitment": commit}})
        assert r.status_code == 201, r.text[:160]

    # a 5-year 2.0M exit through the default american waterfall
    w = c.post(f"/projects/{pid}/waterfall", json={
        "exit_amount": 2_000_000, "contribution_date": "2021-01-15", "exit_date": "2026-01-15"}).json()
    assert w["total_distributable"] == 2_000_000, w["total_distributable"]
    assert w["lp_contrib"] == 900_000 and w["gp_contrib"] == 100_000, w
    # dollar conservation across LP + GP
    assert abs(w["lp_distributions"] + w["gp_distributions"] - 2_000_000) < 0.02, w
    # IRRs/EMs computed and internally consistent (the tier MATH itself is pinned in test_waterfall;
    # here we lock the wrapper: LPs cleared their pref on a 2x deal, capital fully returned)
    assert w["lp_irr"] is not None and w["lp_irr"] > 0.08, w["lp_irr"]
    assert w["gp_irr"] is not None, w["gp_irr"]
    assert abs(w["lp_equity_multiple"] - w["lp_distributions"] / w["lp_contrib"]) < 0.01, w
    assert abs(w["gp_equity_multiple"] - w["gp_distributions"] / w["gp_contrib"]) < 0.01, w
    assert w["lp_unreturned"] == 0.0, w["lp_unreturned"]
    # per-investor allocation is pro-rata within the LP class (Alpha 2× Beta), sorted desc
    per = {x["investor"]: x["distribution"] for x in w["per_investor"]}
    assert abs(per["Alpha LP"] - 2 * per["Beta LP"]) < 0.02, per
    assert abs(sum(per.values()) - 2_000_000) < 0.05, per
    assert [x["distribution"] for x in w["per_investor"]] == sorted(
        (x["distribution"] for x in w["per_investor"]), reverse=True), w["per_investor"]

    # multi-period distributable with SHORT dates → periods synthesized annually from the base date
    m = c.post(f"/projects/{pid}/waterfall", json={
        "distributable": [500_000, 500_000, 1_500_000], "contribution_date": "2022-06-10"}).json()
    assert m["total_distributable"] == 2_500_000 and len(m["periods"]) == 3, m
    assert abs(m["lp_distributions"] + m["gp_distributions"] - 2_500_000) < 0.02, m

    # pref-rate override reaches the engine and is echoed back
    o = c.post(f"/projects/{pid}/waterfall",
               json={"exit_amount": 1_000_000, "pref_rate": 0.10}).json()
    assert o["pref_rate"] == 0.10, o["pref_rate"]

print("DISTWATERFALL OK - empty cap table zeroes with a note; 2.0M exit over 900k LP / 100k GP "
      "conserves every dollar, LP IRR clears the 8% pref with capital fully returned, EMs are "
      "internally consistent, and allocation is pro-rata within the LP class (Alpha=2×Beta, sorted "
      "desc); short dates synthesize annual periods (3 for 3 distributions); pref_rate override "
      "echoed. (Tier math itself is pinned in test_waterfall.)")
