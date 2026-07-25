"""W10-2 — parametric family shapes: build a **real section** for a type, not just a box.

v0.3.662 taught the platform to *read* thirteen parameterised IFC4 profiles (`families._PROFILE_BOUNDS`),
so imported manufacturer content stopped reporting `dims: null`. This is the symmetric half: the
catalog could still only *make* rectangles, so anything authored in-app was a box no matter what it
represented. A family declaring `{"profile": "ishape", "overall_width": 0.2, …}` now gets an actual
I-shape, and everything downstream — take-off bounds, drawings, the type inspector — reads it through
the same path as imported content.

Three ways to make a shape, in the order you should reach for them:

  * **profile + extrude** — a parameterised section swept along Z. Covers structural members, pipes,
    tubes, trim. This is native IFC: the section survives round-trip as parameters, not as a mesh.
  * **profile + revolve** — the same sections spun about an axis, for round goods (a bollard, a tank).
  * **boolean subtraction** — a base shape minus simple cutters, for holes and notches.

Deliberately **not** here: mesh/tessellated shapes. A mesh is where parametric authoring goes to die
— it cannot be resized, scheduled by section, or read back as dimensions — so a family that needs one
belongs in an imported pack (`docs/families.md`), not in the generator.

Pure over an `ifcopenshell.file` — no I/O.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell

# spec key → (IFC entity, required params, optional params). Mirrors the READ table in
# `families._PROFILE_BOUNDS` — anything we can measure, we can also build, and the test asserts that
# symmetry so the two can never drift apart.
PROFILES: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "rectangle":     ("IfcRectangleProfileDef", ("x_dim", "y_dim"), ()),
    "rect_hollow":   ("IfcRectangleHollowProfileDef", ("x_dim", "y_dim", "wall_thickness"),
                      ("inner_fillet_radius", "outer_fillet_radius")),
    "rounded_rect":  ("IfcRoundedRectangleProfileDef", ("x_dim", "y_dim", "rounding_radius"), ()),
    "ishape":        ("IfcIShapeProfileDef", ("overall_width", "overall_depth", "web_thickness",
                                              "flange_thickness"), ("fillet_radius",)),
    # a plate girder / crane rail beam: the flanges differ, so both widths are carried
    "asym_ishape":   ("IfcAsymmetricIShapeProfileDef",
                      ("bottom_flange_width", "overall_depth", "web_thickness",
                       "bottom_flange_thickness", "top_flange_width"),
                      ("top_flange_thickness", "bottom_flange_fillet_radius",
                       "top_flange_fillet_radius")),
    "tshape":        ("IfcTShapeProfileDef", ("depth", "flange_width", "web_thickness",
                                              "flange_thickness"), ()),
    "ushape":        ("IfcUShapeProfileDef", ("depth", "flange_width", "web_thickness",
                                              "flange_thickness"), ()),
    "cshape":        ("IfcCShapeProfileDef", ("depth", "width", "wall_thickness", "girth"), ()),
    "zshape":        ("IfcZShapeProfileDef", ("depth", "flange_width", "web_thickness",
                                              "flange_thickness"), ()),
    "lshape":        ("IfcLShapeProfileDef", ("depth", "thickness"), ("width",)),
    "circle":        ("IfcCircleProfileDef", ("radius",), ()),
    "circle_hollow": ("IfcCircleHollowProfileDef", ("radius", "wall_thickness"), ()),
    "ellipse":       ("IfcEllipseProfileDef", ("semi_axis1", "semi_axis2"), ()),
    "trapezium":     ("IfcTrapeziumProfileDef", ("bottom_x_dim", "top_x_dim", "y_dim"),
                      ("top_x_offset",)),
}

# spec key (snake) → IFC attribute (Pascal). Only the ones whose casing isn't a plain title-case.
_ATTR_OVERRIDE = {
    "x_dim": "XDim", "y_dim": "YDim", "bottom_x_dim": "BottomXDim", "top_x_dim": "TopXDim",
    "top_x_offset": "TopXOffset", "semi_axis1": "SemiAxis1", "semi_axis2": "SemiAxis2",
}

MAX_CUTTERS = 32          # a family is a catalog entry, not a CSG tree; keep booleans bounded


def _attr(key: str) -> str:
    return _ATTR_OVERRIDE.get(key) or "".join(p.title() for p in key.split("_"))


def _pos2d(model: ifcopenshell.file):
    o = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    return model.create_entity("IfcAxis2Placement2D", Location=o)


def _pos3d(model: ifcopenshell.file, origin=(0.0, 0.0, 0.0), axis=None):
    p = model.create_entity("IfcCartesianPoint", Coordinates=tuple(float(x) for x in origin))
    kw: dict[str, Any] = {"Location": p}
    if axis:
        kw["Axis"] = model.create_entity("IfcDirection", DirectionRatios=tuple(float(x) for x in axis))
    return model.create_entity("IfcAxis2Placement3D", **kw)


def build_profile(model: ifcopenshell.file, spec: dict) -> Any:
    """Build a parameterised IFC profile from ``{"profile": <key>, <param>: <metres>, …}``.

    Every parameter must be a positive number: a zero web thickness or a negative radius produces a
    profile that parses, renders as nothing, and silently takes off as zero — so it is refused here
    rather than written.
    """
    key = str(spec.get("profile") or "").strip().lower()
    if key not in PROFILES:
        raise ValueError(f"unknown profile {key!r}; have {', '.join(sorted(PROFILES))}")
    entity, required, optional = PROFILES[key]
    kw: dict[str, Any] = {"ProfileType": "AREA", "Position": _pos2d(model)}
    if spec.get("profile_name"):
        kw["ProfileName"] = str(spec["profile_name"])[:120]
    for group, must in ((required, True), (optional, False)):
        for p in group:
            if p not in spec or spec[p] is None:
                if must:
                    raise ValueError(f"profile {key!r} needs {p!r} (required: {', '.join(required)})")
                continue
            try:
                v = float(spec[p])
            except (TypeError, ValueError):
                raise ValueError(f"{p!r} must be a number, got {spec[p]!r}") from None
            if v <= 0:
                raise ValueError(f"{p!r} must be positive, got {v}")
            kw[_attr(p)] = v
    return model.create_entity(entity, **kw)


def _cutter(model: ifcopenshell.file, c: dict):
    """One boolean cutter: a box or a cylinder, positioned in the type's own coordinate space."""
    kind = str(c.get("shape") or "box").lower()
    at = c.get("at") or (0.0, 0.0, 0.0)
    if kind == "cylinder":
        r, h = float(c.get("radius", 0)), float(c.get("height", 0))
        if r <= 0 or h <= 0:
            raise ValueError("a cylinder cutter needs a positive radius and height")
        axis = c.get("axis") or (0.0, 0.0, 1.0)
        return model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=model.create_entity("IfcCircleProfileDef", ProfileType="AREA",
                                          Position=_pos2d(model), Radius=r),
            Position=_pos3d(model, at, axis),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=h)
    if kind != "box":
        raise ValueError(f"cutter shape must be 'box' or 'cylinder', got {kind!r}")
    w, d, h = (float(c.get(k, 0)) for k in ("width", "depth", "height"))
    if min(w, d, h) <= 0:
        raise ValueError("a box cutter needs positive width, depth and height")
    return model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                      Position=_pos2d(model), XDim=w, YDim=d),
        Position=_pos3d(model, at),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=h)


