"""W11 · B6 — MEP system browser + connectivity check.

Segments (`IfcDuctSegment`/`IfcPipeSegment`/…), fittings (`IfcDuctFitting`/…) and terminals are grouped
into logical **`IfcDistributionSystem`s** (via `IfcRelAssignsToGroup`). This reads the systems back for a
browser — per-system member breakdown by class + a simple connectivity signal (elements whose ports are
not yet connected to another port), the openBIM equivalent of "unconnected MEP" review.
"""
from __future__ import annotations

import ifcopenshell

_SEG = ("IfcDuctSegment", "IfcPipeSegment", "IfcCableCarrierSegment", "IfcCableSegment")
_FIT = ("IfcDuctFitting", "IfcPipeFitting", "IfcCableCarrierFitting", "IfcCableFitting")
# terminal classes counted as system endpoints (MEP-FP adds fire-suppression: sprinkler heads, etc.)
_TERM = ("IfcFlowTerminal", "IfcAirTerminal", "IfcSanitaryTerminal", "IfcFireSuppressionTerminal")

# MEP-FP: an IfcDistributionSystem PredefinedType → the discipline it belongs to. Fire protection is a
# first-class discipline beside HVAC / plumbing / electrical, not folded into a generic "MEP" bucket.
_DISCIPLINE_BY_PREDEF = {
    "VENTILATION": "hvac", "AIRCONDITIONING": "hvac", "EXHAUST": "hvac", "HEATING": "hvac",
    "REFRIGERATION": "hvac", "CHILLEDWATER": "hvac", "CONDENSERWATER": "hvac",
    "DOMESTICCOLDWATER": "plumbing", "DOMESTICHOTWATER": "plumbing", "DRAINAGE": "plumbing",
    "SEWAGE": "plumbing", "WATERSUPPLY": "plumbing", "RAINWATER": "plumbing", "STORMWATER": "plumbing",
    "WASTEWATER": "plumbing", "GAS": "plumbing", "FUEL": "plumbing",
    "ELECTRICAL": "electrical", "LIGHTING": "electrical", "POWERGENERATION": "electrical",
    "EARTHING": "electrical",
    "FIREPROTECTION": "fire",
    "COMMUNICATION": "comms", "DATA": "comms", "TELEPHONE": "comms", "SIGNAL": "comms", "TV": "comms",
    "SECURITY": "comms", "CONTROL": "comms",
}


def _discipline(sysobj, members) -> str:
    """The discipline of a distribution system: from its PredefinedType when set, otherwise inferred from
    the member element classes (fire-suppression terminal → fire; duct → hvac; cable → electrical;
    pipe → plumbing)."""
    pt = str(getattr(sysobj, "PredefinedType", None) or "").upper()
    if pt in _DISCIPLINE_BY_PREDEF:
        return _DISCIPLINE_BY_PREDEF[pt]
    cls = {m.is_a() for m in members}
    if any(c == "IfcFireSuppressionTerminal" for c in cls):
        return "fire"
    if any(c.startswith("IfcDuct") for c in cls):
        return "hvac"
    if any(c.startswith("IfcCable") for c in cls):
        return "electrical"
    if any(c.startswith("IfcPipe") for c in cls):
        return "plumbing"
    return "other"


def _is_terminal(m) -> bool:
    return any(m.is_a(t) for t in _TERM)


def _ports(el):
    """Connection ports on an element (IfcRelNests → IfcDistributionPort), across IFC2x3/IFC4 shapes."""
    ports = []
    for rel in (getattr(el, "IsNestedBy", None) or []):
        ports.extend(p for p in rel.RelatedObjects if p.is_a("IfcDistributionPort"))
    # IFC2x3 fallback: HasPorts inverse
    for rel in (getattr(el, "HasPorts", None) or []):
        p = getattr(rel, "RelatingPort", None)
        if p is not None and p.is_a("IfcDistributionPort"):
            ports.append(p)
    return ports


def _port_connected(port) -> bool:
    return bool(getattr(port, "ConnectedTo", None) or getattr(port, "ConnectedFrom", None))


