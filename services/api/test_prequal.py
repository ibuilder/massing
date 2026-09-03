"""Sub prequalification Q-score + COI-expiry tracking.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_prequal.py"""
import os
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_prequal.db"
os.environ["STORAGE_DIR"] = "./test_storage_prequal"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_prequal.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import prequalification as pq  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- engine: a strong sub scores high/low-risk; a weak one scores low/high-risk ---
strong = {"data": {"company": "Ace", "trade": "Concrete", "emr": 0.7, "annual_revenue": 50_000_000,
                   "bonding_capacity": 20_000_000, "largest_project": 8_000_000, "references": ["a", "b", "c"],
                   "rating": "A", "expires": "2999-01-01"}}
weak = {"data": {"company": "Risky", "trade": "Concrete", "emr": 1.4, "annual_revenue": 1_000_000,
                 "largest_project": 200_000, "references": [], "rating": "D", "status": "submitted",
                 "expires": "2000-01-01"}}
s = pq.score_record(strong, project_size=5_000_000)
w = pq.score_record(weak, project_size=5_000_000)
assert s["score"] > 75 and s["risk_band"] == "low", s
assert w["score"] < 50 and w["risk_band"] == "high", w
assert "EMR above 1.0" in w["flags"] and "no bonding capacity" in w["flags"] and "prequalification expired" in w["flags"], w
assert sum(f["of"] for f in s["factors"]) == 100                 # weights sum to 100
assert s["score"] > w["score"]

# --- the rejection FLAG answers to the same field as `in_pool` (v0.3.1126) ------------------------
# It did not until then, and the two came out INVERTED: measured through /prequal/scores, a sub
# rejected by the real transition was out of the pool carrying no flag, while one merely submitted
# with "Rejected" typed into the status field carried the flag and stayed in. The flag fired on the
# sub who was still biddable and was silent on the one the team had refused.
_refused = pq.score_record({"workflow_state": "rejected", "data": {"company": "Refused"}})
assert "rejected" in _refused["flags"], ("the workflow's own refusal must raise the flag",
                                         _refused["flags"])
# The blob is not silently believed OR silently dropped — a disagreement is named, because
# modules.transition() never writes `data`, so the two drift with nothing to reconcile them.
_typed = pq.score_record({"workflow_state": "submitted", "data": {"company": "Typed",
                                                                  "status": "Rejected"}})
_dis = [f for f in _typed["flags"] if "status field says rejected" in f]
assert _dis and "submitted" in _dis[0], ("a typed rejection that the workflow contradicts must be "
                                         "reported as a DISAGREEMENT, not as a rejection", _typed["flags"])
assert "rejected" not in _typed["flags"], ("...and must not be reported as a plain rejection",
                                           _typed["flags"])
# POSITIVE CONTROL: a record with neither raises neither, so the two assertions above cannot pass
# merely because this function flags everything.
assert not [f for f in pq.score_record({"workflow_state": "approved",
                                        "data": {"company": "Clean"}})["flags"]
            if "reject" in f.lower()]

# --- and the FLAG and the POOL must agree on the NORMALISATION, not just on the field -------------
# The first cut of v0.3.1126 fixed which field to read and left score_project comparing the raw
# stored value, which reproduced the same defect one line away: with workflow_state "Rejected",
# measured through /prequal/scores, the flag read `rejected` while in_pool stayed true and the sub
# kept its place in pool_count and high_risk. Transitions write canonical states, but a bundle
# import preserves what it is given, so this is reachable rather than theoretical.
for _raw in ("rejected", "Rejected", "  REJECTED  "):
    assert pq.state_key({"workflow_state": _raw}) == "rejected", _raw
    assert "rejected" in pq.score_record({"workflow_state": _raw, "data": {}})["flags"], _raw
# POSITIVE CONTROL for the loop above: a state that is NOT a refusal must survive canonicalisation
# without becoming one, or the assertions could pass on a helper that returns "rejected" always.
assert pq.state_key({"workflow_state": "  Approved "}) == "approved"
assert "rejected" not in pq.score_record({"workflow_state": " Approved ", "data": {}})["flags"]

# --- endpoints ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    for r in (strong, weak):
        assert c.post(f"/projects/{pid}/modules/prequalification", json=r).status_code == 201
    sc = c.get(f"/projects/{pid}/prequal/scores?project_size=5000000").json()
    assert sc["count"] == 2 and sc["high_risk"] == 1, sc
    assert sc["subs"][0]["company"] == "Risky", sc["subs"][0]           # worst first

    # COI: one expired, one expiring within 30 days, one far future
    today = date.today()
    cois = [("expired", (today - timedelta(days=5)).isoformat()),
            ("soon", (today + timedelta(days=10)).isoformat()),
            ("ok", (today + timedelta(days=200)).isoformat())]
    for vendor, exp in cois:
        c.post(f"/projects/{pid}/modules/coi",
               json={"data": {"vendor": vendor, "coverage_type": "GL", "carrier": "X", "expires": exp}})
    ce = c.get(f"/projects/{pid}/prequal/coi-expiry?soon_days=30").json()
    assert ce["expired_count"] == 1 and ce["expiring_count"] == 1, ce
    assert ce["expired"][0]["vendor"] == "expired" and ce["expiring_soon"][0]["vendor"] == "soon", ce

print("PREQUAL OK - transparent Q-score (weights sum 100): strong sub low-risk >75, weak sub high-risk "
      "<50 with EMR/bonding/expired flags; scores sorted worst-first; COI expiry = 1 expired + 1 soon")
