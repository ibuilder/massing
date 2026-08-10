"""The single rounding site, and the single date-type guard.

Two conversions in this engine are dangerous out of proportion to their size,
and both are dangerous because they are invisible when they go wrong.

**Hours to days.** Primavera stores durations in hours; this engine works in
days. The conversion appeared in three separate places in the code this was
ported from, and one of them additionally rounded to two decimals. A 7.5-day
task imported as 8 days, exported as 64 hours, and reimported as 8 -- drift
accumulating across round trips with nowhere to point at. There is now exactly
one ``ceil`` in the whole package, and it is here.

**date versus datetime.** ``date(2026, 6, 1) == datetime(2026, 6, 1, 0, 0)`` is
``False``. A single ``datetime`` leaking in from a database driver makes an
activity silently unmatched in ``compare()``, and a timezone-aware one raises
``TypeError`` deep inside the backward pass where the traceback names nothing
useful. So it is rejected at the boundary, by name, with the field it came from.
"""

from __future__ import annotations

from datetime import date, datetime
from math import ceil

HOURS_PER_DAY_DEFAULT = 8.0

#: Subtracted before ceiling. ``40 / 8.0`` is not always exactly ``5.0`` in
#: binary floating point; without this, a 40-hour task on an 8-hour calendar
#: becomes six days. The bug is invisible in the output and reappears every time
#: somebody "simplifies" the expression, which is why the constant is named and
#: this comment sits next to it.
ROUNDING_EPSILON = 1e-9


class UnitError(ValueError):
    """A value could not be interpreted in the units the engine works in."""


def days_from_hours(hours: float | None, hours_per_day: float) -> int:
    """Whole working days covering ``hours`` of work. The only ``ceil`` in the package.

    Rounds up, because a task needing 33 hours on an 8-hour calendar occupies
    five days, not four and an eighth: you cannot schedule a crew for a fraction
    of a shift and then hand the space over.
    """
    if hours is None:
        return 0
    if hours_per_day <= 0:
        raise UnitError(f"hours_per_day must be positive, got {hours_per_day!r}")
    if hours < 0:
        raise UnitError(f"negative duration {hours!r} hours")
    if hours == 0:
        return 0
    return max(0, ceil(hours / hours_per_day - ROUNDING_EPSILON))


def hours_from_days(days: int, hours_per_day: float) -> float:
    """Hours equivalent to ``days`` on a calendar of ``hours_per_day``."""
    if hours_per_day <= 0:
        raise UnitError(f"hours_per_day must be positive, got {hours_per_day!r}")
    return days * hours_per_day


def as_date(value: object, *, field: str) -> date:
    """Coerce to ``date``, rejecting anything that would compare unequal to one.

    A ``datetime`` at midnight is accepted and narrowed -- that is what every
    database driver hands back for a DATE column, and refusing it would make the
    engine unusable. A ``datetime`` with a real time component is rejected rather
    than truncated: truncating silently discards information the caller thought
    it was passing.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise UnitError(
                f"{field}: timezone-aware datetime {value!r}; the engine works in "
                "calendar dates and has no timezone to resolve it against"
            )
        if (value.hour, value.minute, value.second, value.microsecond) != (0, 0, 0, 0):
            raise UnitError(
                f"{field}: datetime {value!r} carries a time of day; pass a date, "
                "or decide explicitly which day it belongs to"
            )
        return value.date()
    if isinstance(value, date):
        return value
    raise UnitError(f"{field}: expected a date, got {type(value).__name__} {value!r}")


def maybe_date(value: object, *, field: str) -> date | None:
    """``as_date``, but ``None`` passes through. For optional columns."""
    if value is None:
        return None
    return as_date(value, field=field)
