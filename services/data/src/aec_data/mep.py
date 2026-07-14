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


def mep_summary(model: ifcopenshell.file) -> dict:
    """Every IfcDistributionSystem with its member breakdown (segments / fittings / terminals / other)
    and a connectivity signal: how many member elements have at least one *unconnected* port. Returns
    {systems:[…], total_systems, unassigned:{segments,fittings}}."""
    systems: list[dict] = []
    for sysobj in model.by_type("IfcDistributionSystem"):
        members = [o for rel in (getattr(sysobj, "IsGroupedBy", None) or []) for o in rel.RelatedObjects]
        segs = sum(1 for m in members if m.is_a() in _SEG)
        fits = sum(1 for m in members if m.is_a() in _FIT)
        terms = sum(1 for m in members if m.is_a("IfcFlowTerminal")
                    or m.is_a("IfcAirTerminal") or m.is_a("IfcSanitaryTerminal"))
        open_ports = 0
        for m in members:
            ps = _ports(m)
            if ps and any(not _port_connected(p) for p in ps):
                open_ports += 1
        systems.append({
            "guid": sysobj.GlobalId, "name": sysobj.Name or "System",
            "members": len(members), "segments": segs, "fittings": fits, "terminals": terms,
            "other": len(members) - segs - fits - terms,
            "elements_with_open_ports": open_ports,
        })
    # segments/fittings not assigned to any system (a coordination gap)
    def _unassigned(classes):
        n = 0
        for cls in classes:
            for el in model.by_type(cls):
                grouped = any(rel.is_a("IfcRelAssignsToGroup") and rel.RelatingGroup.is_a("IfcDistributionSystem")
                              for rel in (getattr(el, "HasAssignments", None) or []))
                if not grouped:
                    n += 1
        return n

    return {"total_systems": len(systems),
            "systems": sorted(systems, key=lambda s: s["name"]),
            "unassigned": {"segments": _unassigned(_SEG), "fittings": _unassigned(_FIT)}}
