"""Stakeholder register + power/interest (Mendelow) analysis.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_stakeholder.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_stakeholder.db"
os.environ["STORAGE_DIR"] = "./test_storage_stakeholder"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_stakeholder.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _stk(c, pid, **data):
    r = c.post(f"/projects/{pid}/modules/stakeholder", json={"data": data})
    assert r.status_code == 201, r.text[:160]
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    _stk(c, pid, name="City Planning Dept", organization="City", category="Authority / Regulator",
         power="High", interest="High", stance="Neutral")               # manage closely
    _stk(c, pid, name="Lender", organization="BigBank", category="Investor / Lender",
         power="High", interest="Low", stance="Blocker")                 # keep satisfied + high-power blocker
    _stk(c, pid, name="Neighborhood Assoc.", organization="NA", category="Community",
         power="Low", interest="High", stance="Supporter")               # keep informed
    _stk(c, pid, name="Passerby", organization="", category="Community",
         power="Low", interest="Low", stance="Neutral")                  # monitor

    a = c.get(f"/projects/{pid}/stakeholders/analysis").json()
    assert a["total"] == 4, a["total"]
    q = a["quadrants"]
    assert q["manage_closely"]["count"] == 1 and q["keep_satisfied"]["count"] == 1, q
    assert q["keep_informed"]["count"] == 1 and q["monitor"]["count"] == 1, q
    assert a["stance"]["Blocker"] == 1 and a["stance"]["Supporter"] == 1, a["stance"]
    # the high-power blocker (the Lender) is flagged
    assert len(a["high_power_blockers"]) == 1 and a["high_power_blockers"][0]["organization"] == "BigBank", \
        a["high_power_blockers"]
    assert a["supporter_pct"] == 25.0, a["supporter_pct"]

    # --- STAKEHOLDER-MEDIUM ---------------------------------------------------------------------
    # The four records above use only High and Low, which is why this shipped: *every test of the
    # engine supplied its own well-formed inputs.* The register scores power and interest on THREE
    # levels and neither field is required, so these two are what a real project looks like. They
    # are added HERE, after the assertions above, so none of those numbers has to change — a new
    # phase rather than a rewrite of somebody else's expectations.
    _stk(c, pid, name="Adjacent Owner", organization="AdjCo", category="Community",
         power="Medium", interest="Medium", stance="Blocker")       # Medium/Medium AND a blocker
    _stk(c, pid, name="Utility Co", organization="UtilCo", category="Other",
         stance="Neutral")                                          # no power, no interest at all
    b = c.get(f"/projects/{pid}/stakeholders/analysis").json()
    bq = b["quadrants"]
    assert b["total"] == 6 and b["assessed"] == 5, (b["total"], b["assessed"])

    # ① UNASSESSED IS NOT "MONITOR". Utility Co used to land in "Low power + low interest — monitor
    # with minimal effort", so a register nobody had filled in read as "everybody is low priority
    # and there are no blockers". *The default branch of a 2x2 is not a place to put "unknown".*
    assert bq["unassessed"]["count"] == 1, bq["unassessed"]
    assert bq["unassessed"]["stakeholders"][0]["organization"] == "UtilCo", bq["unassessed"]
    assert "not been recorded" in bq["unassessed"]["advice"], bq["unassessed"]["advice"]

    # ② MEDIUM STILL SITS ON THE LOW SIDE — a product decision, not a bug — but it is STATED now
    # rather than implied, and the distribution is reported so a wall of "Monitor" can be read as
    # "everybody is Medium" instead of as a finding.
    assert bq["monitor"]["count"] == 2, bq["monitor"]               # Passerby + Adjacent Owner
    assert b["grid"]["high_level"] == "High", b["grid"]
    assert b["grid"]["levels"] == ["High", "Medium", "Low"], b["grid"]
    assert b["grid"]["by_level"]["power"]["Medium"] == 1, b["grid"]["by_level"]
    assert b["grid"]["by_level"]["interest"]["Medium"] == 1, b["grid"]["by_level"]
    assert b["grid"]["unrecorded"] == {"power": 1, "interest": 1}, b["grid"]["unrecorded"]
    assert "THREE" in b["note"], b["note"]

    # ③ A MEDIUM-POWER BLOCKER IS NOW MENTIONED. `high_power_blockers` demands High, so Adjacent
    # Owner appeared NOWHERE in this response — while the PDF's "Blockers" KPI counted it, so the
    # page showed a count of 2 above a table of 1 with nothing saying why.
    assert b["stance"]["Blocker"] == 2, b["stance"]
    assert {x["organization"] for x in b["blockers"]} == {"BigBank", "AdjCo"}, b["blockers"]
    assert len(b["high_power_blockers"]) == 1, b["high_power_blockers"]
    # the discrepancy that was on the page, as an assertion: the count and the list must agree
    assert b["stance"]["Blocker"] == len(b["blockers"]), (b["stance"], b["blockers"])

    # ④ THE BUCKET LIST IS OWNED BY THE ENGINE, so a consumer cannot enumerate four of five by hand
    # — which `report_builders/precon.py` did, and which is why the circulated PDF would have
    # dropped the new bucket while its KPI counted the members.
    from aec_api import stakeholder as _stake
    assert set(_stake.QUADRANT_ORDER) == set(b["quadrants"]), \
        (sorted(_stake.QUADRANT_ORDER), sorted(b["quadrants"]))

    # the coverage sentence tells "nothing to grid" from "everything gridded"
    assert "1 of 6" in b["grid"]["reason"], b["grid"]["reason"]
    _empty = c.post("/projects", json={"name": "Empty"}).json()["id"]
    assert c.get(f"/projects/{_empty}/stakeholders/analysis").json()["grid"]["reason"] \
        == "no active stakeholder is recorded"

    # the Stakeholder Analysis report is registered + builds (PDF endpoint)
    assert any(r["id"] == "stakeholder_analysis" for r in c.get("/reports").json()["reports"])
    rp = c.get(f"/projects/{pid}/reports/stakeholder_analysis.pdf")
    assert rp.status_code == 200 and rp.content[:4] == b"%PDF", rp.status_code

print(f"stakeholder OK — quadrants "
      f"{ {k: v['count'] for k, v in a['quadrants'].items()} }, {len(a['high_power_blockers'])} blocker(s)")
print("STAKEHOLDER-MEDIUM: Medium/Medium sits on the low side of a 2x2 split at High and the "
      "response says so; an unassessed party is its own bucket rather than 'monitor with minimal "
      "effort'; blockers are listed at every power level so the count and the table agree; and the "
      "bucket list is owned by the engine so the PDF cannot enumerate four of five")
print("test_stakeholder OK")
