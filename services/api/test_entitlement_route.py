"""R22-ENTITLE-RISK over HTTP — the endpoint answers, and it refuses what the engine refuses.

The arithmetic is pinned in `test_entitlement_risk.py`. This asserts the route exists, that the
pydantic layer does not quietly accept what the engine would reject (a schema that validates a
duration with no carry cost would let the "looks modelled but changes nothing" case through before
the engine ever sees it), and that the conditional labelling survives serialization — the labels are
the whole reason `metrics_given_approval` is safe to publish.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_entitlement_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_entitle_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_entitle_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_entitle_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


DEAL = {
    "timing": {"construction_months": 18, "leaseup_months": 12, "hold_years": 5,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 17},
        {"category": "soft", "name": "Soft costs", "amount": 3_000_000, "curve": "linear",
         "start_month": 0, "end_month": 17},
    ],
    "debt": {"ltc": 0.65, "rate": 0.085, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 120_000,
                   "opex_annual": 1_300_000, "stabilized_occ": 0.94, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2},
                            {"hurdle": None, "lp": 0.6, "gp": 0.4}]},
    "discount_rate": 0.10,
}

ENT = {
    "approval_probability": 0.7,
    "duration_months": {"kind": "triangular", "low": 6, "mode": 12, "high": 30},
    "carry_cost_monthly": 45_000,
    "pursuit_cost": 850_000,
    "land_basis": 4_000_000,
    "land_recovery_pct": 0.9,
}

with TestClient(app) as c:
    c.headers.update({"X-User": "ent@test"})

    r = c.post("/proforma/entitlement-risk",
               json={"assumptions": DEAL, "entitlement": ENT, "iterations": 400,
                     "seed": 42, "targets": {"returns.equity_irr": 0.15}})
    check("POST /proforma/entitlement-risk answers 200", r.status_code == 200, r.text[:300])
    J = r.json()

    # The floor, first: everything below is satisfiable at zero.
    check("draws actually solved", J["solved"] > 0 and J["solve_failures"] == 0,
          (J["solved"], J["solve_failures"]))
    check("  approved + denied == iterations", J["approved"] + J["denied"] == 400)
    check("  and some were denied at p=0.7", 0 < J["denied"] < 400, J["denied"])

    check("returns are labelled as conditional on approval", "metrics_given_approval" in J)
    check("  with the condition spelled out in the payload",
          "GRANTED" in J["metrics_are_conditional"])
    check("  and the label survived JSON", isinstance(J["metrics_are_conditional"], str))
    check("the denial branch is reported separately", J["denial"]["n"] == J["denied"])
    check("  with a negative mean loss", J["denial"]["mean_net_loss"] < 0)
    check("  and no IRR anywhere in it",
          not any("irr" in k.lower() for k in J["denial"]), sorted(J["denial"]))

    pc = J["probability_of_clearing"]["returns.equity_irr"]
    check("the hurdle probability counts every iteration", pc["of_iterations"] == 400)
    check("  and is not larger than the conditional figure",
          pc["probability"] <= pc["probability_given_approval"],
          (pc["probability"], pc["probability_given_approval"]))

    ev = J["expected_value"]
    check("expected value blends NPV only", ev["blended"] == "npv only")
    check("  and names what it excluded", "returns.equity_irr" in ev["excluded_metrics"])

    check("the entitlement duration is summarized", J["entitlement_months"]["n"] == J["approved"])

    # --- the schema must not accept what the engine refuses ---------------------------------------
    no_carry = c.post("/proforma/entitlement-risk",
                      json={"assumptions": DEAL,
                            "entitlement": {k: v for k, v in ENT.items()
                                            if k != "carry_cost_monthly"},
                            "iterations": 200})
    check("a duration with no carry cost is a 422, not a run that changes nothing",
          no_carry.status_code == 422, no_carry.status_code)
    check("  with the reason, not a bare validation error",
          "changes no output" in no_carry.text or "looks modelled" in no_carry.text,
          no_carry.text[:200])

    for label, ent in (("probability above 1", {**ENT, "approval_probability": 1.4}),
                       ("negative probability", {**ENT, "approval_probability": -0.2}),
                       ("land recovery above 1", {**ENT, "land_recovery_pct": 1.4}),
                       ("negative carry", {**ENT, "carry_cost_monthly": -5})):
        resp = c.post("/proforma/entitlement-risk",
                      json={"assumptions": DEAL, "entitlement": ent, "iterations": 200})
        check(f"a {label} is rejected", resp.status_code == 422, resp.status_code)

    # --- the degenerate ends, over the wire --------------------------------------------------------
    sure = c.post("/proforma/entitlement-risk",
                  json={"assumptions": DEAL, "entitlement": {**ENT, "approval_probability": 1.0},
                        "iterations": 200, "seed": 3}).json()
    check("at 100% approval nothing is denied",
          sure["denied"] == 0 and sure["denial"]["n"] == 0)
    never = c.post("/proforma/entitlement-risk",
                   json={"assumptions": DEAL, "entitlement": {**ENT, "approval_probability": 0.0},
                         "iterations": 200, "seed": 3,
                         "targets": {"returns.equity_irr": 0.15}}).json()
    check("at 0% approval nothing is solved", never["solved"] == 0 and never["denied"] == 200)
    check("  and the hurdle probability is 0.0, not null",
          never["probability_of_clearing"]["returns.equity_irr"]["probability"] == 0.0)

    # --- determinism over the wire -----------------------------------------------------------------
    body = {"assumptions": DEAL, "entitlement": ENT, "iterations": 300, "seed": 77}
    a = c.post("/proforma/entitlement-risk", json=body).json()
    b = c.post("/proforma/entitlement-risk", json=body).json()
    check("the same seed gives the same answer over HTTP",
          a["denied"] == b["denied"] and a["metrics_given_approval"] == b["metrics_given_approval"])

    # --- entitlement-free behaviour is unchanged ----------------------------------------------------
    mc = c.post("/proforma/monte-carlo", json={
        "assumptions": DEAL,
        "variables": [{"path": "exit.exit_cap", "dist": {"kind": "uniform", "low": 0.05, "high": 0.06}}],
        "iterations": 200, "seed": 42})
    check("the existing /proforma/monte-carlo endpoint still works", mc.status_code == 200,
          mc.text[:200])
    check("  and is untouched by this change", mc.json()["solved"] > 0)

print()
if FAILED:
    print(f"entitlement_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("entitlement_route: all checks passed")
