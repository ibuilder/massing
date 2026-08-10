"""Renewable resource demand, availability, and over-allocation.

Two decisions here shape everything the leveller can do.

**Demand is units-per-day held level across the span**, not total units spread
linearly. With linear spreading an activity's peak demand becomes a function of
its duration, so levelling -- which changes where durations sit -- turns
non-monotonic and can *increase* the peak it was asked to reduce. Cost spreads
linearly and crew does not; the consuming product conflates the two, which is
right for the cash-flow curve and wrong for the histogram.

**Over-allocation is evaluated per day, then bucketed for display.** Bucketing
first hides a Monday-only spike of three times the cap inside a week that
averages under it, which is exactly the week somebody needed to be warned about.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from .timeaxis import WorkCalendar, instant_of


@dataclass(frozen=True)
class ResourceAvailability:
    """How much of a resource exists, and when.

    ``calendar_id`` is the resource's own calendar -- a crew on a Mon-Fri
    calendar is not available on a Saturday even if the activity's calendar
    says the work happens then, and that is a genuine conflict rather than an
    over-allocation.
    """

    resource_id: str
    units_per_day: float
    calendar_id: str | None = None
    exceptions: Mapping[date, float] = field(default_factory=dict)

    def available_on(self, day: date, calendars: Mapping[str, WorkCalendar]) -> float:
        if day in self.exceptions:
            return self.exceptions[day]
        if self.calendar_id:
            cal = calendars.get(self.calendar_id)
            if cal is not None and not cal.is_working(instant_of(day)):
                return 0.0
        return self.units_per_day


@dataclass(frozen=True)
class Demand:
    """One activity's draw on one resource, held level across its span."""

    activity_id: str
    resource_id: str
    units_per_day: float


@dataclass(frozen=True)
class OverAllocation:
    resource_id: str
    day: date
    demanded: float
    available: float
    contributors: tuple[str, ...]

    @property
    def excess(self) -> float:
        return self.demanded - self.available

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_id": self.resource_id,
            "day": self.day.isoformat(),
            "demanded": round(self.demanded, 3),
            "available": round(self.available, 3),
            "excess": round(self.excess, 3),
            "contributors": list(self.contributors),
        }


def daily_profile(
    spans: Mapping[str, tuple[date, date]],
    demands: Sequence[Demand],
    calendars: Mapping[str, WorkCalendar],
    activity_calendar: Mapping[str, str],
    *,
    exclude: Sequence[str] = (),
) -> dict[str, dict[date, float]]:
    """``{resource_id: {day: units}}`` over the working days of each span.

    ``exclude`` drops completed activities. Counting last month's crew against
    this month's availability blocks all future work, and the leveller then
    reports the whole remaining schedule as unresolvable.
    """
    skip = set(exclude)
    profile: dict[str, dict[date, float]] = {}
    for demand in demands:
        if demand.activity_id in skip:
            continue
        span = spans.get(demand.activity_id)
        if span is None:
            continue
        start, finish = span
        cal = calendars.get(activity_calendar.get(demand.activity_id, ""))
        bucket = profile.setdefault(demand.resource_id, {})
        for day in _working_days(start, finish, cal):
            bucket[day] = bucket.get(day, 0.0) + demand.units_per_day
    return profile


def _working_days(start: date, finish: date, cal: WorkCalendar | None) -> list[date]:
    """Inclusive span, filtered to the calendar's working days."""
    from datetime import timedelta

    days: list[date] = []
    cursor = start
    while cursor <= finish:
        if cal is None or cal.is_working(instant_of(cursor)):
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def over_allocations(
    spans: Mapping[str, tuple[date, date]],
    demands: Sequence[Demand],
    availability: Sequence[ResourceAvailability],
    calendars: Mapping[str, WorkCalendar],
    activity_calendar: Mapping[str, str],
    *,
    exclude: Sequence[str] = (),
    tolerance: float = 1e-9,
) -> list[OverAllocation]:
    """Days where demand exceeds availability, one row per resource-day."""
    caps = {a.resource_id: a for a in availability}
    profile = daily_profile(spans, demands, calendars, activity_calendar, exclude=exclude)
    skip = set(exclude)

    by_resource: dict[str, list[Demand]] = {}
    for demand in demands:
        if demand.activity_id not in skip:
            by_resource.setdefault(demand.resource_id, []).append(demand)

    found: list[OverAllocation] = []
    for resource_id in sorted(profile):
        cap = caps.get(resource_id)
        if cap is None:
            continue
        for day in sorted(profile[resource_id]):
            demanded = profile[resource_id][day]
            available = cap.available_on(day, calendars)
            if demanded - available <= tolerance:
                continue
            contributors = tuple(
                sorted(
                    d.activity_id
                    for d in by_resource.get(resource_id, [])
                    if (span := spans.get(d.activity_id)) and span[0] <= day <= span[1]
                )
            )
            found.append(OverAllocation(resource_id, day, demanded, available, contributors))
    return found


def histogram(
    profile: Mapping[str, Mapping[date, float]],
    *,
    bucket: Literal["day", "week", "month"] = "week",
) -> list[dict[str, object]]:
    """Bucketed demand for display. Bucketing happens *after* detection."""
    rows: list[dict[str, object]] = []
    for resource_id in sorted(profile):
        buckets: dict[date, float] = {}
        peaks: dict[date, float] = {}
        for day, units in profile[resource_id].items():
            key = _bucket_start(day, bucket)
            buckets[key] = buckets.get(key, 0.0) + units
            peaks[key] = max(peaks.get(key, 0.0), units)
        for key in sorted(buckets):
            rows.append(
                {
                    "resource_id": resource_id,
                    "period": key.isoformat(),
                    "total_units": round(buckets[key], 3),
                    # The peak day inside the bucket, kept so a smoothed weekly bar
                    # cannot hide the Monday that needed three crews.
                    "peak_day_units": round(peaks[key], 3),
                }
            )
    return rows


def _bucket_start(day: date, bucket: str) -> date:
    from datetime import timedelta

    if bucket == "day":
        return day
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def peak_by_resource(profile: Mapping[str, Mapping[date, float]]) -> dict[str, float]:
    return {
        resource_id: (max(days.values()) if days else 0.0) for resource_id, days in profile.items()
    }


class AssignmentLike(Protocol):
    """The shape this function needs.

    A protocol rather than importing ``ExchangeAssignment``: this module sits
    below the hub model and importing upward would make the dependency graph a
    cycle. It is also what lets a caller pass its own ORM row without adapting it.
    """

    activity_id: str
    resource_id: str
    units_per_day: float | None


def demands_from_assignments(
    assignments: Sequence[AssignmentLike], *, default_units: float = 1.0
) -> list[Demand]:
    """Build level demands from hub-model assignments.

    ``units_per_day`` is used when the file carried it. When it did not, one
    unit per day is assumed -- enough to detect a genuine clash between two
    activities wanting the same crew, which is the common case, and honest
    because it does not invent a magnitude the file never stated.
    """
    return [
        Demand(
            activity_id=assignment.activity_id,
            resource_id=assignment.resource_id,
            units_per_day=float(assignment.units_per_day or default_units),
        )
        for assignment in assignments
    ]


__all__ = [
    "Demand",
    "OverAllocation",
    "ResourceAvailability",
    "daily_profile",
    "demands_from_assignments",
    "histogram",
    "over_allocations",
    "peak_by_resource",
]
