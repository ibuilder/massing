"""SEC-BODY-PID — a project id in the request BODY must be authorised like one in the path.

`POST /test-fit/optimize` read another project's `purchase_price` and hard $/sf with **no gate of
any kind**, from a `pid` supplied in the request body. Four independent mechanisms exist and not one
of them could see it:

1. `rbac.require_role(...)` is a dependency whose inner signature is `dep(pid: str, ...)`, so
   FastAPI resolves that `pid` from the **path or query**. A body field is unreachable to it. The
   route could not have used it even if someone had tried.
2. `test_route_authz` walks `/projects/{pid}` routes only. **No `{pid}` in the path ⇒ outside its
   remit** — the same shape already recorded as "require_role on a GLOBAL route".
3. `main._PROTECTED_PREFIXES` is a hand-maintained list of top-level prefixes and does not contain
   `/test-fit`. (It also only applies with `AEC_RBAC=1`, so it is a second layer, never the fix.)
4. `test_global_authz` had the route in its **frozen BASELINE**, grouped under the comment
   "stateless compute — no stored state". It was the only one of the five routes under that label
   that takes a `Session`: `/test-fit/compare`, `/structure/recommend`, `/generate/massing/preview`
   and `/massing/optioneer` are genuine calculators; this one reads the database.

**That fourth point is the one worth keeping.** The exemption list did not fail to notice the route
— it had *examined* it and filed it as safe by association with its neighbours, on the strength of
the file it lives in and the shape of its signature. `test_global_authz`'s own docstring says
"triaging all 43 is real work and this test does not pretend to have done it", which was honest, and
this is what that honesty cost. **A frozen baseline preserves the reasoning of the day it was
written, including the parts that were wrong.**

The predicate that isolates it is not "has no authz" (34 routes, mostly fine) but **"has no authz
AND takes a DB session"** — a route that cannot read stored data cannot leak it.

WHAT THIS ASSERTS. With RBAC on, a caller with no role on the target project must be refused before
the project is read. Not "the values are not echoed" — they are not, but the caller controls
`plate_w`, `plate_d`, `floors` and the rest of `econ`, so the returned ranking is **invertible**:
vary the inputs, observe the yield, solve for the seed. Refusing the read is the only honest fix.

The no-`pid` case must keep working. Without `pid` the route is a pure calculator over
caller-supplied numbers and is legitimately open, like its four siblings — a fix that closed it
would have broken the feature to fix the leak.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_body_pid_authz.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_body_pid_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_body_pid_authz"
os.environ["AEC_RBAC"] = "1"            # the gate is a no-op with RBAC off, as require_role is
os.environ["AEC_TRUST_XUSER"] = "1"     # lets the suite act as a named user via X-User
for _f in ("./test_body_pid_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project, ProjectMember  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)

LAND = 7_350_000.0     # distinctive values so a leak is unambiguous in the output
HARD_PSF = 412.5

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


db = SessionLocal()
db.add(Project(id="secret-deal", name="Confidential Deal",
               dev_property={"purchase_price": LAND},
               dev_budget={"lines": [{"category": "hard", "unit_cost": HARD_PSF,
                                      "quantity": 1000, "description": "shell $/sf"}]}))
db.add(ProjectMember(project_id="secret-deal", user="owner", role="admin"))
db.commit()
db.close()

BODY = {"plate_w": 120.0, "plate_d": 70.0, "floors": 6, "targets": {}, "econ": {}}


def optimize(user: str | None, pid: str | None):
    body = dict(BODY)
    if pid:
        body["pid"] = pid
    headers = {"X-User": user} if user else {}
    return client.post("/test-fit/optimize", json=body, headers=headers)


# 1) THE DEFECT. A caller with no role on the project must not reach it. This is the assertion that
#    fails on the unfixed code: it returned 200 and seeded the econ from someone else's deal.
r = optimize("stranger", "secret-deal")
check("a caller with no role on the project is refused", r.status_code == 403,
      f"got {r.status_code} — an unauthorised caller reached another project's financials")

# 2) An ANONYMOUS caller likewise. `current_user` returns the literal "anonymous" with RBAC on and no
#    credential, which identifies without authorising — the mistake this repo has shipped twice.
r = optimize(None, "secret-deal")
check("an anonymous caller is refused", r.status_code == 403, f"got {r.status_code}")

# 3) The owner still works — a gate that refuses everyone is not a fix.
r = optimize("owner", "secret-deal")
check("a member with the role still succeeds", r.status_code == 200, f"got {r.status_code}")

# 4) The no-pid calculator stays open. Closing it would break the feature to fix the leak.
r = optimize(None, None)
check("no pid: the pure calculator is still reachable", r.status_code == 200, f"got {r.status_code}")

# 5) A refused response must not carry the values in ANY form. Asserting the status alone would pass
#    for a 403 that had already computed and attached the ranking.
r = optimize("stranger", "secret-deal")
blob = r.text
check("the refusal leaks neither value", str(LAND) not in blob and str(HARD_PSF) not in blob,
      "a seeded value appears in the refused response body")

# 6) The route must be gone from test_global_authz's frozen baseline — FIXED, not re-frozen. Without
#    this, a future edit could drop the gate and the baseline would silently declare it acceptable
#    again. Same reason the /pdf/* and /templates entries were deleted rather than kept.
src = open(os.path.join(os.path.dirname(__file__), "test_global_authz.py"), encoding="utf-8").read()
baseline = src[src.index("BASELINE = {"):src.index("}", src.index("BASELINE = {"))]
check("the route is not re-frozen in the global-authz baseline",
      '"/test-fit/optimize"' not in baseline,
      "it is still listed as known-unguarded, which would re-accept the defect")

# ---------------------------------------------------------------------------------------------------
# SEC-SCENARIO-COMPARE — the same class, two more routes, found by an independent pass 2026-10-13.
#
# Added HERE rather than in a file of their own because this file's whole subject is "a privileged
# object addressed by something other than the path parameter", and splitting one class across three
# records is what TURNOVER-UNGATED and CLASSIFY-DARK each paid for. The STATIC derivations live in
# `test_scenario_authz.py`; these are the behavioural arms, because a check that an authoriser is
# MENTIONED is not a check that it EXCLUDES anybody.
# ---------------------------------------------------------------------------------------------------
#: The real `Assumptions` shape, lifted verbatim from `test_fin_gov.py`. The first draft of this
#: block invented a plausible one — `debt.io`, `equity.lp_share`, `exit.cost_of_sale_pct` — which
#: pydantic 422'd, so every probe below failed on the FIXTURE and two of them passed VACUOUSLY,
#: because a 422 body carries no financial figure either. *A fixture that is merely plausible makes
#: a passing assertion and a broken harness look the same*, which is the second time in this
#: session a harness guess has reported a defect in correct code.
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

_db = SessionLocal()
_db.add(Project(id="other-co", name="Another Tenant"))
_db.add(ProjectMember(project_id="other-co", user="rival", role="admin"))
_db.commit()
_db.close()

# A scenario owned by `secret-deal`, created by its own admin.
_sid = client.post("/proforma/scenarios", headers={"X-User": "owner"},
                   json={"name": "VictimDeal", "project_id": "secret-deal",
                         "assumptions": DEAL}).json().get("id")
check("the victim's scenario was created for the probes below", bool(_sid), "no scenario id")

# 7) POST /proforma/compare took a list of scenario ids with NO authorisation of any kind — no
#    `current_user`, no `_can_read`, no project scoping — and returned each one's `returns` AND
#    `sources_uses`. That is strictly MORE financial data than the `list_scenarios` leak closed one
#    commit earlier, and it was invisible to `test_scenario_authz`'s derivation because
#    `ast.unparse` renders `db.get(Scenario, sid)` with a COMMA after `Scenario`, which none of that
#    gate's four spellings matched.
r = client.post("/proforma/compare", json=[_sid], headers={"X-User": "rival"})
check("compare: a caller with no role on the project gets nothing back",
      r.status_code == 200 and r.json() == [],
      f"got {r.status_code} {r.text[:200]}")

# ...and the refusal must not leak the figures in any form, for the same reason as (5).
check("compare: no financial figure survives the filter",
      "equity_irr" not in r.text and "sources_uses" not in r.text, r.text[:200])

# It was also a batch EXISTENCE ORACLE: unknown ids are silently dropped, so one request told a
# caller exactly which of N ids exist. An unreadable id and an absent one must be indistinguishable.
r_unknown = client.post("/proforma/compare", json=["no-such-id"], headers={"X-User": "rival"})
check("compare: an unreadable id and an absent one are indistinguishable",
      r_unknown.status_code == 200 and r_unknown.json() == [] and r.json() == [],
      "the oracle survives")

# The owner still gets their own data — a filter that refuses everyone is not a fix.
r_own = client.post("/proforma/compare", json=[_sid], headers={"X-User": "owner"})
check("compare: the owner still sees their own scenario",
      r_own.status_code == 200 and len(r_own.json()) == 1, f"got {r_own.status_code} {r_own.text[:160]}")

# 8) draw-package authorised the SCENARIO (which the caller owns) and took its DESTINATION project
#    from the request body, unauthorised — then deleted every SOV row for that project and rewrote
#    them from this scenario's cost tree. SOV is what the AIA G702/G703 pay application is computed
#    from, i.e. what a lender draws against, so this was destroy + forge + disclose in one call.
_rival_sid = client.post("/proforma/scenarios", headers={"X-User": "rival"},
                         json={"name": "RivalDeal", "project_id": "other-co",
                               "assumptions": DEAL}).json().get("id")
check("the rival's own scenario was created", bool(_rival_sid), "no scenario id")
r = client.post(f"/proforma/scenarios/{_rival_sid}/draw-package", headers={"X-User": "rival"},
                json={"project_id": "secret-deal", "actuals": [{"actual_to_date": 1.0}],
                      "as_of_month": 9, "app_no": 1})
check("draw-package: a body-supplied project the caller has no role on is refused",
      r.status_code == 403, f"got {r.status_code} — another tenant's SOV was rewritten")
check("draw-package: the refusal leaks no G702 total",
      "line1_original_contract_sum" not in r.text and "g703_totals" not in r.text, r.text[:200])

# 9) `project_id: ""` is a SUPPLIED project id, and the guard's truthiness test skipped it. Refused
#    as malformed now; `None` stays open, because an unattached scenario is scratch work over
#    caller-supplied numbers and closing it would break the feature to fix the leak.
r = client.post("/proforma/scenarios", headers={"X-User": "rival"},
                json={"name": "Empty", "project_id": "", "assumptions": DEAL})
check("create_scenario: an empty project_id is refused rather than stored", r.status_code == 422,
      f"got {r.status_code} {r.text[:160]}")
r = client.post("/proforma/scenarios", headers={"X-User": "rival"},
                json={"name": "Unattached", "project_id": None, "assumptions": DEAL})
check("create_scenario: an OMITTED project_id still works — the calculator case", r.status_code == 201,
      f"got {r.status_code} {r.text[:160]}")
r = client.post("/proforma/scenarios", headers={"X-User": "rival"},
                json={"name": "Theirs", "project_id": "secret-deal", "assumptions": DEAL})
check("create_scenario: another tenant's project is still refused", r.status_code == 403,
      f"got {r.status_code}")

# 10) ROLE FLOORS on the scenario write routes. `_can_write` returned true for ANY project role
#     until 2026-10-13, so `ROLE_ORDER` was never consulted and a **viewer** could approve and
#     publish the committed underwriting basis and grant a permanent read of the deal's financials
#     to an arbitrary identity. Asserted behaviourally, because the static gate can only see that a
#     guard is called, never what rank it demands.
_db2 = SessionLocal()
_db2.add(ProjectMember(project_id="secret-deal", user="looker", role="viewer"))
_db2.add(ProjectMember(project_id="secret-deal", user="checker", role="reviewer"))
_db2.commit()
_db2.close()


def _as(user: str, path: str, body: dict | None = None):
    return client.post(path, json=body if body is not None else {}, headers={"X-User": user})


check("a viewer cannot submit a scenario for review",
      _as("looker", f"/proforma/scenarios/{_sid}/review", {"action": "submit"}).status_code == 403,
      "a read-only member moved the governance state")
check("a REVIEWER can — the floor is a floor, not a wall",
      _as("checker", f"/proforma/scenarios/{_sid}/review", {"action": "submit"}).status_code == 200,
      "the rank that exists for this cannot use it")
check("a viewer cannot APPROVE either",
      _as("looker", f"/proforma/scenarios/{_sid}/review", {"action": "approve"}).status_code == 403,
      "a read-only member approved the underwriting basis")
check("a viewer cannot grant another identity a permanent read",
      _as("looker", f"/proforma/scenarios/{_sid}/share", {"user": "mallory"}).status_code == 403,
      "a read-only member handed out access to the deal's financials")
check("...and a reviewer cannot either — sharing is `editor`, not a participant's act",
      _as("checker", f"/proforma/scenarios/{_sid}/share", {"user": "mallory"}).status_code == 403,
      "sharing is still below its intended floor")
check("a viewer cannot clone", _as("looker", f"/proforma/scenarios/{_sid}/clone",
                                   {"name": "Sneaky"}).status_code == 403, "a viewer wrote a row")
check("a viewer cannot edit the assumptions",
      client.put(f"/proforma/scenarios/{_sid}", headers={"X-User": "looker"},
                 json={"name": "VictimDeal", "project_id": "secret-deal",
                       "assumptions": DEAL}).status_code == 403, "a viewer authored")
# and the owner (admin) still does everything — a floor that refuses everyone is not a fix
check("the project admin still shares", _as("owner", f"/proforma/scenarios/{_sid}/share",
                                            {"user": "lp-partner"}).status_code == 201,
      "the floor locked out the role that should pass")

print(f"\ntest_body_pid_authz {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
