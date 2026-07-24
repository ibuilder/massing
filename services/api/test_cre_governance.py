"""R20 Tier 2 — CRE-COVENANT (day-count basis + clock start), CRE-AUTHORITY (per-fact-type
authority that GATES), CRE-SUPPLY (evidence-weighted competitive supply), CRE-DECISION-GATE
(unknown evidence blocks).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cre_governance.py"""
import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite:///./test_cre_governance.db"
os.environ["STORAGE_DIR"] = "./test_storage_cregov"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_cre_governance.db"):
    os.remove("./test_cre_governance.db")

from aec_api import covenants, deal_authority, decision_gate, supply_pipeline  # noqa: E402

# =========================== CRE-COVENANT ===========================================================
# 2026-07-01 is a Wednesday. +10 CALENDAR days = 07-11 (a Saturday).
cal = covenants.add_days(date(2026, 7, 1), 10, "calendar")
assert cal["due"] == date(2026, 7, 11) and cal["skipped"] == []
# +10 BUSINESS days skips two weekends -> 07-15, and every skipped day is named
bus = covenants.add_days(date(2026, 7, 1), 10, "business")
assert bus["due"] == date(2026, 7, 15), bus["due"]
assert len(bus["skipped"]) == 4 and all(s["why"] == "weekend" for s in bus["skipped"])
# a holiday inside the run pushes it one more day
hol = covenants.add_days(date(2026, 7, 1), 10, "business", holidays=["2026-07-03"])
assert hol["due"] == date(2026, 7, 16)
assert any(s["why"] == "holiday" for s in hol["skipped"])

# THE TRAP: notice sent 07-01, received 07-06 — the two clock readings give different due dates
ob = {"name": "Casualty notice", "days": 10, "day_basis": "business",
      "clock_start": "our_receipt", "lender_notice_date": "2026-07-01",
      "received_date": "2026-07-06"}
d = covenants.obligation_due(ob)
assert d["computable"] and d["anchor_date"] == "2026-07-06" and d["anchor_source"] == "our receipt"
assert d["clock_start_matters"] is True
assert d["alternate_reading"]["clock_start"] == "lender_notice"
assert d["alternate_reading"]["due_date"] == "2026-07-15"        # 5 days earlier than our reading
assert d["alternate_reading"]["days_difference"] > 0 and "counsel" in d["alternate_reading"]["warning"]
# an obligation with no anchor at all is NOT computable, and says what it needed
assert covenants.obligation_due({"name": "Orphan", "days": 10})["computable"] is False
assert "anchor" in covenants.obligation_due({"name": "Orphan", "days": 10})["reason"]

cal_out = covenants.calendar([
    {"name": "Quarterly statements", "days": 45, "day_basis": "calendar",
     "clock_start": "lender_notice", "period_end": "2026-06-30"},
    {"name": "Annual audit", "days": 120, "day_basis": "calendar", "period_end": "2025-12-31"},
    {"name": "Filed early", "days": 45, "period_end": "2026-05-31", "delivered_date": "2026-06-10"},
    {"name": "Due next week", "days": 30, "period_end": "2026-07-01"},
    {"name": "No anchor", "days": 10},
], as_of=date(2026, 7, 24))
names = {r["name"]: r for r in cal_out["obligations"] if r.get("computable")}
assert names["Quarterly statements"]["due_date"] == "2026-08-14"
assert names["Quarterly statements"]["days_remaining"] == 21
assert names["Quarterly statements"]["risk"] == "ok"              # 21 days out clears the 14-day flag
assert names["Due next week"]["due_date"] == "2026-07-31"
assert names["Due next week"]["risk"] == "due_soon"               # 7 days out trips it
assert names["Annual audit"]["risk"] == "overdue"                 # 2025-12-31 + 120d = 2026-04-30
assert names["Filed early"]["status"] == "filed_on_time"
assert cal_out["counts"]["overdue"] == 1 and cal_out["counts"]["due_soon"] == 1
assert len(cal_out["not_computable"]) == 1
assert cal_out["not_computable"][0]["name"] == "No anchor"

