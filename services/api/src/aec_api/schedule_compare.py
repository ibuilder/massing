"""R45-SCHED-REACH ③ — baseline-to-baseline comparison and delay attribution.

The last of the 21 vendored modules, and the one the R45 table recorded as **blocked**: `compare`
needs two *schedules*, and a captured baseline was two dates and a budget. Nothing to re-schedule.

The block was in the snapshot, not the engine. `schedule_baselines._snapshot` now freezes the logic
too — durations, predecessors, calendar, constraints — behind an explicit `schema` version, and a
baseline captured that way runs back through the CPM engine exactly as the live schedule does.

## Why a version number and not a heuristic

An old (v1) snapshot and a new one taken of a schedule that genuinely has no relationships are
**indistinguishable from the data**. Rebuilt as a network, a v1 snapshot comes back as a set of
1-day tasks with no predecessors — a fully-parallel schedule finishing on day one — and `compare`
would then diff that against the real schedule and report an enormous, precisely-attributed delay
caused by logic nobody ever removed. Every number in it would be wrong and none of them would look
it. So the version is recorded at capture and a v1 baseline is **refused** here, with the sentence
that says what to do about it. Variance against a v1 baseline still works and is unaffected.

## Identity matching

Both sides come out of our own module store, so `id` is stable and exact — unlike the P6 re-export
case the engine's own docstring is written around, where ids are regenerated and matching on them
reports every activity as removed-and-added. `ref` (the planner's `A1010`) is offered as an
alternative for the case that does occur here: an activity deleted and re-created keeps its code and
loses its id. Ambiguous codes are reported, never paired — the engine refuses to match "Pour slab" on
level 2 with "Pour slab" on level 5, and this surfaces that refusal rather than hiding it.

## The invariant is checked here too

The engine guarantees the delay contributions sum exactly to the finish move. That guarantee is
re-asserted before returning: a delay analysis whose parts do not sum to the whole is not evidence.
If it ever fails, this reports `available: false` rather than serving numbers that do not add up.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.compare import MatchKey
from massingplan.core.compare import compare as _compare
from massingplan.core.graph import ScheduleCycleError
from massingplan.core.schedule import schedule_network

from . import schedule_baselines, schedule_engine

#: Match keys a caller may ask for. `NAME_AND_WBS` is deliberately not offered: our records carry no
#: WBS on most projects, so it would degrade to matching on title alone — which is precisely the
#: ambiguous pairing the engine refuses to make.
_MATCHES = {"id": MatchKey.ID, "code": MatchKey.CODE}


def compare(
    current_activities: list[dict],
    pid: str,
    baseline_id: str | None = None,
    match: str = "id",
) -> dict[str, Any]:
    """Diff the live schedule against a named baseline and attribute the finish move."""
    key = _MATCHES.get(str(match or "id").strip().lower())
    if key is None:
        return _unavailable(
            f"unknown match key {match!r}; use one of: {', '.join(sorted(_MATCHES))}")

    if not current_activities:
        return _unavailable("no activities — there is no current schedule to compare")

    base = schedule_baselines._get(pid, baseline_id)
    if base is None:
        return _unavailable(
            "no baseline to compare against" if baseline_id is None
            else f"no baseline with id {baseline_id!r}")

    # The refusal that keeps a v1 snapshot from being scheduled as a parallel plan. Asked as a
    # question, NOT caught as an exception: the first draft did `_unavailable(str(exc))`, and CodeQL
    # flagged it as `py/stack-trace-exposure` within the hour — the same finding as v0.3.956, in a
    # module written after that fix. `str(exc)` on a response path relays whatever raised, and the
    # only durable defence is a shape where no exception text can reach the response at all.
    gap = schedule_baselines.logic_gap(base)
    if gap is not None:
        return _unavailable(gap, baseline=schedule_baselines._meta(base))

    base_records = schedule_baselines.to_records(base)
    if not base_records:
        return _unavailable("the baseline is empty — nothing was captured in it",
                            baseline=schedule_baselines._meta(base))

    base_tasks, base_links, calendars, _ = schedule_engine.build_network(base_records)
    curr_tasks, curr_links, _, issues = schedule_engine.build_network(current_activities)

    # Both sides schedule from their OWN data date. Forcing the baseline forward to today's data
    # date would re-schedule the plan against progress that had not happened when it was committed,
    # and the resulting "slip" would be an artefact of the comparison rather than of the job.
    try:
        base_out = schedule_network(base_tasks, base_links, calendars,
                                    data_date=schedule_engine.data_date_for(base_records))
    except ScheduleCycleError as exc:
        return _unavailable("the baseline's logic contains a loop, so it cannot be re-scheduled",
                            cycle=list(exc.cycle), baseline=schedule_baselines._meta(base))
    try:
        curr_out = schedule_network(curr_tasks, curr_links, calendars,
                                    data_date=schedule_engine.data_date_for(current_activities))
    except ScheduleCycleError as exc:
        return _unavailable("the current logic contains a loop, so it cannot be scheduled",
                            cycle=list(exc.cycle), baseline=schedule_baselines._meta(base))

    codes = {"baseline_codes": {r["id"]: str(r["ref"]) for r in base_records if r.get("ref")},
             "current_codes": {r["id"]: str(r["ref"]) for r in current_activities if r.get("ref")}}

    result = _compare(
        base_out, curr_out,
        baseline_network=(base_tasks, base_links),
        current_network=(curr_tasks, curr_links),
        match=key,
        **codes,
    )

    if not result.driving_path.attribution_sums:
        # Should be unreachable — the engine enforces it — so this is a guard, not a branch we
        # expect to take. Serving an attribution that does not add up would be worse than serving
        # none, because it reads as evidence.
        return _unavailable(
            "the delay attribution did not sum to the finish move, so it is not reportable",
            baseline=schedule_baselines._meta(base))

    # --- the unit seam, surfaced rather than left as a mystery -------------------------------------
    #
    # The engine's `finish_move_days` is CALENDAR days (two dates subtracted). Its per-activity
    # contributions are WORKING days (durations subtracted). The invariant still holds — but only
    # because the `UNEXPLAINED` bucket absorbs the difference, and a residual labelled "unexplained"
    # is read by a human as a cause nobody has found yet. On a ten-working-day growth it is four
    # days of weekend, every time.
    #
    # Reported as its own number so the reader can subtract it before going looking. Not fixed in
    # the engine: this is a vendored drop that gets re-synced, and the fix belongs upstream.
    move_working = curr_out.duration_working_days - base_out.duration_working_days
    move_calendar = (result.current_finish - result.baseline_finish).days

    return {
        "available": True,
        "baseline": schedule_baselines._meta(base),
        "issues": [i.to_dict() for i in issues],
        "finish_move_working_days": move_working,
        # How much of any UNEXPLAINED residual is arithmetic rather than an unknown cause.
        "calendar_vs_working_gap_days": move_calendar - move_working,
        **result.to_dict(),
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Every count `None`, never 0. 'Nothing moved' and 'nothing was measured' must not render alike."""
    return {
        "available": False,
        "reason": reason,
        "baseline": None,
        "issues": [],
        "match_key": None,
        "baseline_finish": None,
        "current_finish": None,
        "finish_move_days": None,
        "finish_move_working_days": None,
        "calendar_vs_working_gap_days": None,
        "activity_count": None,
        "changed_count": None,
        "changes_by_kind": {},
        "link_changes": None,
        "criticality_gained": [],
        "criticality_lost": [],
        "ambiguous_matches": [],
        "driving_path": None,
        "activities": [],
        "links": [],
        **extra,
    }
