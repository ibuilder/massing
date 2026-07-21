"""SELECTIONS (SPRINT D phase-3) — owner selections & allowances rollup: allowance vs actual, net
over/under, per-category deltas, approval count, and the over-allowance change-order candidates.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_selections.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_selections.db"
os.environ["STORAGE_DIR"] = "./test_storage_selections"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_selections.db"):
    os.remove("./test_selections.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import selections  # noqa: E402
from aec_api.main import app  # noqa: E402

# the currency parser is tolerant of formatted strings even though the module API stores numbers
assert selections._num("$540.00") == 540.0 and selections._num("1,200.50") == 1200.5, "currency parse"
assert selections._num(None) is None and selections._num("") is None and selections._num("n/a") is None

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Custom Home"}).json()["id"]

    def mk(item, cat, allow, actual, approve=False):
        r = c.post(f"/projects/{pid}/modules/selection",
                   json={"data": {"item": item, "category": cat, "allowance": allow, "actual_cost": actual}}).json()
        if approve:
            c.post(f"/projects/{pid}/modules/selection/{r['id']}/transition", json={"action": "select"})
            c.post(f"/projects/{pid}/modules/selection/{r['id']}/transition", json={"action": "approve"})
        return r

    # over allowance (CO candidate), under allowance (credit), at allowance, and one not-yet-priced
    mk("Kitchen faucet", "Fixtures", 400, 650, approve=True)     # +250 over
    mk("Master tile", "Flooring", 3000, 2400)                    # -600 under (credit)
    mk("Front door", "Other", 1200, 1200)                        # on allowance
    mk("Pendant lights", "Lighting", 800, None)                  # not priced yet
    mk("Cabinet pulls", "Cabinetry", 300, 540)                   # +240 over

    s = c.get(f"/projects/{pid}/selections/summary")
    assert s.status_code == 200, s.text[:200]
    j = s.json()
    assert j["count"] == 5 and j["priced"] == 4 and j["approved"] == 1, j
    # totals: allowance 400+3000+1200+800+300 = 5700; actual (priced only) 650+2400+1200+540 = 4790
    assert j["total_allowance"] == 5700.0 and j["total_actual"] == 4790.0, j
    assert j["net_delta"] == round(4790.0 - 5700.0, 2) == -910.0 and j["direction"] == "under", j
    assert j["over_count"] == 2 and j["under_count"] == 1 and j["on_count"] == 1, j
    # CO candidates = the two over-allowance items, worst (biggest delta) first
    cands = j["co_candidates"]
    assert j["co_candidate_count"] == 2 and [x["item"] for x in cands] == ["Kitchen faucet", "Cabinet pulls"], cands
    assert cands[0]["delta"] == 250.0 and cands[1]["delta"] == 240.0, cands
    assert cands[0]["state"] == "approved", cands[0]           # the faucet was owner-approved
    # per-category rollup carries the signed delta
    by = {c2["category"]: c2 for c2 in j["by_category"]}
    assert by["Fixtures"]["delta"] == 250.0 and by["Flooring"]["delta"] == -600.0, by
    assert by["Lighting"]["actual"] == 0.0, by                  # unpriced contributes allowance only

    # empty project → zeroed summary, no crash
    pid2 = c.post("/projects", json={"name": "Empty"}).json()["id"]
    e = c.get(f"/projects/{pid2}/selections/summary").json()
    assert e["count"] == 0 and e["net_delta"] == 0.0 and e["direction"] == "on-allowance" and e["co_candidates"] == [], e
    assert c.get("/projects/no-such/selections/summary").status_code == 404

print("SELECTIONS OK - the selections log rolls up to the allowance-vs-actual money picture: 5 selections "
      "(4 priced, 1 owner-approved), total allowance $5,700 vs actual $4,790 → net -$910 UNDER; 2 over / 1 "
      "under / 1 on-allowance; the two over-allowance items surface as change-order candidates worst-first "
      "(faucet +$250 approved, pulls +$240), per-category signed deltas "
      "(Fixtures +250 / Flooring -600), and an empty project returns a zeroed summary; 404 on unknown.")
