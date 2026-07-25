"""W10-2 — parametric family shapes: a family can be a real section, not just a box.

v0.3.662 taught the platform to READ thirteen parameterised profiles. This is the write half, so the
test that matters most is the **symmetry**: anything we can measure we must also be able to build,
or authored content and imported content diverge.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_family_shapes.py"""
import math
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_family_shapes.db"
os.environ["STORAGE_DIR"] = "./test_storage_family_shapes"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_family_shapes.db"):
    os.remove("./test_family_shapes.db")

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402

from aec_data import families  # noqa: E402
from aec_data import family_shapes as fs


def model():
    m = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="Shapes")
    ifcopenshell.api.run("unit.assign_unit", m, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model", context_identifier="Body",
                         target_view="MODEL_VIEW", parent=ctx)
    return m


# ---- SYMMETRY: every profile the reader understands, the writer can build ---------------------------
# families._PROFILE_BOUNDS is the read table; fs.PROFILES is the write table. If one grows without the
# other, authored content stops being measurable — exactly the defect class fixed in v0.3.662.
readable = set(families._PROFILE_BOUNDS)
writable = {ent for ent, _, _ in fs.PROFILES.values()}
assert writable <= readable, f"can build but not measure: {sorted(writable - readable)}"
assert readable <= writable, f"can measure but not build: {sorted(readable - writable)}"

# ---- every profile builds, and the built geometry measures back to the spec -------------------------
SPECS = {
    "rectangle":     {"x_dim": 0.3, "y_dim": 0.5},
    "rect_hollow":   {"x_dim": 0.3, "y_dim": 0.6, "wall_thickness": 0.0127},
    "rounded_rect":  {"x_dim": 0.4, "y_dim": 0.2, "rounding_radius": 0.02},
    "ishape":        {"overall_width": 0.2, "overall_depth": 0.4, "web_thickness": 0.01,
                      "flange_thickness": 0.015},
    "asym_ishape":   {"bottom_flange_width": 0.3, "overall_depth": 0.5, "web_thickness": 0.012,
                      "bottom_flange_thickness": 0.02, "top_flange_width": 0.2,
                      "top_flange_thickness": 0.016},
    "tshape":        {"depth": 0.2, "flange_width": 0.15, "web_thickness": 0.01, "flange_thickness": 0.012},
    "ushape":        {"depth": 0.25, "flange_width": 0.09, "web_thickness": 0.008, "flange_thickness": 0.012},
    "cshape":        {"depth": 0.2, "width": 0.08, "wall_thickness": 0.004, "girth": 0.02},
    "zshape":        {"depth": 0.2, "flange_width": 0.07, "web_thickness": 0.006, "flange_thickness": 0.008},
    "lshape":        {"depth": 0.1, "thickness": 0.01},
    "circle":        {"radius": 0.15},
    "circle_hollow": {"radius": 0.1, "wall_thickness": 0.008},
    "ellipse":       {"semi_axis1": 0.2, "semi_axis2": 0.1},
    "trapezium":     {"bottom_x_dim": 0.4, "top_x_dim": 0.25, "y_dim": 0.3},
}
assert set(SPECS) == set(fs.PROFILES), set(SPECS) ^ set(fs.PROFILES)

# ---- every attribute name the writer generates must EXIST on the IFC4 entity -----------------------
# Hand-mapped snake_case → PascalCase is exactly where a plausible-looking guess slips through:
# `round_radius` looked right but IFC4 calls it `RoundingRadius`, and ifcopenshell only complains at
# create time. Check the whole table against the real schema instead of finding these one at a time.
_schema = ifcopenshell.ifcopenshell_wrapper.schema_by_name("IFC4")
for key, (entity, required, optional) in fs.PROFILES.items():
    real = {a.name() for a in _schema.declaration_by_name(entity).all_attributes()}
    for p in required + optional:
        assert fs._attr(p) in real, (key, p, "->", fs._attr(p), "not on", entity, sorted(real))

