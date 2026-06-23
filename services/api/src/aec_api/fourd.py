"""4D construction sequencing (C3) — tie the takt schedule to model elements so the build sequence
is a scrubable timeline: each element gets a completion day from the trade that installs its class
on its floor, and the timeline reports cumulative progress frame by frame. Pure over a takt plan +
an element list (guid, ifc_class, storey); the viewer scrubs the frames to animate construction."""
from __future__ import annotations

import re
from typing import Any

# which takt trade installs each IFC class (drives when the element appears)
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