# covenants: untested is NOT passing; a breach inside a cure window reads differently
cov = covenants.test_covenants([
    {"name": "DSCR", "metric": "dscr", "direction": "min", "threshold": 1.25, "cure_days": 30,
     "breach_date": "2026-07-20"},
    {"name": "LTV", "metric": "ltv", "direction": "max", "threshold": 0.65},
    {"name": "Debt yield", "metric": "debt_yield", "direction": "min", "threshold": 0.08},
], actuals={"dscr": 1.10, "ltv": 0.60}, as_of=date(2026, 7, 24))
by = {r["name"]: r for r in cov["covenants"]}
assert by["DSCR"]["tested"] and by["DSCR"]["passing"] is False
assert by["DSCR"]["status"] == "cure_period_open" and by["DSCR"]["cure_ends"] == "2026-08-19"
assert by["LTV"]["passing"] is True and by["LTV"]["headroom"] == 0.05
assert by["Debt yield"]["tested"] is False                        # no actual supplied
assert cov["counts"]["untested"] == 1 and cov["clean"] is False
assert "not a passing one" in cov["note"]
# past the cure window it is a plain breach
late = covenants.test_covenants([{"name": "DSCR", "metric": "dscr", "direction": "min",
                                  "threshold": 1.25, "cure_days": 30, "breach_date": "2026-05-01"}],
                                actuals={"dscr": 1.10}, as_of=date(2026, 7, 24))
assert late["covenants"][0]["status"] == "breach"

reg = covenants.register({"name": "Construction loan", "lender": "Bank",
                          "obligations": [{"name": "Annual audit", "days": 120,
                                           "period_end": "2025-12-31"}],
                          "covenants": [{"name": "DSCR", "metric": "dscr", "direction": "min",
                                         "threshold": 1.25}]},
                         actuals={"dscr": 1.10}, as_of=date(2026, 7, 24))
assert reg["at_risk"] is True and reg["summary"]["overdue_filings"] == 1
assert reg["summary"]["covenant_breaches"] == 1

# =========================== CRE-AUTHORITY ==========================================================
ENTRIES = [
    {"fact_type": "rent_roll", "document": "RR_2026-07-01.xlsx", "as_of": "2026-07-01",
     "reviewer": "analyst"},
    {"fact_type": "operating_statement", "document": "T12_2026-06.xlsx", "as_of": "2026-06-30"},
    {"fact_type": "tax", "document": "Tax_2019.pdf", "as_of": "2019-11-01"},      # very stale
    {"fact_type": "offering", "document": "OM_v3.pdf", "as_of": "2026-06-01",
     "supersedes": ["OM_v2.pdf"]},
    {"fact_type": "offering", "document": "OM_v2.pdf", "as_of": "2025-01-01",
     "authoritative": False},
]
clean = deal_authority.validate(ENTRIES)
assert len(clean) == 5 and clean[0]["freshness_days"] == 45
# two authoritative docs for one fact type is refused
try:
    deal_authority.validate(ENTRIES + [{"fact_type": "rent_roll", "document": "RR_old.xlsx",
                                        "as_of": "2026-01-01"}])
    raise AssertionError("two authoritative rent rolls must be refused")
except ValueError as e:
    assert "exactly one wins" in str(e)
# an undated document is refused — it cannot be judged fresh or stale
try:
    deal_authority.validate([{"fact_type": "tax", "document": "no_date.pdf"}])
    raise AssertionError("an undated entry must be refused")
except ValueError as e:
    assert "as_of" in str(e)
try:
    deal_authority.validate([{"fact_type": "nonsense", "document": "x", "as_of": "2026-01-01"}])
    raise AssertionError("unknown fact type must be refused")
except ValueError:
    pass

a = deal_authority.assess(clean, as_of=date(2026, 7, 24))
assert a["gate"]["passes"] is False                                # tax is stale AND required
stale_types = {s["fact_type"] for s in a["stale"]}
assert "tax" in stale_types and "rent_roll" not in stale_types
assert any(b["fact_type"] == "tax" for b in a["gate"]["blocking"])
rr = next(t for t in a["table"] if t["fact_type"] == "rent_roll")
assert rr["fresh"] is True and rr["age_days"] == 23 and rr["required"] is True
# a table missing a required fact type blocks on the absence, naming it
missing = deal_authority.assess([e for e in clean if e["fact_type"] != "rent_roll"],
                                as_of=date(2026, 7, 24))
