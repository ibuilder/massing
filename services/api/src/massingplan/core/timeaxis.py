"""The absolute time axis and per-calendar working-day arithmetic.

This module is the kernel. Every other module in the engine assumes its
invariant silently: the forward pass derives finishes with ``add_working_days``,
the backward pass derives late starts with ``sub_working_days``, float is
``count_working_days`` between the two, levelling steps spans with ``add``, and
the Monte Carlo simulation calls all three two thousand times.

    sub_working_days(add_working_days(i, n), n) == i
    add_working_days(sub_working_days(i, n), n) == i
    count_working_days(i, add_working_days(i, n)) == n

If ``add`` and ``sub`` are off by one on exactly the instants that straddle a
holiday, the error shows up only on activities crossing a shutdown -- which are
disproportionately the ones on the critical path, because a shutdown is where
slack gets consumed. The dates stay plausible, nothing raises, and the critical
path is wrong by a day all the way through the export, the DCMA report, the risk
P80 and the delay claim. Hence 100% branch coverage and a dedicated CI job.

Named ``timeaxis`` rather than ``calendar`` deliberately. ``core/calendar.py``
shadows the standard library's ``calendar`` module, which is survivable in an
application and is not survivable in a package that gets copied into somebody
else's source tree. The name is also more honest: this is an absolute time axis,
and ``WorkCalendar`` is one pattern laid over it.

Time representation
-------------------
``Instant`` is ``date.toordinal()``, read as the boundary at 00:00 of that day.
Activity spans are half-open, ``[start, finish)``. An activity that works
D1..Dn has ``start = ordinal(D1)`` and ``finish = ordinal(Dn) + 1``, so
``count_working_days(start, finish) == duration`` with no ``+1`` anywhere. The
inclusive reading -- "the finish date is the last day worked" -- is a display
rule, applied once, in ``core/schedule.py``.

Portions derive from ibuilder/AIHackScheduler ``core/calendar.py`` (MIT): the
inclusive-finish semantics and the weekday presets. The O(days) loops it used
did not survive; see ``_lattice`` below.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

Instant = int

#: How far either side of a bound window the lattice is padded. Two years is
#: enough that ordinary date arithmetic near the project edges -- a lookahead, a
#: 600-day probe in DCMA check 12, a Monte Carlo tail -- stays inside the window
#: without the caller having to think about it.
_PAD_DAYS = 730

#: The lattice refuses to build across more than this span. A calendar with no
#: working days at all would otherwise loop to the heat death of the universe;
#: this turns that into an immediate, named error.
_MAX_WINDOW_DAYS = 200 * 365


class TimeAxisError(ValueError):
    """Base class for time-axis failures that name the calendar involved."""


class TimeAxisWindowError(TimeAxisError):
    """An instant fell outside the window the calendar's lattice was built for.

    Raised rather than extending silently, because an extension at query time
    would be a different answer depending on the order queries arrived in.
    """


class EmptyCalendarError(TimeAxisError):
    """A calendar has no working days in its window, so no arithmetic is defined."""


def instant_of(day: date) -> Instant:
    """The instant at 00:00 on ``day``."""
    return day.toordinal()


def day_of(i: Instant) -> date:
    """The date whose 00:00 boundary is ``i``."""
    return date.fromordinal(i)


@dataclass(frozen=True)
class WorkPattern:
    """Which days a crew can work.

    ``working_weekdays`` uses ``date.weekday()`` numbering: Monday is 0, Sunday
    is 6. ``holidays`` removes days the pattern would otherwise include;
    ``extra_work_days`` adds days it would otherwise exclude, which is how a
    make-up Saturday is modelled. An extra work day wins over a holiday on the
    same date -- if a planner has explicitly said "we are working that day", the
    generic holiday list is the less specific statement.
    """

    working_weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})
    holidays: frozenset[date] = frozenset()
    extra_work_days: frozenset[date] = frozenset()

    def covers(self, day: date) -> bool:
        if day in self.extra_work_days:
            return True
        if day in self.holidays:
            return False
        return day.weekday() in self.working_weekdays


@dataclass
class _LatticeCache:
    """The built lattice and the window it covers. Mutable, and private."""

    window: tuple[Instant, Instant] | None = None
    days: list[Instant] | None = None


STANDARD_5_DAY = WorkPattern(frozenset({0, 1, 2, 3, 4}))
SIX_DAY = WorkPattern(frozenset({0, 1, 2, 3, 4, 5}))
SEVEN_DAY = WorkPattern(frozenset({0, 1, 2, 3, 4, 5, 6}))


@dataclass(frozen=True)
class WorkCalendar:
    """A named work pattern plus the hours it counts as a day.

    Frozen and hashable so the same calendar object can be shared safely across
    two thousand Monte Carlo iterations. The lattice is built lazily into a
    field excluded from equality and hashing, so building it does not change the
    calendar's identity.

    ``hours_per_day`` exists because Primavera stores durations in hours and the
    conversion needs the calendar's own figure. A hardcoded 8 turns a 10-hour-day
    calendar's 40-hour task into 5 days when the file means 4.
    """

    id: str
    name: str
    pattern: WorkPattern = STANDARD_5_DAY
    hours_per_day: float = 8.0

    #: Mutable cache on a frozen dataclass, deliberately excluded from
    #: ``__eq__``/``__hash__`` so building the lattice does not change the
    #: calendar's identity. Typed rather than a ``dict[str, object]``: the
    #: untyped form silently defeats the type checker on every read, in the one
    #: module where an off-by-one is invisible.
    _cache: _LatticeCache = field(
        default_factory=lambda: _LatticeCache(), compare=False, hash=False, repr=False
    )

    # -- lattice -----------------------------------------------------------

    def bind(self, first: date, last: date) -> None:
        """Build the working-day lattice covering ``[first, last]`` plus padding.

        Called once per scheduling run rather than lazily per query, because a
        Monte Carlo simulation that rebuilds a five-year lattice inside its inner
        loop is two thousand times slower than it needs to be and nothing in the
        output says why.
        """
        lo = first.toordinal() - _PAD_DAYS
        hi = last.toordinal() + _PAD_DAYS
        if hi - lo > _MAX_WINDOW_DAYS:
            raise TimeAxisError(
                f"calendar {self.id!r}: refusing to build a lattice over "
                f"{hi - lo} days ({day_of(lo)} to {day_of(hi)})"
            )
        existing = self._cache.window
        if existing is not None:
            have_lo, have_hi = existing
            if have_lo <= lo and hi <= have_hi:
                return
            lo = min(lo, have_lo)
            hi = max(hi, have_hi)
        lattice = [i for i in range(lo, hi + 1) if self.pattern.covers(day_of(i))]
        if not lattice:
            raise EmptyCalendarError(
                f"calendar {self.id!r} has no working days between {day_of(lo)} and {day_of(hi)}"
            )
        self._cache.window = (lo, hi)
        self._cache.days = lattice

    def _lattice(self) -> list[Instant]:
        if self._cache.days is None:
            # An unbound calendar binds itself around today rather than raising.
            # A caller poking at a single date should not have to know about
            # windows; a caller scheduling a project always calls bind_window.
            today = date.today()
            self.bind(today - timedelta(days=_PAD_DAYS), today + timedelta(days=_PAD_DAYS))
        assert self._cache.days is not None  # noqa: S101 - bind() sets it or raises
        return self._cache.days

    def _window(self) -> tuple[Instant, Instant]:
        self._lattice()
        window = self._cache.window
        assert window is not None  # noqa: S101 - _lattice() guarantees bind() ran
        return window

    def window_bounds(self) -> tuple[Instant, Instant]:
        """The first and last *working* instants currently on the lattice.

        Public because callers legitimately need to know how far the arithmetic
        can reach before it raises -- a 600-day probe in DCMA check 12, or a
        levelling pass considering a long right-shift, would otherwise have to
        discover the edge by catching an exception.
        """
        lattice = self._lattice()
        return lattice[0], lattice[-1]

    def working_days_after(self, i: Instant) -> int:
        """How many working days remain in the window at or after ``i``.

        The upper bound on ``n`` for ``add_working_days(i, n)``.
        """
        _first, last = self.window_bounds()
        if i > last:
            return 0
        return self.count_working_days(i, last)

    def working_days_before(self, i: Instant) -> int:
        """How many working days precede ``i`` in the window.

        The upper bound on ``n`` for ``sub_working_days(i, n)``.
        """
        first, _last = self.window_bounds()
        if i < first:
            return 0
        return self.count_working_days(first, i)

    def _require_in_window(self, i: Instant, what: str) -> None:
        lo, hi = self._window()
        if not (lo <= i <= hi):
            raise TimeAxisWindowError(
                f"calendar {self.id!r}: {what} {day_of(i)} is outside the bound "
                f"window {day_of(lo)}..{day_of(hi)}"
            )

    # -- queries -----------------------------------------------------------

    def is_working(self, i: Instant) -> bool:
        """True when the day beginning at ``i`` is a working day."""
        return self.pattern.covers(day_of(i))

    def snap_start_forward(self, i: Instant) -> Instant:
        """The least working instant >= ``i``. Idempotent."""
        self._require_in_window(i, "start")
        lattice = self._lattice()
        pos = bisect_left(lattice, i)
        if pos >= len(lattice):
            raise TimeAxisWindowError(
                f"calendar {self.id!r}: no working day at or after {day_of(i)} in window"
            )
        return lattice[pos]

    def snap_start_back(self, i: Instant) -> Instant:
        """The greatest working instant <= ``i``. Idempotent."""
        self._require_in_window(i, "start")
        lattice = self._lattice()
        pos = bisect_right(lattice, i) - 1
        if pos < 0:
            raise TimeAxisWindowError(
                f"calendar {self.id!r}: no working day at or before {day_of(i)} in window"
            )
        return lattice[pos]

    def snap_finish_forward(self, i: Instant) -> Instant:
        """The least finish boundary >= ``i``, i.e. the least ``j >= i`` with ``j-1`` working.

        Finish boundaries live one past the last day worked, so they snap against
        ``j-1`` rather than ``j``. Getting this wrong puts a finish milestone on
        the Saturday after the work it marks.
        """
        self._require_in_window(i, "finish")
        return self.snap_start_forward(i - 1) + 1

    def snap_finish_back(self, i: Instant) -> Instant:
        """The greatest finish boundary <= ``i``."""
        self._require_in_window(i, "finish")
        return self.snap_start_back(i - 1) + 1

    def add_working_days(self, i: Instant, n: int) -> Instant:
        """The instant ``n`` working days after the working instant ``i``.

        ``i`` must already be on the lattice; callers snap first. ``n`` may be
        negative, in which case this is ``sub_working_days``.
        """
        if n < 0:
            return self.sub_working_days(i, -n)
        self._require_in_window(i, "instant")
        lattice = self._lattice()
        pos = bisect_left(lattice, i)
        if pos >= len(lattice) or lattice[pos] != i:
            raise TimeAxisError(
                f"calendar {self.id!r}: {day_of(i)} is not a working day; snap before adding"
            )
        target = pos + n
        if target >= len(lattice):
            raise TimeAxisWindowError(
                f"calendar {self.id!r}: {day_of(i)} + {n} working days runs past the window"
            )
        return lattice[target]

    def sub_working_days(self, i: Instant, n: int) -> Instant:
        """The instant ``n`` working days before the working instant ``i``."""
        if n < 0:
            return self.add_working_days(i, -n)
        self._require_in_window(i, "instant")
        lattice = self._lattice()
        pos = bisect_left(lattice, i)
        if pos >= len(lattice) or lattice[pos] != i:
            raise TimeAxisError(
                f"calendar {self.id!r}: {day_of(i)} is not a working day; snap before subtracting"
            )
        target = pos - n
        if target < 0:
            raise TimeAxisWindowError(
                f"calendar {self.id!r}: {day_of(i)} - {n} working days runs before the window"
            )
        return lattice[target]

    def count_working_days(self, a: Instant, b: Instant) -> int:
        """Working days in the half-open span ``[a, b)``. Signed: negative when ``b < a``.

        Signed on purpose. Total float is ``count(early_start, late_start)`` and
        a constrained schedule legitimately produces a negative answer; clamping
        it here would erase the single most important output a constraint has.
        """
        if b < a:
            return -self.count_working_days(b, a)
        self._require_in_window(a, "span start")
        self._require_in_window(b, "span end")
        lattice = self._lattice()
        return bisect_left(lattice, b) - bisect_left(lattice, a)

    def finish_from_start(self, start: Instant, duration_days: int) -> Instant:
        """The half-open finish boundary of ``duration_days`` work beginning at ``start``.

        A zero-duration activity finishes where it starts -- a milestone is an
        instant, not a day. Clamping it to one day is one of the four documented
        Primavera import traps, and it is just as wrong computed as imported.
        """
        if duration_days < 0:
            raise TimeAxisError(f"negative duration {duration_days}")
        if duration_days == 0:
            return start
        last_day = self.add_working_days(self.snap_start_forward(start), duration_days - 1)
        return last_day + 1

    def start_from_finish(self, finish: Instant, duration_days: int) -> Instant:
        """The start instant of ``duration_days`` work ending at the boundary ``finish``."""
        if duration_days < 0:
            raise TimeAxisError(f"negative duration {duration_days}")
        if duration_days == 0:
            return finish
        last_day = self.snap_start_back(finish - 1)
        return self.sub_working_days(last_day, duration_days - 1)


def bind_window(
    calendars: Mapping[str, WorkCalendar] | Iterable[WorkCalendar],
    first: date,
    last: date,
) -> None:
    """Build every calendar's lattice once, before any scheduling arithmetic.

    Takes either a mapping or a plain iterable so callers can pass the dict they
    already hold without unpacking it at every call site.
    """
    values = calendars.values() if isinstance(calendars, Mapping) else calendars
    for cal in values:
        cal.bind(first, last)


def standard_calendar(cal_id: str = "STD", name: str = "Standard 5-day") -> WorkCalendar:
    """A Monday-to-Friday, 8-hour calendar. The default when a file names none."""
    return WorkCalendar(id=cal_id, name=name, pattern=STANDARD_5_DAY, hours_per_day=8.0)
