"""R46 ① — contemporaneous windows analysis (AACE 29R-03 MIP 3.3).

## The finding this module exists to answer

`aec_api/eot.py` offers four AACE methods and refuses to produce a number without one, on the correct
argument that *"an EOT number without its method cannot be weighed"*. **When this module was written
it did not perform any of them.** Measured on one input — a 10-day weather event, a 6-day change, a
baseline and an actual finish:

| declared method | eot_days |
|---|---|
| `as_planned_vs_as_built` — *"the weakest"* | **16.0** |
| `impacted_as_planned` | **16.0** |
| `time_impact` — *"preferred by most protocols"* | **16.0** |
| `windows` — *"most defensible, most data-hungry"* | **16.0** |

One number, four labels. The method was recorded and then not used: the arithmetic was
events-minus-float in every branch. A user who picked the most defensible method got the answer the
weakest one gives, and the label travelled with it into a claim as though it had been earned.

This module performs one of them for real, and `schedule_modelled` performs two more.

**`eot.py` itself was corrected in v0.3.971**, after these two modules made the alternative visible:
it now computes the additive and end-state methods differently, and **refuses** `windows` and
`time_impact` — naming this module as the thing that performs the first. That is the point of the
table above surviving here rather than being deleted: the fix is legible only next to what it fixed.

## Where the series of updates comes from

Windows analysis needs the schedule **as it stood on a series of dates** — not two end states. Our
baseline library is exactly that: up to twelve captured snapshots, each dated, and since v0.3.961
each carrying the logic needed to re-schedule it. That capability was added for `compare`; this is
the second thing it bought, and it is the more valuable one.

**A schema-1 baseline cannot take part.** Those hold dates but no predecessors, and re-scheduling one
produces a fully-parallel plan — which here would not merely be wrong, it would be wrong *inside one
window*, moving time into a period it did not happen in. They are excluded and counted, never
silently dropped.

## What is deliberately not done

**The capture date is used as the data date, and that is stated rather than assumed.** The engine's
own docstring warns that a wrong data date moves a delay into the neighbouring window, "and the
neighbouring window is very often the other party's". A captured baseline's data date is the day it
was captured — which is right for snapshots of our own live schedule, and is a *recorded* date rather
than a typed one. If a project imports P6 updates with their own data dates, that is what `p6xml`
brings and this adapter should read those instead.

**Acceleration is reported as a negative, not dropped.** A window that pulled time back is a fact,
and an analysis that counts only the slips overstates itself. The engine enforces that the windows
sum to the total move; that invariant is re-checked here before returning.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.compare import MatchKey
from massingplan.core.graph import ScheduleCycleError
from massingplan.core.schedule import schedule_network
from massingplan.core.windows import Update, WindowsError
from massingplan.core.windows import analyse as _analyse

from . import schedule_baselines, schedule_engine

#: Fewer than this many usable snapshots and there is no window to measure.
_MIN_UPDATES = 2


def windows(pid: str, match: str = "id") -> dict[str, Any]:
    """A windows analysis over the project's captured baseline library, oldest first."""
    key = {"id": MatchKey.ID, "code": MatchKey.CODE}.get(str(match or "id").strip().lower())
    if key is None:
        return _unavailable(f"unknown match key {match!r}; use one of: code, id")

    stored = schedule_baselines._load(pid)
    if not stored:
        return _unavailable("no baselines captured — a windows analysis reads the schedule as it "
                            "stood on a series of dates, and nothing has been captured yet")

    updates: list[Update] = []
    skipped_no_logic: list[str] = []
    skipped_cyclic: list[str] = []
    for b in stored:                                    # `_load` returns oldest-first
        meta = schedule_baselines._meta(b)
        if schedule_baselines.logic_gap(b) is not None:
            skipped_no_logic.append(meta["name"] or meta["id"])
            continue
        records = schedule_baselines.to_records(b)
        if not records:
            continue
        tasks, links, calendars, _ = schedule_engine.build_network(records)
        dd = schedule_baselines._date(b.get("captured_at"))
        if dd is None:
            continue
        try:
            outcome = schedule_network(tasks, links, calendars,
                                       data_date=schedule_engine.data_date_for(records, dd))
        except ScheduleCycleError:
            # One unusable snapshot must not take out the series; it is named instead.
            skipped_cyclic.append(meta["name"] or meta["id"])
            continue
        updates.append(Update(data_date=dd, outcome=outcome, tasks=tasks, links=links,
                              name=str(meta["name"] or meta["id"])))

    if len(updates) < _MIN_UPDATES:
        return _unavailable(
            f"only {len(updates)} baseline(s) can be re-scheduled, and a window needs two "
            "consecutive ones to sit between",
            skipped_without_logic=skipped_no_logic, skipped_cyclic=skipped_cyclic,
            hint=("capture a new baseline — the ones already stored predate logic being frozen "
                  "into them" if skipped_no_logic else None))

    try:
        result = _analyse(updates, match=key)
    except WindowsError:
        # The engine refuses duplicate or out-of-order data dates rather than sorting them, because
        # sorting moves a delay into a window it did not happen in. Two baselines captured the same
        # day is the case that reaches this, and it is a real input problem, not a crash.
        #
        # The reason is composed HERE, not relayed: `str(exc)` on a response path is the
        # `py/stack-trace-exposure` shape this repo fixed three times in v0.3.962.
        return _unavailable(
            "two captured baselines share a date, or they run backwards — the engine refuses to "
            "sort them, because sorting moves a delay into a window it did not happen in",
            skipped_without_logic=skipped_no_logic, skipped_cyclic=skipped_cyclic)

    if not result.windows_sum:
        return _unavailable(
            "the windows did not sum to the total slip, so the analysis is not reportable",
            skipped_without_logic=skipped_no_logic, skipped_cyclic=skipped_cyclic)

    return {
        "available": True,
        "updates": [u.label for u in updates],
        # Named, because a windows analysis that quietly analysed 3 of a project's 8 snapshots is
        # answering a question about a different job.
        "skipped_without_logic": skipped_no_logic,
        "skipped_cyclic": skipped_cyclic,
        **result.to_dict(),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'nothing slipped' and 'nothing was analysed' must not render alike."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "updates": [],
        "skipped_without_logic": [], "skipped_cyclic": [],
        "method": None, "window_count": None, "first_finish": None, "last_finish": None,
        "total_slip_days": None, "windows_sum": None, "worst_window": None,
        "worst_window_slip_days": None, "path_changes": None, "by_cause": {},
        "issue_count": None, "windows": [], "issues": [],
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
