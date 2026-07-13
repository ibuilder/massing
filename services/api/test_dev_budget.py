"""Developer cost budget — engine math + persistence + proforma cost-line mapping.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_dev_budget.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_devbudget.db"
os.environ["STORAGE_DIR"] = "./test_storage_devbudget"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_devbudget.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import dev_budget as dvb  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- pure engine: line totals, contingency, category rollups -----------------
budget = {
    "contingency": {"hard": 0.10, "soft": 0.10, "acquisition": 0.0},
    "lines": [
        {"category": "acquisition", "description": "Purchase", "unit_cost": 15_744_700, "quantity": 1},
        {"category": "hard", "description": "Solar panels", "unit_cost": 330, "quantity": 25_000},
        {"category": "hard", "description": "Wind turbines", "unit_cost": 5_000, "quantity": 1_161},
        {"category": "soft", "description": "Architect", "unit_cost": 350_000, "quantity": 1},
        {"category": "soft", "description": "Energy consultant", "unit_cost": 75_000, "quantity": 1},
    ],
}
s = dvb.summarize(budget)
assert s["categories"]["hard"]["subtotal"] == 330 * 25_000 + 5_000 * 1_161, s["categories"]["hard"]
assert s["categories"]["hard"]["contingency"] == round(s["categories"]["hard"]["subtotal"] * 0.10, 2)
assert s["categories"]["soft"]["subtotal"] == 425_000.0
assert s["categories"]["acquisition"]["contingency"] == 0.0
expect_grand = (s["categories"]["acquisition"]["total"] + s["categories"]["hard"]["total"]
                + s["categories"]["soft"]["total"])
assert abs(s["grand_total"] - round(expect_grand, 2)) < 0.01, (s["grand_total"], expect_grand)
assert 0 < s["soft_pct"] < s["hard_pct"] < 1, (s["hard_pct"], s["soft_pct"])   # hard dominates

# --- cost_lines mapping: rolled category line + its contingency as a separate line ---
cl = dvb.to_cost_lines(budget)
cats = [c["category"] for c in cl]
assert "land" in cats and "hard" in cats and "soft" in cats and "contingency" in cats, cats
assert sum(c["amount"] for c in cl) == s["grand_total"], "cost_lines must reconcile to grand total"

# --- persistence round-trip via the API --------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Dev Tower"}).json()["id"]
    # starter budget served when none saved
    g0 = c.get(f"/projects/{pid}/dev-budget").json()
    assert g0["budget"]["lines"] and "summary" in g0, g0
    # save + recompute
    r = c.put(f"/projects/{pid}/dev-budget", json={"lines": budget["lines"], "contingency": budget["contingency"]})
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["grand_total"] == s["grand_total"]
    # persisted
    assert c.get(f"/projects/{pid}/dev-budget").json()["summary"]["grand_total"] == s["grand_total"]
    # cost-lines endpoint reconciles
    clr = c.get(f"/projects/{pid}/dev-budget/cost-lines").json()
    assert round(sum(x["amount"] for x in clr["cost_lines"]), 2) == s["grand_total"], clr

    # --- Sources & Uses (built from the budget) ------------------------------
    from aec_api import sources_uses as su  # noqa: E402
    sub = su.build(s, {"ltc": 0.65, "rate": 0.075, "construction_months": 18, "lp_pct": 0.9})
    assert sub["balanced"] and sub["total_uses"] == sub["total_sources"], sub
    assert sub["total_uses"] > s["grand_total"], "financing interest should add to uses"
    assert sub["debt"] + sub["equity"] == sub["total_sources"]
    assert abs(sub["ltc"] - 0.65) < 0.02 and sub["binding_constraint"] == "LTC", sub
    # money-handling invariant: the displayed line items reconcile to the totals to the dollar
    # (no per-line rounding drift) and SOURCES tie to USES exactly — a non-90/10 split still ties.
    assert sum(u["amount"] for u in sub["uses"]) == sub["total_uses"], sub["uses"]
    assert sum(s2["amount"] for s2 in sub["sources"]) == sub["total_sources"], sub["sources"]
    odd = su.build(s, {"ltc": 0.65, "rate": 0.075, "lp_pct": 0.873})   # awkward split exercises the remainder
    assert sum(s2["amount"] for s2 in odd["sources"]) == odd["total_sources"] == odd["total_uses"], odd
    assert odd["balanced"], odd
    # DSCR cap can bind below LTC when NOI is tight
    capped = su.build(s, {"ltc": 0.65, "rate": 0.075, "min_dscr": 1.25, "noi": 500_000})
    assert capped["debt"] < sub["debt"] and capped["binding_constraint"] == "DSCR", capped
    assert sum(s2["amount"] for s2 in capped["sources"]) == capped["total_sources"], capped
    # endpoint
    sue = c.get(f"/projects/{pid}/sources-uses").json()
    assert sue["balanced"] and sue["total_uses"] == sue["total_sources"], sue

    # --- investment memo PDF -------------------------------------------------
    # no scenario yet → memo still renders (capital stack from the budget)
    m1 = c.get(f"/projects/{pid}/investment-memo.pdf")
    assert m1.status_code == 200 and m1.content[:4] == b"%PDF" and len(m1.content) > 2000, (m1.status_code, len(m1.content))
    # add a solved scenario → memo includes underwritten returns (and is larger)
    assumptions = {
        "timing": {"construction_months": 18, "hold_years": 5},
        "cost_lines": clr["cost_lines"],
        "debt": {"ltc": 0.65, "rate": 0.075}, "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
        "operations": {"potential_rent_annual": 3_000_000, "opex_annual": 1_000_000, "stabilized_occ": 0.93},
        "exit": {"exit_cap": 0.05}, "waterfall": {"pref_rate": 0.08, "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
    }
    sc = c.post("/proforma/scenarios", json={"name": "Base", "project_id": pid, "assumptions": assumptions})
    assert sc.status_code == 201, sc.text
    m2 = c.get(f"/projects/{pid}/investment-memo.pdf")
    assert m2.status_code == 200 and m2.content[:4] == b"%PDF", m2.status_code
    # pitch-deck (slide) variant renders too — 9 slides: title, exec summary, deal-in-numbers,
    # market & positioning, S&U, capital stack, timeline, business plan, returns & the ask
    dk = c.get(f"/projects/{pid}/investment-deck.pdf")
    assert dk.status_code == 200 and dk.content[:4] == b"%PDF" and len(dk.content) > 1500, (dk.status_code, len(dk.content))
    pages = dk.content.count(b"/Type /Page") - dk.content.count(b"/Type /Pages")
    assert pages == 9, f"deck should have 9 slides (title/exec/numbers/market/S&U/stack/timeline/plan/returns), got {pages}"

print(f"DEV-BUDGET OK - line totals + per-category contingency + grand ${s['grand_total']:,.0f}; "
      f"hard {s['hard_pct']*100:.0f}% / soft {s['soft_pct']*100:.0f}%; cost_lines reconcile; "
      f"persisted via API; Sources & Uses balances (debt+equity=uses); "
      f"investment-memo PDF renders (no-scenario + with-scenario)")