assert any(m["fact_type"] == "rent_roll" for m in missing["missing"])
assert any(b["fact_type"] == "rent_roll" for b in missing["gate"]["blocking"])
# a fresh, complete table passes
good = deal_authority.assess([
    {"fact_type": "rent_roll", "document": "RR.xlsx", "as_of": "2026-07-20", "freshness_days": 45},
    {"fact_type": "operating_statement", "document": "T12.xlsx", "as_of": "2026-07-01",
     "freshness_days": 60},
    {"fact_type": "tax", "document": "Tax_2026.pdf", "as_of": "2026-01-15", "freshness_days": 365},
], as_of=date(2026, 7, 24))
assert good["gate"]["passes"] is True and good["counts"]["blocking"] == 0

# =========================== CRE-SUPPLY =============================================================
PROJECTS = [
    {"name": "Tower A", "units": 300, "delivery_date": "2027-06-01", "product_type": "multifamily",
     "loan_recorded": True},
    {"name": "Tower B", "units": 200, "delivery_date": "2027-09-01", "product_type": "multifamily",
     "permit_issued": True},
    {"name": "Rendering C", "units": 400, "delivery_date": "2028-01-01", "product_type": "multifamily",
     "status": "announced"},
    {"name": "Office D", "units": 500, "delivery_date": "2027-06-01", "product_type": "office",
     "loan_recorded": True},
    {"name": "Late E", "units": 250, "delivery_date": "2030-01-01", "product_type": "multifamily",
     "permit_issued": True},
]
sup = supply_pipeline.assess(PROJECTS, window_start="2027-01-01", window_end="2028-06-30",
                             product_type="multifamily")
assert sup["counts"]["competing"] == 3                            # A, B, C (D wrong product, E late)
assert sup["excluded"]["counts"]["wrong_product"] == 1
assert sup["excluded"]["counts"]["out_of_window"] == 1
# a recorded loan counts fully; a permit at 85%; a rendering at 5% and stays "rumored"
assert sup["raw_units"] == 900.0
assert sup["weighted_units"] == round(300 * 1.0 + 200 * 0.85 + 400 * 0.05, 1) == 490.0
assert sup["certain_supply_units"] == 500.0 and sup["rumored_supply_units"] == 400.0
assert sup["discount_pct"] > 45
rendering = next(r for r in sup["competing"] if r["name"] == "Rendering C")
assert rendering["rumored"] is True and rendering["evidence"] == "announced"
# a project with no evidence at all falls to the weakest weight, never an optimistic default
none_ev = supply_pipeline.evidence_of({"name": "X"})
assert none_ev["evidence"] == "unknown" and none_ev["weight"] == 0.05
# explicit flags beat a status label
assert supply_pipeline.evidence_of({"status": "announced", "loan_recorded": True})["evidence"] \
    == "loan_recorded"

idx = supply_pipeline.supply_index(PROJECTS, monthly_absorption=20.0,
                                   window_start="2027-01-01", window_end="2028-06-30",
                                   product_type="multifamily")
assert idx["weighted_index"]["months_of_supply"] == 24.5          # 490 / 20
assert idx["raw_index"]["months_of_supply"] == 45.0               # 900 / 20
assert idx["delta_months"] == 20.5                                # the discount, made visible

# =========================== CRE-DECISION-GATE ======================================================
# nothing supplied -> every gate unknown, and unknown BLOCKS
empty = decision_gate.evaluate({})
assert empty["verdict"] == "blocked" and empty["ready"] is False
assert empty["counts"]["unknown"] >= 5 and empty["counts"]["passed"] <= 2
assert all(g["action"] for g in empty["blocking"])                # every block says what to do
assert "must never read as a pass" in empty["note"]

FULL = {
    "cited_answer": {"coverage": 1.0, "fully_cited": True, "uncited_claims": []},
    "comps": {"statistics": {"price_psf": {"n": 4, "worst_tier": "confirmed", "unattributed": 0}}},
    "t12": {"tie_out": {"reconciles": True}, "adjusted_noi": 454000.0, "unmapped_count": 0},
    "rent_scrub": {"clean": True, "counts": {"ran": 7, "failed": 0, "not_applicable": 0}},
    "authority": {"gate": {"passes": True, "blocking": []}},
    "exhibits": ["Rent roll", "T-12", "Comps"],
    "sign_off": {"by": "Dana Reyes", "at": "2026-07-24"},
}
ready = decision_gate.evaluate(FULL, required_exhibits=["Rent roll", "T-12", "Comps"])
assert ready["verdict"] == "ready" and ready["ready"] is True
assert ready["counts"]["failed"] == 0 and ready["counts"]["unknown"] == 0

