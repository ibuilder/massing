"""REFUSAL-READERS — the behavioural gate for the class.

A recurring defect: an engine reads records of a type whose workflow carries a REFUSAL state
(rejected / void / superseded / denied / expired / withdrawn) and computes as though the refusal
never happened. v0.3.1122 shipped the accounting instances, v0.3.1123 the design-comparison ones;
this file covers the remaining five and is the gate that keeps the class from re-opening.

The gate's shape, per record type: drive the REAL route, transition a record into refusal, and
assert the consuming number does not move. Two rules, both learned by getting them wrong:

  1. An exclusion test whose subject COULD NOT HAVE WON proves nothing. Every assertion below
     therefore carries a POSITIVE CONTROL — the same record, measured while still live, must be the
     one driving the number — so a green run cannot mean "the subject was uncompetitive anyway".
  2. When you filter a computation, EVERY count derived from that set moves with it. Each block
     asserts the response RECONCILES: the filtered population plus the excluded list equals the
     total the same response reports.

Run: PYTHONPATH=src ./.venv/bin/python test_refusal_readers.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_refusal_readers.db"
# setdefault, not assignment: run_tests.py gives each suite an isolated `./_storage_{test}` and
# sweeps it, but only the name IT chose — a suite that overrides STORAGE_DIR owns that directory
# and the runner reports it rather than deleting it (91 such dirs, 122 MB, in the last full run).
# The fallback below is for a direct `python test_refusal_readers.py`, and is cleared at startup.
os.environ.setdefault("STORAGE_DIR", "./test_storage_refusal_readers")
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_refusal_readers.db",):
    if os.path.exists(_f):
        os.remove(_f)
if os.environ["STORAGE_DIR"] == "./test_storage_refusal_readers":   # direct run only
    import shutil
    shutil.rmtree("./test_storage_refusal_readers", ignore_errors=True)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def _mk(c, pid, key, data):
    r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
    assert r.status_code == 201, f"{key}: {r.text[:200]}"
    return r.json()


def _act(c, pid, key, rid, action):
    r = c.post(f"/projects/{pid}/modules/{key}/{rid}/transition", json={"action": action})
    assert r.status_code < 300, f"{key} {action}: {r.text[:200]}"
    return r.json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Refusal readers"}).json()["id"]

    # ---- 1. rfi.register: a WITHDRAWN RFI is not exposure ---------------------------------------
    live = _mk(c, pid, "rfi", {"subject": "Live RFI", "question": "Confirm rebar lap length.",
                               "discipline": "Structural", "priority": "High",
                               "due_date": "2099-01-01", "cost_impact": "None",
                               "schedule_impact": "None"})
    _act(c, pid, "rfi", live["id"], "submit")
    dead = _mk(c, pid, "rfi", {"subject": "Withdrawn RFI", "question": "Confirm slab depth.",
                               "discipline": "Structural", "priority": "High",
                               "due_date": "2099-01-01", "cost_impact": "Yes",
                               "schedule_impact": "Yes"})
    _act(c, pid, "rfi", dead["id"], "submit")

    # POSITIVE CONTROL: while the RFI is merely open, it IS the only source of exposure. Without
    # this the assertion after the void could pass on an RFI that never carried impact at all.
    reg = c.get(f"/projects/{pid}/rfi/register").json()
    assert reg["cost_impacted_count"] == 1, reg["cost_impacted_count"]
    assert reg["schedule_impacted_count"] == 1, reg["schedule_impacted_count"]

    _act(c, pid, "rfi", dead["id"], "void")
    reg = c.get(f"/projects/{pid}/rfi/register").json()
    # Measured before the fix: 1 and 1 — the entire reported cost and schedule exposure on this job
    # came from a question the team had retracted.
    assert reg["cost_impacted_count"] == 0, reg["cost_impacted_count"]
    assert reg["schedule_impacted_count"] == 0, reg["schedule_impacted_count"]
    assert reg["voided_count"] == 1, reg
    assert reg["withdrawn_excluded"] == [dead["ref"]], reg["withdrawn_excluded"]
    # ... while everything that was ALREADY right stays right: void has its own court, sits inside
    # closed_count, and never counted as open or overdue. Asserted so a future "fix" cannot quietly
    # double-count it.
    assert reg["open_count"] == 1 and reg["overdue_count"] == 0, reg
    assert reg["ball_in_court"].get("Void") == 1, reg["ball_in_court"]
    assert reg["open_count"] + reg["closed_count"] == reg["rfi_count"], reg
    assert reg["voided_count"] <= reg["closed_count"], reg

    # The turnaround metric was DEAD, not merely unfiltered: it read `updated_at`, a key no module
    # row carries (the column is `modified_at`), so it was permanently None and any refusal filter
    # over it would have been vacuous. An answered RFI must now produce a real number.
    ans = _mk(c, pid, "rfi", {"subject": "Answered RFI", "question": "Bar size?",
                              "answer": "Use #5 bars.", "discipline": "Structural"})
    _act(c, pid, "rfi", ans["id"], "submit")
    _act(c, pid, "rfi", ans["id"], "respond")
    reg = c.get(f"/projects/{pid}/rfi/register").json()
    assert reg["avg_response_days"] is not None, "avg_response_days is dead again"
    assert reg["avg_response_days"] >= 0, reg["avg_response_days"]

    # ---- 2. prequalification.score_project: a REJECTED sub is not the pool's risk ----------------
    good = _mk(c, pid, "prequalification", {"company": "Solid Steel", "trade": "Structural steel",
                                            "emr": 0.7, "annual_revenue": 40000000,
                                            "bonding_capacity": 20000000,
                                            "largest_project": 9000000,
                                            "references": "A\nB\nC", "rating": "A",
                                            "expires": "2099-01-01"})
    _act(c, pid, "prequalification", good["id"], "submit")
    _act(c, pid, "prequalification", good["id"], "approve")
    bad = _mk(c, pid, "prequalification", {"company": "Shaky Trades", "trade": "Drywall",
                                           "emr": 2.4, "annual_revenue": 100000,
                                           "largest_project": 20000, "rating": "D",
                                           "expires": "2000-01-01"})
    _act(c, pid, "prequalification", bad["id"], "submit")

    # POSITIVE CONTROL: submitted (not yet refused), this sub IS the high-risk one. An application
    # under review stays in the pool deliberately — it is a real bidder to weigh.
    sc = c.get(f"/projects/{pid}/prequal/scores").json()
    assert sc["high_risk"] == 1, sc["high_risk"]
    assert sc["pool_count"] == 2, sc

    _act(c, pid, "prequalification", bad["id"], "reject")
    sc = c.get(f"/projects/{pid}/prequal/scores").json()
    # Measured before the fix: high_risk 1, on a project whose only high-risk sub had already been
    # turned down. `score_record` even raised a "marked rejected" flag — reading data["status"],
    # the typed field, while ignoring workflow_state, the field the transition sets.
    assert sc["high_risk"] == 0, sc["high_risk"]
    assert sc["pool_count"] == 1, sc
    assert [x["company"] for x in sc["not_in_pool"]] == ["Shaky Trades"], sc["not_in_pool"]
    # Still LISTED, worst-first, with its score intact — excluded from the headline, not hidden.
    assert [s["company"] for s in sc["subs"]] == ["Shaky Trades", "Solid Steel"], sc["subs"]
    assert sc["subs"][0]["score"] == 20.0 and sc["subs"][0]["risk_band"] == "high", sc["subs"][0]
    assert sc["pool_count"] + len(sc["not_in_pool"]) == sc["count"], sc

    # ---- 3. approval_conditions: a DENIED entitlement imposes nothing ----------------------------
    ok = _mk(c, pid, "entitlement", {"subject": "Live CUP", "application_type": "Conditional use",
                                     "agency": "City", "hearing_date": "2026-03-01",
                                     "decision_date": "2026-03-02",
                                     "conditions": "1. Provide 20 parking stalls.\n"
                                                   "2. Dedicate a 10ft easement."})
    for a in ("submit", "schedule_hearing", "approve"):
        _act(c, pid, "entitlement", ok["id"], a)
    dn = _mk(c, pid, "entitlement", {"subject": "Refused variance", "application_type": "Variance",
                                     "agency": "City", "hearing_date": "2026-03-01",
                                     "decision_date": "2026-03-02",
                                     "conditions": "1. Build a 40ft sound wall.\n"
                                                   "2. Fund a traffic signal.\n"
                                                   "3. Reduce height to 3 storeys."})
    for a in ("submit", "schedule_hearing"):
        _act(c, pid, "entitlement", dn["id"], a)

    # POSITIVE CONTROL: at hearing, its three conditions ARE counted — a condition proposed before a
    # decision is a real thing to track. Only the settled refusal is refused.
    ac = c.get(f"/projects/{pid}/entitlements/conditions").json()
    assert ac["total_open"] == 5, ac["total_open"]

    _act(c, pid, "entitlement", dn["id"], "deny")
    ac = c.get(f"/projects/{pid}/entitlements/conditions").json()
    # Measured before the fix: total_open 5 — three of them the terms of a permission that was
    # refused (a sound wall, a traffic signal, a height reduction nobody owes).
    assert ac["total_open"] == 2, ac["total_open"]
    assert ac["live_count"] == 1, ac
    assert [x["ref"] for x in ac["refused"]] == [dn["ref"]], ac["refused"]
    assert ac["refused"][0]["condition_count"] == 3, ac["refused"]
    assert ac["live_count"] + len(ac["refused"]) == ac["entitlement_count"], ac
    denied_row = next(x for x in ac["entitlements"] if x["ref"] == dn["ref"])
    assert denied_row["status"] == "refused" and denied_row["open_count"] == 0, denied_row
    # Still listed with its conditions readable — an appeal puts them back in play.
    assert len(denied_row["conditions"]) == 3, denied_row["conditions"]

    # ...and the SAME refusal must hold one level up, where the conditions are checked against the
    # model. `/entitlements/condition-check` reads the same rows, so a denied entitlement's terms
    # would otherwise be model-checked and their misses reported as compliance failures.
    # POSITIVE CONTROL first: the refused entitlement's conditions are real, parseable ones that do
    # reach the checker — without this the assertion below could pass on conditions nobody checks.
    cc = c.get(f"/projects/{pid}/entitlements/condition-checks").json()
    assert cc["in_force_count"] == 1, cc
    assert [x["ref"] for x in cc["refused"]] == [dn["ref"]], cc["refused"]
    assert cc["in_force_count"] + len(cc["refused"]) == len(cc["entitlements"]), cc
    refused_row = next(x for x in cc["entitlements"] if x["ref"] == dn["ref"])
    assert refused_row["refused"] is True, refused_row
    assert (refused_row["exceeds_count"] + refused_row["not_checkable_count"]) > 0, \
        "the refused entitlement must carry checkable conditions, or the exclusion proves nothing"
    assert cc["total_exceeds"] + cc["total_not_checkable"] == sum(
        x["exceeds_count"] + x["not_checkable_count"] for x in cc["entitlements"] if not x["refused"]), cc

    # CONVERSE: appealing a denial makes the entitlement live again and its conditions count.
    _act(c, pid, "entitlement", dn["id"], "appeal")
    ac = c.get(f"/projects/{pid}/entitlements/conditions").json()
    assert ac["total_open"] == 5, f"appeal must restore the conditions: {ac['total_open']}"
    assert ac["refused"] == [], ac["refused"]
    _act(c, pid, "entitlement", dn["id"], "rehear")
    _act(c, pid, "entitlement", dn["id"], "deny")

    # ---- 4/5. spec_section: a VOID section demands nothing and is not a chain gap ----------------
    pkg = _mk(c, pid, "bid_package", {"name": "Concrete package", "discipline": "Structural",
                                      "budget": 500000})
    _mk(c, pid, "spec_section", {"section_number": "03 30 00", "title": "Cast-in-place concrete",
                                 "division": "03 - Concrete", "discipline": "Structural",
                                 "bid_package": pkg["id"],
                                 "submittals_required": "Product Data\nShop Drawings"})
    gone = _mk(c, pid, "spec_section", {"section_number": "09 91 00", "title": "Painting (deleted)",
                                        "division": "09 - Finishes", "discipline": "Architectural",
                                        "submittals_required": "Product Data\nSamples\nMock-up"})

    # A submittal LOGGED against the section that is about to be withdrawn. Without it the
    # `logged_total` assertion below would be vacuous — the same trap the carbon mutation fell into.
    _mk(c, pid, "submittal", {"title": "Paint colour samples", "spec_section": "09 91 00",
                              "type": "Sample"})

    # POSITIVE CONTROL: while issued, this section really does drive 3 of the 5 required submittals,
    # owns the only logged submittal, and really is an unpackaged link in the chain. All three
    # numbers must be ITS doing before the void.
    sl = c.get(f"/projects/{pid}/specs/submittal-log").json()
    assert sl["required_total"] == 5 and sl["missing_total"] == 4, sl
    assert sl["logged_total"] == 1, sl["logged_total"]
    assert sl["by_division"].get("09 - Finishes") == 3, sl["by_division"]
    tr = c.get(f"/projects/{pid}/spine/traceability").json()
    assert tr["coverage"]["specs_packaged_pct"] == 50.0, tr["coverage"]
    assert [g["ref"] for g in tr["gaps"]["specs_without_bid_package"]] == [gone["ref"]], tr["gaps"]

    _act(c, pid, "spec_section", gone["id"], "void")

    sl = c.get(f"/projects/{pid}/specs/submittal-log").json()
    # Measured before the fix: required_total 5, missing_total 5 — three of those missing-submittal
    # gaps were work orders against a section that had been deleted from the manual.
    assert sl["required_total"] == 2, sl["required_total"]
    assert sl["missing_total"] == 2, sl["missing_total"]
    # `logged_total` is summed submittal-side, so filtering the ROWS did not move it: found in
    # review, and the fourth time in this class that a count derived from a filtered set stayed
    # behind. The only logged submittal belonged to the withdrawn section, so it must now be 0.
    assert sl["logged_total"] == 0, sl["logged_total"]
    assert "09 - Finishes" not in sl["by_division"], sl["by_division"]
    assert sl["by_type"] == {"Product Data": 1, "Shop Drawing": 1}, sl["by_type"]
    assert sl["enforced_spec_count"] == 1 and sl["spec_count"] == 2, sl
    assert [x["ref"] for x in sl["withdrawn_excluded"]] == [gone["ref"]], sl["withdrawn_excluded"]
    assert sl["enforced_spec_count"] + len(sl["withdrawn_excluded"]) == sl["spec_count"], sl
    # Still a row, showing what it USED to ask for, requiring and missing nothing.
    void_row = next(r for r in sl["rows"] if r["ref"] == gone["ref"])
    assert void_row["withdrawn"] and void_row["required_count"] == 0, void_row
    assert void_row["missing_count"] == 0 and len(void_row["required"]) == 3, void_row

    tr = c.get(f"/projects/{pid}/spine/traceability").json()
    # Measured before the fix: 50.0%, with the void section named in the gap list as a broken link
    # for somebody to go fix. A withdrawn section is not an unpackaged one; it is not in the chain.
    assert tr["coverage"]["specs"] == 1, tr["coverage"]
    assert tr["coverage"]["specs_packaged_pct"] == 100.0, tr["coverage"]
    assert tr["gaps"]["specs_without_bid_package"] == [], tr["gaps"]
    assert [x["ref"] for x in tr["withdrawn_excluded"]] == [gone["ref"]], tr["withdrawn_excluded"]
    assert tr["coverage"]["specs"] + len(tr["withdrawn_excluded"]) == tr["spec_count"], tr
    assert [d["discipline"] for d in tr["disciplines"]] == ["Structural"], tr["disciplines"]

    # CONVERSE: the two readers share ONE rule (specs.SPEC_SECTION_WITHDRAWN), so they cannot drift
    # apart — asserted by identity, not by both happening to agree today.
    import inspect

    from aec_api import specs as specs_engine
    from aec_api import spine as spine_engine  # noqa: F401  (import proves the module loads)
    assert "SPEC_SECTION_WITHDRAWN" in inspect.getsource(spine_engine.traceability), \
        "spine.traceability must use the shared spec-section rule, not its own copy"
    assert specs_engine.SPEC_SECTION_WITHDRAWN == ("void",), specs_engine.SPEC_SECTION_WITHDRAWN

    # ---- the class's own invariant: refusal rules are CONSTANTS, not inline string literals -------
    # Every fix in this class named its rule. That is what makes a record type with several readers
    # survivable — v0.3.1122's owner_invoice had five, v0.3.1123's design_option three, and the
    # spec_section rule here has two. A rule spelled out inline in each reader is a rule with N
    # places to rot.
    from aec_api import approval_conditions, design_options, prequalification, project_budget, rfi
    for mod, name, expected in (
        (project_budget, "OWNER_INVOICE_NOT_BILLED", ("rejected",)),
        (design_options, "DESIGN_OPTION_NOT_IN_CONTENTION", ("rejected",)),
        (rfi, "RFI_WITHDRAWN", ("void",)),
        (prequalification, "PREQUAL_NOT_IN_POOL", ("rejected",)),
        (approval_conditions, "REFUSED_STATES", ("denied",)),
        (specs_engine, "SPEC_SECTION_WITHDRAWN", ("void",)),
    ):
        got = getattr(mod, name, None)
        assert got == expected, f"{mod.__name__}.{name}: {got!r} != {expected!r}"

print("refusal-readers gate OK — 5 instances + the dead turnaround metric, all positive-controlled")
