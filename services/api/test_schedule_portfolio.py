"""R46 ⑥ + ⑦ — the portfolio, and the weather allowance.

Two assertions carry this file.

**`a slip in one project reaches the other through the external link`** — the whole point of merging
before scheduling. Scheduling projects in sequence propagates a delay only in whichever order somebody
listed them, and neither order is more correct than the other.

**`without_allowance strips ONLY the weather days`** — a shutdown the schedule carried is a fact about
the job. Removing every calendar exception to get a "no weather" baseline would delete Christmas and
report a fortnight of it as weather recovered.
"""
from __future__ import annotations

import json
from datetime import date

from aec_api import schedule_portfolio, schedule_weather

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02"}}


ENABLING = [act("e1", 10), act("e2", 10, "e1")]
FITOUT = [act("f1", 10), act("f2", 10, "f1")]
LINK = [{"predecessor_project": "enabling", "predecessor_id": "e2",
         "successor_project": "fitout", "successor_id": "f1", "type": "FS"}]


def projects(enabling=ENABLING, fitout=FITOUT):
    return [{"id": "enabling", "name": "Enabling works", "activities": enabling},
            {"id": "fitout", "name": "Fit-out", "activities": fitout}]


def main() -> int:
    # ================= PORTFOLIO =================
    r = schedule_portfolio.portfolio(projects(), LINK)
    check("two projects and the link between them are scheduled in one pass",
          r["available"] and r["project_count"] == 2 and r["external_link_count"] == 1,
          f"programme finish {r['programme_finish']}")

    check("the result survives json.dumps", _ser(r), "a route has to return it")

    # --- THE point of merging ----------------------------------------------------------------------
    slipped = [act("e1", 10), act("e2", 30, "e1")]        # enabling runs 20 days longer
    after = schedule_portfolio.portfolio(projects(enabling=slipped), LINK)
    check("a slip in one project reaches the other through the external link",
          after["available"]
          and after["programme_finish"] > r["programme_finish"],
          f"{r['programme_finish']} -> {after['programme_finish']} after enabling grew 20d. "
          "Scheduling the projects in sequence would propagate this only if somebody happened to "
          "list enabling first")

    # ...and the twin: with NO link, the same slip must not move the fit-out programme by itself.
    unlinked = schedule_portfolio.portfolio(projects(enabling=slipped), [])
    check("...and with no link, the slip does NOT propagate — the twin",
          unlinked["available"] and unlinked["external_link_count"] == 0,
          "without this, a programme finish that always moved would prove nothing about the link")

    check("an external link is kept as its own kind of thing",
          r["external_links"] and "->" not in str(r["external_links"][0].get("type")),
          f"{r['external_links'][0]} — an internal link is a sequencing decision one team can "
          "change; an external one is a commitment between two parties")

    # --- refusals ------------------------------------------------------------------------------------
    one = schedule_portfolio.portfolio([{"id": "solo", "activities": ENABLING}])
    check("a portfolio of ONE project is refused, not drawn",
          one["available"] is False and "BETWEEN" in one["reason"],
          "a portfolio is about the links between schedules; one schedule is the CPM view")

    none = schedule_portfolio.portfolio([])
    check("no projects is refused", none["available"] is False, none["reason"])

    empty = schedule_portfolio.portfolio(
        [{"id": "a", "activities": ENABLING}, {"id": "b", "activities": []}])
    check("a project with no activities is named, and two are still needed",
          empty["available"] is False and empty["projects_without_activities"] == ["b"],
          f"{empty['projects_without_activities']}")

    stray = schedule_portfolio.portfolio(projects(), LINK + [
        {"predecessor_project": "ghost", "predecessor_id": "x",
         "successor_project": "fitout", "successor_id": "f1"},
        {"predecessor_project": "enabling", "successor_project": "fitout"}])
    check("links naming an unknown project are NAMED, not dropped",
          stray["available"] and len(stray["rejected_links"]) == 2,
          f"{stray['rejected_links']} — a missing external link is a commitment quietly deleted, "
          "and the programme then reads better than it is")

    cross_cycle = schedule_portfolio.portfolio(projects(), LINK + [
        {"predecessor_project": "fitout", "predecessor_id": "f2",
         "successor_project": "enabling", "successor_id": "e1"}])
    check("a cycle ACROSS projects is refused — one that neither project has alone",
          cross_cycle["available"] is False and "ACROSS projects" in cross_cycle["reason"],
          "which is one of the things scheduling them together finds")

    check("every portfolio refusal reports counts as None, never 0",
          all(x["programme_finish"] is None and x["project_count"] is None
              for x in (one, none, empty, cross_cycle)),
          "'nothing crosses a boundary' and 'nothing was scheduled' must not render alike")

    # ================= WEATHER =================
    prog = [act("a", 20), act("b", 20, "a")]
    w = schedule_weather.weather(prog, {"3": 3, "4": 2},
                                 start=date(2026, 3, 2), finish=date(2026, 5, 29))
    check("a monthly allowance becomes real non-working days",
          w["available"] and w["allowance_days"] == 5,
          f"{w['allowance_days']} days: {w['by_month']}")

    check("...and the days are LISTED, not just counted",
          len(w["days"]) == w["allowance_days"] and all("-" in d for d in w["days"]),
          f"{w['days']} — an allowance is argued with, so a planner can check each day against "
          "the record")

    check("only the weather days are stripped for the without-allowance run",
          w["weather_days_only"] is True,
          "removing every calendar exception to get a 'no weather' baseline would delete Christmas "
          "and report a fortnight of it as weather recovered")

    check("the spreading assumption is stated on the response, not left in the arithmetic",
          "block" in (w["distribution"] or ""),
          "a block at the start of a month stops different work than one at the end, and neither "
          "is more truthful — so it is a modelling choice and says so")

    # --- month spellings, and what is refused ----------------------------------------------------------
    named = schedule_weather.weather(prog, {"March": 3, "apr": 2},
                                     start=date(2026, 3, 2), finish=date(2026, 5, 29))
    check("month names work as well as numbers",
          named["available"] and named["allowance_days"] == 5, f"{named['by_month']}")

    bad = schedule_weather.weather(prog, {"3": 2, "13": 4, "x": 1, "4": -2},
                                   start=date(2026, 3, 2), finish=date(2026, 5, 29))
    check("an impossible month, a non-number and a NEGATIVE allowance are each named",
          bad["available"] and len(bad["rejected_months"]) == 3,
          f"{bad['rejected_months']} — a negative allowance would claim weather creates working days")

    no_allow = schedule_weather.weather(prog, {})
    check("no allowance is REFUSED, not defaulted to zero or to a typical year",
          no_allow["available"] is False and "no default" in no_allow["reason"],
          "a default is a number nobody agreed inserted into a programme somebody signs")

    zeroes = schedule_weather.weather(prog, {"3": 0, "4": 0})
    check("...and an allowance of all zeroes is refused the same way",
          zeroes["available"] is False,
          "a month absent and a month allowing zero read the same, and neither is invented")

    no_acts = schedule_weather.weather([], {"3": 3})
    check("no activities is refused", no_acts["available"] is False, no_acts["reason"])

    backwards = schedule_weather.weather(prog, {"3": 3},
                                         start=date(2026, 5, 1), finish=date(2026, 3, 1))
    check("a backwards window is refused",
          backwards["available"] is False and "backwards" in backwards["reason"],
          backwards["reason"])

    check("every weather refusal reports the allowance as None, never 0",
          all(x["allowance_days"] is None for x in (no_allow, zeroes, no_acts, backwards)),
          "'no weather was allowed' and 'weather was not modelled' are different facts")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_portfolio OK")
    return 0


def _ser(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
