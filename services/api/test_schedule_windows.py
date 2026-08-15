"""R46 ① — the windows adapter, and the four EOT methods that were one number.

Read `the four AACE methods in eot.py return an IDENTICAL number` first. It is the reason this module
exists, it is measured rather than argued, and it is pinned here so the gap cannot close by accident
and go unnoticed — or widen.

The rest is about the series: a window is an interval between two dated snapshots, so the assertions
that matter are the ones about which snapshots take part and what happens to the ones that cannot.
"""
from __future__ import annotations

import json

from aec_api import eot, schedule_baselines, schedule_windows

_FAILURES: list[str] = []
_REAL_LOAD = schedule_baselines._load


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02"}}


def snap(bid: str, captured: str, acts: list[dict], schema: int = 2) -> dict:
    frozen = {}
    for r in acts:
        d = r["data"]
        row = {"ref": r["ref"], "name": r["title"], "start": d.get("start"),
               "finish": None, "budget": None}
        if schema >= schedule_baselines.SCHEMA:
            row.update({k: d[k] for k in ("duration", "predecessors") if d.get(k) not in (None, "")})
        frozen[r["id"]] = row
    return {"id": bid, "name": bid.upper(), "captured_at": captured,
            "schema": schema, "activities": frozen}


#: Three dated snapshots of one chain. `b` grows 10 -> 20 in the first window; `c` grows 15 -> 25 in
#: the second. Two distinct periods, two distinct causes — which is the whole point of windowing.
CHAIN_1 = [act("a", 5), act("b", 10, "a"), act("c", 15, "b")]
CHAIN_2 = [act("a", 5), act("b", 20, "a"), act("c", 15, "b")]
CHAIN_3 = [act("a", 5), act("b", 20, "a"), act("c", 25, "b")]

SERIES = [snap("bl1", "2026-03-01", CHAIN_1),
          snap("bl2", "2026-04-01", CHAIN_2),
          snap("bl3", "2026-05-01", CHAIN_3)]


def stub(baselines: list[dict]) -> None:
    schedule_baselines._load = lambda pid: baselines      # type: ignore[assignment]