def build_solid(model: ifcopenshell.file, spec: dict):
    """A swept (and optionally cut) solid from a shape spec.

    ``{"profile": …, "depth": 3.0}``                          → extrusion along +Z
    ``{"profile": …, "revolve_angle": 360, "axis_x": 0.5}``   → revolution about a Z axis offset in X
    ``{…, "holes": [{"shape": "cylinder", "radius": .02, "height": .3, "at": [0,0,0]}]}`` → subtracted

    Returns the solid entity. The result is native IFC geometry — the section stays *parameters*, so
    it survives a round-trip and can still be measured, scheduled and resized. Nothing here produces
    a mesh.
    """
    profile = build_profile(model, spec)
    if spec.get("revolve_angle") is not None:
        ang = float(spec["revolve_angle"])
        if not 0 < ang <= 360:
            raise ValueError(f"revolve_angle must be in (0, 360], got {ang}")
        # revolve about an axis parallel to Z, offset in X — the usual lathe setup for round goods
        ax_x = float(spec.get("axis_x") or 0.0)
        axis = model.create_entity(
            "IfcAxis1Placement",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(ax_x, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)))
        base = model.create_entity("IfcRevolvedAreaSolid", SweptArea=profile,
                                   Position=_pos3d(model), Axis=axis, Angle=ang)
    else:
        # NB the sweep is `length`, never `depth`. `depth` is a *profile* parameter on the T/U/C/Z/L
        # sections (their section depth), so overloading it for the extrusion would silently build a
        # member the length of its own web — geometry that parses and is simply wrong.
        length = float(spec.get("length") or 0.0)
        if length <= 0:
            raise ValueError("an extruded shape needs a positive 'length' (metres) — note the sweep "
                             "is 'length'; 'depth' is a profile parameter on T/U/C/Z/L sections")
        base = model.create_entity(
            "IfcExtrudedAreaSolid", SweptArea=profile, Position=_pos3d(model),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=length)

    holes = list(spec.get("holes") or [])
    if len(holes) > MAX_CUTTERS:
        raise ValueError(f"too many holes ({len(holes)}) — max {MAX_CUTTERS}")
    for h in holes:
        base = model.create_entity("IfcBooleanResult", Operator="DIFFERENCE",
                                   FirstOperand=base, SecondOperand=_cutter(model, h))
    return base


