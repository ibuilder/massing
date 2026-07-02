"""IFC → gbXML (Green Building XML) export.

Scope (honest): a space/zone schedule with **areas + volumes from the real IFC geometry** plus the
building's exterior **envelope areas** (exterior wall / window / roof / ground floor) — a simplified,
early-design energy model (shoebox level). It carries the spaces, areas and volumes that energy tools
(OpenStudio / EnergyPlus / IES / DesignBuilder) import to seed a model. It is NOT a full
surface-by-surface thermal model with adjacencies (that needs IfcRelSpaceBoundary geometry) — so the
envelope is emitted at building level, not per-space. Produces valid gbXML 6.01.
"""
from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from . import energy, spaces
from .ifc_loader import open_model


def _num(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def to_gbxml(model, project_name: str = "Project") -> str:
    rooms = spaces.space_schedule(model)
    areas = energy.envelope_areas(model)
    out: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append('<gbXML xmlns="http://www.gbxml.org/schema" version="6.01" temperatureUnit="C" '
               'lengthUnit="Meters" areaUnit="SquareMeters" volumeUnit="CubicMeters" '
               'useSIUnitsForResults="true">')
    out.append('<Campus id="campus-1">')
    out.append(f'<Name>{escape(project_name)}</Name>')
    out.append('<Location><Name>Site</Name></Location>')
    out.append('<Building id="bldg-1" buildingType="Unknown">')
    total_area = sum(_num(r.get("net_area")) for r in rooms)
    out.append(f'<Area>{total_area:.2f}</Area>')
    for i, r in enumerate(rooms):
        area = _num(r.get("net_area"))
        vol = _num(r.get("volume"))
        name = str(r.get("name") or r.get("number") or f"Space {i + 1}")
        out.append(f'<Space id="space-{i + 1}" spaceType="Unknown" '
                   f'conditionType="HeatedAndCooled">')
        out.append(f'<Name>{escape(name)}</Name>')
        if r.get("storey"):
            out.append(f'<Description>{escape(str(r["storey"]))}</Description>')
        out.append(f'<Area>{area:.2f}</Area><Volume>{vol:.2f}</Volume>')
        occ = _num(r.get("occupancy"))
        if occ:
            out.append(f'<PeopleNumber unit="NumberOfPeople">{occ:g}</PeopleNumber>')
        out.append('</Space>')
    # building-level exterior envelope (aggregate areas from geometry) — surfaceType per gbXML enum
    for st, val, opening in (("ExteriorWall", areas.wall, areas.window),
                             ("Roof", areas.roof, 0.0),
                             ("UndergroundSlab", areas.floor, 0.0)):
        a = _num(val)
        if a <= 0:
            continue
        out.append(f'<Surface id={quoteattr("srf-" + st.lower())} surfaceType={quoteattr(st)} '
                   f'exposedToSun={quoteattr("true" if st != "UndergroundSlab" else "false")}>')
        out.append(f'<Name>{escape(st)}</Name>')
        out.append('<AdjacentSpaceId spaceIdRef="space-1"/>' if rooms else '')
        out.append(f'<RectangularGeometry><Area>{a:.2f}</Area></RectangularGeometry>')
        if _num(opening) > 0:
            out.append(f'<Opening id={quoteattr("op-" + st.lower())} openingType="OperableWindow">'
                       f'<Name>Windows</Name><RectangularGeometry><Area>{_num(opening):.2f}</Area>'
                       f'</RectangularGeometry></Opening>')
        out.append('</Surface>')
    out.append('</Building>')
    out.append('</Campus>')
    out.append(f'<!-- Simplified export: {len(rooms)} spaces, total {total_area:.1f} m2; envelope from IFC '
               f'geometry (wall {areas.wall:.1f}, window {areas.window:.1f}, roof {areas.roof:.1f}, '
               f'floor {areas.floor:.1f} m2). Not a full surface-boundary thermal model. -->')
    out.append('</gbXML>')
    return "\n".join(x for x in out if x)


def to_gbxml_file(ifc_path: str, project_name: str = "Project") -> str:
    return to_gbxml(open_model(ifc_path), project_name)
