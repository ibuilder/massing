"""R46 ② — modelled delay analysis: impacted as-planned (MIP 3.6) and collapsed as-built (MIP 3.9).

`schedule_windows` performs one of `eot.py`'s four declared methods for real. This performs two more,
and they are the two that **alter the network** rather than observing it — the distinction an expert
report turns on, and the reason the AACE taxonomy separates them at all.

* **Impacted as-planned** inserts the delay events into the *baseline* and reschedules. Additive,
  prospective, single base. It answers "what should this delay have cost", and it is silent on what
  the contractor actually did afterwards.
* **Collapsed as-built** removes them from the *as-built* and reschedules the remainder — the
  "but-for" programme. Subtractive. It answers "when would this have finished without them".

## Two preconditions, both refused rather than approximated

**Impacted as-planned runs on the baseline.** The engine's own docstring: *"impacting a progressed
schedule is a different method with a different name, and doing it here by accident is how an
analysis ends up unable to say what it did."* So this reads a captured schema-2 baseline and refuses
if there is none — it will not quietly impact the live schedule instead.

**Collapsed as-built needs the events to already be activities in the as-built network.** Ours are
not: `notice_clock` detects events from the field record and our `schedule_activity` register does not
carry them as tasks. The engine refuses with a message naming which are missing, and that refusal is
surfaced rather than worked around, because the alternative — inserting them and then removing them —
is impacted as-planned wearing the subtractive method's name.

## The duration is the caller's, and that is stated

`notice_clock.detect()` returns `{type, date, description, source, source_id}` and **no `days`
field**, deliberately: detection says an event happened, never what it cost. `eot_sourced` made the
same argument. So the days come from the caller, and every result carries `days_source: "caller"` so
a reader can see that the most contested input was typed rather than derived. `responsibility` is
carried through untouched — whose delay it was is a contractual question, not an arithmetic one.

## Concurrency is measured, not asserted

`eot.analyse` "names concurrency rather than apportioning it", which is the right refusal to make
without a network. With one, it is measurable: `concurrency_days` is how much the sum of the
individual impacts exceeds their combined impact. Two five-day delays running concurrently move the
finish five days, not ten, and that overlap is the five nobody is entitled to twice.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.modelled import (
    DelayEvent,
    ModelledDelayError,
)
from massingplan.core.modelled import (
    collapsed_as_built as _collapsed,
)
from massingplan.core.modelled import (
    impacted_as_planned as _impacted,
)

from . import schedule_baselines, schedule_engine


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _events(raw: list[dict]) -> tuple[list[DelayEvent], list[str]]:
    """Caller-supplied events, with the malformed ones named rather than dropped."""
    out, bad = [], []
    for i, e in enumerate(raw or []):
        eid = str(e.get("id") or e.get("ref") or f"E{i + 1}").strip()
        try:
            days = int(float(e.get("days") if e.get("days") not in (None, "") else
                             e.get("duration_days")))
        except (TypeError, ValueError):
            bad.append(f"{eid}: no usable duration")
            continue
        impacts = str(e.get("impacts") or e.get("activity") or "").strip()
        if not impacts:
            # Without this the event has nothing to attach to, and attaching it anywhere is an
            # assumption the method cannot carry.
            bad.append(f"{eid}: names no activity it delayed")
            continue
        try:
            out.append(DelayEvent(
                id=eid, name=str(e.get("name") or e.get("description") or eid),
                duration_days=days, impacts=impacts,
                onset=_date(e.get("onset") or e.get("date")),
                responsibility=str(e.get("responsibility") or "")))
        except ModelledDelayError:
            # The engine refuses a negative duration and an empty id. Counted, never raised into
            # the route — one malformed row must not take out the analysis.
            bad.append(f"{eid}: refused by the engine as a delay event")
    return out, bad


def impacted(pid: str, events: list[dict], baseline_id: str | None = None) -> dict[str, Any]:
    """AACE 29R-03 MIP 3.6 — insert the events into the captured baseline and reschedule."""
    parsed, bad = _events(events)
    if not parsed:
        return _unavailable(
            "no usable delay events — impacted as-planned with no events models nothing, which is "
            "a missing input rather than an empty result", rejected_events=bad)

    base = schedule_baselines._get(pid, baseline_id)
    if base is None:
        return _unavailable(
            "no baseline to impact. This method inserts events into the AS-PLANNED programme; "
            "impacting the live schedule is a different method with a different name",
            rejected_events=bad)
    gap = schedule_baselines.logic_gap(base)
    if gap is not None:
        return _unavailable(gap, baseline=schedule_baselines._meta(base), rejected_events=bad)

    records = schedule_baselines.to_records(base)
    if not records:
        return _unavailable("the baseline is empty — nothing was captured in it",
                            baseline=schedule_baselines._meta(base), rejected_events=bad)
    tasks, links, calendars, _ = schedule_engine.build_network(records)
    try:
        result = _impacted(tasks, links, calendars, events=parsed,
                           data_date=schedule_engine.data_date_for(records))
    except ScheduleCycleError:
        return _unavailable("the baseline's logic contains a loop, so it cannot be rescheduled",
                            baseline=schedule_baselines._meta(base), rejected_events=bad)
    except ModelledDelayError:
        # Composed here, not relayed — `str(exc)` on a response path is the shape v0.3.962 gated.
        return _unavailable(
            "an event does not attach to any activity in the baseline; check that each event names "
            "an activity the baseline contains", baseline=schedule_baselines._meta(base),
            rejected_events=bad)

    return {"available": True, "baseline": schedule_baselines._meta(base),
            "rejected_events": bad, "days_source": "caller", **result.to_dict()}


def collapsed(activities: list[dict], events: list[dict]) -> dict[str, Any]:
    """AACE 29R-03 MIP 3.9 — remove the events from the as-built and reschedule the remainder."""
    parsed, bad = _events(events)
    if not parsed:
        return _unavailable(
            "no usable delay events — collapsed as-built with no events removes nothing",
            rejected_events=bad)
    if not activities:
        return _unavailable("no activities — there is no as-built network to collapse",
                            rejected_events=bad)

    tasks, links, calendars, _ = schedule_engine.build_network(activities)
    try:
        result = _collapsed(tasks, links, calendars, events=parsed,
                            data_date=schedule_engine.data_date_for(activities))
    except ScheduleCycleError:
        return _unavailable("the as-built logic contains a loop, so it cannot be rescheduled",
                            rejected_events=bad)
    except ModelledDelayError:
        # THE precondition, and the one our data does not meet today. Reported as its own sentence
        # because the workaround — insert the events, then remove them — is impacted as-planned
        # wearing the subtractive method's name, and a report that did that could not say what it
        # had done.
        present = {t.id for t in tasks}
        missing = [e.id for e in parsed
                   if e.activity_id not in present and e.id not in present]
        return _unavailable(
            "collapsed as-built removes activities that are already in the as-built network, and "
            "these are not in it. Record the delays as activities in the schedule, or use "
            "impacted as-planned, which adds events that are not there",
            missing_from_as_built=missing, rejected_events=bad)

    return {"available": True, "baseline": None, "rejected_events": bad,
            "days_source": "caller", **result.to_dict()}


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'no delay' and 'not analysed' must not render alike."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "baseline": None, "rejected_events": [],
        "days_source": None, "method": None, "mip": None,
        "unimpacted_finish": None, "impacted_finish": None,
        "total_days": None, "total_calendar_days": None, "sum_of_individual_days": None,
        "concurrency_days": None, "is_concurrent": None, "per_event": [], "notes": [],
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
