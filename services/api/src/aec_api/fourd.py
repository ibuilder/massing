"""4D construction sequencing (C3) — tie the takt schedule to model elements so the build sequence
is a scrubable timeline: each element gets a completion day from the trade that installs its class
on its floor, and the timeline reports cumulative progress frame by frame. Pure over a takt plan +
an element list (guid, ifc_class, storey); the viewer scrubs the frames to animate construction."""
from __future__ import annotations

import re
from typing import Any

# Which takt *trade* installs each IFC class (drives when the element appears in the 4D sequence). This is
# a build-sequence axis, deliberately SEPARATE from the design discipline / sheet series (which live in the
# `classification` SSOT — `discipline_of_ifc_class` / `series_of_ifc_class`): a wall's discipline is
# Architectural but its trade is Envelope, a column is Structural discipline AND Structure trade. Keep this
# keyed to construction sequence, not discipline. (DISC-SSOT: discipline↔series unified; trade is its own.)
TRADE_FOR_CLASS = {
    "IfcFooting": "Structure", "IfcPile": "Structure", "IfcColumn": "Structure",
    "IfcBeam": "Structure", "IfcSlab": "Structure", "IfcStair": "Structure", "IfcMember": "Structure",
    "IfcWall": "Envelope", "IfcWallStandardCase": "Envelope", "IfcCurtainWall": "Envelope",
    "IfcWindow": "Envelope", "IfcDoor": "Envelope", "IfcRoof": "Envelope", "IfcPlate": "Envelope",
    "IfcDuctSegment": "MEP rough-in", "IfcPipeSegment": "MEP rough-in", "IfcCableSegment": "MEP rough-in",
    "IfcFlowTerminal": "MEP rough-in", "IfcTransportElement": "MEP rough-in",
    "IfcSpace": "Interiors", "IfcFurniture": "Finishes", "IfcCovering": "Finishes",
}
_DEFAULT_TRADE = "Finishes"


# class-trade (above) → schedule_activity `trade` option, so the GC schedule's trades drive the 4D
_CLASS_TRADE_TO_ACTIVITY_TRADE = {
    "Structure": "Structure", "Envelope": "Envelope", "MEP rough-in": "MEP",
    "Interiors": "Interiors", "Finishes": "Finishes",
}


