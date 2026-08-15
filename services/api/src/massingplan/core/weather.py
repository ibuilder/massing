"""Weather allowance: the lost days a programme already assumes, made visible.

Every construction programme in a wet or a hot climate carries weather loss.
It is almost never *modelled* -- it is padded into activity durations, where a
five-day pour becomes seven and nobody afterwards can say which two days were
weather and which were the estimator being careful. Once it is inside a
duration it cannot be argued about, cannot be claimed against, and cannot be
compared with what the weather actually did.

Put it in the calendar instead
------------------------------
A weather day is a day nobody works. That is precisely what a non-working day
is, and this engine already has one: `CalendarException`. Adding the allowance
as calendar exceptions rather than duration padding buys three things the
padding cannot:

* the days appear in the **resource histogram** as days with no demand, so a
  crew is not shown on site in a storm;
* they move the **float profile**, so DCMA's checks see them and a run with
  the allowance can be compared against one without;
* they are **separable**. `without_allowance` gives back the same calendar
  with the weather days removed, which is what makes the difference measurable
  rather than asserted.

An allowance is a plan, not a forecast
--------------------------------------
This does not predict weather. It records what the programme has *allowed* --
"November gets four lost days" -- which is a commercial position taken at
tender and the thing a claim is measured against. Where the allowance sits in
the month is arbitrary and is spread evenly on purpose, because clustering it
at one end silently makes the allowance a lead or a lag: at the start it
delays everything downstream by the full amount, at the end it delays nothing
until the month is over.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import Calendar, CalendarException

#: The name every exception this module writes carries, so they can be told
#: apart from a Christmas shutdown the file already contained. Removing "all
#: the exceptions" to measure the allowance would remove the shutdown too, and
#: report the difference as weather.
WEATHER = "weather allowance"


class WeatherError(ValueError):
    """The allowance cannot be applied as stated."""


@dataclass(frozen=True)
class Allowance:
    """Lost days per month, for one calendar.

    Keyed by month number, 1 to 12. A month absent from the mapping allows
    nothing, which is different from allowing zero only in that nobody wrote it
    down -- so both read the same and neither is invented.
    """

    calendar_id: str
    days_by_month: Mapping[int, int]

    def __post_init__(self) -> None:
        for month, days in self.days_by_month.items():
            if not 1 <= month <= 12:
                raise WeatherError(f"{self.calendar_id}: {month} is not a month")
            if days < 0:
                raise WeatherError(
                    f"{self.calendar_id}: month {month} allows {days} days. A negative "
                    "allowance would be a claim that weather creates working days"
                )

    def days_in(self, month: int) -> int:
        return int(self.days_by_month.get(month, 0))


@dataclass(frozen=True)
class AppliedAllowance:
    """What was actually added, and where -- so it can be argued with."""

    calendar_id: str
    days: tuple[date, ...] = field(default_factory=tuple)

    @property
    def total_days(self) -> int:
        return len(self.days)

    def by_month(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for day in self.days:
            key = f"{day.year}-{day.month:02d}"
            out[key] = out.get(key, 0) + 1
        return out

    def to_dict(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "total_days": self.total_days,
            "by_month": self.by_month(),
            "days": [d.isoformat() for d in self.days],
        }


def _working_days_in_month(calendar: Calendar, year: int, month: int) -> list[date]:
    """The days the calendar already works in that month, in order.

    Days the calendar does not work are not available to lose, and neither are
    days it has already lost to a shutdown -- a Christmas holiday cannot also
    be a weather day, and counting it twice would inflate the allowance by
    exactly the length of the shutdown.
    """
    already_off = {e.day for e in calendar.exceptions if not e.working}
    extra_on = {e.day for e in calendar.exceptions if e.working}
    out: list[date] = []
    day = date(year, month, 1)
    while day.month == month:
        works = day.weekday() in calendar.working_weekdays or day in extra_on
        if works and day not in already_off:
            out.append(day)
        day += timedelta(days=1)
    return out


def _spread(days: Sequence[date], count: int) -> list[date]:
    """`count` days spread evenly through `days`.

    Evenly, and deterministically. Clustering the allowance at the start of the
    month delays everything downstream by the whole amount on the first day;
    clustering it at the end delays nothing until the month is over. Both are
    defensible-sounding and both make the allowance behave like a lead or a lag
    rather than like weather.
    """
    if count <= 0 or not days:
        return []
    if count >= len(days):
        return list(days)
    # Midpoints of `count` equal buckets: for 2 days out of 20 that is the 5th
    # and the 15th, which is what "spread evenly" means to a reader.
    step = len(days) / count
    return [days[min(len(days) - 1, int(step * (i + 0.5)))] for i in range(count)]


def apply_allowance(
    calendar: Calendar,
    allowance: Allowance,
    *,
    start: date,
    finish: date,
) -> tuple[Calendar, AppliedAllowance]:
    """A copy of ``calendar`` with the allowance added as non-working days.

    Never mutates its argument: a calendar is shared between activities and
    between a with-allowance and a without-allowance run, and editing it in
    place would make the second run measure the first.
    """
    if finish < start:
        raise WeatherError(f"the window runs backwards: {start} to {finish}")

    added: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (finish.year, finish.month):
        count = allowance.days_in(month)
        if count:
            available = [
                day
                for day in _working_days_in_month(calendar, year, month)
                if start <= day <= finish
            ]
            added.extend(_spread(available, count))
        month += 1
        if month == 13:
            year, month = year + 1, 1

    out = Calendar(
        id=calendar.id,
        name=calendar.name,
        working_weekdays=set(calendar.working_weekdays),
        exceptions=list(calendar.exceptions),
        hours_per_day=calendar.hours_per_day,
        is_default=calendar.is_default,
    )
    for day in added:
        out.exceptions.append(CalendarException(day=day, working=False, name=WEATHER))
    return out, AppliedAllowance(calendar_id=calendar.id, days=tuple(sorted(added)))


def without_allowance(calendar: Calendar) -> Calendar:
    """The same calendar with only the weather days removed.

    Only the weather days: a shutdown the source file carried is a fact about
    the job and stays. Stripping every exception to get a "no weather" baseline
    would delete the Christmas holiday too and report a fortnight of it as
    weather recovered.
    """
    return Calendar(
        id=calendar.id,
        name=calendar.name,
        working_weekdays=set(calendar.working_weekdays),
        exceptions=[e for e in calendar.exceptions if e.name != WEATHER],
        hours_per_day=calendar.hours_per_day,
        is_default=calendar.is_default,
    )


def apply_to_all(
    calendars: Iterable[Calendar],
    allowances: Sequence[Allowance],
    *,
    start: date,
    finish: date,
) -> tuple[list[Calendar], list[AppliedAllowance]]:
    """Apply each allowance to the calendar it names.

    A calendar with no allowance comes back unchanged rather than being
    dropped, and an allowance naming a calendar that is not here raises --
    silently allowing nothing is the failure that shows up as "the weather
    allowance did not seem to do anything".
    """
    by_id = {c.id: c for c in calendars}
    for allowance in allowances:
        if allowance.calendar_id not in by_id:
            raise WeatherError(
                f"allowance names calendar {allowance.calendar_id!r}, which is not in this "
                f"schedule. It holds {sorted(by_id)}"
            )

    applied: list[AppliedAllowance] = []
    out: dict[str, Calendar] = dict(by_id)
    for allowance in allowances:
        updated, record = apply_allowance(
            by_id[allowance.calendar_id], allowance, start=start, finish=finish
        )
        out[allowance.calendar_id] = updated
        applied.append(record)
    return list(out.values()), applied


__all__ = [
    "WEATHER",
    "Allowance",
    "AppliedAllowance",
    "WeatherError",
    "apply_allowance",
    "apply_to_all",
    "without_allowance",
]
