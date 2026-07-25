"""COST-SPINE — cost-code identity across budget → commitment → actual → invoice.

The failure this exists to catch is the one a per-code total cannot show: the same scope wearing
different codes at different stages, or spend booked against a code nobody budgeted. So the
assertions are about PRESENCE and coverage, not just arithmetic.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cost_spine.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cost_spine.db"
os.environ["STORAGE_DIR"] = "./test_storage_cost_spine"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_cost_spine.db"):
    os.remove("./test_cost_spine.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Spine"}).json()["id"]

    def rec(module, data):
        r = c.post(f"/projects/{pid}/modules/{module}", json={"data": data})
        assert r.status_code in (200, 201), (module, r.status_code, r.text[:200])
        return r.json()["id"]

    # an empty project traces to nothing and SAYS so rather than reporting 0% or 100%
    empty = c.get(f"/projects/{pid}/cost-spine").json()
    assert empty["traceability_pct"] is None and empty["code_count"] == 0, empty
    assert "nothing to trace" in empty["note"], empty["note"]

    # --- the register -----------------------------------------------------------------------------
    cc_conc = rec("cost_code", {"code": "03-3000", "description": "Cast-in-place concrete"})
    cc_steel = rec("cost_code", {"code": "05-1200", "description": "Structural steel"})
    cc_glaz = rec("cost_code", {"code": "08-4400", "description": "Curtain wall"})
    cc_never = rec("cost_code", {"code": "09-9100", "description": "Painting"})   # never used anywhere

    # 03-3000 — a complete, healthy chain through all four stages
    rec("budget", {"cost_code": cc_conc, "description": "Concrete", "budget": 1_000_000})
    rec("commitment", {"cost_code": cc_conc, "description": "Concrete sub", "amount": 900_000})
    rec("direct_cost", {"cost_code": cc_conc, "description": "Concrete cost", "amount": 400_000})
    rec("sub_invoice", {"cost_code": cc_conc, "vendor": "Ironwood Concrete", "amount": 350_000})

    # 05-1200 — SPEND WITH NO BUDGET: the expensive break. A per-code margin row shows a big negative
    # variance; only presence shows that nobody ever budgeted this scope.
    rec("commitment", {"cost_code": cc_steel, "description": "Steel sub", "amount": 600_000})
    rec("direct_cost", {"cost_code": cc_steel, "description": "Steel cost", "amount": 250_000})

    # 08-4400 — budget with nothing behind it: fine early, a re-coding smell later
    rec("budget", {"cost_code": cc_glaz, "description": "Curtain wall", "budget": 750_000})

    # and spend carrying NO cost code at all — untraceable to any scope
    rec("direct_cost", {"description": "General conditions, uncoded", "amount": 120_000})
    rec("commitment", {"description": "Uncoded PO", "amount": 80_000})

    t = c.get(f"/projects/{pid}/cost-spine").json()
    by = {r["code"]: r for r in t["rows"]}

    # ---- the healthy chain reaches every stage and is flagged clean ------------------------------
    conc = by["03-3000"]
    assert conc["stages_present"] == ["budget", "committed", "actual", "billed"], conc["stages_present"]
    assert conc["stage_count"] == 4 and conc["first_break"] is None, conc
    assert conc["flags"] == [] and conc["traceable"] is True, conc
    assert conc["budget"] == 1_000_000 and conc["billed"] == 350_000, conc

    # ---- spend without budget is named, not just implied by a negative variance -------------------
    steel = by["05-1200"]
    assert "spend_without_budget" in steel["flags"], steel
    assert steel["traceable"] is False and "budget" not in steel["stages_present"], steel
    # …and it hands back the button that fixes it, filtered to the code
    act = steel["actions"][0]
    assert act["kind"] == "open_module" and act["module"] == "budget" and act["q"] == "05-1200", act

    # ---- budget with nothing behind it is the other direction ------------------------------------
    glaz = by["08-4400"]
    assert glaz["flags"] == ["budget_without_spend"], glaz
    assert glaz["stages_present"] == ["budget"] and glaz["first_break"] == "committed", glaz

    # ---- uncoded spend is surfaced separately — it can never appear in a per-code row -------------
    assert t["unassigned_count"] == 2, t["unassigned"]
    assert t["unassigned_total"] == 200_000, t["unassigned_total"]
    assert t["unassigned"]["actual"]["amount"] == 120_000, t["unassigned"]
    assert t["unassigned"]["committed"]["amount"] == 80_000, t["unassigned"]

    # ---- the headline: traceability, and it must NOT round up to a comfortable number -------------
    # traceable committed+actual = 03-3000's 900k + 400k = 1.3M
    # total = 1.3M + steel's 850k + uncoded 200k = 2.35M  ->  55.3%
    assert t["traceable_spend"] == 1_300_000, t["traceable_spend"]
    assert t["total_spend"] == 2_350_000, t["total_spend"]
    assert t["traceability_pct"] == 55.3, t["traceability_pct"]
    assert "55.3% of committed+actual cost sits on a budgeted code" in t["note"], t["note"]
    assert "no cost code at all" in t["note"], t["note"]
    # the note ties the coverage back to the margin number that depends on it
    assert "inherits that coverage" in t["note"], t["note"]

    # ---- a register code nobody used is reported ---------------------------------------------------
    assert any("09-9100" in u for u in t["unused_register_codes"]), t["unused_register_codes"]
    assert not any("03-3000" in u for u in t["unused_register_codes"]), t["unused_register_codes"]

    # ---- broken rows sort first, biggest money first ------------------------------------------------
    assert t["rows"][0]["code"] == "05-1200", [r["code"] for r in t["rows"]]   # broken + most money
    assert t["rows"][-1]["code"] == "03-3000", [r["code"] for r in t["rows"]]  # the only clean row, last
    assert set(t["broken"]) and all("03-3000" not in b for b in t["broken"]), t["broken"]

    # ---- billed over committed is caught -----------------------------------------------------------
    rec("sub_invoice", {"cost_code": cc_conc, "vendor": "Ironwood Concrete", "amount": 700_000})   # 350k + 700k > 900k committed
    t2 = c.get(f"/projects/{pid}/cost-spine").json()
    conc2 = next(r for r in t2["rows"] if r["code"] == "03-3000")
    assert "billed_over_committed" in conc2["flags"], conc2
    assert any(a["module"] == "sub_invoice" for a in conc2["actions"]), conc2["actions"]

    # ---- a fully-budgeted project reports 100% and says so plainly ----------------------------------
    pid2 = c.post("/projects", json={"name": "Clean"}).json()["id"]
    cc = c.post(f"/projects/{pid2}/modules/cost_code",
                json={"data": {"code": "01-0000", "description": "GCs"}}).json()["id"]
    for mod, data in (("budget", {"cost_code": cc, "budget": 100_000}),
                      ("commitment", {"cost_code": cc, "description": "GC sub", "amount": 90_000}),
                      ("direct_cost", {"cost_code": cc, "description": "GC cost", "amount": 50_000})):
        assert c.post(f"/projects/{pid2}/modules/{mod}", json={"data": data}).status_code in (200, 201)
    clean = c.get(f"/projects/{pid2}/cost-spine").json()
    assert clean["traceability_pct"] == 100.0 and clean["broken"] == [], clean
    assert "Every committed and actual dollar" in clean["note"], clean["note"]

    # the route is project-scoped and role-gated like every other /projects/{pid} route
    assert c.get("/projects/does-not-exist/cost-spine").status_code == 404

print("COST-SPINE OK - cost-code identity traced across budget→commitment→actual→invoice, reporting "
      "PRESENCE not just amounts: a complete chain reaches all four stages with no flags, while "
      "spend booked against a code nobody budgeted is NAMED (spend_without_budget) rather than left "
      "to show up as a large negative variance, budget with nothing behind it reports where the chain "
      "first breaks, and invoices exceeding their commitment are caught. Records carrying no cost code "
      "at all are surfaced separately because they can never appear in a per-code row — the thing a "
      "margin report structurally cannot tell you. The headline is traceability: 55.3% of "
      "committed+actual sits on a budgeted code here, stated with the reminder that the margin number "
      "inherits exactly that coverage; a fully-budgeted project says 100% plainly and an empty one "
      "refuses to report a percentage at all.")
