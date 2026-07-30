"""R22-OPTION-OBJECT over HTTP — a real scenario, really solved, reaching the option card.

The basis rules are pinned in `test_option_economics.py` against a stand-in scenario. What only a live
app shows is that the link actually closes: a `design_option` record carrying a `scenario` reference
resolves to a real `Scenario` row, `proforma.solve()` runs on its assumptions, and the resulting IRR
appears on the SAME card that `design_options.compare()` already served — rather than only on a new
endpoint nobody opens.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_economics_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_option_economics_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_option_economics_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_option_economics_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# A real deal. Fixture shape copied from `test_fin_gov.py`, NOT invented — my first attempt used
# `lp_share`/`gp_share` where the Assumptions model wants `lp_pct`/`gp_pct`, and `cost_of_sale_pct`
# where it wants `selling_cost_pct`. A 422 caught it here, but the same habit has silently produced
# fixtures that exercise nothing before. Copy a shape that a passing test already POSTs.
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
    c.headers.update({"X-User": "econ@test"})
    pid = c.post("/projects", json={"name": "Option Economics"}).json()["id"]

    def opt(**data):
        r = c.post(f"/projects/{pid}/modules/design_option", json={"data": data})
        assert r.status_code in (200, 201), (r.status_code, r.text[:200])
        return r.json()

    empty = c.get(f"/projects/{pid}/design/options/economics")
    check("GET /design/options/economics answers 200 with nothing set up", empty.status_code == 200,
          empty.text[:200])
    check("  and says nothing can be priced rather than returning an empty success",
          empty.json()["priced_count"] == 0 and empty.json()["message"] is not None)

    # a real scenario, stored the way the proforma router stores them
    sc = c.post("/proforma/scenarios", json={"name": "Base case", "project_id": pid, "assumptions": DEAL})
    check("a proforma scenario can be created", sc.status_code in (200, 201), sc.text[:200])
    sid = sc.json()["id"]

    linked = opt(name="A — linked", gross_area_sf=50_000, scenario=sid)
    check("the new `scenario` field round-trips through the module engine",
          (linked.get("data") or {}).get("scenario") == sid, linked.get("data"))
    opt(name="B — optimistic", gross_area_sf=50_000, scenario=sid, irr_pct=45.0)
    opt(name="C — typed only", gross_area_sf=50_000, hard_cost=9_000_000, irr_pct=17.5)
    opt(name="D — unlinked", gross_area_sf=50_000)

    r = c.get(f"/projects/{pid}/design/options/economics")
    check("the roll-up answers 200", r.status_code == 200, r.text[:200])
    J = r.json()
    rows = {o["name"]: o for o in J["options"]}

    a = rows["A — linked"]
    check("the linked option is DERIVED — solve() actually ran", a["basis"] == "derived", a["basis"])
    check("  it has a real cost from the proforma's total uses",
          isinstance(a["hard_cost"], (int, float)) and a["hard_cost"] > 5_000_000, a["hard_cost"])
    check("  and a real levered IRR as a percentage",
          isinstance(a["irr_pct"], (int, float)) and -100 < a["irr_pct"] < 200, a["irr_pct"])
    check("  the scenario is named on the row, so the number is traceable",
          a["scenario_name"] == "Base case", a["scenario_name"])
    check("  the equity/loan split came through", a["equity"] > 0 and a["loan_amount"] > 0,
          (a["equity"], a["loan_amount"]))

    b = rows["B — optimistic"]
    check("a typed 45% IRR against a solved one is flagged as disagreeing",
          b["agrees_with_declared"] is False, (b["declared_irr_pct"], b["irr_pct"]))
    check("  and appears in the named disagreement list",
          "B — optimistic" in [x["name"] for x in J["declared_disagrees_with_derived"]],
          J["declared_disagrees_with_derived"])
    check("  with the declared figure preserved, not overwritten",
          b["declared_irr_pct"] == 45.0 and b["irr_pct"] != 45.0, (b["declared_irr_pct"], b["irr_pct"]))

    check("a typed-only option is labelled 'declared', not 'derived'",
          rows["C — typed only"]["basis"] == "declared", rows["C — typed only"]["basis"])
    d = rows["D — unlinked"]
    check("an option naming no scenario is NOT priced from the project's scenario",
          d["irr_pct"] is None and d["basis"] == "unlinked", (d["basis"], d["irr_pct"]))
    check("  and the note names the candidate so linking it is obvious",
          "Base case" in (d["note"] or ""), d["note"])
    check("the project's scenarios are listed for linking",
          [s["name"] for s in J["scenarios"]] == ["Base case"], J["scenarios"])

    # THE ASK: provenance on the EXISTING card, additively.
    comp = c.get(f"/projects/{pid}/design/options/compare")
    check("the existing option card still answers 200", comp.status_code == 200, comp.text[:200])
    C = comp.json()
    card = {o["name"]: o for o in C["options"]}
    check("  every card row carries an economics_basis",
          all("economics_basis" in o for o in C["options"]))
    check("  the linked option reads 'derived' on the card",
          card["A — linked"]["economics_basis"] == "derived",
          card["A — linked"]["economics_basis"])
    check("  and carries the solved IRR beside the typed one",
          isinstance(card["A — linked"]["derived_irr_pct"], (int, float)),
          card["A — linked"]["derived_irr_pct"])
    check("  the optimistic option is marked as not agreeing with its own proforma",
          card["B — optimistic"]["irr_agrees_with_proforma"] is False)
    # Additive: the pre-existing columns keep their meaning — `irr_pct` is still what was TYPED.
    check("  `irr_pct` on the card still means the recorded figure, unchanged",
          card["B — optimistic"]["irr_pct"] == 45.0, card["B — optimistic"]["irr_pct"])
    check("  and the earlier carbon work on this card is untouched",
          all(k in card["A — linked"] for k in ("carbon_basis", "embodied_kgco2e", "kgco2e_per_sf")))
    check("  as are the original program/economics columns",
          all(k in card["A — linked"] for k in
              ("cost_per_sf", "gross_area_sf", "efficiency_pct", "unit_count", "hard_cost")))

print()
if FAILED:
    print(f"option_economics_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("option_economics_route: all checks passed")
