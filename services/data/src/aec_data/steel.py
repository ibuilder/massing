"""Structural steel sections (P4) — parametric AISC W-shapes as native IFC ``IfcIShapeProfileDef``.

openBIM authors standard steel by feeding published section *dimensions* into IFC's parametric profile
entity — no imported geometry. The dimensions below are **facts** re-keyed from the AISC Shapes Database
(imperial, inches); we do not redistribute AISC's file. A column/beam then extrudes this profile along
its axis (see ``edit.add_steel_column`` / ``add_steel_beam``). Attribution: docs/ATTRIBUTIONS.md.
"""
from __future__ import annotations

from typing import Any

_IN = 0.0254   # inch -> metre

# W-shape dimensions in INCHES: d = overall depth, bf = flange width, tf = flange thickness,
# tw = web thickness (AISC Shapes Database v16 nominal values). Common gravity/lateral members.
W_SHAPES: dict[str, dict[str, float]] = {
    "W8x31":  {"d": 8.00,  "bf": 8.000, "tf": 0.435, "tw": 0.285},
    "W10x33": {"d": 9.73,  "bf": 7.960, "tf": 0.435, "tw": 0.290},
    "W12x26": {"d": 12.22, "bf": 6.490, "tf": 0.380, "tw": 0.230},
    "W14x30": {"d": 13.84, "bf": 6.730, "tf": 0.385, "tw": 0.270},
    "W16x40": {"d": 16.01, "bf": 6.995, "tf": 0.505, "tw": 0.305},
    "W18x50": {"d": 17.99, "bf": 7.495, "tf": 0.570, "tw": 0.355},
    "W21x62": {"d": 20.99, "bf": 8.240, "tf": 0.615, "tw": 0.400},
    "W24x76": {"d": 23.92, "bf": 8.990, "tf": 0.680, "tw": 0.440},
}

# Standard US reinforcing bar sizes: designation -> nominal diameter (metres).
REBAR_SIZES: dict[str, float] = {
    "#3": 0.375 * _IN, "#4": 0.500 * _IN, "#5": 0.625 * _IN, "#6": 0.750 * _IN,
    "#7": 0.875 * _IN, "#8": 1.000 * _IN, "#9": 1.128 * _IN, "#10": 1.270 * _IN, "#11": 1.410 * _IN,
}


def section_dims_m(name: str) -> dict[str, float]:
    """W-shape dimensions in METRES; falls back to W12x26 for an unknown name."""
    s = W_SHAPES.get(name) or W_SHAPES["W12x26"]
    return {k: v * _IN for k, v in s.items()}


def i_profile(model, name: str):
    """A native IfcIShapeProfileDef for a W-shape (with a Position — web-ifc needs it)."""
    d = section_dims_m(name)
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    return model.create_entity(
        "IfcIShapeProfileDef", ProfileType="AREA", ProfileName=name, Position=pos,
        OverallWidth=d["bf"], OverallDepth=d["d"], WebThickness=d["tw"], FlangeThickness=d["tf"])


def rebar_diameter(size: str) -> float:
    """Nominal bar diameter (metres) for a size designation like '#5'; default #5."""
    return REBAR_SIZES.get(size, REBAR_SIZES["#5"])


def catalog() -> dict[str, Any]:
    """Picker data: the W-shapes (name + nominal depth) + rebar sizes (designation + diameter mm)."""
    return {
        "w_shapes": [{"section": k, "depth_in": v["d"], "flange_in": v["bf"]} for k, v in W_SHAPES.items()],
        "rebar_sizes": [{"size": k, "diameter_mm": round(v * 1000, 1)} for k, v in REBAR_SIZES.items()],
    }
