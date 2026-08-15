"""R46 ② — the modelled-delay adapter: impacted as-planned and collapsed as-built.

Two assertions carry this file.

**`concurrency is MEASURED, not asserted`** — `eot.analyse` names concurrency and declines to
apportion it, which is the right refusal to make without a network. With one it is arithmetic: two
overlapping delays move the finish by less than their sum, and the difference is the entitlement
nobody gets twice.

**`collapsed as-built is REFUSED on our data, and says why`** — the method removes activities that
are already in the as-built network, and ours are not there. The refusal is the finding. The
workaround (insert the events, then remove them) is impacted as-planned wearing the other method's
name, and a report that did it could not say what it had done.
"""
from __future__ import annotations

import json

from aec_api import schedule_baselines, schedule_modelled

_FAILURES: list[str] = []
_REAL_GET = schedule_baselines._get


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02"}}


CHAIN = [act("a", 5), act("b", 10, "a"), act("c", 15, "b")]


def snapshot(acts: list[dict], schema: int = 2) -> dict:
    frozen = {}
    for r in acts:
        d = r["data"]
        row = {"ref": r["ref"], "name": r["title"], "start": d.get("start"),
               "finish": None, "budget": None}
        if schema >= schedule_baselines.SCHEMA:
            row.update({k: d[k] for k in ("duration", "predecessors") if d.get(k) not in (None, "")})
        frozen[r["id"]] = row
    return {"id": "b1", "name": "GMP", "captured_at": "2026-02-01",
            "schema": schema, "activities": frozen}


def stub(base: dict | None) -> None:
    schedule_baselines._get = lambda pid, bid: base        # type: ignore[assignment]


#: Two events on the SAME activity, overlapping in time. Individually 8 + 6 = 14 days; together they
#: cannot cost 14, because they ran through the same stretch of the critical path.
CONCURRENT = [
    {"id": "E1", "name": "Storm shutdown", "days": 8, "impacts": "b",
     "onset": "2026-03-09", "responsibility": "employer"},
    {"id": "E2", "name": "Late design release", "days": 6, "impacts": "b",
     "onset": "2026-03-09", "responsibility": "employer"},
]
#: One event, for the clean single-cause case.
SINGLE = [{"id": "E1", "name": "Storm shutdown", "days": 8, "impacts": "b",
           "onset": "2026-03-09", "responsibility": "employer"}]


