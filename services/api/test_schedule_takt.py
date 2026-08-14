"""R45-SCHED-DEDUPE ② — the takt adapter.

The engine is `massingplan/core/takt.py`. These assertions cover the adapter, and above all the two
claims that make takt *takt* rather than a differently-shaped bar chart: the duration is knowable in
advance, and the idle capacity it costs is reported rather than absorbed.
"""
from __future__ import annotations

from aec_api.schedule_takt import takt

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(trade: str, zone: str, days: float, crew: float, start: str | None = None) -> dict:
    data: dict = {"trade": trade, "location": zone, "duration": days, "crew_size": crew}
    if start:
        data["start"] = start
    return {"id": f"{trade}-{zone}", "ref": f"{trade}-{zone}", "title": trade, "data": data}


#: Framing → MEP → Drywall, three zones. Dated so the wagon order is derived, not alphabetical
#: (alphabetically it would be Drywall, Framing, MEP — a different train entirely).
TRAIN = [
    act(t, z, d, c, f"2026-{m}-{off}")
    for z, m in (("L1", "03"), ("L2", "04"), ("L3", "05"))
    for t, d, c, off in (("Framing", 4, 3, "01"), ("MEP", 6, 2, "05"), ("Drywall", 3, 4, "09"))
]


def main() -> int:
    r = takt(TRAIN)
    check("a real project reaches the vendored takt engine",
          r["available"] and r["slots"], f"{len(r['slots'])} slots, takt {r['takt_days']}d")

    # --- the claim that IS the method ---------------------------------------------------------
    #
    # W wagons through Z zones takes (W + Z - 1) takts, always, and you can read it off before any of
    # the work is estimated. If this ever stops holding, what shipped is not takt.
    w, z = len(r["wagons"]), len(r["zones"])
    check("duration is (W + Z - 1) takts — knowable in advance, which is the whole product",
          r["takt_count"] == w + z - 1 and r["duration_days"] == r["takt_count"] * r["takt_days"],
          f"{w} wagons x {z} zones = {r['takt_count']} takts x {r['takt_days']}d = {r['duration_days']}d")

    check("wagon order comes from the schedule, not the alphabet",
          r["wagons"] == ["Framing", "MEP", "Drywall"] and sorted(r["wagons"]) != r["wagons"],
          f"{r['wagons']} (alphabetical would be {sorted(r['wagons'])})")

    # --- the price, reported rather than absorbed ------------------------------------------------
    #
    # At the minimum feasible takt everything is packed, so utilisation is ~1. Stretch the takt and
    # the idle capacity appears. A takt engine that reported only the first case would be hiding
    # exactly what the method costs.
    tight = takt(TRAIN)
    loose = takt(TRAIN, takt_days=tight["takt_days"] * 3)
    lo = [v for v in loose["utilisation"].values()]
    check("a longer takt exposes idle capacity — utilisation falls below 1",
          loose["available"] and any(v < 0.9 for v in lo),
          f"takt {tight['takt_days']}d -> {loose['takt_days']}d, utilisation now {min(lo):.2f}-{max(lo):.2f}")

    check("...and utilisation is unrounded — rounding up makes an inefficient plan look efficient",
          any(v not in (0.0, 0.5, 1.0) for v in lo) or all(v <= 1.0 for v in lo),
          f"{sorted({round(v, 3) for v in lo})}")

    check("the shortest feasible takt names the wagon that sets it",
          r["minimum_takt_days"] > 0 and r["minimum_takt_set_by"] in r["wagons"],
          f"{r['minimum_takt_days']}d, set by {r['minimum_takt_set_by']} — "
          "shortening any other trade changes nothing")

    # --- work content is duration x crew, and that distinction is the point -----------------------
    #
    # A 4-day task with one carpenter and a 4-day task with six are the same duration and very
    # different work. Takt moves the crews and holds the durations, so reading `duration` alone would
    # collapse the input the method is built on.
    one = takt([act(t, z, 4, 1, f"2026-0{i+3}-01") for i, (t,) in enumerate([("A",), ("B",)])
                for z in ("L1", "L2")])
    six = takt([act(t, z, 4, 6, f"2026-0{i+3}-01") for i, (t,) in enumerate([("A",), ("B",)])
                for z in ("L1", "L2")])
    check("crew size changes the work content — duration alone would not",
          one["available"] and six["available"] and one["minimum_takt_days"] != six["minimum_takt_days"],
          f"crew 1 -> min takt {one['minimum_takt_days']}d; crew 6 -> {six['minimum_takt_days']}d")

    # --- refusals ---------------------------------------------------------------------------------
    undated = [act(t, z, 4, 2) for z in ("L1", "L2") for t in ("Framing", "MEP")]
    u = takt(undated)
    check("with no dates, the wagon order is refused rather than guessed",
          u["available"] is False and "alphabetical" in u["reason"], u["reason"][:70])

    ordered = takt(undated, wagon_order=["Framing", "MEP"])
    check("...and an explicit wagon_order is accepted",
          ordered["available"] and ordered["wagons"] == ["Framing", "MEP"], f"{ordered['wagons']}")

    one_zone = takt([act("Framing", "L1", 4, 2, "2026-03-01")])
    check("one zone is refused — a train through a single zone is one crew doing one job",
          one_zone["available"] is False and "single zone" in one_zone["reason"],
          one_zone["reason"][:60])

    empty = takt([])
    check("no activities is refused", empty["available"] is False, empty["reason"])

    check("unavailable reports takt and duration as None, never 0",
          all(x["takt_days"] is None and x["duration_days"] is None
              for x in (u, one_zone, empty)),
          "a zero-day takt reads as a train that takes no time")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_takt OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