def _by_type(model, cls):
    """by_type that returns [] for a class absent from the model's schema (IfcDistributionSystem and the
    duct/pipe/fitting classes are IFC4+; model.by_type raises RuntimeError on an IFC2x3 model)."""
    try:
        return model.by_type(cls)
    except RuntimeError:
        return []


def mep_summary(model: ifcopenshell.file) -> dict:
    """Every IfcDistributionSystem with its member breakdown (segments / fittings / terminals / other)
    and a connectivity signal: how many member elements have at least one *unconnected* port. Returns
    {systems:[…], total_systems, unassigned:{segments,fittings}}."""
    systems: list[dict] = []
    by_discipline: dict[str, dict[str, int]] = {}
    for sysobj in _by_type(model, "IfcDistributionSystem"):
        members = [o for rel in (getattr(sysobj, "IsGroupedBy", None) or []) for o in rel.RelatedObjects]
        segs = sum(1 for m in members if m.is_a() in _SEG)
        fits = sum(1 for m in members if m.is_a() in _FIT)
        terms = sum(1 for m in members if _is_terminal(m))
        open_ports = 0
        for m in members:
            ps = _ports(m)
            if ps and any(not _port_connected(p) for p in ps):
                open_ports += 1
        disc = _discipline(sysobj, members)
        pt = getattr(sysobj, "PredefinedType", None)
        systems.append({
            "guid": sysobj.GlobalId, "name": sysobj.Name or "System",
            "discipline": disc, "predefined_type": (str(pt) if pt else None),
            "members": len(members), "segments": segs, "fittings": fits, "terminals": terms,
            "other": len(members) - segs - fits - terms,
            "elements_with_open_ports": open_ports,
        })
        agg = by_discipline.setdefault(disc, {"systems": 0, "members": 0})
        agg["systems"] += 1
        agg["members"] += len(members)
    # segments/fittings not assigned to any system (a coordination gap)
    def _unassigned(classes):
        n = 0
        for cls in classes:
            for el in _by_type(model, cls):
                grouped = any(rel.is_a("IfcRelAssignsToGroup") and rel.RelatingGroup.is_a("IfcDistributionSystem")
                              for rel in (getattr(el, "HasAssignments", None) or []))
                if not grouped:
                    n += 1
        return n

    return {"total_systems": len(systems),
            "systems": sorted(systems, key=lambda s: (s["discipline"], s["name"])),
            "by_discipline": by_discipline,
            "has_fire_protection": "fire" in by_discipline,
            "unassigned": {"segments": _unassigned(_SEG), "fittings": _unassigned(_FIT)}}


def connectivity(model: ifcopenshell.file) -> dict:
    """W10-4 connectivity validation: over every MEP segment/fitting/terminal, count ports connected vs
    open (`IfcRelConnectsPorts`), the number of port-to-port connections, and the **dangling** elements —
    those whose ports are ALL unconnected (floating, not wired into any run). The openBIM 'unconnected MEP'
    review. Returns {elements, ports_total, ports_connected, ports_open, connections, dangling:[…]}."""
    classes = (*_SEG, *_FIT, *_TERM)
    seen: set[int] = set()
    els = []
    for cls in classes:
        for el in _by_type(model, cls):
            if el.id() not in seen:
                seen.add(el.id())
                els.append(el)

    ports_total = ports_conn = 0
    dangling: list[dict] = []
    connected_ports: set[int] = set()
    for el in els:
        ps = _ports(el)
        conn = [p for p in ps if _port_connected(p)]
        ports_total += len(ps)
        ports_conn += len(conn)
        for p in conn:
            connected_ports.add(p.id())
        if ps and not conn:                       # every port open → floating element
            dangling.append({"guid": el.GlobalId, "class": el.is_a(), "name": getattr(el, "Name", None)})

    return {
        "elements": len(els),
        "ports_total": ports_total,
        "ports_connected": ports_conn,
        "ports_open": ports_total - ports_conn,
        # one logical port-to-port link joins two ports (ifcopenshell may store the reciprocal rel too, so
        # count linked port-pairs, not raw IfcRelConnectsPorts entities)
        "connections": ports_conn // 2,
        "dangling_count": len(dangling),
        "dangling": dangling[:50],
        "connected_pct": round(100.0 * ports_conn / ports_total, 1) if ports_total else 0.0,
    }