# each individual failure blocks, with a specific reason
low_cov = decision_gate.evaluate({**FULL, "cited_answer": {"coverage": 0.6, "uncited_claims": ["x"]}})
assert low_cov["ready"] is False
assert next(g for g in low_cov["gates"] if g["gate"] == "sourced")["status"] == "fail"

weak = decision_gate.evaluate({**FULL, "comps": {"statistics": {
    "price_psf": {"n": 2, "worst_tier": "unknown", "unattributed": 1}}}})
g = next(x for x in weak["gates"] if x["gate"] == "comps_tiered")
assert g["status"] == "fail" and g["unattributed"] == 1

untied = decision_gate.evaluate({**FULL, "t12": {"tie_out": {"reconciles": False},
                                                 "adjusted_noi": None, "unmapped_count": 1}})
assert next(x for x in untied["gates"] if x["gate"] == "income_tied")["status"] == "fail"

# "the team" is not a named person
role = decision_gate.evaluate({**FULL, "sign_off": {"by": "the team"}})
assert next(x for x in role["gates"] if x["gate"] == "signed_off")["status"] == "fail"
# a missing exhibit is named
ex = decision_gate.evaluate({**FULL, "exhibits": ["Rent roll"]},
                            required_exhibits=["Rent roll", "T-12"])
gx = next(x for x in ex["gates"] if x["gate"] == "exhibits")
assert gx["status"] == "fail" and gx["missing"] == ["T-12"]

# =========================== routes =================================================================
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Gov"}).json()["id"]

    r = c.post(f"/projects/{pid}/loan/covenants",
               json={"loan": {"name": "Loan", "obligations": [
                         {"name": "Annual audit", "days": 120, "period_end": "2025-12-31"}],
                     "covenants": [{"name": "DSCR", "metric": "dscr", "direction": "min",
                                    "threshold": 1.25}]},
                     "actuals": {"dscr": 1.1}})
    assert r.status_code == 200 and r.json()["at_risk"] is True, r.text

    r = c.put(f"/projects/{pid}/deal-room/authority", json={"entries": ENTRIES})
    assert r.status_code == 200 and r.json()["assessment"]["gate"]["passes"] is False, r.text
    assert c.get(f"/projects/{pid}/deal-room/authority").json()["counts"]["stale"] >= 1
    bad = c.put(f"/projects/{pid}/deal-room/authority",
                json={"entries": [{"fact_type": "tax", "document": "x"}]})
    assert bad.status_code == 422
    # the bad PUT left the good table intact
    assert c.get(f"/projects/{pid}/deal-room/authority").json()["counts"]["declared"] >= 3

    r = c.post(f"/projects/{pid}/supply/competitive",
               json={"projects": PROJECTS, "window_start": "2027-01-01",
                     "window_end": "2028-06-30", "product_type": "multifamily",
                     "monthly_absorption": 20.0})
    assert r.status_code == 200 and r.json()["delta_months"] == 20.5, r.text

    r = c.post(f"/projects/{pid}/decision-gate", json={"evidence": {}})
    assert r.status_code == 200 and r.json()["verdict"] == "blocked"
    r = c.post(f"/projects/{pid}/decision-gate",
               json={"evidence": FULL, "required_exhibits": ["Rent roll", "T-12", "Comps"]})
    assert r.json()["ready"] is True, r.json()["blocking"]

print("CRE-GOV OK - COVENANT counts days honestly (10 calendar -> Jul 11; 10 BUSINESS -> Jul 15 "
      "naming all four skipped weekend days; a holiday pushes to Jul 16) and flags THE trap: a "
      "notice sent Jul 1 but received Jul 6 gives two different due dates, both shown with a "
      "counsel warning; covenants with no actual are UNTESTED not passing, and a breach inside an "
      "open cure window reads differently from one past it. AUTHORITY refuses two authoritative "
      "docs per fact type and any undated entry, and GATES on a stale required tax bill / a missing "
      "rent roll. SUPPLY discounts 900 raw units to 490 by recorded evidence (loan 100%, permit 85%, "
      "rendering 5% and still 'rumored'), excludes the office and the 2030 delivery with reasons, "
      "and shows 45.0 vs 24.5 months of supply so the discount is visible. DECISION-GATE blocks on "
      "an empty evidence set because unknown != pass, passes a complete one, and fails "
      "individually on thin coverage, an unattributed comp, a failed tie-out, 'the team' as a "
      "signer, and a missing exhibit — every block carrying the action to take.")
