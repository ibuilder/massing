"""R20 Tier 1 — CRE-COMP-TIER (source hierarchy decides ties, worst tier carried forward),
CRE-T12 (normalization behind a hard tie-out gate + add-back questions), CRE-RRSCRUB (rent roll vs
income, with checks that report when they CANNOT run).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cre_deal_desk.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cre_deal_desk.db"
os.environ["STORAGE_DIR"] = "./test_storage_credesk"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_cre_deal_desk.db"):
    os.remove("./test_cre_deal_desk.db")

from aec_api import comp_tier, rent_scrub  # noqa: E402
from aec_api import t12 as t12e  # noqa: E402

# =========================== CRE-COMP-TIER ==========================================================
assert comp_tier.tier_of("County recorder deed")["tier"] == "recorded_sale"
assert comp_tier.tier_of("Verified with the buyer")["tier"] == "verified"
assert comp_tier.tier_of("Vendor estimate / AVM")["tier"] == "estimate"
assert comp_tier.tier_of("Asking price on the MLS")["tier"] == "listing"
assert comp_tier.tier_of("Broker OM")["tier"] == "broker"
# an unrecognized source is the WEAKEST tier, never an optimistic middle
u = comp_tier.tier_of("Bob said so")
assert u["tier"] == "unknown" and u["matched"] is False and u["rank"] == 7
assert comp_tier.tier_of(None)["tier"] == "unknown"

# two comps for the SAME address disagree: the recorded sale must win, the loser stays visible
comps = [
    {"data": {"address": "100 Main St", "price_psf": 250, "cap_rate": 5.5, "source": "Broker OM"}},
    {"data": {"address": "100 Main St", "price_psf": 210, "cap_rate": 6.2, "source": "County recorded deed"}},
    {"data": {"address": "200 Oak Ave", "price_psf": 205, "cap_rate": 6.1, "source": "Verified with seller"}},
    {"data": {"address": "300 Elm Rd", "price_psf": 400, "cap_rate": 4.0, "source": "Asking price, listing site"}},
]
res = comp_tier.resolve_conflicts(comps)
assert res["comp_count"] == 3 and res["conflict_count"] == 1, res["comp_count"]
main = next(c for c in res["comps"] if c["address"] == "100 Main St")
assert main["tier"] == "recorded_sale" and main["price_psf"] == 210      # the deed wins, not the OM
conflict = res["conflicts"][0]
assert conflict["kept_tier"] == "recorded_sale"
assert any(d["field"] == "price_psf" and d["kept"] == 210 and d["outranked"] == 250
           for d in conflict["value_deltas"]), conflict["value_deltas"]

# the band reports the WEAKEST tier it rests on — here an asking price
stat = comp_tier.statistic(comps, "price_psf")
assert stat["n"] == 3 and stat["worst_tier"] == "listing", stat
assert stat["best_tier"] == "recorded_sale" and stat["conflicts_resolved"] == 1
assert stat["median"] == 210.0 and stat["min"] == 205.0 and stat["max"] == 400.0
assert "Listing" in stat["note"] or "listing" in stat["note"]   # the note names the weak source
# drop the asking-price comp and the band strengthens
strong = comp_tier.statistic(comps[:3], "price_psf")
assert strong["worst_tier"] == "verified", strong["worst_tier"]
assert comp_tier.statistic([], "price_psf")["n"] == 0

# =========================== CRE-T12 ================================================================
assert t12e.classify("Management Fee")["category"] == "management_fee"
assert t12e.classify("Property management fee")["category"] == "management_fee"   # longest wins
assert t12e.classify("Electric - common area")["category"] == "utilities"
assert t12e.classify("Roof replacement - capital")["treatment"] == "capital"
assert t12e.classify("Insurance settlement (one-time)")["treatment"] == "one_time"
assert t12e.classify("Blorptastic widget")["category"] == "unmapped"
assert t12e._num("(1,200.50)") == -1200.50 and t12e._num("$3,000") == 3000.0

LINES = [
    {"description": "Gross potential rent", "amount": 1_000_000},
    {"description": "Vacancy loss", "amount": -70_000},
    {"description": "Other income - laundry", "amount": 30_000},
    {"description": "Payroll", "amount": 120_000},
    {"description": "Repairs & maintenance", "amount": 80_000},
    {"description": "Utilities", "amount": 90_000},
    {"description": "Property taxes", "amount": 140_000},
    {"description": "Insurance", "amount": 40_000},
    {"description": "Management fee", "amount": 36_000},
]
# income = 1,000,000 - 70,000 + 30,000 = 960,000 ; expense = 506,000 ; NOI = 454,000
ok = t12e.normalize({"lines": LINES}, units=100)
assert ok["tie_out"]["reconciles"] is True, ok["tie_out"]
assert ok["mapped_totals"] == {"income": 960000.0, "expense": 506000.0, "noi": 454000.0}
assert ok.get("stopped") is not True and ok["adjusted_noi"] == 454000.0
assert ok["unmapped_count"] == 0

# THE GATE: an unmappable line breaks the tie-out against stated source totals -> no adjusted NOI
bad = t12e.normalize({"lines": LINES + [{"description": "Blorptastic widget", "amount": 25_000}],
                      "totals": {"income": 960_000, "expense": 531_000, "noi": 429_000}})
assert bad["stopped"] is True and bad["adjusted_noi"] is None
assert bad["tie_out"]["reconciles"] is False
assert bad["unmapped_count"] == 1 and bad["unmapped"][0]["amount"] == 25000.0
assert any(i["issue"] == "unmapped line" for i in bad["reconciling_items"])
assert "STOPPED" in bad["note"]

# one-time items lift adjusted NOI above trailing (a one-time EXPENSE is added back)
ot = t12e.normalize({"lines": LINES + [{"description": "Storm damage repair (one-time)", "amount": 50_000}]})
assert ot["tie_out"]["reconciles"] and ot["adjusted_noi"] > ot["mapped_totals"]["noi"]
assert ot["adjusted_noi"] == 454000.0 and ot["mapped_totals"]["noi"] == 404000.0
assert len(ot["one_time_items"]) == 1

# capital sits BELOW the line: it must not move NOI at all
cap = t12e.normalize({"lines": LINES + [{"description": "Roof replacement - capital", "amount": 200_000}]})
assert cap["mapped_totals"]["noi"] == 454000.0 and cap["capital_items"][0]["amount"] == 200000.0

# run-rate: the last three months annualized, compared against trailing
months = t12e.normalize({"lines": [
    {"description": "Gross potential rent", "months": [10_000] * 9 + [12_000] * 3},
    {"description": "Utilities", "months": [1_000] * 12}]})
rr = {r["category"]: r for r in months["run_rate_vs_trailing"]}
assert rr["gross_potential_rent"]["trailing"] == 126000.0
assert rr["gross_potential_rent"]["run_rate"] == 144000.0     # 12k x 3 x 4
assert rr["gross_potential_rent"]["delta"] == 18000.0

# add-back questions: the owner-operated tells, as QUESTIONS with numbers
owner_run = t12e.normalize({"lines": [
    {"description": "Gross potential rent", "amount": 1_000_000},
    {"description": "Utilities", "amount": 90_000}]}, units=100)
checks = {q["check"]: q for q in owner_run["add_back_questions"]}
assert "management_fee" in checks and checks["management_fee"]["severity"] == "high"
assert "payroll" in checks and "property_taxes" in checks and "insurance" in checks
assert "repairs_maintenance" in checks                          # $0/unit is below market
assert checks["management_fee"]["pct_of_income"] == 0.0
# and a properly-staffed statement raises none of them
assert not any(q["check"] in ("management_fee", "payroll") for q in ok["add_back_questions"])

# =========================== CRE-RRSCRUB ============================================================
leases = [
    {"tenant": "A", "suite": "101", "base_rent_annual": 120_000, "end_date": "2030-01-01"},
    {"tenant": "B", "suite": "102", "base_rent_annual": 100_000, "end_date": "2030-01-01"},
]
# with NO income and NO units, every dependent check reports not-run — never a silent pass
bare = rent_scrub.scrub(leases)
by = {c["check"]: c for c in bare["checks"]}
assert by["scheduled_vs_gpr"]["applicable"] is False
assert "gross_potential_rent" in by["scheduled_vs_gpr"]["needs"]
assert by["occupied_without_lease"]["applicable"] is False
assert by["bad_debt_vs_occupancy"]["applicable"] is False
assert bare["counts"]["not_applicable"] >= 5 and "never as passing" in bare["coverage_note"]
assert bare["clean"] is True                                     # the one check that ran, passed

# scheduled rent 220k vs GPR 200k = 10% apart -> a diligence item at the 5% threshold
gap = rent_scrub.scrub(leases, income={"gross_potential_rent": 200_000})
sv = next(c for c in gap["checks"] if c["check"] == "scheduled_vs_gpr")
assert sv["applicable"] and sv["passed"] is False and sv["variance_pct"] == 10.0
assert sv["tolerance_pct"] == 5.0 and gap["clean"] is False
# inside tolerance it passes
assert next(c for c in rent_scrub.scrub(leases, income={"gross_potential_rent": 215_000})["checks"]
            if c["check"] == "scheduled_vs_gpr")["passed"] is True

# unit-level checks
units = [
    {"unit": "101", "occupied": True, "receivable": 0, "arrears_by_month": [0, 0, 0]},
    {"unit": "103", "occupied": True, "receivable": 500},                       # no lease on file
    {"unit": "104", "occupied": False, "receivable": 900},                      # vacant w/ receivable
    {"unit": "105", "occupied": True, "receivable": 0, "arrears_by_month": [100, 250, 700]},
]
full = rent_scrub.scrub(leases, income={"gross_potential_rent": 220_000, "bad_debt": 30_000,
                                        "prior_bad_debt": 10_000, "occupancy_pct": 94.0,
                                        "prior_occupancy_pct": 94.3}, units=units)
c = {x["check"]: x for x in full["checks"]}
assert c["occupied_without_lease"]["passed"] is False and "103" in c["occupied_without_lease"]["units"]
assert c["vacant_with_receivable"]["passed"] is False
assert c["vacant_with_receivable"]["units"][0]["unit"] == "104"
assert c["arrears_rising"]["passed"] is False and c["arrears_rising"]["units"][0]["unit"] == "105"
assert c["bad_debt_vs_occupancy"]["passed"] is False              # 3x bad debt, flat occupancy
assert c["scheduled_vs_gpr"]["passed"] is True                    # 220k vs 220k
assert full["counts"]["not_applicable"] == 1                      # only rent_vs_executed lacks input
assert len(full["findings"]) == 4 and full["clean"] is False

# executed-terms mismatch + expired lease
mismatch = rent_scrub.scrub([
    {"tenant": "C", "suite": "201", "base_rent_annual": 100_000,
     "executed_rent_annual": 92_000, "end_date": "2030-01-01"},
    {"tenant": "D", "suite": "202", "base_rent_annual": 50_000, "end_date": "2020-01-01"}])
m = {x["check"]: x for x in mismatch["checks"]}
assert m["rent_vs_executed_terms"]["passed"] is False
assert m["rent_vs_executed_terms"]["leases"][0]["stated"] == 100000.0
assert m["expired_still_active"]["passed"] is False and m["expired_still_active"]["leases"][0]["tenant"] == "D"

# =========================== routes =================================================================
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c2:
    pid = c2.post("/projects", json={"name": "Desk"}).json()["id"]
    for comp in comps:
        assert c2.post(f"/projects/{pid}/modules/comparable",
                       json={"data": comp["data"]}).status_code in (200, 201)
    r = c2.get(f"/projects/{pid}/comps/tiered")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["comp_count"] == 3 and body["conflict_count"] == 1
    assert body["statistics"]["price_psf"]["worst_tier"] == "listing"

    r = c2.post(f"/projects/{pid}/t12/normalize", json={"t12": {"lines": LINES}, "units": 100})
    assert r.status_code == 200 and r.json()["adjusted_noi"] == 454000.0, r.text
    r = c2.post(f"/projects/{pid}/t12/normalize",
                json={"t12": {"lines": LINES + [{"description": "Blorp", "amount": 25_000}],
                              "totals": {"income": 960_000, "expense": 531_000, "noi": 429_000}}})
    assert r.json()["stopped"] is True and r.json()["adjusted_noi"] is None

    for lease in leases:                       # the module requires rentable_sf; execute needs dates
        payload = {**lease, "rentable_sf": 1000, "start_date": "2026-01-01"}
        cr = c2.post(f"/projects/{pid}/modules/lease", json={"data": payload})
        assert cr.status_code in (200, 201), cr.text
        rid = cr.json()["id"]
        tr = c2.post(f"/projects/{pid}/modules/lease/{rid}/transition", json={"action": "execute"})
        assert tr.status_code == 200, tr.text
    r = c2.post(f"/projects/{pid}/rent-roll/scrub",
                json={"income": {"gross_potential_rent": 200_000}, "units": units})
    assert r.status_code == 200, r.text
    sc = r.json()
    assert sc["lease_count"] == 2 and sc["clean"] is False
    assert any(f["check"] == "scheduled_vs_gpr" for f in sc["findings"])

print("CRE-DESK OK - COMP-TIER ranks sources (a county deed outranks the OM for the same address, "
      "the overruled $250/sf stays visible beside the kept $210, and an unrecognized source lands "
      "in the WEAKEST tier) while every band names the weakest tier it rests on ('listing' here, "
      "'verified' once the asking-price comp is dropped); T-12 maps to the operating chart and the "
      "TIE-OUT IS A GATE — an unmapped $25k line yields stopped=true with adjusted_noi=null instead "
      "of a plausible number — with one-time expense added back, capital kept below the line, "
      "last-3-annualized run-rate, and owner-operated add-backs raised as questions; RRSCRUB flags "
      "the 10% scheduled-vs-GPR gap at the 5% threshold, the occupied unit with no lease, the vacant "
      "unit with a receivable, monotonically rising arrears, tripled bad debt against flat occupancy, "
      "an executed-terms mismatch and an expired-but-active lease — and every check lacking its "
      "inputs reports applicable=false with what it needed, never a pass.")
