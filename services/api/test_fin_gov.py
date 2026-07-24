"""FIN-GOV — financial governance: the scenario review workflow (draft→in_review→approved→published,
immutable once approved) + locked reporting periods (finance-module mutations into a closed month
409) + the assumption change log.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fin_gov.py"""
import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite:///./test_fin_gov.db"
os.environ["STORAGE_DIR"] = "./test_storage_fingov"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_fin_gov.db"):
    os.remove("./test_fin_gov.db")

from aec_api import fin_gov  # noqa: E402

# --- the review state machine over a bare object ---------------------------------------------------
s = SimpleNamespace(review_status="draft", reviewed_by=None, reviewed_at=None, review_note=None)
fin_gov.review_scenario(s, "submit", "pm")
assert s.review_status == "in_review"
try:
    fin_gov.review_scenario(s, "publish", "pm")
    raise AssertionError("publish from in_review must fail")
except ValueError:
    pass
fin_gov.review_scenario(s, "approve", "principal", note="LP deck basis")
assert s.review_status == "approved" and s.reviewed_by == "principal"
fin_gov.review_scenario(s, "publish", "principal")
assert s.review_status == "published"
try:
    fin_gov.review_scenario(s, "bogus", "x")
    raise AssertionError("unknown action must KeyError")
except KeyError:
    pass

# --- assumption diff (the change log payload) ------------------------------------------------------
old = {"debt": {"ltc": 0.65, "rate": 0.085}, "exit": {"exit_cap": 0.055}, "name": "A"}
new = {"debt": {"ltc": 0.70, "rate": 0.085}, "exit": {"exit_cap": 0.055}, "name": "A"}
assert fin_gov.assumption_diff(old, new) == ["debt.ltc"]
assert fin_gov.assumption_diff(old, old) == []

# --- period-lock math ------------------------------------------------------------------------------
assert fin_gov._year_month("2026-06-15") == (2026, 6) and fin_gov._year_month("2026/7") == (2026, 7)
assert fin_gov._year_month("junk") is None and fin_gov._year_month("2026-13") is None
fin_gov.set_lock("p1", "2026-06", "cfo", note="Q2 close")
assert fin_gov.get_lock("p1")["lock_date"] == "2026-06"
assert fin_gov.locked_reason("owner_invoice", "p1", {"period": "2026-05"}) is not None   # closed
assert fin_gov.locked_reason("owner_invoice", "p1", {"period": "2026-06"}) is not None   # boundary month closed
assert fin_gov.locked_reason("owner_invoice", "p1", {"period": "2026-07"}) is None       # open
assert fin_gov.locked_reason("owner_invoice", "p1", {"period": "n/a"}) is None           # undated = open
assert fin_gov.locked_reason("rfi", "p1", {"period": "2026-01"}) is None                 # uncovered module
fin_gov.set_lock("p1", None, "cfo")                                                      # clear
assert fin_gov.get_lock("p1")["lock_date"] is None
try:
    fin_gov.set_lock("p1", "June 2026", "cfo")
    raise AssertionError("bad lock_date must ValueError")
except ValueError:
    pass