def bounding_dims(spec: dict) -> list[float] | None:
    """The shape's bounding [w, d, h] in metres, computed from the spec — so a caller can record
    nominal dimensions without having to build and then re-measure the geometry. None when the spec
    does not describe a bound we can state honestly (a partial revolve, for instance, sweeps a volume
    this simple formula would overstate)."""
    key = str(spec.get("profile") or "").lower()
    if key not in PROFILES or spec.get("revolve_angle") is not None:
        return None
    def f(k, default=0.0):
        try:
            return float(spec.get(k, default) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    w, d = {
        "rectangle": (f("x_dim"), f("y_dim")),
        "rect_hollow": (f("x_dim"), f("y_dim")),
        "rounded_rect": (f("x_dim"), f("y_dim")),
        "ishape": (f("overall_width"), f("overall_depth")),
        # bounded by the WIDER flange — the same rule the reader uses, so the two agree
        "asym_ishape": (max(f("bottom_flange_width"), f("top_flange_width")), f("overall_depth")),
        "tshape": (f("flange_width"), f("depth")),
        "ushape": (f("flange_width"), f("depth")),
        "cshape": (f("width"), f("depth")),
        "zshape": (f("flange_width"), f("depth")),
        "lshape": (f("width") or f("depth"), f("depth")),
        "circle": (f("radius") * 2, f("radius") * 2),
        "circle_hollow": (f("radius") * 2, f("radius") * 2),
        "ellipse": (f("semi_axis1") * 2, f("semi_axis2") * 2),
        "trapezium": (max(f("bottom_x_dim"), f("top_x_dim")), f("y_dim")),
    }[key]
    h = f("length")                      # the sweep — unambiguous, see build_solid
    if w <= 0 or d <= 0 or h <= 0:
        return None
    return [round(w, 4), round(d, 4), round(h, 4)]


def area(spec: dict) -> float | None:
    """Cross-sectional area (m²) for the profiles where it is exact. None when we would have to
    approximate — an approximate area silently feeds an inaccurate take-off, so it is not offered."""
    key = str(spec.get("profile") or "").lower()
    def f(k):
        try:
            return float(spec.get(k) or 0.0)
        except (TypeError, ValueError):
            return 0.0
    if key == "rectangle":
        return round(f("x_dim") * f("y_dim"), 6)
    if key == "rect_hollow":
        t = f("wall_thickness")
        inner = max(0.0, f("x_dim") - 2 * t) * max(0.0, f("y_dim") - 2 * t)
        return round(f("x_dim") * f("y_dim") - inner, 6)
    if key == "circle":
        return round(math.pi * f("radius") ** 2, 6)
    if key == "circle_hollow":
        return round(math.pi * (f("radius") ** 2 - max(0.0, f("radius") - f("wall_thickness")) ** 2), 6)
    if key == "ellipse":
        return round(math.pi * f("semi_axis1") * f("semi_axis2"), 6)
    if key == "ishape":
        bf, d, tw, tf = f("overall_width"), f("overall_depth"), f("web_thickness"), f("flange_thickness")
        return round(2 * bf * tf + max(0.0, d - 2 * tf) * tw, 6)   # fillets ignored → slight under-read
    return None
