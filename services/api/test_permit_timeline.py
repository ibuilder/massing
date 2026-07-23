"""PERMIT-TIMELINE — days-to-issue percentiles by jurisdiction × type × valuation band + a pro-forma
estimate (median expected / p75 conservative) that broadens the cohort when a specific one is thin.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_permit_timeline.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_permit_timeline.db"
os.environ["STORAGE_DIR"] = "./test_storage_permit"
os.environ.pop("AEC_RBAC", None)

from aec_api import permit_timeline as pt  # noqa: E402


def _p(jur, typ, val, filed, issued):
    return {"jurisdiction": jur, "type": typ, "valuation": val, "filed": filed, "issued": issued}


permits = [
    _p("Austin", "New Commercial", 5_000_000, "2026-01-01", "2026-02-01"),   # 31
    _p("Austin", "New Commercial", 5_000_000, "2026-01-01", "2026-03-01"),   # 59
    _p("Austin", "New Commercial", 5_000_000, "2026-01-01", "2026-04-01"),   # 90
    _p("Austin", "New Commercial", 5_000_000, "2026-01-01", "2026-05-01"),   # 120
    _p("Austin", "New Commercial", 5_000_000, "2026-01-01", "2026-06-01"),   # 151
    _p("Austin", "New Commercial", 5_000_000, "2026-05-01", "2026-01-01"),   # invalid (issued < filed) → skipped
    _p("Austin", "Residential", 50_000, "2026-01-01", "2026-01-15"),         # 14, different group + band
]
r = pt.analyze(permits, {"jurisdiction": "Austin", "type": "New Commercial", "valuation": 5_000_000})
assert r["permit_count"] == 7 and r["measured"] == 6, r                       # the invalid one is dropped
assert r["overall"]["n"] == 6 and r["overall"]["median"] == 74.5, r["overall"]

grp = next(g for g in r["groups"] if g["type"] == "New Commercial" and g["band"] == "$1M–10M")
assert grp["n"] == 5 and grp["p25"] == 59 and grp["median"] == 90 and grp["p75"] == 120, grp
assert r["seasonal"], r["seasonal"]

# estimate for the well-sampled cohort — no broadening
est = r["estimate"]
assert est["basis"] == "jurisdiction × type × band" and est["sample_size"] == 5, est
assert est["expected_days"] == 90 and est["conservative_days"] == 120 and est["expected_months"] == 3.0, est

# a thin cohort broadens: Residential <$100k has 1 → falls back to the jurisdiction median (all Austin, n=6)
r2 = pt.analyze(permits, {"jurisdiction": "Austin", "type": "Residential", "valuation": 50_000})
assert r2["estimate"]["basis"] == "jurisdiction" and r2["estimate"]["sample_size"] == 6, r2["estimate"]
assert r2["estimate"]["expected_days"] == 74.5, r2["estimate"]

assert pt.analyze([])["measured"] == 0                                        # empty is well-formed

# --- route: 404 missing project; 409 no data; 200 with supplied permits ----------------------------
if os.path.exists("./test_permit_timeline.db"):
    os.remove("./test_permit_timeline.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/permits/timeline", json={"permits": permits}).status_code == 404
    pid = c.post("/projects", json={"name": "Permit"}).json()["id"]
    assert c.post(f"/projects/{pid}/permits/timeline", json={}).status_code == 409   # no permit data
    rr = c.post(f"/projects/{pid}/permits/timeline",
                json={"permits": permits, "target": {"jurisdiction": "Austin", "type": "New Commercial", "valuation": 5_000_000}})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["measured"] == 6 and j["estimate"]["expected_days"] == 90, j

print("PERMIT-TIMELINE OK - days-to-issue = issued − filed over cached permits (an issued<filed row dropped): "
      "the Austin New-Commercial $1M–10M cohort of 5 has p25/median/p75 = 59/90/120 days; the pro-forma "
      "estimate returns median 90d (3.0mo expected) + p75 120d (conservative carry) at basis 'jurisdiction × "
      "type × band'; a thin Residential cohort broadens to the jurisdiction median (74.5d over all 6 Austin "
      "permits); the /permits/timeline route 404s on a missing project and 409s with no permit data.")