for key, params in SPECS.items():
    m = model()
    spec = {"profile": key, "length": 3.0, **params}
    guid = families.create_type(m, "IfcBeamType", f"T-{key}", shape=spec)
    typ = m.by_guid(guid)
    solid = typ.RepresentationMaps[0].MappedRepresentation.Items[0]
    assert solid.is_a("IfcExtrudedAreaSolid"), (key, solid.is_a())
    assert solid.SweptArea.is_a() == fs.PROFILES[key][0], (key, solid.SweptArea.is_a())
    assert abs(solid.Depth - 3.0) < 1e-9, (key, solid.Depth)
    # …and the SAME reader used for imported content measures it
    dims = families.type_detail(m, guid)["dims"]
    assert dims is not None, (key, "authored shape must be measurable")
    assert abs(dims[2] - 3.0) < 1e-4, (key, dims)
    # the spec-only bound agrees with the geometry, so a caller can record dims without building first
    assert fs.bounding_dims(spec) == dims, (key, fs.bounding_dims(spec), dims)

# ---- the depth/length collision that would have shipped silently -----------------------------------
# `depth` is a PROFILE parameter on T/U/C/Z/L. If the sweep were also called `depth`, a 0.2 m-deep
# tee swept 4 m would have been built 0.2 m long — geometry that parses and is simply wrong.
m = model()
g = families.create_type(m, "IfcBeamType", "Tee", shape={"profile": "tshape", "depth": 0.2,
                                                         "flange_width": 0.15, "web_thickness": 0.01,
                                                         "flange_thickness": 0.012, "length": 4.0})
solid = m.by_guid(g).RepresentationMaps[0].MappedRepresentation.Items[0]
assert abs(solid.Depth - 4.0) < 1e-9, solid.Depth            # the sweep
assert abs(solid.SweptArea.Depth - 0.2) < 1e-9, solid.SweptArea.Depth   # the section
# an extrusion without a length is refused, and the message names the trap
try:
    fs.build_solid(model(), {"profile": "tshape", "depth": 0.2, "flange_width": 0.15,
                             "web_thickness": 0.01, "flange_thickness": 0.012})
    raise AssertionError("expected a refusal without 'length'")
except ValueError as e:
    assert "length" in str(e) and "depth" in str(e), str(e)

# ---- degenerate parameters are refused, not written ------------------------------------------------
for bad, why in (({"profile": "ishape", "overall_width": 0.2, "overall_depth": 0.4,
                   "web_thickness": 0, "flange_thickness": 0.015, "length": 1}, "zero thickness"),
                 ({"profile": "circle", "radius": -0.1, "length": 1}, "negative radius"),
                 ({"profile": "circle", "length": 1}, "missing required param"),
                 ({"profile": "nope", "length": 1}, "unknown profile"),
                 ({"profile": "circle", "radius": "big", "length": 1}, "non-numeric")):
    try:
        fs.build_solid(model(), bad)
        raise AssertionError(f"expected refusal: {why}")
    except ValueError:
        pass

# ---- revolve ---------------------------------------------------------------------------------------
m = model()
g = families.create_type(m, "IfcFurnitureType", "Bollard",
                         shape={"profile": "rectangle", "x_dim": 0.1, "y_dim": 0.9,
                                "revolve_angle": 360, "axis_x": 0.05})
rev = m.by_guid(g).RepresentationMaps[0].MappedRepresentation.Items[0]
assert rev.is_a("IfcRevolvedAreaSolid") and abs(rev.Angle - 360) < 1e-9, rev.is_a()
# a partial revolve sweeps a volume the simple bound would overstate, so no bound is offered
assert fs.bounding_dims({"profile": "rectangle", "x_dim": 0.1, "y_dim": 0.9,
                         "revolve_angle": 180}) is None
for ang in (0, -10, 361):
    try:
        fs.build_solid(model(), {"profile": "circle", "radius": 0.1, "revolve_angle": ang})
        raise AssertionError(f"expected refusal for angle {ang}")
    except ValueError:
        pass

# ---- boolean cut-outs ------------------------------------------------------------------------------
m = model()
g = families.create_type(m, "IfcPlateType", "Base plate", shape={
    "profile": "rectangle", "x_dim": 0.4, "y_dim": 0.4, "length": 0.025,
    "holes": [{"shape": "cylinder", "radius": 0.011, "height": 0.05, "at": [0.15, 0.15, -0.01]},
              {"shape": "cylinder", "radius": 0.011, "height": 0.05, "at": [-0.15, 0.15, -0.01]}]})
