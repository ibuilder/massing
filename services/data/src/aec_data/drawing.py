"""W11 · Track C — construction-drawing generation (C1: plan SVG).

Our production geometry path is web-ifc → Fragments; the ifcopenshell OpenCASCADE engine produces no mesh
in this build, so the HLR section-cut approach isn't available. Instead we take the research-recommended
*optimization*: derive 2D linework **directly from the authored extruded-profile geometry**. Every element
our recipes create is an `IfcExtrudedAreaSolid` (rectangle or arbitrary-closed profile) extruded vertically,
so its plan footprint is exactly the profile polygon transformed by (element placement × solid position) —
computable deterministically, no geometry kernel needed. This covers walls/slabs/columns/roofs/footings/
spaces (the bulk of a plan).

`plan_svg` emits a clean, class-styled SVG plan (one polygon per element, CSS classes per IFC class so a
stylesheet controls poché/linweight) at a given scale — the first slice of the construction-document set.
Later slices add dimensions, tags/keynotes (from the Track-D classification codes), sheets and PDF/DXF.
"""
from __future__ import annotations

import math

import ifcopenshell

# per-IFC-class fill/stroke so the plan reads like a drawing (poché). CSS classes, not inline styles.
_STYLE = """
.sheet{fill:#fff}
.el{stroke:#111;stroke-width:0.4;fill:#e8e8e8}
.IfcWall{fill:#4a4a4a}
.IfcColumn{fill:#2a2a2a}
.IfcSlab{fill:#f2f2f2}
.IfcSpace{fill:#eef4ff;stroke:#9bb7e0;stroke-dasharray:2 2}
.IfcRoof{fill:#f6efe6}
.grid{stroke:#b00;stroke-width:0.2;stroke-dasharray:4 2}
.label{font:2px sans-serif;fill:#333}
""".strip()


def _placement_matrix(el):
    import ifcopenshell.util.placement as up
    import numpy as np

    if el.ObjectPlacement is None:
        return np.eye(4)
    return np.array(up.get_local_placement(el.ObjectPlacement), dtype=float)


def _axis2placement3d(pl):
    """A 4×4 from an IfcAxis2Placement3D (or 2D) — location + optional axis/refdirection."""
    import numpy as np

    m = np.eye(4)
    if pl is None:
        return m
    loc = getattr(pl, "Location", None)
    if loc is not None:
        c = list(loc.Coordinates) + [0.0] * (3 - len(loc.Coordinates))
        m[0:3, 3] = c[:3]
    axis = getattr(pl, "Axis", None)              # Z
    ref = getattr(pl, "RefDirection", None)       # X
    if axis is not None and ref is not None:
        z = np.array(list(axis.DirectionRatios) + [0.0] * (3 - len(axis.DirectionRatios)))[:3]
        x = np.array(list(ref.DirectionRatios) + [0.0] * (3 - len(ref.DirectionRatios)))[:3]
        z = z / (np.linalg.norm(z) or 1.0)
        x = x - z * float(np.dot(x, z))
        x = x / (np.linalg.norm(x) or 1.0)
        y = np.cross(z, x)
        m[0:3, 0], m[0:3, 1], m[0:3, 2] = x, y, z
    elif ref is not None and hasattr(ref, "DirectionRatios") and len(ref.DirectionRatios) == 2:
        d = ref.DirectionRatios
        ang = math.atan2(d[1], d[0])
        c, s = math.cos(ang), math.sin(ang)
        m[0:2, 0], m[0:2, 1] = [c, s], [-s, c]
    return m


def _profile_points(profile):
    """2D points (profile coords) for a rectangle or arbitrary-closed profile, or None."""
    import numpy as np

    if profile is None:
        return None
    if profile.is_a("IfcRectangleProfileDef"):
        x, y = float(profile.XDim) / 2.0, float(profile.YDim) / 2.0
        pts = np.array([[-x, -y], [x, -y], [x, y], [-x, y]])
        pos = getattr(profile, "Position", None)
        return _apply2d(pos, pts)
    if profile.is_a("IfcArbitraryClosedProfileDef"):
        curve = profile.OuterCurve
        if curve is not None and curve.is_a("IfcPolyline"):
            pts = np.array([[float(p.Coordinates[0]), float(p.Coordinates[1])] for p in curve.Points])
            return pts
    return None


