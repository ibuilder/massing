"""R21-DIM-COMPONENT — a section carries the layer build-up of every assembly it cuts, and says so
when the model's stated assembly disagrees with the model's own geometry.

The floor-to-floor chain answers "how high". A fabricator asks "made of what, how thick" — that is the
`IfcMaterialLayerSet`, and a section that shows a single 300 mm overall thickness cannot be built from.

The part worth testing hardest is not the drawing, it is the **disagreement**. `declared_m` (the sum of
the layers the model states) and `measured_m` (the element's own geometry) are two different claims.
When a layer set summing to 300 mm sits on a wall modelled at 250 mm, the drawing and the specification
disagree and there is no basis for choosing between them — so the assembly is FLAGGED rather than
reconciled. Silently printing the declared total is how a fabricator ends up building to a number
nobody checked.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_dim_component.py
"""
import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_dim_component.db")
if os.path.exists("./test_dim_component.db"):
    os.remove("./test_dim_component.db")

import ifcopenshell  # noqa: E402
import ifcopenshell.api as A  # noqa: E402

from aec_data import drawings  # noqa: E402

# --- fixture: built here, not read from samples/ ---------------------------------------------------
# `samples/*.ifc` are gitignored, and a test that reads one turns main red on a fresh clone.
f = ifcopenshell.file(schema="IFC4")
proj = A.run("root.create_entity", f, ifc_class="IfcProject", name="DimComp")
A.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
ctx = A.run("context.add_context", f, context_type="Model")
site = A.run("root.create_entity", f, ifc_class="IfcSite", name="S")
bld = A.run("root.create_entity", f, ifc_class="IfcBuilding", name="B")
st = A.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="L1")
A.run("aggregate.assign_object", f, products=[site], relating_object=proj)
A.run("aggregate.assign_object", f, products=[bld], relating_object=site)
A.run("aggregate.assign_object", f, products=[st], relating_object=bld)


def layerset(name, spec):
    ls = f.create_entity("IfcMaterialLayerSet", LayerSetName=name)
    ls.MaterialLayers = [f.create_entity("IfcMaterialLayer",
                                         Material=f.create_entity("IfcMaterial", Name=m),
                                         LayerThickness=t) for m, t in spec]
    return ls


def wall(name, x, thick, ls=None):
    w = A.run("root.create_entity", f, ifc_class="IfcWall", name=name)
    A.run("spatial.assign_container", f, products=[w], relating_structure=st)
    prof = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=6.0, YDim=thick)
    solid = f.create_entity(
        "IfcExtrudedAreaSolid", SweptArea=prof,
        Position=f.create_entity("IfcAxis2Placement3D",
                                 Location=f.create_entity("IfcCartesianPoint", Coordinates=(x, 0., 0.))),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.)), Depth=3.0)
    w.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[
        f.create_entity("IfcShapeRepresentation", ContextOfItems=ctx, RepresentationIdentifier="Body",
                        RepresentationType="SweptSolid", Items=[solid])])
    if ls is not None:
        f.create_entity("IfcRelAssociatesMaterial", GlobalId=ifcopenshell.guid.new(),
                        RelatedObjects=[w], RelatingMaterial=ls)
    return w


wall("EXT-A", 0.0, 0.300, layerset("EXT-300", [("Brick", 0.100), ("Cavity", 0.050),
                                               ("Insul", 0.100), ("Board", 0.050)]))
wall("EXT-B", 8.0, 0.250, layerset("EXT-MISMATCH", [("Brick", 0.100), ("Insul", 0.150),
                                                    ("Board", 0.050)]))
wall("PLAIN", 16.0, 0.200)                       # no layer set at all — must be ABSENT, not invented
path = str(Path(tempfile.gettempdir()) / "dim_component.ifc")
f.write(path)
model = ifcopenshell.open(path)

# --- the layer breakdown reaches the section -------------------------------------------------------
comps = drawings.component_dims_section(model, "y", 0.0)
by = {c["name"]: c for c in comps}
assert set(by) == {"EXT-300", "EXT-MISMATCH"}, sorted(by)
assert len(by["EXT-300"]["layers"]) == 4, by["EXT-300"]["layers"]
assert [ly["material"] for ly in by["EXT-300"]["layers"]] == ["Brick", "Cavity", "Insul", "Board"]

# An element with NO layer set is absent rather than fabricated. This is the assertion that keeps the
# feature honest: the alternative — emitting a single-layer assembly from the overall thickness — would
# look like data and carry no information.
assert "PLAIN" not in " ".join(by), by

# --- declared vs measured are TWO claims, and disagreement is reported, never reconciled ------------
ok = by["EXT-300"]
assert ok["declared_m"] == 0.3 and ok["measured_m"] == 0.3, ok
assert ok["agrees"] is True and ok["delta_m"] == 0.0, ok

bad = by["EXT-MISMATCH"]
assert bad["declared_m"] == 0.3, bad          # the layer set says 300
assert bad["measured_m"] == 0.25, bad         # the geometry says 250
assert bad["agrees"] is False, bad
assert bad["delta_m"] == -0.05, bad
# Neither number is silently preferred. Both survive to the caller, because choosing one would be
# inventing agreement that the model does not have.
assert bad["declared_m"] != bad["measured_m"]

