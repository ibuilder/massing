"""ESTIMATE-DARK — the stored cost rule set, and the second coverage axis it creates.

`POST /projects/{pid}/cost/estimate` was frozen in `test_route_reachability.UNREACHABLE_ROUTES`
because nothing in this product stored a `rules` body, so no card could call it without inventing
one. `aec_api.cost_rules` is that store.

**The pin that matters is the one about PROVENANCE.** `fived.estimate`'s `complete` is a verdict
about coverage of the MODEL — no unpriced element, no missing quantity, no element a `vintage` rule
could not rate. It is silent on whether anybody chose the rates, and it has to be: the rules arrive
as a list and a list does not say who wrote it. The store seeds a starter set so a new project is
not an empty box, which makes a CONFIDENT total over placeholder rates reachable. So the route
carries `rules_seeded` out of the store and beside the total, and this file asserts the two axes are
independent — because the day they are folded into one is the day one of them stops being read.

Run: PYTHONPATH=src ./.venv/bin/python test_cost_rules.py
"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_cost_rules.db"
os.environ["STORAGE_DIR"] = "./test_storage_cost_rules"
os.environ["IFC_DIR"] = "./test_ifc_cost_rules"
os.environ.pop("AEC_RBAC", None)
import shutil  # noqa: E402

for f in ("./test_cost_rules.db",):
    if os.path.exists(f):
        os.remove(f)
# The rule set is a STORAGE blob, not a database row, so dropping the db leaves the previous run's
# saved rules behind and `effective()` reports `seeded: False` on a fresh run. Swept by exact name
# rather than a glob: a pattern written for scratch directories also matches source files.
if os.path.isdir("./test_storage_cost_rules"):
    shutil.rmtree("./test_storage_cost_rules")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import cost_rules as cr  # noqa: E402
from aec_api import fived  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.query_dsl import QueryError  # noqa: E402

# --- unit: the starter set is VALID, and it is valid by the estimate's own rules ---------------
# Not a separate validator: `save` runs `fived.validate_rules`, the function `/cost/estimate` runs,
# so a set that stores is a set that prices. A second copy of the checks here is how the two drift,
# and the drift surfaces as a 422 at estimate time on a rule the editor accepted.
assert cr.STARTER_RULES, "the starter set may not be empty — an empty box is what it exists to avoid"
clean = fived.validate_rules([dict(r) for r in cr.STARTER_RULES])
assert len(clean) == len(cr.STARTER_RULES)

# Every starter rule QUOTES its rate. A `vintage` starter would hand a brand-new project an estimate
# of zero lines and a `no_rate_count` equal to its whole model — honest, and useless as a start.
assert all(r["rate_from"] == "quoted" for r in cr.STARTER_RULES), cr.STARTER_RULES
# ...and every one says so in its description, because a starter rate that looks authored is worse
# than one that looks provisional.
assert all("PLACEHOLDER" in r["description"] for r in cr.STARTER_RULES), cr.STARTER_RULES

# The save bound is DERIVED from the estimate's, not restated — restating it is how a project comes
# to hold a set the estimate then refuses.
assert cr.MAX_RULES == fived.MAX_RULES

# --- unit: load / save / effective ------------------------------------------------------------
PID = "cost-rules-unit"
assert cr.load(PID) == [], "nothing saved yet"
rules, seeded = cr.effective(PID)
assert seeded is True and rules == [dict(r) for r in cr.STARTER_RULES]
# `effective` hands back a COPY: a caller that mutates what it was given must not edit the module's
# own starter set for every other project in the process.
rules[0]["unit_cost"] = 99999.0
assert cr.STARTER_RULES[0]["unit_cost"] != 99999.0, "effective() leaked the module-level starter set"

saved = cr.save(PID, [{"selector": "IfcWall", "code": "03 30 00", "basis": "area",
                       "unit_cost": 42.0, "rate_from": "quoted", "description": "Our walls"}])
assert len(saved) == 1 and saved[0]["unit_cost"] == 42.0
rules, seeded = cr.effective(PID)
assert seeded is False and len(rules) == 1, (seeded, rules)

# A BAD RULE refuses the WHOLE save, and nothing is written — a partially-saved cost rule set would
# price part of the model at rates the author did not finish choosing, and the half that stored
# would look as deliberate as the half that did not.
try:
    cr.save(PID, [
        {"selector": "IfcSlab", "code": "03 30 53", "basis": "area", "unit_cost": 16.0},
        {"selector": "", "code": "bad", "basis": "area", "unit_cost": 1.0},
    ])
    raise AssertionError("a rule with no selector must refuse the save")
except QueryError:
    pass
assert len(cr.load(PID)) == 1 and cr.load(PID)[0]["code"] == "03 30 00", "the refused save WROTE"

# WHAT "THE SELECTOR IS VALIDATED" IS WORTH, measured rather than assumed — and it is much less
# than it sounds. `query_dsl.parse` refuses an EMPTY query and essentially nothing else: `"(((("`,
# `"IfcWall &"`, `"=b"`, `"!"` and `"a>b>c"` all parse. So the selector check is non-emptiness plus
# a length bound, and **a typo'd property name saves cleanly and then matches nothing.**
for permissive in ("((((", "IfcWall &", "=b", "!"):
    saved_ok = cr.save(PID, [{"selector": permissive, "code": "x", "basis": "count",
                              "unit_cost": 1.0}])
    assert saved_ok[0]["selector"] == permissive, permissive
# *This is why the estimate has to be the one that tells you a rule did nothing*, and why
# `costEstimateRead.rulesPricedNothing` exists: no save-time check can catch a selector that is
# well-formed and wrong, so the only honest place to find it is the result.
cr.save(PID, [{"selector": "IfcWall", "code": "03 30 00", "basis": "area", "unit_cost": 42.0,
               "rate_from": "quoted", "description": "Our walls"}])
assert len(cr.load(PID)) == 1

# a missing cost code is refused by the same function, for the same reason
for bad in ({"selector": "IfcWall", "basis": "area", "unit_cost": 1.0},
            {"selector": "IfcWall", "code": "x", "basis": "nonsense", "unit_cost": 1.0},
            {"selector": "IfcWall", "code": "x", "basis": "area", "rate_from": "quoted"}):
    try:
        cr.save(PID, [bad])
        raise AssertionError(f"must refuse {bad}")
    except QueryError:
        pass
assert len(cr.load(PID)) == 1, "a refused save WROTE"

try:
    cr.save(PID, [dict(cr.STARTER_RULES[0]) for _ in range(cr.MAX_RULES + 1)])
    raise AssertionError("over MAX_RULES must refuse")
except QueryError:
    pass

# --- integration: the routes, and the two axes ------------------------------------------------
# THE ESTIMATE PRICES THE PROPERTY INDEX, NOT THE SOURCE IFC. `_run_estimate` runs
# `fived.estimate(_idx_for(pid), ...)`, and `_idx_for` reads `{pid}/props.json` — the index the data
# service produces and a client UPLOADS. A project with a perfectly good source IFC and no uploaded
# index prices NOTHING, and that is asserted below rather than discovered on a screen: measured, the
# response is `total: 0 · coverage_pct: 0 · unpriced_count: 0 · complete: False`, which reads as "no
# rule matched anything" and is actually "there was nothing to match against". *Two very different
# states that differ only in a number nobody prints* — hence `estimateCoverage().noModelIndex`.
PROPS = {
    "schema": "demo", "project": {"name": "Priced Tower"},
    "elements": [
        {"guid": "W1", "ifc_class": "IfcWall", "storey": "L1", "name": "Wall 1"},
        {"guid": "W2", "ifc_class": "IfcWall", "storey": "L1", "name": "Wall 2"},
        {"guid": "D1", "ifc_class": "IfcDoor", "storey": "L1", "name": "Door 1"},
        {"guid": "B1", "ifc_class": "IfcBeam", "storey": "L1", "name": "Beam 1"},
    ],
}
QTY = {"W1": {"area": 400.0}, "W2": {"area": 250.0}}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Priced Tower"}).json()["id"]

    g = c.get(f"/projects/{pid}/cost/rules")
    assert g.status_code == 200, g.text[:200]
    assert g.json()["seeded"] is True
    assert len(g.json()["rules"]) == len(cr.STARTER_RULES)
    assert c.get("/projects/no-such-project/cost/rules").status_code == 404

    # NO INDEX YET — the route is reachable and answers honestly about nothing.
    blind = c.post(f"/projects/{pid}/cost/estimate", json={})
    assert blind.status_code == 200, blind.text[:300]
    bj = blind.json()
    assert bj["rules_seeded"] is True and bj["rule_count"] == len(cr.STARTER_RULES)
    assert bj["total"] == 0 and bj["complete"] is False
    # the signature of an EMPTY index rather than an unmatched one: nothing priced AND nothing
    # unpriced, because `unpriced` is derived over the index itself
    assert bj["priced_count"] == 0 and bj["unpriced_count"] == 0 and bj["no_rate_count"] == 0

    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 4, up.text[:200]

    # THE ROUTE IS REACHABLE WITH NO BODY AT ALL, which is the whole point: an absent `rules` means
    # *use the project's stored set*, where it used to mean *price nothing*.
    e = c.post(f"/projects/{pid}/cost/estimate", json={"quantities": QTY})
    assert e.status_code == 200, e.text[:300]
    est = e.json()
    assert est["rules_seeded"] is True, "the starter set must be declared as the starter set"
    assert est["rule_count"] == len(cr.STARTER_RULES)
    # The starter set covers walls and doors and NOT beams, so all three axes have something on them
    assert est["total"] > 0, est["total"]
    assert est["unpriced_count"] == 1, est["unpriced"]            # the beam: no rule matched it
    assert est["complete"] is False
    # ...and the engine's axis is untouched and still means what it meant
    assert set(est) >= {"total", "complete", "coverage_pct", "unpriced_count",
                        "missing_quantity_count", "no_rate_count"}, sorted(est)
    print(f"  starter set: total={est['total']} complete={est['complete']} "
          f"coverage={est['coverage_pct']}% unpriced={est['unpriced_count']} "
          f"missing_qty={est['missing_quantity_count']} no_rate={est['no_rate_count']}")

    # THE TWO AXES ARE INDEPENDENT, and this is the pin that matters. A rule set covering every
    # element in the index, with every quantity present, returns `complete: True` — over rates
    # nobody chose. A screen reading `complete` alone cannot tell this from the firm's own number.
    all_covered = [
        {"selector": "IfcWall", "code": "03 30 00", "basis": "area", "unit_cost": 28.0,
         "rate_from": "quoted", "description": "Walls"},
        {"selector": "IfcDoor", "code": "08 11 00", "basis": "count", "unit_cost": 1450.0,
         "rate_from": "quoted", "description": "Doors"},
        {"selector": "IfcBeam", "code": "05 12 00", "basis": "count", "unit_cost": 900.0,
         "rate_from": "quoted", "description": "Beams"},
    ]
    sent = c.post(f"/projects/{pid}/cost/estimate",
                  json={"rules": all_covered, "quantities": QTY}).json()
    assert sent["complete"] is True, (sent["unpriced"], sent["missing_quantity"], sent["no_rate"])
    assert sent["rules_seeded"] is False, "a SENT set is never the starter set, whatever is stored"
    assert sent["rule_count"] == 3
    assert c.get(f"/projects/{pid}/cost/rules").json()["seeded"] is True, \
        "a what-if estimate must not write the stored set"

    # Save the firm's own set → the rate axis shuts and the number becomes the firm's.
    put = c.put(f"/projects/{pid}/cost/rules", json={"rules": all_covered})
    assert put.status_code == 200, put.text[:300]
    assert put.json()["saved"] == 3
    assert c.get(f"/projects/{pid}/cost/rules").json()["seeded"] is False

    e2 = c.post(f"/projects/{pid}/cost/estimate", json={"quantities": QTY}).json()
    assert e2["rules_seeded"] is False, "a saved set is not the starter set"
    assert e2["rule_count"] == 3 and e2["complete"] is True
    # the total MOVED, which is the proof the STORED rules are the ones being run rather than a
    # default the route fell back to
    assert e2["total"] != est["total"], (e2["total"], est["total"])
    assert e2["total"] == sent["total"], "the stored set must price exactly as it did when sent"

    # A bad rule is a 422 from the ROUTE, not a 500 at estimate time two screens later.
    bad = c.put(f"/projects/{pid}/cost/rules", json={"rules": [
        {"selector": "", "code": "x", "basis": "area", "unit_cost": 1.0}]})
    assert bad.status_code == 422, (bad.status_code, bad.text[:200])
    assert len(c.get(f"/projects/{pid}/cost/rules").json()["rules"]) == 3, "the 422 WROTE"

    # /cost/sov SHARES `_run_estimate`, so it is unblocked by the same change and must agree.
    sov = c.post(f"/projects/{pid}/cost/sov", json={"markup_pct": 10, "quantities": QTY})
    assert sov.status_code == 200, sov.text[:300]
    sj = sov.json()
    assert sj["estimate_total"] == e2["total"], (sj["estimate_total"], e2["total"])
    assert sj["covers_whole_model"] is True, sj["excluded"]
    assert sj["at_cost"] is False and sj["markup_pct"] == 10
    assert sj["reconciles"] is True and sj["reconciles_by_element"] is True
    assert sj["duplicate_guids"] == []
    # at cost is the DEFAULT, and the flag is the only thing that says so — correct for cost-plus,
    # an under-bill on lump sum
    free = c.post(f"/projects/{pid}/cost/sov", json={"quantities": QTY}).json()
    assert free["at_cost"] is True and free["sov_total"] == free["estimate_total"]

    # ===========================================================================================
    # THE DANGEROUS COMBINATION, PROVED RATHER THAN DESCRIBED: `complete: True` AND
    # `rules_seeded: True` on the same response. Everything above proved the two axes exist
    # separately, which is not the same claim — *asserting each half of a conjunction is not
    # asserting the conjunction*, and this is the state a screen reading `complete` alone presents
    # as a finished estimate.
    #
    # A model of nothing but walls and doors is all it takes, because that is what the starter set
    # happens to cover. On a real project it takes a firm that priced four trades and stopped.
    # ===========================================================================================
    pid2 = c.post("/projects", json={"name": "Starter Complete"}).json()["id"]
    c.post(f"/projects/{pid2}/properties/index", files={"file": ("props.json", json.dumps({
        "schema": "demo", "project": {"name": "Starter Complete"},
        "elements": [{"guid": "SW1", "ifc_class": "IfcWall", "name": "Wall"},
                     {"guid": "SD1", "ifc_class": "IfcDoor", "name": "Door"}],
    }).encode(), "application/json")})
    danger = c.post(f"/projects/{pid2}/cost/estimate",
                    json={"quantities": {"SW1": {"area": 120.0}}}).json()
    assert danger["complete"] is True, (danger["unpriced"], danger["missing_quantity"],
                                        danger["no_rate"])
    assert danger["rules_seeded"] is True, "the starter set must still be declared as the starter set"
    assert danger["total"] > 0
    print(f"  COMPLETE OVER PLACEHOLDER RATES: total={danger['total']} "
          f"complete={danger['complete']} rules_seeded={danger['rules_seeded']} "
          f"coverage={danger['coverage_pct']}% — the state `complete` alone cannot distinguish "
          f"from the firm's own number")

print("ESTIMATE-DARK OK - a cost rule set is storable, and it is validated by the SAME function the "
      "estimate runs, so a set that saves is a set that prices. An absent `rules` body now means "
      "USE THE STORED SET rather than price nothing, which is why /cost/estimate had no caller. "
      "And the response carries `rules_seeded` out of the store: `complete` is a verdict about "
      "coverage of the MODEL and is silent on whether anybody chose the RATES, so a confident total "
      "over the starter set's placeholders is reachable and the flag is the only thing that says so.")