def main() -> int:
    try:
        # --- THE FINDING, measured ------------------------------------------------------------
        #
        # `eot.METHODS` names four AACE methods with real distinctions in its own docstrings — one is
        # "the weakest", another "preferred by most protocols", another "most defensible". Run on one
        # input they return the same number, because the method is recorded and then not used.
        ev = [{"type": "weather_delay", "date": "2026-03-02", "days": 10, "activity": "b"},
              {"type": "change_constructive", "date": "2026-03-20", "days": 6, "activity": "c"}]
        acts = [{"id": "b", "early_start": 1, "late_start": 1},
                {"id": "c", "early_start": 5, "late_start": 12}]
        answers = {m: eot.analyse(ev, acts, method=m, baseline_finish="2026-06-01",
                                  actual_finish="2026-07-15")["eot_days"]
                   for m in eot.METHODS}
        check("the four AACE methods in eot.py return an IDENTICAL number",
              len(set(answers.values())) == 1 and len(answers) == 4,
              f"{answers} — the label travels into a claim as though it had been earned. Pinned, "
              "NOT endorsed: if this ever fails because the numbers diverged, that is the fix "
              "landing and this assertion should be replaced, not relaxed")

        check("...and eot.py never re-schedules a network, which is why they cannot differ",
              "schedule_network" not in (eot.analyse.__doc__ or "")
              and not hasattr(eot, "schedule_network"),
              "impacted-as-planned and windows are network operations; nothing here builds one")

        # --- the adapter, on a real series ------------------------------------------------------
        stub(SERIES)
        r = schedule_windows.windows("p1")
        check("three dated baselines become two windows",
              r["available"] and r["window_count"] == 2,
              f"{r['updates']} -> {r['window_count']} windows, {r['total_slip_days']}d total")

        check("the result survives json.dumps", _ser(r), "a route has to return it")

        check("THE INVARIANT: the windows sum to the total slip",
              r["windows_sum"]
              and sum(w["slip_days"] for w in r["windows"]) == r["total_slip_days"],
              f"{[w['slip_days'] for w in r['windows']]} = {r['total_slip_days']}d — an analysis "
              "whose periods do not add to the whole is not evidence")

        check("...and each window is dated, so a cause can be looked for in the right period",
              all(w["opened"] < w["closed"] for w in r["windows"])
              and r["windows"][0]["opened"] == "2026-03-01",
              f"{[(w['opened'], w['closed'], w['slip_days']) for w in r['windows']]}")

        check("the worst window is named — this is the answer the method exists to give",
              r["worst_window"] is not None and r["worst_window_slip_days"] > 0,
              f"window {r['worst_window']} lost {r['worst_window_slip_days']}d — 'where did the "
              "time go' answered by period, which as-planned-vs-as-built structurally cannot")

        check("...and the causes are totalled across the series",
              bool(r["by_cause"]) and sum(r["by_cause"].values()) == r["total_slip_days"],
              f"{r['by_cause']} — the residual causes are in here with the rest, because reporting "
              "only the flattering ones is what the sum prevents")

        # --- acceleration is a fact, not a dropped row --------------------------------------------
        recovered = [snap("bl1", "2026-03-01", CHAIN_2),      # starts long
                     snap("bl2", "2026-04-01", CHAIN_1)]      # pulled back
        stub(recovered)
        acc = schedule_windows.windows("p1")
        check("a window that pulled time back is reported as a NEGATIVE, not dropped",
              acc["available"] and acc["windows"][0]["slip_days"] < 0,
              f"{acc['windows'][0]['slip_days']}d — a claim that counts only the slips overstates "
              "itself, and the sum invariant would not hold if recovery were discarded")

        # --- which snapshots take part, and what happens to the rest ------------------------------
        mixed = [snap("old", "2026-02-01", CHAIN_1, schema=1),
                 snap("bl1", "2026-03-01", CHAIN_1),
                 snap("bl2", "2026-04-01", CHAIN_2)]
        stub(mixed)
        m = schedule_windows.windows("p1")
        check("a pre-v0.3.961 baseline is EXCLUDED and named, never silently dropped",
              m["available"] and m["skipped_without_logic"] == ["OLD"] and m["window_count"] == 1,
              f"skipped {m['skipped_without_logic']} — it holds dates but no predecessors, and "
              "re-scheduling it would put a fully-parallel plan inside one window")

        check("...and the analysed series is listed, so nobody reads it as covering everything",
              m["updates"] == ["BL1", "BL2"],
              f"{m['updates']} of 3 stored — an analysis over 2 of 8 snapshots answers a question "
              "about a different job")

        # --- refusals ------------------------------------------------------------------------------
        stub([])
        none = schedule_windows.windows("p1")
        check("no baselines is refused", none["available"] is False, none["reason"][:60])

        stub([snap("bl1", "2026-03-01", CHAIN_1)])
        one = schedule_windows.windows("p1")
        check("a single snapshot is refused — one date has no window either side",
              one["available"] is False and "two" in one["reason"], one["reason"][:70])

        stub([snap("old1", "2026-02-01", CHAIN_1, schema=1),
              snap("old2", "2026-03-01", CHAIN_2, schema=1)])
        legacy = schedule_windows.windows("p1")
        check("...and when the reason is that they ALL predate logic, it says so",
              legacy["available"] is False and legacy.get("hint")
              and "capture a new baseline" in legacy["hint"],
              legacy.get("hint", ""))

        same_day = [snap("bl1", "2026-03-01", CHAIN_1), snap("bl2", "2026-03-01", CHAIN_2)]
        stub(same_day)
        dup = schedule_windows.windows("p1")
        check("two baselines captured the SAME DAY are refused, not sorted",
              dup["available"] is False and "sort" in dup["reason"],
              "sorting them would move a delay into a window it did not happen in")

        check("...and the refusal is OUR sentence, not the exception's text",
              dup["available"] is False and "WindowsError" not in dup["reason"]
              and "Traceback" not in dup["reason"],
              "`str(exc)` on a response path is the py/stack-trace-exposure shape fixed in v0.3.962")

        cyc = [snap("bl1", "2026-03-01", CHAIN_1),
               snap("bad", "2026-04-01", [act("a", 5, "c"), act("b", 5, "a"), act("c", 5, "b")]),
               snap("bl3", "2026-05-01", CHAIN_3)]
        stub(cyc)
        cy = schedule_windows.windows("p1")
        check("one cyclic snapshot is named and skipped — it does not take out the series",
              cy["available"] and cy["skipped_cyclic"] == ["BAD"] and cy["window_count"] == 1,
              f"skipped {cy['skipped_cyclic']}, {cy['window_count']} window(s) still analysed")

        stub(SERIES)
        bad_match = schedule_windows.windows("p1", match="name_and_wbs")
        check("an unsupported match key is refused and the valid ones listed",
              bad_match["available"] is False and "code" in bad_match["reason"],
              bad_match["reason"])

        check("every refusal reports counts as None, never 0",
              all(x["total_slip_days"] is None and x["window_count"] is None
                  and x["windows_sum"] is None
                  for x in (none, one, legacy, dup, bad_match)),
              "'nothing slipped' and 'nothing was analysed' must not render alike")

        # --- the method is named on the output ------------------------------------------------------
        check("the analysis states its method, in the protocol's own words",
              "29R-03" in (r["method"] or "") and "contemporaneous" in (r["method"] or ""),
              r["method"])
    finally:
        schedule_baselines._load = _REAL_LOAD             # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_windows OK")
    return 0


def _ser(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
