"""EVM-COVERAGE — `front_loaded_flag` accused a contractor on SURVEY COVERAGE, and its guard's
threshold was one record.

`evm.model_ev` compares the schedule's earned value against earned value derived from physically
installed model elements, and raises `front_loaded_flag` when the schedule runs materially ahead:
rendered in the EVM panel as *"Reported progress is running ahead of physical installation —
possible front-loaded SOV"*, beside a PDF download button. That is a fraud allegation.

**The engine had already identified this exact failure mode and guarded it**, in a comment reading
*"with zero verified elements the model EV is 0 by definition, and flagging 'front-loaded' then
would falsely accuse an un-surveyed job"*. The guard was `has_field_data = tracked > 0`. So the
threshold was ONE RECORD: survey a single element of four thousand and `model_percent_complete` is
at most 0.025%, `divergence` is nearly the entire EV, and the flag fires — on how much of the
building somebody had walked, not on what was reported. *A guard whose threshold is one covers only
the single case that was already harmless*, and `test_evm.py` asserted precisely that case
(`has_field_data is False`) and nothing past it. **A test can assert every neighbouring state of a
property and never the one the property is about.**

THE REPAIR IS A BOUND, NOT A BIGGER THRESHOLD
---------------------------------------------
Any coverage percentage would have been invented here. What is not invented is the CEILING: the most
physical progress the evidence could possibly support is everything except the elements known to
deviate, because every undetermined element might turn out to be installed. If the schedule's EV
sits under that ceiling, the whole gap is explained by what nobody has looked at yet and there is no
claim to make. At full coverage the ceiling equals the measured figure and the flag is unchanged —
so the bound only ever withholds a claim the evidence cannot carry, and never suppresses a real one.
That last sentence is the one worth distrusting, so it is asserted below in both directions.

AND `pending` IS NOT EVIDENCE
-----------------------------
Coverage is `determined / denominator`, not `tracked / total`. A `pending` row is a queued
inspection; counting it as coverage is the same mistake one layer down — it would report a job as
fully surveyed the moment somebody generated an inspection list for it.

THE SECOND DEFECT: THE DENOMINATOR SWAPPED SILENTLY
---------------------------------------------------
`denom = total or tracked or 1` falls back from the model's element count to the surveyed count, so
`model_percent_complete` measures a different quantity under one field name: 8 installed of 10
surveyed reads **80%** with no index loaded and **0.2%** against a 4,000-element index. Same data,
two answers, 400× apart, same key. `basis` now names it.

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_evm_coverage.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_evm_coverage.db"
os.environ["STORAGE_DIR"] = "./test_storage_evm_coverage"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_evm_coverage.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import timedelta  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import money  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.model_index import _INDEX  # noqa: E402
from aec_api.timeutil import utc_today  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


# ── the rule, isolated from the engine so it can be MUTATED directly ──────────────────────────────
#
# `test_unique_read_guard` paid for this shape: asserting that a function still REPORTS a site is
# not asserting how it CLASSIFIES it. The verdict is the thing under test, so the verdict is callable
# on its own, and the shipped engine is then checked to agree with it end to end.

def verdict_shipped(bac, ev_sched, ev_model, tracked):
    """The PRE-FIX rule, verbatim: any record at all, and a 5%-of-BAC raw divergence."""
    return bool(tracked > 0 and bac and money.q2(ev_sched - ev_model) > 0.05 * bac)


def verdict_fixed(bac, ev_sched, ev_model_max, tracked):
    """The shipped rule now: the gap must clear the CEILING the evidence allows."""
    return bool(tracked > 0 and bac and money.q2(ev_sched - ev_model_max) > 0.05 * bac)


with TestClient(app) as c:
    today = utc_today()

    def project(name):
        pid = c.post("/projects", json={"name": name}).json()["id"]
        cc = c.post(f"/projects/{pid}/modules/cost_code",
                    json={"data": {"code": "03-30", "description": "Concrete", "division": "03"}}
                    ).json()["id"]
        # One activity: BAC 1,000,000, reported 60% complete, window straddling today.
        r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": {
            "name": "Structure", "cost_code": cc, "budget": 1_000_000, "percent": 60,
            "start": str(today - timedelta(days=30)), "finish": str(today + timedelta(days=30))}})
        assert r.status_code == 201, r.text[:200]
        return pid

    def index(pid, n):
        _INDEX[pid] = {f"g{i}": {"guid": f"g{i}", "ifc_class": "IfcWall", "storey": "L1"}
                       for i in range(n)}

    def mark(pid, guid, status):
        r = c.put(f"/projects/{pid}/verification/{guid}", json={"status": status})
        assert r.status_code == 200, r.text[:200]

    def mev(pid):
        r = c.get(f"/projects/{pid}/evm/model-ev")
        assert r.status_code == 200, r.text[:200]
        return r.json()

    # ── ① THE SHIPPED DEFECT, REPRODUCED: one record on a 4,000-element model ─────────────────────
    print("\n-- the defect: a 4,000-element model, ONE element surveyed --")
    p1 = project("Thin coverage")
    index(p1, 4000)
    mark(p1, "g0", "installed")
    m = mev(p1)
    ok(m["total_elements"] == 4000 and m["tracked_elements"] == 1,
       f"the setup is the shipped shape   total={m['total_elements']} tracked={m['tracked_elements']}")
    ok(m["ev_schedule"] > 0 and m["bac"] > 0,
       f"there is a schedule EV to compare against   ev_sched={m['ev_schedule']} bac={m['bac']}")
    # PROOF OF REACH: the pre-fix rule must ACCUSE on this input, or the gate proves nothing.
    ok(verdict_shipped(m["bac"], m["ev_schedule"], m["ev_model"], m["tracked_elements"]) is True,
       "PROOF OF REACH: the PRE-FIX rule fires here — the defect was real")
    ok(m["front_loaded_flag"] is False,
       "...and the shipped engine now withholds the accusation")
    ok(verdict_fixed(m["bac"], m["ev_schedule"], m["ev_model_max"], m["tracked_elements"]) is False,
       "...which is the fixed rule's verdict, computed independently")
    ok(m["has_field_data"] is True,
       "`has_field_data` is still True — it answers a DIFFERENT question and no longer gates the flag")
    ok(m["coverage_pct"] < 0.1 and m["determined_elements"] == 1,
       f"coverage is reported, and it is the number the old guard ignored   {m['coverage_pct']}% "
       f"({m['determined_elements']} determined)")
    # THE ROUNDING IS A TRAP, and it is the same defect one layer down: 1 of 4,000 rounds to 0.0%,
    # which is the string an UNTOUCHED job prints. The counts have to travel with the percentage, or
    # "nobody looked" and "somebody looked once" render identically.
    ok(m["coverage_pct"] == 0.0 and m["determined_elements"] > 0,
       "...and the ROUNDED percentage is 0.0% on a non-zero coverage, so it is not the authority")
    ok("1 of 4000" in m["note"],
       "...so the note quotes the COUNTS, not only the percentage")
    ok(m["model_percent_complete"] < 1 <= m["model_percent_complete_max"],
       "the response carries a RANGE, not a point: "
       f"{m['model_percent_complete']}%..{m['model_percent_complete_max']}%")
    ok(str(m["coverage_pct"]) in m["note"] and "between" in m["note"],
       "and the note gives the range in words, for a reader who sees only the PDF")

    # ── ② THE FIX DOES NOT DISABLE THE FEATURE: full coverage still accuses ───────────────────────
    print("\n-- full coverage, genuinely behind: the accusation must SURVIVE --")
    p2 = project("Fully surveyed")
    index(p2, 10)
    for i in range(10):
        mark(p2, f"g{i}", "deviation" if i else "installed")
    m2 = mev(p2)
    ok(m2["coverage_pct"] == 100.0,
       f"every element has a determined status   coverage={m2['coverage_pct']}%")
    ok(m2["model_percent_complete"] == 10.0 and m2["model_percent_complete_max"] == 10.0,
       "at full coverage the ceiling EQUALS the measured figure — the bound adds nothing   "
       f"{m2['model_percent_complete']}% / {m2['model_percent_complete_max']}%")
    ok(m2["ev_model"] == m2["ev_model_max"],
       "...so the two EVs coincide and the fixed rule reduces to the shipped one")
    ok(m2["front_loaded_flag"] is True,
       "AND THE FLAG STILL FIRES: 60% reported against 10% in place is a real finding")
    ok(verdict_shipped(m2["bac"], m2["ev_schedule"], m2["ev_model"], m2["tracked_elements"])
       is verdict_fixed(m2["bac"], m2["ev_schedule"], m2["ev_model_max"], m2["tracked_elements"]),
       "...and both rules agree here, which is what 'only ever withholds' has to mean")

    # ── ③ `pending` IS NOT COVERAGE ───────────────────────────────────────────────────────────────
    print("\n-- a queued inspection list is not a surveyed building --")
    p3 = project("All pending")
    index(p3, 10)
    for i in range(10):
        mark(p3, f"g{i}", "pending")
    m3 = mev(p3)
    ok(m3["tracked_elements"] == 10 and m3["determined_elements"] == 0,
       f"ten rows, nothing determined   tracked={m3['tracked_elements']} "
       f"determined={m3['determined_elements']}")
    ok(m3["coverage_pct"] == 0.0,
       "coverage is 0% — `tracked / total` would have said 100%")
    ok(m3["front_loaded_flag"] is False,
       "...and generating an inspection list does not become evidence of front-loading")
    ok(m3["model_percent_complete_max"] == 100.0,
       "the ceiling is 100%: with nothing determined, everything might be installed")

    # ── ④ THE DENOMINATOR SWAP IS NAMED ───────────────────────────────────────────────────────────
    print("\n-- what the percentage is a share OF --")
    p4 = project("No index")
    _INDEX.pop(p4, None)
    for i in range(10):
        mark(p4, f"g{i}", "installed" if i < 8 else "deviation")
    m4 = mev(p4)
    ok(m4["total_elements"] == 0 and m4["basis"] == "surveyed elements",
       f"with no index the denominator is the surveyed set, and `basis` SAYS SO   {m4['basis']!r}")
    ok(m4["model_percent_complete"] == 80.0,
       f"8 of 10 surveyed = 80%   {m4['model_percent_complete']}%")
    # The same eight elements against a loaded index of 4,000 is 0.2% — 400x apart, one field name.
    p5 = project("Same data, index loaded")
    index(p5, 4000)
    for i in range(10):
        mark(p5, f"g{i}", "installed" if i < 8 else "deviation")
    m5 = mev(p5)
    ok(m5["basis"] == "model elements" and m5["model_percent_complete"] == 0.2,
       f"...the SAME eight elements read {m5['model_percent_complete']}% against the model   "
       f"basis={m5['basis']!r}")
    ok(m4["basis"] != m5["basis"],
       "two bases, two answers, and the field that distinguishes them is in the response")
    ok(m4["basis"] in m4["note"] and m5["basis"] in m5["note"],
       "...and in the note, because the PDF carries the note and not the JSON")

    # ── ⑤ AN UN-SURVEYED JOB IS STILL AN UN-SURVEYED JOB ──────────────────────────────────────────
    print("\n-- the one case the old guard did cover must keep working --")
    p6 = project("Nothing surveyed")
    index(p6, 4000)
    m6 = mev(p6)
    ok(m6["has_field_data"] is False and m6["front_loaded_flag"] is False,
       "no records at all: no field data, no accusation")
    ok("No field verification recorded yet" in m6["note"],
       "...and the note still says which of the two reasons applies")
    ok(m6["coverage_pct"] == 0.0 and m6["model_percent_complete_max"] == 100.0,
       "coverage 0%, ceiling 100% — the same shape as ③, which is correct: both are 'nobody looked'")
    ok(m6["determined_elements"] == 0 and m["determined_elements"] == 1
       and m6["coverage_pct"] == m["coverage_pct"],
       "AND THIS JOB PRINTS THE SAME 0.0% AS ① — only the counts tell them apart")
    ok("0 of 4000" in m6["note"],
       "...which is why the note carries them")

    # ── ⑥ THE ARITHMETIC IDENTITY, so a future refactor cannot drift the parts apart ──────────────
    print("\n-- the parts must still add up --")
    for nm, r in (("thin", m), ("full", m2), ("pending", m3), ("no-index", m4)):
        denom = r["total_elements"] or r["tracked_elements"] or 1
        ok(r["determined_elements"] == r["installed_elements"] + r["deviated_elements"],
           f"{nm}: determined == installed + deviated   "
           f"{r['determined_elements']} == {r['installed_elements']} + {r['deviated_elements']}")
        ok(r["model_percent_complete_max"] == round(100 * max(0, denom - r["deviated_elements"])
                                                    / denom, 1),
           f"{nm}: the ceiling is 'everything but the known deviations'")
        ok(r["divergence_unexplained"] <= r["divergence"],
           f"{nm}: the unexplained gap never exceeds the measured one   "
           f"{r['divergence_unexplained']} <= {r['divergence']}")

    # ── ⑦ THE SECOND SITE: `wip.model_progress`, found after the first and WORSE ────────────────────
    #
    # Same defect in the WIP schedule, where `percent_complete` is `installed / total` over the whole
    # model and `schedule(method="units-installed")` multiplies it by the contract value to get
    # EARNED REVENUE — which drives over/under-billing, which `accounting.journal_entries` posts back
    # as the WIP-ADJ line. *The EVM instance raises a banner; this one moves a number in a financial
    # statement.* The loud one was found first, and severity ran the other way.
    print("\n-- wip.model_progress: the same gap, driving earned revenue --")

    def wip_project(name, elements, marks, budget=800_000, actual=400_000):
        pid = c.post("/projects", json={"name": name}).json()["id"]
        cc = c.post(f"/projects/{pid}/modules/cost_code",
                    json={"data": {"code": "03-30", "description": "Concrete", "division": "03"}}
                    ).json()["id"]
        for key, data in (("budget", {"cost_code": cc, "description": "C", "revised": budget}),
                          ("prime_contract", {"name": "GMP", "type": "GMP", "value": 1_000_000}),
                          ("direct_cost", {"description": "c", "cost_code": cc, "amount": actual})):
            r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
            assert r.status_code == 201, r.text[:160]
        # The schedule of values is what makes `cost.summary`'s `budget` non-zero, and
        # `estimated_cost = budget or forecast` silently falls back to the actual-cost floor without
        # it — which makes cost-to-cost 100% and the whole comparison meaningless. Asserted below
        # rather than assumed, because a fixture that quietly measures the wrong thing is how the
        # first draft of this section reported two failures it could not explain.
        c.post(f"/projects/{pid}/cost/sov/from-budget?replace=true")
        _INDEX[pid] = {f"e{i}": {"guid": f"e{i}", "ifc_class": "IfcWall", "storey": "L1"}
                       for i in range(elements)}
        for guid, st in marks:
            assert c.put(f"/projects/{pid}/verification/{guid}",
                         json={"status": st}).status_code == 200
        return pid

    def flag_shipped(m_pct, c_pct):
        """The PRE-FIX rule: the raw divergence, in BOTH directions."""
        d = round(m_pct - c_pct, 1)
        return "cost-ahead" if d <= -10 else "physical-ahead" if d >= 10 else "aligned"

    # 4,000 elements, ONE installed, cost-to-cost at 50%.
    wp = wip_project("WIP thin coverage", 4000, [("e0", "installed")])
    mp = c.get(f"/projects/{wp}/wip/model-progress").json()
    ok(mp["total_elements"] == 4000 and mp["installed_elements"] == 1
       and mp["determined_elements"] == 1,
       f"the setup is the shipped shape   total={mp['total_elements']} "
       f"determined={mp['determined_elements']}")
    w = c.get(f"/projects/{wp}/wip").json()
    mb = w["model"]
    ok(w["estimated_cost"] == 800_000 and w["cost_to_date"] == 400_000,
       f"the cost side is the fixture's, not a fallback   est={w['estimated_cost']} "
       f"actual={w['cost_to_date']}")
    ok(mb["cost_percent_complete"] == 50.0 and mb["model_percent_complete"] == 0.0,
       f"cost says 50%, the model says {mb['model_percent_complete']}% — because nobody walked it")
    ok(flag_shipped(mb["model_percent_complete"], mb["cost_percent_complete"]) == "cost-ahead",
       "PROOF OF REACH: the PRE-FIX rule calls this `cost-ahead` — "
       "its own note's \"classic front-loaded-billing signal\"")
    ok(mb["flag"] == "aligned",
       f"...and the shipped engine now says {mb['flag']!r}, because the ceiling is "
       f"{mb['model_percent_complete_max']}%")
    ok(mb["fully_determined"] is False and mb["coverage_pct"] < 0.1,
       f"the coverage is reported   fully_determined={mb['fully_determined']} "
       f"coverage={mb['coverage_pct']}%")
    # THE COUNTS, not the rounded ratio — 1 of 4,000 is `coverage_pct: 0.0`, the same string an
    # untouched job prints. Added after a mutation stripping the counts from this note survived:
    # the EVM site asserted it and this one did not. *The same lesson, unasserted at the second
    # site, is the lesson not learned.*
    ok("1 of 4000" in mp["note"] and "unsurveyed, not absent" in mp["note"],
       "...and the model-progress note gives the COUNTS and says what the remainder is")

    # ── ⑧ THE ASYMMETRY, which is the whole design of that bound ──────────────────────────────────
    #
    # Missing coverage can only ever DEPRESS the measured physical %, so it biases the comparison in
    # ONE direction. `physical-ahead` cannot be manufactured by a gap; `cost-ahead` is exactly what a
    # gap fabricates. Bounding both would suppress a real finding to fix a false one.
    print("\n-- the bound is asymmetric, and both halves are asserted --")
    # 100 elements, 75 installed, 25 untouched; cost 50%. Physical (75%) is ahead DESPITE the gap.
    wp2 = wip_project("WIP physical ahead", 100, [(f"e{i}", "installed") for i in range(75)])
    mb2 = c.get(f"/projects/{wp2}/wip").json()["model"]
    ok(mb2["model_percent_complete"] == 75.0 and mb2["fully_determined"] is False,
       f"75% installed with 25 unsurveyed   {mb2['model_percent_complete']}% "
       f"(determined {mb2['determined_elements']}/100)")
    ok(mb2["flag"] == "physical-ahead",
       "`physical-ahead` is UNBOUNDED and still fires — a coverage gap works against it")
    # 10 elements fully determined: 1 installed, 9 deviations; cost 50%. A real `cost-ahead`.
    wp3 = wip_project("WIP cost ahead", 10,
                      [("e0", "installed")] + [(f"e{i}", "deviation") for i in range(1, 10)])
    mb3 = c.get(f"/projects/{wp3}/wip").json()["model"]
    ok(mb3["fully_determined"] is True and mb3["model_percent_complete_max"] == 10.0,
       f"every element determined, so the ceiling IS the figure   "
       f"{mb3['model_percent_complete']}% / {mb3['model_percent_complete_max']}%")
    ok(mb3["flag"] == "cost-ahead",
       "AND `cost-ahead` STILL FIRES on real evidence — the bound withholds, it does not disable")
    ok(flag_shipped(mb3["model_percent_complete"], mb3["cost_percent_complete"]) == mb3["flag"],
       "...and at full coverage the two rules agree, which is what 'only ever withholds' means")

    # ── ⑨ THE REVENUE BAND IS NAMED ON THE ROW THAT CARRIES THE MONEY ──────────────────────────────
    print("\n-- units-installed POC on a partial survey --")
    wu = c.get(f"/projects/{wp}/wip?method=units-installed").json()
    # `.get` rather than `[...]`: a mutation that deletes the band block must REPORT a missing field,
    # not die with a KeyError naming the test as the problem. A red build whose message misdiagnoses
    # is worse than one that stays quiet, because somebody acts on it.
    ok(wu["pct_method"] == "units-installed" and wu.get("poc_coverage_partial") is True,
       "the WIP row itself flags that its driver rests on a partial survey   "
       f"poc_coverage_partial={wu.get('poc_coverage_partial')!r}")
    ok(wu["earned_revenue"] == 0.0 and wu.get("earned_revenue_max") == 1_000_000.0,
       f"earned revenue is a BAND: {wu['earned_revenue']} … {wu.get('earned_revenue_max')}")
    ok("1 of 4000" in wu["note"] and "accounting policy decision" in wu["note"],
       "...and the note gives the counts and says which end is recognised")
    # `earned_revenue` is deliberately UNCHANGED: which end a WIP schedule recognises is revenue-
    # recognition policy, not an engine's choice. What was wrong was that nothing said a band existed.
    ok(wu["earned_revenue"] == round(wu["percent_complete"] / 100 * wu["contract_value"], 2),
       "the recognised figure is still the measured lower bound — no policy was invented here")
    wf = c.get(f"/projects/{wp3}/wip?method=units-installed").json()
    ok("poc_coverage_partial" not in wf and "earned_revenue_max" not in wf,
       "and a fully-surveyed job carries no band and no caveat")

    # ── A QUEUED INSPECTION IS NOT COVERAGE, at this site either ──────────────────────────────────
    #
    # Added after a mutation survived: `determined_guids = every tracked guid` changed no assertion,
    # because every WIP fixture above marks elements as installed or deviation. *A distinction can
    # hold at one site and be unasserted at the other; the two engines shared a lesson and not a
    # test.*
    print("\n-- wip: ten pending inspections are not ten surveyed elements --")
    wp4 = wip_project("WIP pending", 10, [(f"e{i}", "pending") for i in range(10)])
    mb4 = c.get(f"/projects/{wp4}/wip").json()["model"]
    ok(mb4["determined_elements"] == 0 and mb4["coverage_pct"] == 0.0,
       f"ten rows, nothing determined   determined={mb4['determined_elements']} "
       f"coverage={mb4['coverage_pct']}%")
    ok(mb4["fully_determined"] is False,
       "...so the job is NOT fully surveyed, which `tracked >= total` would have claimed")
    ok(mb4["flag"] == "aligned" and mb4["model_percent_complete_max"] == 100.0,
       "...and generating an inspection list does not become a front-loaded-billing signal   "
       f"flag={mb4['flag']!r}")

    # ── ⑩ THE QUANTITY-WEIGHTED CEILING IS WEIGHTED THE SAME WAY ────────────────────────────────────
    #
    # A count-weighted ceiling over a quantity-weighted percentage is not a bound: one unsurveyed
    # 400 m³ pour is 1 element and a quarter of the concrete.
    print("\n-- the ceiling must be weighted like the figure it bounds --")
    # THE TWO CEILINGS MUST DIFFER IN THIS FIXTURE, or the assertion cannot see which one is used.
    # The first draft had two elements and no deviation, so count-max and quantity-max were BOTH
    # 100% and a mutation leaving the ceiling count-weighted passed. One deviation on the big pour
    # separates them: 2 of 3 by count (66.7%) against 100 of 500 m³ (20%).
    wq = c.post("/projects", json={"name": "WIP quantity"}).json()["id"]
    _INDEX[wq] = {
        "q1": {"guid": "q1", "ifc_class": "IfcSlab",            # installed, 10 m³
               "qtos": {"Qto_SlabBaseQuantities": {"NetVolume": 10}}},
        "q2": {"guid": "q2", "ifc_class": "IfcSlab",            # deviation, 400 m³
               "qtos": {"Qto_SlabBaseQuantities": {"NetVolume": 400}}},
        "q3": {"guid": "q3", "ifc_class": "IfcSlab",            # untouched, 90 m³
               "qtos": {"Qto_SlabBaseQuantities": {"NetVolume": 90}}},
    }
    assert c.put(f"/projects/{wq}/verification/q1", json={"status": "installed"}).status_code == 200
    assert c.put(f"/projects/{wq}/verification/q2", json={"status": "deviation"}).status_code == 200
    mq = c.get(f"/projects/{wq}/wip/model-progress?quantity=NetVolume").json()
    ok(mq["percent_complete"] == round(100 * 10 / 500, 1),
       f"one of three elements installed is {mq['percent_complete']}% of the concrete")
    ok(mq["percent_complete_max"] == round(100 * 100 / 500, 1)
       and mq["undetermined_quantity"] == 90.0,
       f"the ceiling is QUANTITY-weighted: {mq['percent_complete_max']}% "
       f"(installed 10 + undetermined {mq['undetermined_quantity']} of 500 m³)")
    ok(mq["percent_complete_count"] == round(100 / 3, 1)
       and mq["percent_complete_count_max"] == round(100 * 2 / 3, 1),
       "...and the COUNT pair is reported beside it and is a different number   "
       f"{mq['percent_complete_count']}% / {mq['percent_complete_count_max']}%")
    ok(mq["percent_complete_max"] != mq["percent_complete_count_max"],
       "...which is what makes the assertion above able to fail: one unsurveyed 90 m³ pour is "
       "a third of the elements and a fifth of the concrete")

print()
if FAILED:
    print(f"evm_coverage: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("EVM-COVERAGE OK - TWO sites. evm.model_ev: front_loaded_flag no longer fires on survey coverage: the accusation must "
      "clear the CEILING the evidence allows (everything but the known deviations), which at full "
      "coverage equals the measured figure so a real finding still fires; `pending` is not counted "
      "as coverage; `basis` names which denominator `model_percent_complete` is a share of; and the "
      "pre-fix rule is replayed and must accuse on the thin-coverage input before the gate reports. "
      "wip.model_progress (the worse site, found second - it drives EARNED REVENUE): `cost-ahead` must "
      "clear the same ceiling while `physical-ahead` stays unbounded, because a coverage gap biases "
      "the comparison in ONE direction; the units-installed WIP row carries the revenue band and "
      "names which end it recognises; and the quantity-weighted ceiling is quantity-weighted.")