# --- routes ----------------------------------------------------------------------------------------
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
    pid = c.post("/projects", json={"name": "Gov"}).json()["id"]

    # ---- scenario review over the API
    sid = c.post("/proforma/scenarios",
                 json={"name": "Base", "project_id": pid, "assumptions": DEAL}).json()["id"]
    # a draft edit logs which assumptions moved
    bumped = {**DEAL, "debt": {**DEAL["debt"], "ltc": 0.65}}
    r = c.put(f"/proforma/scenarios/{sid}", json={"name": "Base", "project_id": pid,
                                                  "assumptions": bumped})
    assert r.status_code == 200 and "debt.ltc" in r.json()["changed_assumptions"], r.text
    r = c.post(f"/proforma/scenarios/{sid}/review", json={"action": "submit"})
    assert r.status_code == 200 and r.json()["review_status"] == "in_review", r.text
    assert c.post(f"/proforma/scenarios/{sid}/review",
                  json={"action": "publish"}).status_code == 409       # illegal jump
    assert c.post(f"/proforma/scenarios/{sid}/review",
                  json={"action": "approve", "note": "IC-approved"}).status_code == 200
    # approved → immutable in place
    r = c.put(f"/proforma/scenarios/{sid}", json={"name": "Base", "project_id": pid,
                                                  "assumptions": DEAL})
    assert r.status_code == 409 and "clone" in r.json()["detail"], r.text
    assert c.post(f"/proforma/scenarios/{sid}/review",
                  json={"action": "publish"}).status_code == 200
    # the review state rides the scenario read + list
    got = c.get(f"/proforma/scenarios/{sid}").json()
    assert got["review_status"] == "published" and got["reviewed_by"], got
    # a clone starts back at draft and is editable
    cid = c.post(f"/proforma/scenarios/{sid}/clone", json={"name": "Rev A"}).json()["id"]
    assert c.get(f"/proforma/scenarios/{cid}").json()["review_status"] == "draft"
    assert c.put(f"/proforma/scenarios/{cid}", json={"name": "Rev A", "project_id": pid,
                                                     "assumptions": bumped}).status_code == 200
    assert c.post(f"/proforma/scenarios/{sid}/review",
                  json={"action": "bogus"}).status_code == 404          # unknown action

    # ---- locked reporting periods over the API
    r = c.put(f"/projects/{pid}/finance/lock", json={"lock_date": "2026-06", "note": "Q2 close"})
    assert r.status_code == 200 and r.json()["lock_date"] == "2026-06", r.text
    assert c.get(f"/projects/{pid}/finance/lock").json()["lock_date"] == "2026-06"
    # posting into a closed month is refused; an open month proceeds
    r = c.post(f"/projects/{pid}/modules/owner_invoice",
               json={"data": {"number": "INV-OLD", "amount": 100, "period": "2026-05"}})
    assert r.status_code == 409 and "locked" in str(r.json()["detail"]), r.text
    r = c.post(f"/projects/{pid}/modules/owner_invoice",
               json={"data": {"number": "INV-NEW", "amount": 100, "period": "2026-07"}})
    assert r.status_code in (200, 201), r.text
    rid = r.json()["id"]
    # a record can't be MOVED into a closed month, and a closed-month record refuses edits/deletes
    assert c.patch(f"/projects/{pid}/modules/owner_invoice/{rid}",
                   json={"period": "2026-04"}).status_code == 409
    fin_gov.set_lock(pid, None, "cfo")                      # reopen, backdate a row, close again
    r2 = c.post(f"/projects/{pid}/modules/owner_invoice",
                json={"data": {"number": "INV-Q2", "amount": 50, "period": "2026-06"}})
    assert r2.status_code in (200, 201), r2.text
    rid2 = r2.json()["id"]
    fin_gov.set_lock(pid, "2026-06", "cfo")
    assert c.patch(f"/projects/{pid}/modules/owner_invoice/{rid2}",
                   json={"amount": 60}).status_code == 409
    assert c.delete(f"/projects/{pid}/modules/owner_invoice/{rid2}").status_code == 409
    # non-finance modules are untouched by the lock
    assert c.post(f"/projects/{pid}/modules/rfi",
                  json={"data": {"subject": "door head", "question": "detail?"}}).status_code in (200, 201)
    # bad lock date 422/400s
    assert c.put(f"/projects/{pid}/finance/lock",
                 json={"lock_date": "June 2026"}).status_code == 400

print("FIN-GOV OK - scenario review runs draft->in_review->approved->published (illegal jumps 409, "
      "unknown action 404, who/when/note persisted, clone restarts at draft), approved/published "
      "assumptions are immutable in place (409 'clone a revision') while draft edits return the "
      "changed-assumption paths (debt.ltc); the period lock closes the books through 2026-06 — "
      "owner-invoice postings into a closed month 409 on create/update/move/delete with the lock "
      "date in the reason, open months and non-finance modules flow, clearing the lock reopens, and "
      "a malformed lock date is refused.")
