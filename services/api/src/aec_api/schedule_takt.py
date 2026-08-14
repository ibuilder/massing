"""R45-SCHED-DEDUPE ② — real takt planning, and the naming collision it exposes.

**This is additive, not a replacement, and the reason is worth stating before the code.**

`aec_api/takt.py` and `massingplan/core/takt.py` both define `plan()`, which is how the R45 table
first read them: two implementations of one thing, pick the better. Reading both says otherwise —
they are **two different methods**, and the vendored module's own docstring draws the line:

> Line of balance lets every trade run at its own natural pace and then shifts the lines apart until
> nobody trespasses. **Takt does the opposite, and the difference is a decision, not a detail:** every
> wagon occupies exactly one zone for exactly one takt. The crew sizes move so the durations do not.

Our `takt.py` gives each trade its own `takt_days` — `Structure 5, Envelope 5, MEP 6, Interiors 8,
Finishes 6` — and lets them chase each other up the building. Trades running at *different* rates is
the definition of line of balance. **So `aec_api/takt.py` is a line-of-balance engine wearing the name
"takt", and real takt was missing entirely.**

That matters beyond tidiness, because `locations.py` now ships as `/schedule/flowline` and *is* line of
balance. Left alone, the product would offer the same method twice under two names and still not offer
takt. **Renaming or removing a shipped, user-facing panel is the user's call, so this module does not
touch it** — it adds the method that was absent and files the collision as a decision in the roadmap.

## What real takt buys, and what it costs

`(W + Z - 1)` takts for `W` wagons through `Z` zones — **always**, readable before any of the work is
estimated. A site where every trade hands over on Friday is one where the next trade can be told to
arrive Monday and believed.

It is paid for in **idle capacity**, and this engine refuses to hide it. A wagon with 3.2 crew-days of
work inside a 5-day takt needs one crew and uses 64% of it; the other 36% is paid for and not worked.
`utilisation` is per wagon per zone and unrounded, because rounding up or averaging produces a plan
that looks efficient and is not. It is the takt equivalent of `continuity_cost_days` in the flowline —
the honest price of the method, reported rather than absorbed.

## The input is work content, not duration

Crew-days of work, not "how long it takes": a trade's duration depends on how many crews you put on
it, its work content does not. Our `schedule_activity` records carry `duration` and `crew_size`, so
work content is `duration × crew_size` — which is exactly the quantity that stays fixed when you
change the crew, and the reason both fields have to be read rather than just the first.
"""
from __future__ import annotations

import logging
from typing import Any

from massingplan.core.locations import Location
from massingplan.core.takt import TaktError, Wagon, minimum_takt, plan

from .schedule_locations import _natural_key, _text

_LOG = logging.getLogger(__name__)


def _work_content(row: dict) -> float:
    """Crew-days: duration × crew size.

    Reading `duration` alone would make a 4-day task with one carpenter and a 4-day task with six
    identical, which is the whole distinction takt is built on — the durations are what move.
    """
    data = row.get("data") or {}

    def num(*names: str, default: float) -> float:
        for n in names:
            v = row.get(n, data.get(n))
            try:
                f = float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if f > 0:
                return f
        return default

    return num("duration", "duration_days", default=1.0) * num("crew_size", default=1.0)