# --- grouped by layer SET, not by element ----------------------------------------------------------
# A wall assembly repeated across storeys is ONE dimension string, for the same reason keynotes group.
wall("EXT-A2", 24.0, 0.300, layerset("EXT-300-COPY", [("Brick", 0.300)]))
p2 = str(Path(tempfile.gettempdir()) / "dim_component2.ifc")
f.write(p2)
m2 = ifcopenshell.open(p2)
assert len(drawings.component_dims_section(m2, "y", 0.0)) == 3, "a distinct layer set is a distinct row"

# --- a cut that misses everything reports nothing, rather than every assembly in the model ----------
assert drawings.component_dims_section(model, "y", 999.0) == [], "the cut misses all of it"

# --- it renders, and the disagreement is VISIBLE on the sheet --------------------------------------
svg = drawings.section_svg(model, "y", 0.0, title="SECTION A-A")
assert "ASSEMBLIES" in svg and "EXT-300" in svg and "EXT-MISMATCH" in svg
assert "Brick" in svg and "Insul" in svg
mm = re.search(r"! modelled (\d+) \(([-+]\d+)\)", svg)
assert mm and mm.group(1) == "250" and mm.group(2) == "-50", svg[-800:]
# ...as a NUMBER a reader can act on. A bare warning glyph would say something is wrong without saying
# what, which is the shape of a finding nobody can chase.

# `components=False` returns the un-annotated cut for a CAD hand-off, and reclaims the column.
bare = drawings.section_svg(model, "y", 0.0, title="X", components=False)
assert "ASSEMBLIES" not in bare
# The column is taken out of the DRAWING area, not bolted onto the sheet — a section that silently grew
# wider would no longer fit the titleblock it was laid out for.
assert re.search(r'width="(\d+)"', svg).group(1) == re.search(r'width="(\d+)"', bare).group(1)

# --- a layer with no stated thickness makes the SUM unknowable, and it says so ----------------------
g = ifcopenshell.file(schema="IFC4")
A.run("root.create_entity", g, ifc_class="IfcProject", name="P")
A.run("unit.assign_unit", g, length={"is_metric": True, "raw": "METERS"})
gctx = A.run("context.add_context", g, context_type="Model")
gst = A.run("root.create_entity", g, ifc_class="IfcBuildingStorey", name="L")
gls = g.create_entity("IfcMaterialLayerSet", LayerSetName="PARTIAL")
gls.MaterialLayers = [
    g.create_entity("IfcMaterialLayer", Material=g.create_entity("IfcMaterial", Name="Brick"),
                    LayerThickness=0.1),
    g.create_entity("IfcMaterialLayer", Material=g.create_entity("IfcMaterial", Name="Unknown")),
]
gw = A.run("root.create_entity", g, ifc_class="IfcWall", name="W")
A.run("spatial.assign_container", g, products=[gw], relating_structure=gst)
gp = g.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=6.0, YDim=0.3)
gs = g.create_entity(
    "IfcExtrudedAreaSolid", SweptArea=gp,
    Position=g.create_entity("IfcAxis2Placement3D",
                             Location=g.create_entity("IfcCartesianPoint", Coordinates=(0., 0., 0.))),
    ExtrudedDirection=g.create_entity("IfcDirection", DirectionRatios=(0., 0., 1.)), Depth=3.0)
gw.Representation = g.create_entity("IfcProductDefinitionShape", Representations=[
    g.create_entity("IfcShapeRepresentation", ContextOfItems=gctx, RepresentationIdentifier="Body",
                    RepresentationType="SweptSolid", Items=[gs])])
g.create_entity("IfcRelAssociatesMaterial", GlobalId=ifcopenshell.guid.new(),
                RelatedObjects=[gw], RelatingMaterial=gls)
p3 = str(Path(tempfile.gettempdir()) / "dim_component3.ifc")
g.write(p3)
partial = drawings.component_dims_section(ifcopenshell.open(p3), "y", 0.0)
assert len(partial) == 1, partial
# Summing only the layers that HAPPEN to state a thickness would under-report the assembly and look
# authoritative doing it. An unknowable total is None, and `agrees` cannot be computed from it.
assert partial[0]["declared_m"] is None, partial[0]
assert partial[0]["agrees"] is None and partial[0]["delta_m"] is None, partial[0]

print("R21-DIM-COMPONENT OK - a section now carries the LAYER BUILD-UP of every assembly it cuts "
      "(brick/cavity/insulation/board with each thickness), not just one overall figure a fabricator "
      "cannot build from, drawn in proportion so a 12mm board reads as the sliver it is. The load- "
      "bearing part is the disagreement: `declared_m` (what the layer set states) and `measured_m` "
      "(what the geometry is) are two different claims, and a layer set summing to 300mm on a wall "
      "modelled at 250mm is FLAGGED on the sheet as `! modelled 250 (-50)` rather than reconciled - "
      "there is no basis for preferring either, and printing the declared total silently is how a "
      "trade builds to a number nobody checked. An element with no layer set is absent rather than "
      "fabricated from its overall thickness, a layer with no stated thickness makes the total None "
      "instead of a confident under-count, and the column is taken out of the drawing area so a "
      "section never silently outgrows its titleblock.")