rep = m.by_guid(g).RepresentationMaps[0].MappedRepresentation
res = rep.Items[0]
assert res.is_a("IfcBooleanResult") and res.Operator == "DIFFERENCE", res.is_a()
# a CSG item must be declared CSG — mislabelling it SweptSolid makes checkers and viewers drop it
assert rep.RepresentationType == "CSG", rep.RepresentationType
assert res.FirstOperand.is_a("IfcBooleanResult"), "two holes should nest two differences"
box = families.create_type(m, "IfcPlateType", "Notched", shape={
    "profile": "rectangle", "x_dim": 0.3, "y_dim": 0.3, "length": 0.02,
    "holes": [{"shape": "box", "width": 0.05, "depth": 0.05, "height": 0.04}]})
assert m.by_guid(box).RepresentationMaps[0].MappedRepresentation.Items[0].is_a("IfcBooleanResult")
# cutters are validated too, and the count is bounded
for bad in ({"shape": "cylinder", "radius": 0, "height": 1}, {"shape": "box", "width": 1, "depth": 1},
            {"shape": "sphere", "radius": 1}):
    try:
        fs.build_solid(model(), {"profile": "circle", "radius": 0.1, "length": 1, "holes": [bad]})
        raise AssertionError(f"expected cutter refusal: {bad}")
    except ValueError:
        pass
try:
    fs.build_solid(model(), {"profile": "circle", "radius": 0.1, "length": 1,
                             "holes": [{"shape": "box", "width": .01, "depth": .01, "height": .01}]
                                      * (fs.MAX_CUTTERS + 1)})
    raise AssertionError("expected a cap on cutter count")
except ValueError as e:
    assert "max" in str(e)

# ---- exact areas only ------------------------------------------------------------------------------
assert fs.area({"profile": "rectangle", "x_dim": 0.3, "y_dim": 0.5}) == 0.15
assert abs(fs.area({"profile": "circle", "radius": 0.1}) - math.pi * 0.01) < 1e-6
# HSS 300x600x12.7: outer 0.18 m2 less the 0.2746x0.5746 inner
hss = fs.area({"profile": "rect_hollow", "x_dim": 0.3, "y_dim": 0.6, "wall_thickness": 0.0127})
assert abs(hss - (0.18 - 0.2746 * 0.5746)) < 1e-6, hss
# an I-shape's area ignores fillets, so it slightly UNDER-reads — never over
ish = fs.area({"profile": "ishape", "overall_width": 0.2, "overall_depth": 0.4,
               "web_thickness": 0.01, "flange_thickness": 0.015})
assert abs(ish - (2 * 0.2 * 0.015 + 0.37 * 0.01)) < 1e-9, ish
# profiles where the area would have to be approximated report None rather than a plausible guess
for k in ("tshape", "ushape", "cshape", "zshape", "lshape", "trapezium", "rounded_rect"):
    assert fs.area({"profile": k, **SPECS[k]}) is None, k

# ---- shape wins over dims, and the box path is untouched -------------------------------------------
m = model()
both = families.create_type(m, "IfcBeamType", "Both", dims=[1, 1, 1],
                            shape={"profile": "circle", "radius": 0.05, "length": 2.0})
assert m.by_guid(both).RepresentationMaps[0].MappedRepresentation.Items[0].SweptArea.is_a() \
    == "IfcCircleProfileDef"
plain = families.create_type(m, "IfcFurnitureType", "Desk", dims=[1.4, 0.7, 0.75])
assert families.type_detail(m, plain)["dims"] == [1.4, 0.7, 0.75]

if os.path.exists("./test_family_shapes.db"):
    os.remove("./test_family_shapes.db")

print(f"W10-2 OK - a family can now be a real section, not a box: all {len(fs.PROFILES)} parameterised "
      "profiles build as native IFC (the section stays PARAMETERS, so it round-trips and measures "
      "instead of degrading to a mesh), and the write table is asserted symmetric with the v0.3.662 "
      "read table so authored and imported content can never diverge. Caught in build: `depth` is a "
      "PROFILE parameter on T/U/C/Z/L, so the sweep is `length` — overloading it would have built a "
      "0.2 m-deep tee 0.2 m long, geometry that parses and is simply wrong. Degenerate parameters "
      "(zero web, negative radius, missing, non-numeric, unknown profile) are refused rather than "
      "written as shapes that render as nothing and take off as zero; revolve rejects angles outside "
      "(0,360] and offers no bounding box for a partial sweep it would overstate; boolean cut-outs "
      "nest correctly, declare RepresentationType CSG (mislabelling it SweptSolid makes viewers drop "
      "the geometry) and cap their cutter count; and areas are given ONLY where exact — the shapes "
      "needing approximation return None instead of a plausible guess.")
