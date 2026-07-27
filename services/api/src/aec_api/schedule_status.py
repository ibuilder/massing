"""SCHED-STATUS — a schedule without a data date is a plan, not a status report.

`schedule_activity` records planned `start`/`finish` and `actual_start`/`actual_finish`, and
`schedule_cpm` computes float and the critical path over them. What none of it could answer is the
question a superintendent actually asks: **what is late?**

That question needs an "as of" line. Without one, an activity with no `actual_start` is indeterminate
— it may be future work sitting comfortably ahead of its date, or work that should have begun three
weeks ago. Building `risk_calibrate` ran straight into this: every not-yet-started activity had to be
treated as future work, because there was nothing to compare against.

**The data date is P6's term and P6's semantics**: the line that everything remaining is measured
from ([P6 date fields](https://consultleopard.com/primavera-p6-date-fields-explained/)). It is passed
in rather than assumed, and that is the module's first rule.

**Without a data date, nothing is called late.** Defaulting to today would be wrong on every
historical snapshot, every archived project and every what-if — and it would be wrong *silently*,
producing a page full of red on a job that finished two years ago. Every activity comes back
`unknown` and the report says why.

**A forecast finish is intent, not evidence.** P6's Expected Finish is entered by the person doing
the work; remaining duration is derived from it. So a forecast slip is a *claim by the crew* that they
will be late — valuable, decision-grade, and categorically different from an actual finish that has
already happened. `claim_type` draws that line; this module respects it by reporting forecast slip
separately from actual slip rather than adding them together.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: Where an activity stands relative to the data date.
STATES = ("complete", "in_progress", "not_started", "unknown")

#: What each state means, so a UI need not invent the explanation.
MEANS: dict[str, str] = {
    "complete": "finished — an actual finish date is recorded",
    "in_progress": "started and not finished",
    "not_started": "no actual start recorded",
    "unknown": "cannot be placed — the dates needed are missing, or no data date was supplied",
}


def _d(v: Any) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _ref(a: dict[str, Any]) -> str:
    """One naming rule for every branch. It diverged once — the no-data-date path used only `ref`
    while the normal path fell back to the activity name — so the same record answered to two
    different names depending on whether a data date happened to be supplied."""
    d = a.get("data") if isinstance(a.get("data"), dict) else a
    return str(a.get("ref") or (d or {}).get("name") or "?")


#: Every key a row carries. The unknown/no-data-date branches emit these too, filled with None: a row
#: that is missing eight keys the others have makes `row["days_overdue"]` a KeyError the moment one
#: dateless activity appears, which is a trap for every consumer rather than a fact about the row.
_ROW_KEYS = ("planned_start", "planned_finish", "actual_start", "actual_finish", "expected_finish",
             "late_to_start", "days_late_to_start", "overdue", "days_overdue",
             "actual_slip_days", "forecast_slip_days")


def _blank(ref: str, state: str, detail: str) -> dict[str, Any]:
    return {"ref": ref, "state": state, "detail": detail, **dict.fromkeys(_ROW_KEYS)}


def _row(a: dict[str, Any], dd: date) -> dict[str, Any]:
    d = a.get("data") if isinstance(a.get("data"), dict) else a
    ref = _ref(a)
    p_start, p_finish = _d(d.get("start")), _d(d.get("finish"))
    a_start, a_finish = _d(d.get("actual_start")), _d(d.get("actual_finish"))
    forecast = _d(d.get("expected_finish"))

    # AS OF THE DATA DATE — the whole point of having one, and the first version missed it. State was
    # derived from whether actuals EXIST rather than from whether they had happened yet, so an
    # activity finishing 2026-06-10 read as `complete` at a data date of 2026-01-01, when as of that
    # date it was in progress and five months from done. That is precisely the silent
    # historical-snapshot wrongness this module's docstring says the data date exists to prevent.
    # An actual that lies in the future has not happened yet, so it is disregarded — and the fact
    # that it was disregarded is reported, because quietly ignoring recorded data is its own trap.
    future_actual = bool((a_start and a_start > dd) or (a_finish and a_finish > dd))
    if a_start and a_start > dd:
        a_start = None
    if a_finish and a_finish > dd:
        a_finish = None

    if a_finish:
        state = "complete"
    elif a_start:
        state = "in_progress"
    elif p_start or p_finish:
        state = "not_started"
    else:
        return _blank(ref, "unknown", MEANS["unknown"])

    # LATE TO START: it should have begun by now and has not. Only meaningful for work that has not
    # started — an activity in progress started, whenever that was.
    late_to_start = bool(state == "not_started" and p_start and p_start < dd)
    # OVERDUE: past its planned finish and not complete. An activity finished LATE is not overdue —
    # it is done, and its slip is a fact rather than a risk.
    overdue = bool(state != "complete" and p_finish and p_finish < dd)

    # ACTUAL slip: what already happened. Only a finished activity has one.
    actual_slip = (a_finish - p_finish).days if (a_finish and p_finish) else None
    # FORECAST slip: a CLAIM by the crew that they will be late. Reported separately and never added
    # to actual slip — one has happened and the other is somebody's stated expectation.
    forecast_slip = (forecast - p_finish).days if (forecast and p_finish and state != "complete") else None

    return {
        "ref": ref, "state": state, "detail": MEANS[state],
        "planned_start": p_start.isoformat() if p_start else None,
        "planned_finish": p_finish.isoformat() if p_finish else None,
        "actual_start": a_start.isoformat() if a_start else None,
        "actual_finish": a_finish.isoformat() if a_finish else None,
        "expected_finish": forecast.isoformat() if forecast else None,
        "late_to_start": late_to_start,
        "days_late_to_start": (dd - p_start).days if late_to_start and p_start else None,
        "overdue": overdue,
        "days_overdue": (dd - p_finish).days if overdue and p_finish else None,
        "actual_slip_days": actual_slip,
        "forecast_slip_days": forecast_slip,
        # Stated, not silent: a reader comparing this against the raw record needs to know why a
        # recorded actual did not count.
        "future_actual_ignored": future_actual,
    }


def status(activities: list[dict[str, Any]], data_date: Any = None) -> dict[str, Any]:
    """Where every activity stands as of `data_date`.

    `data_date` is **required** to say anything about lateness. Supplied as None, every activity comes
    back `unknown` and the note says so — because defaulting to today would be wrong on every
    historical snapshot and archived project, and wrong *silently*, painting a finished job red.
    """
    dd = _d(data_date)
    acts = activities or []
    if not dd:
        return {
            "data_date": None,
            "activities": [_blank(_ref(a), "unknown",
                                  "no data date supplied — nothing can be called late")
                           for a in acts],
            "counts": dict.fromkeys(STATES, 0) | {"unknown": len(acts)},
            "late_to_start": [], "overdue": [], "forecast_slipping": [],
            "checked": False,
            "note": ("NO DATA DATE — nothing was assessed. An activity with no actual start may be "
                     "future work or three weeks overdue, and there is no way to tell without an 'as "
                     "of' line. Defaulting to today would be wrong on every historical snapshot and "
                     "wrong silently."),
        }

    rows = [_row(a, dd) for a in acts]
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in STATES}
    return {
        "data_date": dd.isoformat(),
        "activities": rows,
        "counts": counts,
        "late_to_start": [r["ref"] for r in rows if r["late_to_start"]],
        "overdue": [r["ref"] for r in rows if r["overdue"]],
        # Kept apart from `overdue` on purpose: one is a measured fact about the calendar, the other
        # is the crew's stated expectation. Merging them would let a claim masquerade as a condition.
        "forecast_slipping": [r["ref"] for r in rows
                              if (r.get("forecast_slip_days") or 0) > 0],
        "checked": True,
        "note": ("`overdue` is measured against the data date — a fact. `forecast_slipping` is the "
                 "crew's own expected finish running past plan — a CLAIM, kept separate and never "
                 "added to actual slip. An activity that finished late is complete, not overdue: its "
                 "slip already happened."),
    }