def _apply2d(pos, pts):
    import numpy as np

    if pos is None:
        return pts
    m = _axis2placement3d(pos)                    # handles 2D placement too
    out = []
    for px, py in pts:
        v = m @ np.array([px, py, 0.0, 1.0])
        out.append([v[0], v[1]])
    return np.array(out)


def _footprint(el):
    """World-XY footprint polygon [(x,y)…] (file units) for an extruded-profile element, or None."""
    import numpy as np

    rep = getattr(el, "Representation", None)
    if rep is None:
        return None
    solid = None
    for r in rep.Representations:
        for it in (r.Items or []):
            if it.is_a("IfcExtrudedAreaSolid"):
                solid = it
                break
        if solid:
            break
    if solid is None:
        return None
    pts2d = _profile_points(solid.SweptArea)
    if pts2d is None:
        return None
    world = _placement_matrix(el) @ _axis2placement3d(getattr(solid, "Position", None))
    out = []
    for px, py in pts2d:
        v = world @ np.array([px, py, 0.0, 1.0])
        out.append((float(v[0]), float(v[1])))
    return out


# elements worth drawing on a plan, coarsest→finest (drawing order)
_PLAN_CLASSES = ["IfcSlab", "IfcRoof", "IfcSpace", "IfcWall", "IfcColumn", "IfcFooting"]


def plan_svg(model: ifcopenshell.file, storey: str | None = None, scale: int = 100,
             margin_mm: float = 10.0) -> dict:
    """Generate a schematic **plan SVG** from element footprints. `storey` limits to one level (by name);
    `scale` is the drawing scale (1:`scale`). Returns {svg, elements, bounds, scale}. Coordinates are laid
    out in millimetres of paper at the given scale (1 model metre → 1000/scale mm)."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    unit_scale = uu.calculate_unit_scale(model)               # metres per file unit
    paper = (1000.0 / float(scale)) * unit_scale              # file-unit → paper-mm

    shapes: list[tuple[str, list]] = []
    for cls in _PLAN_CLASSES:
        for el in model.by_type(cls):
            if el.is_a("IfcElementType"):
                continue
            if storey:
                st = ue.get_container(el) or ue.get_aggregate(el)
                if st is None or (getattr(st, "Name", None) or "") != storey:
                    continue
            fp = _footprint(el)
            if fp and len(fp) >= 3:
                shapes.append((el.is_a(), fp))

    if not shapes:
        return {"svg": _empty_svg(), "elements": 0, "bounds": None, "scale": scale}

    xs = [p[0] for _, fp in shapes for p in fp]
    ys = [p[1] for _, fp in shapes for p in fp]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = (maxx - minx) * paper + 2 * margin_mm
    h = (maxy - miny) * paper + 2 * margin_mm

    def tx(x):        # world→paper, flip Y (SVG y grows down; plan north is up)
        return round((x - minx) * paper + margin_mm, 2)

    def ty(y):
        return round((maxy - y) * paper + margin_mm, 2)

    polys = []
    for cls, fp in shapes:
        d = " ".join(f"{tx(x)},{ty(y)}" for x, y in fp)
        polys.append(f'<polygon class="el {cls}" points="{d}"/>')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w, 1)}mm" height="{round(h, 1)}mm" '
        f'viewBox="0 0 {round(w, 2)} {round(h, 2)}">'
        f"<style>{_STYLE}</style>"
        f'<rect class="sheet" x="0" y="0" width="{round(w, 2)}" height="{round(h, 2)}"/>'
        + "".join(polys)
        + f'<text class="label" x="{margin_mm}" y="{round(h - 3, 2)}">PLAN 1:{scale}'
        + (f" — {storey}" if storey else "") + "</text>"
        + "</svg>"
    )
    return {"svg": svg, "elements": len(shapes), "scale": scale,
            "bounds": {"min": [minx, miny], "max": [maxx, maxy]}}


def _empty_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="60mm" viewBox="0 0 100 60">'
            f"<style>{_STYLE}</style>"
            '<rect class="sheet" x="0" y="0" width="100" height="60"/>'
            '<text class="label" x="8" y="30">No plan geometry (draw walls/slabs first)</text></svg>')
