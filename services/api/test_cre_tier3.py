"""R20 Tier 3 — CRE-HOLDSELL (hold vs sell on incremental cash flows), CRE-CLAUSE (playbook +
deviation register where an unreviewed clause is an open risk), CRE-ICMEMO (a memo that refuses to
render rather than invent a number).
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cre_tier3.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cre_tier3.db"
os.environ["STORAGE_DIR"] = "./test_storage_cre3"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_cre_tier3.db"):
    os.remove("./test_cre_tier3.db")

from aec_api import clause_playbook as cp  # noqa: E402
from aec_api import hold_sell  # noqa: E402

# =========================== CRE-HOLDSELL ===========================================================
# needs today's income and today's cap — without them there is no call to make
bad = hold_sell.analyze({"noi_annual": 0, "exit_cap_now": 0.06})
assert bad["computable"] is False and "noi_annual" in bad["reason"]

BASE = {"noi_annual": 1_000_000, "exit_cap_now": 0.06, "selling_cost_pct": 0.02,
        "loan_balance_now": 8_000_000, "noi_growth_pct": 3.0}
h = hold_sell.analyze(BASE, hurdle_rate=0.12, max_years=10)
assert h["computable"] is True
# sell now: 1,000,000 / 0.06 = 16,666,667 gross, less 2% and the 8M payoff
assert abs(h["sell_now"]["gross_sale"] - 16_666_666.67) < 1.0
assert abs(h["sell_now"]["net_proceeds"] - (16_666_666.67 - 333_333.33 - 8_000_000)) < 2.0
assert len(h["years"]) == 10 and h["years"][0]["hold_years"] == 1
# NOI grows, so a flat cap makes the future sale bigger than today's
assert h["years"][4]["noi_at_exit"] > 1_000_000
assert h["years"][4]["exit_cap"] == 0.06                     # no drift supplied -> flat
# growing NOI at a flat cap clears a 12% hurdle on an 8.4M equity stub
assert h["breakeven_hold_years"] is not None and h["recommendation"] == "hold"

# cap EXPANSION (a worse exit) is an explicit input and it changes the answer
drift = hold_sell.analyze({**BASE, "cap_drift_bps_per_year": 50}, hurdle_rate=0.12)
assert drift["assumptions"]["cap_drift_bps_per_year"] == 50.0
assert drift["years"][4]["exit_cap"] > h["years"][4]["exit_cap"]
assert drift["years"][4]["net_proceeds_at_exit"] < h["years"][4]["net_proceeds_at_exit"]
# a hurdle nobody can clear returns 'sell' and says so plainly rather than forcing a hold
impossible = hold_sell.analyze(BASE, hurdle_rate=5.0)
assert impossible["breakeven_hold_years"] is None and impossible["recommendation"] == "sell"
assert "clears the hurdle" in impossible["note"]
# amortization reduces the payoff, capex reduces the stream
amort = hold_sell.analyze({**BASE, "annual_loan_amortization": 200_000}, hurdle_rate=0.12)
assert amort["years"][4]["loan_payoff"] == 7_000_000.0        # 8M - 5x200k
assert amort["years"][4]["net_proceeds_at_exit"] > h["years"][4]["net_proceeds_at_exit"]
capex = hold_sell.analyze({**BASE, "capex_per_year": 300_000}, hurdle_rate=0.12)
assert capex["years"][4]["incremental_irr"] < h["years"][4]["incremental_irr"]

# =========================== CRE-CLAUSE =============================================================
assert len(cp.STARTER_CLAUSES) >= 10
assert all(c.get("refuse") for c in cp.STARTER_CLAUSES)       # every starter clause has a red line
pb = cp.validate({"consultant": cp.STARTER_CLAUSES})
assert len(pb["consultant"]) == len(cp.STARTER_CLAUSES)
# a clause with no red line is not a standard
try:
    cp.validate({"x": [{"clause": "Vague", "accept": "whatever"}]})
    raise AssertionError("a clause with no refuse position must be refused")
except ValueError as e:
    assert "red line" in str(e)
for bad_pb, why in (({"x": [{"clause": "A", "refuse": "no"}, {"clause": "a", "refuse": "no"}]}, "dup"),
                    ({"x": [{"clause": "A", "severity": "urgent", "refuse": "no"}]}, "severity"),
                    ({"x": []}, "empty")):
    try:
        cp.validate(bad_pb)
        raise AssertionError(f"expected rejection: {why}")
    except ValueError:
        pass

clauses = pb["consultant"]
rev = cp.review(clauses, [
    {"clause": "Standard of care", "position": "accept"},
    {"clause": "Indemnity", "position": "refuse", "note": "one-way", "reference": "§7.2"},
    {"clause": "Payment terms", "position": "negotiate"},
    {"clause": "Retainage", "position": "absent"},
    {"clause": "Nonexistent clause", "position": "accept"},
], document="Consultant MSA v2")
c = {r["clause"]: r for r in rev["clauses"]}
assert c["Indemnity"]["deviation"] is True and c["Indemnity"]["reference"] == "§7.2"
assert c["Indemnity"]["red_line"] and c["Standard of care"]["deviation"] is False
assert rev["unknown_clauses"] == ["Nonexistent clause"]
# the clauses NOBODY looked at are reported, not assumed fine
reviewed = {r["clause"] for r in rev["clauses"]}
not_reviewed = {r["clause"] for r in rev["not_reviewed"]}
assert "Limitation of liability" in not_reviewed and not (reviewed & not_reviewed)
assert rev["counts"]["not_reviewed"] == len(clauses) - 4
# a high-severity refusal (or an unreviewed high clause) blocks
assert rev["verdict"] == "blocked" and rev["counts"]["high_severity_open"] >= 1
assert "NOT REVIEWED" in rev["note"] and "Not legal advice" in rev["note"]
# deviations sort first, high severity first
assert rev["clauses"][0]["deviation"] is True
assert rev["clauses"][0]["severity"] == "high"

# a full clean review is acceptable
clean = cp.review(clauses, [{"clause": x["clause"], "position": "accept"} for x in clauses])
assert clean["verdict"] == "acceptable" and clean["counts"]["not_reviewed"] == 0
# one medium negotiation, everything else accepted -> negotiate, not blocked
mixed = cp.review(clauses, [{"clause": x["clause"],
                             "position": "negotiate" if x["clause"] == "Retainage" else "accept"}
                            for x in clauses])
assert mixed["verdict"] == "negotiate"

# =========================== routes + CRE-ICMEMO ====================================================
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import reports  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

DEAL = {
    "timing": {"construction_months": 6, "leaseup_months": 3, "hold_years": 2,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 1_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Build", "amount": 4_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 5}],
    "debt": {"ltc": 0.6, "rate": 0.08, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 700_000, "other_income_annual": 0,
                   "opex_annual": 250_000, "stabilized_occ": 0.95, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.06, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
}

assert any(x["id"] == "ic_memo" for x in reports.catalog())

with TestClient(app) as c2:
    pid = c2.post("/projects", json={"name": "T3"}).json()["id"]

    # --- the memo REFUSES to render with no scenario, and says exactly what is missing
    with SessionLocal() as db:
        empty_memo = reports.build(db, pid, "ic_memo")
    assert ("Status", "CANNOT RENDER") in empty_memo.kpis
    assert any(t["name"] == "Missing required inputs" for t in empty_memo.tables)
    assert any(t["name"] == "What to do" for t in empty_memo.tables)

    # --- with a solved, published scenario it renders in full
    sid = c2.post("/proforma/scenarios",
                  json={"name": "Base", "project_id": pid, "assumptions": DEAL}).json()["id"]
    for action in ("submit", "approve", "publish"):
        assert c2.post(f"/proforma/scenarios/{sid}/review",
                       json={"action": action}).status_code == 200
    with SessionLocal() as db:
        memo = reports.build(db, pid, "ic_memo")
    kpis = dict(memo.kpis)
    assert "CANNOT RENDER" not in kpis.get("Status", "")
    assert "published" in kpis["Basis scenario"]
    assert kpis["Exit cap"] == "6.00%"
    names = [t["name"] for t in memo.tables]
    assert "The ask" in names and "Returns" in names and "Governance" in names
    gov = next(t for t in memo.tables if t["name"] == "Governance")
    assert any(row[0] == "Review status" and row[1] == "published" for row in gov["rows"])
    pdf = c2.get(f"/projects/{pid}/reports/ic_memo.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    # --- hold/sell + clause routes
    r = c2.post(f"/projects/{pid}/hold-sell", json={"inputs": BASE, "hurdle_rate": 0.12})
    assert r.status_code == 200 and r.json()["recommendation"] == "hold", r.text

    assert c2.get(f"/projects/{pid}/contracts/playbook").json()["playbook"] == {}
    r = c2.put(f"/projects/{pid}/contracts/playbook",
               json={"playbook": {"consultant": cp.STARTER_CLAUSES}})
    assert r.status_code == 200 and len(r.json()["playbook"]["consultant"]) >= 10, r.text
    assert c2.put(f"/projects/{pid}/contracts/playbook",
                  json={"playbook": {"x": [{"clause": "No red line"}]}}).status_code == 422
    # the bad PUT left the good playbook intact
    assert "consultant" in c2.get(f"/projects/{pid}/contracts/playbook").json()["playbook"]
    r = c2.post(f"/projects/{pid}/contracts/review",
                json={"contract_type": "consultant", "document": "MSA v2",
                      "findings": [{"clause": "Indemnity", "position": "refuse"}]})
    assert r.status_code == 200 and r.json()["verdict"] == "blocked", r.text
    assert r.json()["counts"]["not_reviewed"] >= 9
    # an unknown contract type says so instead of pretending to review
    nb = c2.post(f"/projects/{pid}/contracts/review",
                 json={"contract_type": "gc", "findings": []}).json()
    assert nb["verdict"] == "no_playbook" and "consultant" in nb["available_types"]

print("CRE-TIER3 OK - HOLDSELL prices sell-now off today's reversion (16.67M gross less costs and "
      "the 8M payoff) and every hold year as INCREMENTAL flows against the proceeds declined, so "
      "growing NOI at a flat cap recommends hold while an unreachable hurdle honestly recommends "
      "sell; cap expansion is an explicit input that lowers the future exit, amortization raises "
      "net proceeds and capex lowers the IRR. CLAUSE refuses a playbook clause with no red line, a "
      "duplicate, a bad severity or an empty type; a review flags the one-way indemnity with its "
      "section reference, sorts deviations first, and reports the nine clauses NOBODY read as "
      "not_reviewed (blocking) rather than acceptable. ICMEMO refuses to render without a scenario "
      "— listing what is missing and what to do — and renders the full ask/returns/governance memo "
      "with a published basis once one exists, PDF included.")
