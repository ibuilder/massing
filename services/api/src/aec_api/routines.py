"""R22-ROUTINES — recurring runs, and the catch-up it refuses to perform.

The engines that matter on a cadence already exist (`schedule_risk_mc`, the report builders, the agent
answers) and every one of them is on-demand: somebody has to remember. This is the recurrence layer
that turns them from a tool you remember into infrastructure — a routine states a cadence, and
`due()` says which routines should be enqueued now.

**The dangerous behaviour here is catch-up.** A server down for a quarter leaves a monthly routine
three windows behind. The obvious implementation replays them: three progress reports land at once,
three agent runs bill three times, and a weekly scan that missed a fortnight fires twice into the
same inbox. So:

1. **a missed routine fires ONCE and reports the gap.** `missed_windows` is a number the caller can
   act on — it is the *information* the outage carries — but the run itself is not replayed. Reruns
   of a report whose window has closed are noise, and for anything that calls a paid API they are
   noise that costs money;
2. **a routine already running is never re-enqueued.** Recurrence plus a slow job is how you get a
   pile-up that looks like a load problem and is really a scheduling bug;
3. **cadence is a closed set.** An unknown cadence is refused and listed, not silently treated as
   daily — the same rule the EOT engine applies to its methods, and for the same reason: the caller
   cannot weigh a schedule they did not choose;
4. **`now` is always passed in, never read.** A due-calculation that reads the clock cannot be
   tested at a boundary, and boundaries are the only interesting part of a scheduler.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

CADENCE_DAILY = "daily"
CADENCE_WEEKLY = "weekly"
CADENCE_MONTHLY = "monthly"
CADENCE_QUARTERLY = "quarterly"

#: cadence -> human meaning. A closed set, deliberately: see refusal 3.
CADENCES: dict[str, str] = {
    CADENCE_DAILY: "every day, from midnight UTC",
    CADENCE_WEEKLY: "every Monday, from midnight UTC",
    CADENCE_MONTHLY: "the first of each month, from midnight UTC",
    CADENCE_QUARTERLY: "the first of Jan/Apr/Jul/Oct, from midnight UTC",
}

#: Routine-record fields that are JOB PARAMETERS rather than scheduling fields.
#:
#: `from_project` reads the stored record and hands `evaluate` a deliberately narrow dict — id, kind,
#: cadence, project. Everything else in the record is the user's, and echoing it wholesale into the
#: sweep's response would put arbitrary stored data on a viewer-reachable payload. So the fields a
#: JOB needs are named here rather than passed through by default, and `routines_run` is what knows
#: what to do with them. The scheduler stays ignorant of job kinds: it carries these, it never
#: interprets them.
JOB_PARAM_FIELDS = ("moment", "deliver_to")

STATUS_DUE = "due"
STATUS_NOT_DUE = "not_due"
STATUS_DISABLED = "disabled"
STATUS_RUNNING = "running"
STATUS_BAD_CADENCE = "unknown_cadence"


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def window_start(cadence: str, when: date) -> date | None:
    """The start of the cadence window containing `when`, or None for an unknown cadence.

    Windows are aligned to calendar boundaries rather than to "N days since the last run", so a
    monthly report always covers a month and never drifts into a rolling 30-day window that nobody
    can reconcile against a month-end close.
    """
    if cadence == CADENCE_DAILY:
        return when
    if cadence == CADENCE_WEEKLY:
        return when - timedelta(days=when.weekday())
    if cadence == CADENCE_MONTHLY:
        return when.replace(day=1)
    if cadence == CADENCE_QUARTERLY:
        return when.replace(month=((when.month - 1) // 3) * 3 + 1, day=1)
    return None


def _next_window(cadence: str, start: date) -> date:
    if cadence == CADENCE_DAILY:
        return start + timedelta(days=1)
    if cadence == CADENCE_WEEKLY:
        return start + timedelta(days=7)
    step = 1 if cadence == CADENCE_MONTHLY else 3
    y, m = start.year, start.month + step
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, 1)


def missed_windows(cadence: str, last_run: date | None, now: date) -> int:
    """How many whole windows closed between `last_run` and the current one, without firing.

    Zero for a routine that has never run: a first run is not a missed one, and reporting it as a
    backlog would make every new routine look like it had already failed.
    """
    cur = window_start(cadence, now)
    if cur is None or last_run is None:
        return 0
    w = window_start(cadence, last_run)
    if w is None:
        return 0
    n = -1                                       # the window the last run itself covered is not missed
    while w < cur:
        w = _next_window(cadence, w)
        n += 1
    return max(0, n)


def evaluate(routine: dict, now: datetime, last_run: Any = None,
             in_flight: bool = False) -> dict[str, Any]:
    """Should this routine be enqueued at `now`? Pure — `now` is supplied, never read."""
    rid = routine.get("id")
    cadence = str(routine.get("cadence") or "")
    base = {"id": rid, "kind": routine.get("kind"), "cadence": cadence,
            "project_id": routine.get("project_id"),
            **{k: routine.get(k) for k in JOB_PARAM_FIELDS if routine.get(k) is not None}}
    if cadence not in CADENCES:
        return {**base, "status": STATUS_BAD_CADENCE, "due": False,
                "cadences_available": dict(CADENCES),
                "reason": (f"cadence {cadence!r} is not one this scheduler knows. It is NOT treated "
                           "as daily — a routine running on a schedule nobody chose is worse than "
                           "one that does not run.")}
    if not routine.get("enabled", True):
        return {**base, "status": STATUS_DISABLED, "due": False,
                "reason": "routine is disabled"}
    if in_flight:
        return {**base, "status": STATUS_RUNNING, "due": False,
                "reason": ("the previous run of this routine has not finished. Re-enqueueing on a "
                           "cadence while a run is in flight is how a scheduling bug becomes what "
                           "looks like a load problem.")}

    today = now.date() if isinstance(now, datetime) else now
    cur = window_start(cadence, today)
    lr = _as_date(last_run)
    lr_window = window_start(cadence, lr) if lr else None
    missed = missed_windows(cadence, lr, today)

    if lr_window is not None and lr_window >= cur:
        return {**base, "status": STATUS_NOT_DUE, "due": False, "window_start": cur.isoformat(),
                "last_run": lr.isoformat() if lr else None, "missed_windows": 0,
                "reason": "already ran in the current window"}

    return {**base, "status": STATUS_DUE, "due": True, "window_start": cur.isoformat(),
            "last_run": lr.isoformat() if lr else None,
            "missed_windows": missed, "first_run": lr is None,
            "catch_up_suppressed": missed > 0,
            "reason": (f"{missed} window(s) closed without a run; firing ONCE for the current "
                       "window rather than replaying them. The gap is reported, not re-run — "
                       "replaying closed windows duplicates reports and bills repeat API calls."
                       if missed else ("first run — a routine that has never run is not behind"
                                       if lr is None else "the current window has no run yet"))}


def due(routines: list[dict], now: datetime, last_runs: dict[str, Any] | None = None,
        in_flight: set[str] | None = None) -> dict[str, Any]:
    """Evaluate a set of routines; returns those due plus every skip WITH its reason.

    Skips are returned rather than filtered out: "nothing ran today" and "nothing was due today" are
    different facts, and a scheduler that reports only what it fired cannot tell you which.
    """
    last_runs = last_runs or {}
    in_flight = in_flight or set()
    rows = [evaluate(r, now, last_runs.get(str(r.get("id"))), str(r.get("id")) in in_flight)
            for r in routines or []]
    fire = [r for r in rows if r["due"]]
    return {"as_of": (now.date() if isinstance(now, datetime) else now).isoformat(),
            "due": fire, "due_count": len(fire),
            "skipped": [r for r in rows if not r["due"]],
            "total_missed_windows": sum(r.get("missed_windows") or 0 for r in fire),
            "cadences": dict(CADENCES),
            "note": ("a routine behind by N windows fires ONCE with missed_windows=N. Closed windows "
                     "are reported, never replayed.")}


#: Only routines in this workflow state are ever evaluated. `draft` has not been turned on and
#: `retired` has been turned off deliberately — neither is "disabled by accident", and a scheduler
#: that fires a draft is one nobody can safely author against.
#:
#: The stored register has NO `enabled` field, and that is deliberate. It carried one until
#: `test_field_attrs` refused its `default: true` — a default writes a value nobody chose, and for a
#: switch that governs recurring jobs the record could no longer distinguish "somebody enabled this"
#: from "nobody looked at it". Chasing that turned up the real defect: **`enabled` duplicated the
#: workflow.** `paused` already means disabled, so two switches governed one concept with nothing
#: stating which won. The workflow is the authority — turning a routine on is an explicit `activate`
#: transition, which is the authorisation a scheduled job needs. `evaluate()` still honours a
#: caller-supplied `enabled` for the stateless endpoint, where there is no workflow to consult.
ACTIVE_STATE = "active"


def from_project(db, project_id: str, now: datetime | None = None,
                 in_flight: set[str] | None = None) -> dict[str, Any]:
    """Evaluate the routines stored for one project.

    The stored `last_run` is the routine's own record of when it last fired, so recurrence survives a
    restart — which is the whole point of persisting these. A routine that is not `active` is not
    evaluated at all: `draft` was never switched on and `retired` was switched off on purpose, and
    firing either would be the scheduler inventing intent.
    """
    from . import modules as me

    try:
        rows = me.list_records(db, "routine", project_id, limit=10_000)
    except Exception:                            # noqa: BLE001 — module absent in a trimmed deploy
        return {**due([], now or utc_now()), "note": "the routine register is not installed here"}

    routines, last_runs = [], {}
    for r in rows:
        if str(r.get("workflow_state") or "") != ACTIVE_STATE:
            continue
        d = r.get("data") or {}
        rid = str(r.get("id"))
        # No `enabled` is passed: the workflow state above IS the switch. Reading a stored
        # `enabled` here would reinstate the two-switches ambiguity the register just shed.
        routines.append({"id": rid, "ref": r.get("ref"), "kind": d.get("kind"),
                         "cadence": d.get("cadence"), "project_id": project_id,
                         **{k: d.get(k) for k in JOB_PARAM_FIELDS if d.get(k) is not None}})
        if d.get("last_run"):
            last_runs[rid] = d["last_run"]
    out = due(routines, now or utc_now(), last_runs=last_runs, in_flight=in_flight)
    out["project_id"] = project_id
    out["evaluated"] = len(routines)
    out["stored"] = len(rows)
    out["note"] += (f" {len(rows) - len(routines)} stored routine(s) were not evaluated because they "
                    "are not active — draft was never switched on, retired was switched off."
                    if len(rows) != len(routines) else "")
    return out


def utc_now() -> datetime:
    """The one place the clock is read — so every other function stays testable at a boundary."""
    return datetime.now(timezone.utc)
