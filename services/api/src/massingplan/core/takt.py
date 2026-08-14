"""Takt planning: a fixed rhythm through the zones, and what it costs.

Line of balance (`core/locations.py`) lets every trade run at its own natural
pace and then shifts the lines apart until nobody trespasses. Takt does the
opposite, and the difference is a decision, not a detail:

    **Every wagon occupies exactly one zone for exactly one takt.**

The crew sizes move so the durations do not. A train of `W` wagons through `Z`
zones takes `(W + Z - 1)` takts, always, and you can read that number off the
plan before any of the work is estimated. That predictability is the entire
product: a site where every trade hands over on Friday is a site where the next
trade can be told to arrive on Monday and believed.

What you buy it with
--------------------
**Idle capacity, and this module refuses to hide it.** A wagon whose work
content is 3.2 crew-days inside a 5-day takt needs one crew and uses 64% of it.
The remaining 36% is paid for and not worked. That number -- `utilisation` --
is the takt equivalent of `continuity_cost_days` in the line-of-balance engine:
the honest price of the method, reported rather than absorbed, because it is
what decides whether takt is right for this job.

Rounding it up, or reporting only the average, would produce a plan that looks
efficient and is not. Utilisation is per wagon, per zone, unrounded.

Work content, not duration
--------------------------
The input is **crew-days of work**, not "how long it takes". A trade's duration
depends on how many crews you put on it; its work content does not. Taking
duration as the input makes the crew calculation circular -- you would need the
crew count to know the duration you were using to derive the crew count -- and
the circularity resolves silently to whatever the planner typed first.

So: `crews = ceil(work_content / takt_days)`, and the duration is the takt by
construction.

The takt is chosen, not derived
-------------------------------
`plan()` takes the takt time as an input because it is a management decision --
usually a week, because a week is the unit a site actually runs on. Deriving it
from the work would hide that decision inside an algorithm.

What this module will do is tell you which takts are *feasible*:
`minimum_takt()` returns the shortest rhythm every wagon can meet within a crew
ceiling, and names the wagon that sets it. That is the bottleneck trade, and it
is the one worth attacking -- shortening any other changes nothing.

Deliberate limits, stated rather than discovered
------------------------------------------------
* **One zone per wagon per takt.** A wagon that needs two zones at once is a
  different method (it is no longer a train), not a parameter of this one.
* **No wagon skipping.** Every wagon visits every zone. A trade that genuinely
  does not occur in a zone is modelled as zero work content there, which still
  occupies the slot -- because the train cannot leave a gap without breaking
  the rhythm that is the point of the method. It is reported as an empty wagon
  so the planner can see the cost.
* **Crews are whole.** Half a crew is not a thing you can send to site.
* **The takt is uniform.** Varying takt by zone (a bigger floor plate gets two
  takts) is real practice and is not modelled here; it would be a per-zone
  multiplier and it changes the duration formula, so it is absent rather than
  approximated.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from datetime import date

from .constraints import ConstraintType
from .issues import IssueLog
from .locations import Location
from .network import Link, RelationType, Task
from .timeaxis import WorkCalendar, day_of, instant_of, standard_calendar
from .units import ROUNDING_EPSILON


class TaktError(ValueError):
    """The takt plan cannot be built as stated."""


@dataclass
class Wagon:
    """One trade in the train.

    `work_content` is crew-days per zone, keyed by zone id, and `default_work`
    covers the zones not named. Crew-days, not duration: see the module
    docstring for why taking duration here would be circular.
    """

    id: str
    name: str = ""
    #: Crew-days of work in each zone, by zone id.
    work_content: dict[str, float] = field(default_factory=dict)
    #: Crew-days for any zone not named in `work_content`.
    default_work: float = 1.0
    #: The most crews this trade can physically field. A ceiling, not a target:
    #: two gangs in a bathroom get in each other's way, and pretending
    #: otherwise produces a plan that cannot be built.
    max_crews: int = 4

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise TaktError("every wagon needs an id")
        if self.max_crews < 1:
            raise TaktError(f"{self.id}: max_crews must be at least 1")
        if self.default_work < 0:
            raise TaktError(f"{self.id}: work content cannot be negative")
        for zone, amount in self.work_content.items():
            if amount < 0:
                raise TaktError(f"{self.id}: negative work content in {zone}")
            if not math.isfinite(amount):
                raise TaktError(f"{self.id}: work content in {zone} is not a finite number")

    def work_in(self, zone_id: str) -> float:
        return self.work_content.get(zone_id, self.default_work)


@dataclass(frozen=True)
class Slot:
    """One wagon in one zone for one takt: the cell of the takt grid.

    `takt_index` is which takt of the train this slot occupies, counting from
    zero. It is the position in the rhythm, not a date -- the conversion to
    dates happens at exactly one site, as everywhere else in this package.
    """

    wagon_id: str
    zone_id: str
    takt_index: int
    crews: int
    work_content: float

    @property
    def activity_id(self) -> str:
        return f"{self.wagon_id}@{self.zone_id}"

    def utilisation(self, takt_days: int) -> float:
        """Fraction of the paid crew-time actually worked. Never rounded.

        1.0 is a full wagon. Below 1.0 is capacity bought and not used, which is
        the price of the fixed rhythm and the number the method has to be
        justified against.
        """
        capacity = self.crews * takt_days
        return self.work_content / capacity if capacity else 0.0


@dataclass(frozen=True)
class TaktPlan:
    """The computed train, and what the rhythm cost to hold."""

    slots: tuple[Slot, ...]
    takt_days: int
    #: `(wagons + zones - 1) * takt_days`. Readable off the plan before any of
    #: the work is estimated, which is the point of the method.
    duration_days: int
    #: Crews needed per wagon to meet the takt.
    crews: dict[str, int]
    #: Paid crew-time actually worked, per wagon, unrounded. The price.
    utilisation: dict[str, float]
    #: Wagons that cannot meet the takt even at `max_crews`. Non-empty means the
    #: plan as stated is not buildable, and the issue log says so at ERROR.
    overloaded: tuple[str, ...]
    issues: IssueLog

    @property
    def idle_crew_days(self) -> float:
        """Crew-days paid for and not worked across the whole train.

        The aggregate of `utilisation`, in the unit a commercial manager
        actually argues in.
        """
        return sum(
            slot.crews * self.takt_days - slot.work_content
            for slot in self.slots
            if slot.crews * self.takt_days > slot.work_content
        )

    def by_wagon(self, wagon_id: str) -> tuple[Slot, ...]:
        return tuple(s for s in self.slots if s.wagon_id == wagon_id)

    def to_rows(self, *, start: date, calendar: WorkCalendar) -> list[dict[str, object]]:
        """Takt indices rendered as dates. **The only conversion site here.**

        The same `snap_start_back` as `locations.to_rows` and `schedule._present`
        and for the same reason: `ends - 1` is the calendar day before the
        half-open boundary, which is not necessarily a day anybody worked.
        """
        origin = calendar.snap_start_forward(instant_of(start))
        rows: list[dict[str, object]] = []
        for slot in self.slots:
            begins = calendar.add_working_days(origin, slot.takt_index * self.takt_days)
            ends = calendar.add_working_days(origin, (slot.takt_index + 1) * self.takt_days)
            last_worked = calendar.snap_start_back(ends - 1) if ends > begins else begins
            rows.append(
                {
                    "activity_id": slot.activity_id,
                    "wagon_id": slot.wagon_id,
                    "zone_id": slot.zone_id,
                    "takt_index": slot.takt_index,
                    "crews": slot.crews,
                    "work_content": slot.work_content,
                    "utilisation": round(slot.utilisation(self.takt_days), 4),
                    "start": day_of(begins).isoformat(),
                    "finish": day_of(last_worked).isoformat(),
                    "duration_days": self.takt_days,
                }
            )
        return rows


def crews_for(work_content: float, takt_days: int) -> int:
    """Crews needed to fit `work_content` crew-days into one takt.

    The one `ceil` in this module, with `ROUNDING_EPSILON`, for the reason
    `units.days_from_hours` has one: `4.8 / 1.6` is `2.9999999999999996` in
    binary floating point, and rounding that up gives three crews where two
    will do -- a third of a trade's labour bill, from a representation error.

    Zero work needs zero crews. That is not a degenerate case to be clamped to
    one: a wagon with nothing to do in a zone still occupies the slot, and
    saying it needs a crew there would bill for a gang that is not sent.
    """
    if work_content <= 0:
        return 0
    if takt_days <= 0:
        raise TaktError("a takt must be at least one working day")
    return max(1, math.ceil(work_content / takt_days - ROUNDING_EPSILON))


def minimum_takt(wagons: list[Wagon], zones: list[Location]) -> tuple[int, str]:
    """The shortest feasible takt, and the wagon that sets it.

    Feasible means every wagon fits inside it at or below its own `max_crews`.
    Returned with the wagon's id because "five days" is not actionable and
    "five days, and it is the M&E first fix that says so" is: shortening any
    other trade changes nothing at all.
    """
    if not wagons:
        raise TaktError("a takt plan needs at least one wagon")
    if not zones:
        raise TaktError("a takt plan needs at least one zone")

    worst_days = 1
    bottleneck = wagons[0].id
    for wagon in wagons:
        heaviest = max(wagon.work_in(zone.id) for zone in zones)
        # Ceil, because a takt is whole working days, and the wagon has to fit
        # inside it with the crews it is allowed to field.
        needed = max(1, math.ceil(heaviest / wagon.max_crews - ROUNDING_EPSILON))
        if needed > worst_days:
            worst_days, bottleneck = needed, wagon.id
    return worst_days, bottleneck


def plan(
    wagons: list[Wagon],
    zones: list[Location],
    *,
    takt_days: int,
    issues: IssueLog | None = None,
) -> TaktPlan:
    """Build the train.

    `wagons` are in handover order; `zones` are sorted by `sequence`, which is
    the direction the train travels.

    Wagon `w` enters zone `z` at takt `w + z`, which is the whole scheduling
    calculation: no search, no shifting, no float. That is what a fixed rhythm
    buys, and it is why the duration is knowable in advance.
    """
    issues = issues if issues is not None else IssueLog()
    if not wagons:
        raise TaktError("a takt plan needs at least one wagon")
    if not zones:
        raise TaktError("a takt plan needs at least one zone")
    if takt_days < 1:
        raise TaktError("a takt must be at least one working day")

    ordered_zones = tuple(sorted(zones, key=lambda z: (z.sequence, z.id)))
    seen: set[str] = set()
    for zone in ordered_zones:
        if zone.id in seen:
            raise TaktError(f"duplicate zone id {zone.id!r}")
        seen.add(zone.id)

    seen_wagons: set[str] = set()
    for wagon in wagons:
        if wagon.id in seen_wagons:
            raise TaktError(f"duplicate wagon id {wagon.id!r}")
        seen_wagons.add(wagon.id)

    slots: list[Slot] = []
    crews: dict[str, int] = {}
    utilisation: dict[str, float] = {}
    overloaded: list[str] = []

    for wagon_index, wagon in enumerate(wagons):
        heaviest = max(wagon.work_in(zone.id) for zone in ordered_zones)
        needed = crews_for(heaviest, takt_days)

        if needed > wagon.max_crews:
            # Refused, not squeezed. Silently capping the crew count produces a
            # plan whose wagon cannot finish inside its takt, which breaks the
            # rhythm everywhere downstream -- and the plan still *looks* like a
            # takt plan, which is the dangerous part.
            overloaded.append(wagon.id)
            issues.error(
                "TAKT_OVERLOADED",
                f"{wagon.id} needs {needed} crews to fit a {takt_days}-day takt "
                f"but can field {wagon.max_crews}",
                "lengthen the takt, split the zone, or raise the crew ceiling -- "
                "the plan as stated cannot be built",
                row_key=wagon.id,
                raw_value=heaviest,
            )
            needed = wagon.max_crews

        if heaviest <= 0:
            issues.warn(
                "TAKT_EMPTY_WAGON",
                f"{wagon.id} has no work in any zone",
                "it still occupies a slot in every zone, because the train "
                "cannot leave a gap without breaking the rhythm -- remove the "
                "wagon if the trade is genuinely not on this job",
                row_key=wagon.id,
            )

        crews[wagon.id] = needed
        paid = 0.0
        worked = 0.0
        for zone_index, zone in enumerate(ordered_zones):
            work = wagon.work_in(zone.id)
            slots.append(
                Slot(
                    wagon_id=wagon.id,
                    zone_id=zone.id,
                    takt_index=wagon_index + zone_index,
                    crews=needed,
                    work_content=work,
                )
            )
            paid += needed * takt_days
            worked += work
        utilisation[wagon.id] = worked / paid if paid else 0.0

    duration_days = (len(wagons) + len(ordered_zones) - 1) * takt_days

    # Reported at INFO rather than left for somebody to compute: a wagon at 40%
    # is two-fifths of a trade's labour bill spent standing about, and it is
    # invisible on every chart the method produces.
    for wagon_id, used in utilisation.items():
        if 0 < used < 0.6:
            issues.info(
                "TAKT_LOW_UTILISATION",
                f"{wagon_id} works {used:.0%} of the crew-time it is paid for",
                "a shorter takt, a larger zone or merging the wagon with its "
                "neighbour recovers it -- or accept it as the price of the rhythm",
                row_key=wagon_id,
                raw_value=round(used, 4),
            )

    return TaktPlan(
        slots=tuple(slots),
        takt_days=takt_days,
        duration_days=duration_days,
        crews=crews,
        utilisation=utilisation,
        overloaded=tuple(overloaded),
        issues=issues,
    )


def to_network(
    result: TaktPlan,
    wagons: list[Wagon],
    zones: list[Location],
    *,
    start: date,
    calendar: WorkCalendar | None = None,
) -> tuple[list[Task], list[Link], dict[str, WorkCalendar]]:
    """Emit the takt plan as an ordinary network.

    Same contract as `locations.to_network`, and for the same reason: this
    module decides *where the slots sit*, and the CPM engine does the
    scheduling. Calendars, constraints, actuals, DCMA, risk and baseline
    comparison then all keep working on a takt plan without knowing what one is.

    The links are the two real dependencies, and both are stated rather than
    implied by the dates:

    * **the wagon's own chain** -- a crew finishes a zone and moves to the next,
      FS with no lag, which is what makes it a train rather than a set of
      independent activities;
    * **the handover** -- wagon `n` cannot enter a zone until wagon `n-1` has
      left it, FS, which is the constraint the rhythm exists to satisfy.

    Every slot also carries a start-on-or-after constraint pinning it to its
    takt. Without it, the CPM forward pass would pull the light wagons earlier
    and quietly dissolve the rhythm -- the takt would hold in this module and
    not in the schedule anybody reads.
    """
    calendar = calendar or standard_calendar()
    ordered_zones = tuple(sorted(zones, key=lambda z: (z.sequence, z.id)))
    origin = calendar.snap_start_forward(instant_of(start))

    by_wagon: dict[str, list[Slot]] = {}
    for slot in result.slots:
        by_wagon.setdefault(slot.wagon_id, []).append(slot)

    names = {wagon.id: (wagon.name or wagon.id) for wagon in wagons}
    zone_names = {zone.id: (zone.name or zone.id) for zone in ordered_zones}

    tasks: list[Task] = []
    for slot in result.slots:
        pinned = calendar.add_working_days(origin, slot.takt_index * result.takt_days)
        tasks.append(
            Task(
                id=slot.activity_id,
                name=f"{names.get(slot.wagon_id, slot.wagon_id)} — "
                f"{zone_names.get(slot.zone_id, slot.zone_id)}",
                duration_days=result.takt_days,
                calendar_id=calendar.id,
                constraint=ConstraintType.START_ON_OR_AFTER,
                constraint_date=day_of(pinned),
            )
        )

    links: list[Link] = []
    for wagon_id, wagon_slots in by_wagon.items():
        chain = sorted(wagon_slots, key=lambda s: s.takt_index)
        for earlier, later in itertools.pairwise(chain):
            links.append(Link(earlier.activity_id, later.activity_id, RelationType.FS, 0))
        del wagon_id

    order = [wagon.id for wagon in wagons]
    for zone in ordered_zones:
        for ahead, behind in itertools.pairwise(order):
            links.append(Link(f"{ahead}@{zone.id}", f"{behind}@{zone.id}", RelationType.FS, 0))

    return tasks, links, {calendar.id: calendar}