def main() -> int:
    try:
        # --- impacted as-planned, on the baseline -------------------------------------------------
        stub(snapshot(CHAIN))
        r = schedule_modelled.impacted("p1", SINGLE)
        check("the events reach the vendored engine and move the baseline finish",
              r["available"] and r["total_days"] > 0,
              f"{r['unimpacted_finish']} -> {r['impacted_finish']}, {r['total_days']} working days")

        check("the result survives json.dumps", _ser(r), "a route has to return it")

        check("the method names itself, with its MIP number",
              "3.6" in (r["mip"] or "") and "impacted" in (r["method"] or "").lower(),
              f"{r['method']} ({r['mip']}) — a modelled number without its method cannot be weighed")

        check("...and it is run against the BASELINE, named on the result",
              (r.get("baseline") or {}).get("name") == "GMP",
              "impacting a progressed schedule is a different method with a different name")

        check("the duration is declared as the CALLER'S, not derived",
              r["days_source"] == "caller",
              "notice_clock detects that an event happened and never what it cost; the most "
              "contested input on the page is typed, and the response says so")

        check("...and responsibility is carried through, never computed",
              r["per_event"][0]["responsibility"] == "employer",
              "whose delay it was is a contractual question, not an arithmetic one")

        # Working days, and the engine says why in its own comment: doing this arithmetic on
        # calendar days produced NEGATIVE concurrency -- a number that cannot exist -- on 14 of 150
        # random networks, because a delay spanning a weekend read as 5 against a sum of 3. Same
        # class as the calendar/working seam `schedule_compare` surfaces. Both axes are reported.
        check("each event's impact is in WORKING days, with calendar days beside it",
              r["per_event"][0]["days"] <= r["per_event"][0]["calendar_days"],
              f"{r['per_event'][0]['days']}d working vs {r['per_event'][0]['calendar_days']}d "
              "calendar — mixing the axes is what makes concurrency go negative")

        # --- THE measurement eot.py cannot make ----------------------------------------------------
        conc = schedule_modelled.impacted("p1", CONCURRENT)
        check("CONCURRENCY IS MEASURED, not asserted",
              conc["available"] and conc["is_concurrent"]
              and conc["concurrency_days"] == conc["sum_of_individual_days"] - conc["total_days"]
              and conc["concurrency_days"] > 0,
              f"individually {conc['sum_of_individual_days']}d, together {conc['total_days']}d "
              f"-> {conc['concurrency_days']}d of overlap. `eot.analyse` names concurrency and "
              "declines to apportion it, correctly, because it has no network to measure it on")

        check("...and independent events show ZERO concurrency — the twin",
              (lambda x: x["available"] and x["concurrency_days"] == 0)(
                  schedule_modelled.impacted("p1", [
                      {"id": "E1", "name": "storm", "days": 4, "impacts": "a"},
                      {"id": "E2", "name": "design", "days": 4, "impacts": "c"}])),
              "without this, a concurrency number that was always positive would look like a "
              "finding on every project")

        # --- collapsed as-built: the refusal IS the finding -----------------------------------------
        col = schedule_modelled.collapsed(CHAIN, SINGLE)
        check("collapsed as-built is REFUSED on our data, and says why",
              col["available"] is False and col.get("missing_from_as_built") == ["E1"]
              and "already in the as-built" in col["reason"],
              "the method removes activities that are there; ours are detected from the field "
              "record and are not in the schedule as tasks")

        check("...and it names the alternative rather than leaving a dead end",
              "impacted as-planned" in col["reason"],
              "inserting the events and then removing them is impacted as-planned wearing the "
              "subtractive method's name")

        # It works when the precondition IS met — otherwise the refusal above is the only branch
        # this adapter can ever take, and 'it refuses' would be unfalsifiable.
        as_built = CHAIN + [act("E1", 8, "a")]
        as_built[1]["data"]["predecessors"] = "a,E1"
        ok = schedule_modelled.collapsed(as_built, SINGLE)
        check("...and it RUNS when the events really are in the as-built network",
              ok["available"] and "3.9" in (ok["mip"] or "") and ok["total_days"] > 0,
              f"{ok['method']} ({ok['mip']}): but-for finish {ok['unimpacted_finish']} vs as-built "
              f"{ok['impacted_finish']}, {ok['total_days']}d")

        # --- input hygiene ---------------------------------------------------------------------------
        stub(snapshot(CHAIN))
        mixed = schedule_modelled.impacted("p1", SINGLE + [
            {"id": "BAD1", "name": "no duration", "impacts": "b"},
            {"id": "BAD2", "name": "no activity", "days": 5},
            {"id": "BAD3", "name": "negative", "days": -3, "impacts": "b"}])
        check("malformed events are NAMED and excluded, not silently dropped",
              mixed["available"] and len(mixed["rejected_events"]) == 3,
              f"{mixed['rejected_events']} — a discarded event is an entitlement quietly shrinking")

        check("...and one malformed event does not take out the analysis",
              mixed["total_days"] == r["total_days"],
              "the usable event still produced the same number it produces alone")

        # --- refusals ----------------------------------------------------------------------------------
        no_ev = schedule_modelled.impacted("p1", [])
        check("no events is refused as a MISSING INPUT, not an empty result",
              no_ev["available"] is False and "missing input" in no_ev["reason"],
              no_ev["reason"][:80])

        stub(None)
        no_base = schedule_modelled.impacted("p1", SINGLE)
        check("no baseline is refused — it will not quietly impact the live schedule instead",
              no_base["available"] is False and "different method" in no_base["reason"],
              no_base["reason"][:88])

        stub(snapshot(CHAIN, schema=1))
        v1 = schedule_modelled.impacted("p1", SINGLE)
        check("a pre-v0.3.961 baseline is refused — dates without logic cannot be impacted",
              v1["available"] is False and "captured before logic" in v1["reason"],
              v1["reason"][:70])

        stub(snapshot(CHAIN))
        nowhere = schedule_modelled.impacted("p1", [
            {"id": "E9", "name": "orphan", "days": 5, "impacts": "not_an_activity"}])
        check("an event naming an activity the baseline does not contain is refused",
              nowhere["available"] is False and "attach" in nowhere["reason"],
              nowhere["reason"][:80])

        check("...and the refusal is OUR sentence, not the exception's text",
              "ModelledDelayError" not in nowhere["reason"] and "Traceback" not in nowhere["reason"],
              "`str(exc)` on a response path is the py/stack-trace-exposure shape gated in v0.3.962")

        check("every refusal reports counts as None, never 0",
              all(x["total_days"] is None and x["concurrency_days"] is None
                  and x["is_concurrent"] is None
                  for x in (col, no_ev, no_base, v1, nowhere)),
              "'this delay cost nothing' and 'nothing was modelled' must not render alike")
    finally:
        schedule_baselines._get = _REAL_GET                # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_modelled OK")
    return 0


def _ser(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