def takt(activities: list[dict], *, takt_days: int | None = None,
         zone_order: list[str] | None = None, wagon_order: list[str] | None = None,
         max_crews: int = 4) -> dict[str, Any]:
    """Build the takt train for a project's activities.

    `takt_days` is the rhythm. Absent, the **shortest feasible** takt is computed and reported along
    with the wagon that sets it — that wagon is the constraint, and naming it is more useful than a
    number on its own.
    """
    if not activities:
        return _unavailable("no activities — there is no train to build")

    content: dict[tuple[str, str], float] = {}
    for row in activities:
        trade, zone = _text(row, "trade"), _text(row, "location", "location_loc")
        if not trade or not zone:
            continue
        content[(trade, zone)] = content.get((trade, zone), 0.0) + _work_content(row)

    if not content:
        return _unavailable(
            "no activity carries both a trade and a location — a takt train needs to know which "
            "wagon works in which zone")

    zones = sorted({z for _, z in content}, key=_natural_key)
    if zone_order:
        first = [z for z in zone_order if z in set(zones)]
        zones = first + [z for z in zones if z not in set(first)]

    all_w = {t for t, _ in content}
    if wagon_order:
        ordered = [w for w in wagon_order if w in all_w]
        names = ordered + sorted(all_w - set(ordered), key=_natural_key)
    else:
        # Same rule as the flowline: the order the trades were actually planned in, never the
        # alphabet. A takt train in alphabetical order is a confidently wrong answer.
        starts: dict[str, str] = {}
        for row in activities:
            t = _text(row, "trade")
            st = _text(row, "start", "actual_start", "early_start")
            if t and st and (t not in starts or st < starts[t]):
                starts[t] = st
        missing = sorted(all_w - set(starts), key=_natural_key)
        if missing:
            return _unavailable(
                f"cannot tell what order the wagons run in: {', '.join(missing[:5])} have no start "
                "date. Pass `wagon_order` or date the activities — an alphabetical train is a "
                "confident answer about a sequence nobody planned.",
                zones=zones, wagons=sorted(all_w, key=_natural_key))
        names = sorted(all_w, key=lambda t: (starts[t], _natural_key(t)))

    if len(zones) < 2:
        return _unavailable(
            f"only one zone ({zones[0]!r}) — a train through a single zone is one crew doing "
            "one job", zones=zones, wagons=names)

    wagons = [
        Wagon(id=n, name=n, max_crews=max_crews,
              work_content={z: content[(n, z)] for z in zones if (n, z) in content},
              default_work=1.0)
        for n in names
    ]

    places = [Location(id=z, name=z, sequence=i) for i, z in enumerate(zones)]

    try:
        # The floor is computed either way: when the caller names a takt we still report the shortest
        # feasible one and which wagon sets it, because "your 4-day takt is infeasible, and it is the
        # M&E first fix that says so" is the answer, where "infeasible" alone is not.
        floor, setter = minimum_takt(wagons, places)
        result = plan(wagons, places, takt_days=int(takt_days) if takt_days else floor)
    except TaktError as exc:
        # See `schedule_locations` for why the engine's own message is logged rather than relayed.
        _LOG.warning("takt train refused for %d activities: %s", len(activities), exc)
        return _unavailable(
            "the wagons could not be arranged into a train — the activity zones are inconsistent. "
            "See the server log for the engine's reason.",
            zones=zones, wagons=names)

    return {
        "available": True,
        "zones": zones,
        "wagons": names,
        "takt_days": result.takt_days,
        "duration_days": result.duration_days,
        # (W + Z - 1) is the whole claim of the method — surfaced so a reader can check it.
        "takt_count": len(names) + len(zones) - 1,
        "minimum_takt_days": floor,
        "minimum_takt_set_by": setter,
        "crews": dict(result.crews),
        # Unrounded, per wagon per zone. Rounding up or averaging produces a plan that looks
        # efficient and is not.
        "utilisation": dict(result.utilisation),
        "overloaded": list(result.overloaded),
        "slots": [
            {"wagon_id": s.wagon_id, "zone_id": s.zone_id, "takt_index": s.takt_index,
             "crews": s.crews, "work_content": s.work_content}
            for s in result.slots
        ],
        "issues": [i.to_dict() for i in result.issues],
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing to plan. `takt_days` and `duration_days` are `None`, never `0`."""
    return {
        "available": False,
        "reason": reason,
        "zones": [],
        "wagons": [],
        "takt_days": None,
        "duration_days": None,
        "takt_count": None,
        "minimum_takt_days": None,
        "minimum_takt_set_by": None,
        "crews": {},
        "utilisation": {},
        "overloaded": [],
        "slots": [],
        "issues": [],
        **extra,
    }
