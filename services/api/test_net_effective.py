"""CRE-NER (R20) — net effective rent: the straight-line and discounted forms over the lease
module's own concession fields, the portfolio roll-up, and the route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_net_effective.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_net_effective.db"
os.environ["STORAGE_DIR"] = "./test_storage_ner"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_net_effective.db"):
    os.remove("./test_net_effective.db")

from aec_api import net_effective as ne  # noqa: E402

# --- the textbook case: 12-month lease, one month free, no TI ---------------------------------------
# $1,200/mo for 12 months with 1 free month -> straight-line NER = (14400 - 1200)/1 yr = $13,200/yr
simple = {"tenant": "Textbook", "rentable_sf": 1000, "base_rent_annual": 14400,
          "free_rent_months": 1, "start_date": "2026-01-01", "end_date": "2027-01-01"}
r = ne.lease_ner(simple)
assert r["term_months"] == 12 and r["gross_rent_term"] == 14400.0
assert r["free_rent"] == 1200.0 and r["ti_total"] == 0.0
assert r["ner_annual_straight_line"] == 13200.0, r["ner_annual_straight_line"]
# the discounted form is close but not identical — the abatement is at the FRONT, so it costs more
assert r["ner_annual_discounted"] < r["ner_annual_straight_line"], r
assert r["lc_included"] is False and r["leasing_commission"] == 0.0

# --- escalation compounds annually, not monthly ----------------------------------------------------
esc = {"tenant": "Step", "rentable_sf": 1000, "base_rent_annual": 12000, "escalation_pct": 10.0,
       "start_date": "2026-01-01", "end_date": "2028-01-01"}
rents = ne.monthly_rents(12000, 24, 10.0)
assert abs(rents[0] - 1000.0) < 1e-9 and abs(rents[11] - 1000.0) < 1e-9      # year 1 flat
assert abs(rents[12] - 1100.0) < 1e-9                                        # year 2 steps 10%
assert abs(ne.lease_ner(esc)["gross_rent_term"] - (12000 + 13200)) < 1e-6

# --- a TI-heavy office deal: the discounted form penalizes the up-front cheque ---------------------
office = {"tenant": "Acme", "suite": "400", "rentable_sf": 10000, "base_rent_annual": 300000,
          "escalation_pct": 3.0, "free_rent_months": 6, "ti_allowance_psf": 50,
          "start_date": "2026-01-01", "end_date": "2031-01-01"}
o = ne.lease_ner(office)
assert o["free_rent"] == 150000.0 and o["ti_total"] == 500000.0
assert o["landlord_costs"] == 650000.0
assert o["ner_annual_discounted"] < o["ner_annual_straight_line"] < o["face_rent_annual"]
assert o["concession_load_pct"] > 40 and o["face_to_ner_delta_pct"] > 40
assert o["ner_psf_discounted"] == round(o["ner_annual_discounted"] / 10000, 2)
# a leasing commission only appears when a rate is supplied, and lowers NER further
with_lc = ne.lease_ner(office, lc_pct=4.0)
assert with_lc["lc_included"] and with_lc["leasing_commission"] > 0
assert with_lc["ner_annual_discounted"] < o["ner_annual_discounted"]
# a higher discount rate penalizes the front-loaded concession more
assert ne.lease_ner(office, discount_rate=0.15)["ner_annual_discounted"] < o["ner_annual_discounted"]

# --- unusable leases are named, never silently dropped ---------------------------------------------
bad = {"tenant": "NoDates", "rentable_sf": 500, "base_rent_annual": 20000}
assert ne.lease_ner(bad)["computable"] is False
roll = ne.roll_up([simple, office, bad])
assert roll["lease_count"] == 2 and roll["skipped_count"] == 1
assert roll["skipped"][0]["tenant"] == "NoDates" and "start date" in roll["skipped"][0]["reason"]
assert roll["face_gpr_annual"] == 314400.0                       # 14,400 + 300,000
assert roll["ner_gpr_annual_discounted"] < roll["face_gpr_annual"]
assert roll["face_to_ner_delta_annual"] > 0 and roll["concession_load_pct"] > 0
assert roll["leases"][0]["tenant"] == "Acme"                     # worst face-vs-NER gap first

# --- the route ------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "NER"}).json()["id"]
    ids = []
    for lease in (simple, office):
        rr = c.post(f"/projects/{pid}/modules/lease", json={"data": lease})
        assert rr.status_code in (200, 201), rr.text
        ids.append(rr.json()["id"])
    # a DRAFT lease is not in the rent roll, so it must not be in the NER roll-up either
    draft_only = c.get(f"/projects/{pid}/rent-roll/net-effective").json()
    assert draft_only["lease_count"] == 0 and draft_only["excluded_not_active"] == 2, draft_only
    for rid in ids:                                              # execute both -> active
        assert c.post(f"/projects/{pid}/modules/lease/{rid}/transition",
                      json={"action": "execute"}).status_code == 200
    r = c.get(f"/projects/{pid}/rent-roll/net-effective")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lease_count"] == 2 and body["lc_included"] is False
    assert body["excluded_not_active"] == 0
    assert body["ner_gpr_annual_discounted"] < body["face_gpr_annual"]
    # the face rent the plain rent roll reports is the same number, unchanged
    assert c.get(f"/projects/{pid}/rent-roll").json()["base_rent_annual"] == body["face_gpr_annual"]
    lc = c.get(f"/projects/{pid}/rent-roll/net-effective?lc_pct=4").json()
    assert lc["lc_included"] and lc["ner_gpr_annual_discounted"] < body["ner_gpr_annual_discounted"]

print("NET-EFFECTIVE OK - the textbook case ties exactly ($1,200/mo, one month free -> $13,200/yr "
      "straight-line) and the discounted form comes in lower because the abatement is front-loaded; "
      "escalation steps on the annual anniversary, not monthly; a TI-heavy office deal shows a 40%+ "
      "concession load with discounted < straight-line < face, a leasing commission appears ONLY "
      "when a rate is supplied, and a higher discount rate penalizes the up-front cheque further; "
      "leases missing dates are named in `skipped` rather than dropped; the roll-up ranks the worst "
      "face-vs-NER gap first and the route serves it while the plain rent roll still reports face.")