def _pdate(v: Any):
    from datetime import date
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def timeline_from_activities(activities: list[dict], elements: list[dict]) -> dict[str, Any]:
    """Drive the 4D scrub from the GC schedule (`schedule_activity` records) instead of a generated
    takt plan — so the model sequence plays the *actual* schedule. Each element gets a finish date:
    **(A)** directly, when an activity tags its GUID (`activity['element_guids']`); else **(B)** by
    mapping the element's IFC class → trade → that trade's activities, distributed across floors.
    Frames carry a real calendar `date`; the shape matches `timeline()` so the viewer scrubs it
    unchanged. Returns `linked`/`unlinked` counts so the UI can show how much is hard-tied."""
    acts = []
    for a in activities:
        fin = _pdate(a.get("finish")) or _pdate(a.get("actual_finish"))
        if fin is None:
            continue
        acts.append({"trade": a.get("trade"), "_finish": fin,
                     "_start": _pdate(a.get("start")) or _pdate(a.get("actual_start")) or fin,
                     "_guids": set(a.get("element_guids") or [])})
    empty = {"frames": [], "total_days": 0, "element_count": 0, "by_trade": {},
             "source": "gc", "linked": 0, "unlinked": 0, "activity_count": len(acts)}
    if not acts:
        return empty

    guid_finish: dict[str, Any] = {}
    # (A) direct element tags — earliest finishing activity wins for a shared guid
    for a in acts:
        for g in a["_guids"]:
            if g not in guid_finish or a["_finish"] < guid_finish[g]:
                guid_finish[g] = a["_finish"]
    direct = set(guid_finish)

    # (B) untagged elements: class → trade → distribute across that trade's activities by floor
    by_trade: dict[str, list] = {}
    for a in acts:
        if a["trade"]:
            by_trade.setdefault(a["trade"], []).append(a)
    for v in by_trade.values():
        v.sort(key=lambda x: x["_start"])
    floors = max([_floor_index(e.get("storey")) for e in elements] + [0]) + 1
    last_finish = max(a["_finish"] for a in acts)
    for el in elements:
        g = el.get("guid")
        if not g or g in guid_finish:
            continue
        cls_trade = TRADE_FOR_CLASS.get(el.get("ifc_class"), _DEFAULT_TRADE)
        pool = by_trade.get(_CLASS_TRADE_TO_ACTIVITY_TRADE.get(cls_trade, cls_trade)) or []
        if not pool:
            guid_finish[g] = last_finish            # no matching trade activity → completes at end
            continue
        f = _floor_index(el.get("storey"))
        idx = round(f / max(1, floors - 1) * (len(pool) - 1)) if len(pool) > 1 else 0
        guid_finish[g] = pool[idx]["_finish"]

    if not guid_finish:
        return empty
    d0 = min(guid_finish.values())
    by_date: dict[Any, list] = {}
    for g, d in guid_finish.items():
        by_date.setdefault(d, []).append(g)
    placed = len(guid_finish)
    out, cum = [], 0
    for d in sorted(by_date):
        gs = by_date[d]
        cum += len(gs)
        out.append({"day": (d - d0).days, "date": d.isoformat(), "new": len(gs),
                    "completed_cumulative": cum, "pct": round(cum / placed * 100, 1),
                    "new_guids": gs[:500]})
    linked = sum(1 for el in elements if el.get("guid") in direct)
    return {"frames": out, "total_days": out[-1]["day"] if out else 0,
            "element_count": placed, "by_trade": {t: len(v) for t, v in by_trade.items()},
            "source": "gc", "start_date": d0.isoformat(),
            "finish_date": max(by_date).isoformat(),
            "linked": linked, "unlinked": placed - linked, "activity_count": len(acts)}


def _floor_index(storey: str | None) -> int:
    """'Level 3' / 'Floor 2' / 'L4' → zero-based floor index; default ground (0)."""
    if not storey:
        return 0
    m = re.search(r"(\d+)", str(storey))
    return max(0, int(m.group(1)) - 1) if m else 0


def timeline(takt_plan: dict, elements: list[dict]) -> dict[str, Any]:
    """`takt_plan` from takt.plan(); `elements`: [{guid, ifc_class, storey}]. Returns ordered frames
    (completion day → new + cumulative element counts) so a viewer can scrub the construction sequence."""
    trades = {t["name"]: t for t in takt_plan.get("trades", [])}
    fallback = takt_plan.get("trades", [{}])[-1] if takt_plan.get("trades") else None
    frames: dict[int, list[str]] = {}
    by_trade: dict[str, int] = {}
    placed = 0
    for el in elements:
        trade_name = TRADE_FOR_CLASS.get(el.get("ifc_class"), _DEFAULT_TRADE)
        t = trades.get(trade_name) or fallback
        if not t:
            continue
        starts = t.get("floor_starts") or [0]
        f = min(_floor_index(el.get("storey")), len(starts) - 1)
        finish = int(starts[f]) + int(t.get("takt_days", 5))
        frames.setdefault(finish, []).append(el.get("guid"))
        by_trade[trade_name] = by_trade.get(trade_name, 0) + 1
        placed += 1

    days = sorted(frames)
    out, cum = [], 0
    for d in days:
        cum += len(frames[d])
        out.append({"day": d, "new": len(frames[d]), "completed_cumulative": cum,
                    "pct": round(cum / placed * 100, 1) if placed else 0.0,
                    "new_guids": frames[d][:500]})
    return {"frames": out, "total_days": days[-1] if days else 0,
            "element_count": placed, "by_trade": by_trade}
