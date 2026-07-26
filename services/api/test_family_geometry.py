"""FAMILY-GEOM — the four defects that gated real (non-box) family content, plus the external
family-pack shelf.

Everything below reproduces against the pre-fix code; each block says what went wrong and why it
mattered. The through-line: a type whose geometry is a real section must read its size honestly,
must not be silently reshaped into a box, and must never keep a catalog name that no longer
describes it.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_family_geometry.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_family_geometry.db"
os.environ["STORAGE_DIR"] = "./test_storage_famgeom"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_family_geometry.db",):
    if os.path.exists(f):
        os.remove(f)

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402

from aec_data import families, family_packs  # noqa: E402


def _model(unit="METERS", metric=True):
    m = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="Lib")
    ifcopenshell.api.run("unit.assign_unit", m, length={"is_metric": metric, "raw": unit})
    ctx = ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model", context_identifier="Body",
                         target_view="MODEL_VIEW", parent=ctx)
    return m


def _body(m):
    return next(c for c in m.by_type("IfcGeometricRepresentationSubContext")
                if c.ContextIdentifier == "Body")


def _swept(m, profile, depth, ifc_class="IfcColumnType", name="T"):
    typ = ifcopenshell.api.run("root.create_entity", m, ifc_class=ifc_class, name=name)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", m, context=_body(m),
                               profile=profile, depth=depth)
    ifcopenshell.api.run("geometry.assign_representation", m, product=typ, representation=rep)
    return typ


# ============ DEFECT 1 — real sections read as sizeless ==============================================
# _type_dims only understood IfcRectangleProfileDef, so EVERY imported W-shape, tube and pipe
# reported dims: null — nothing downstream could schedule or take off imported content.
m = _model()
w14 = _swept(m, m.create_entity("IfcIShapeProfileDef", ProfileType="AREA", ProfileName="W14X90",
                                OverallWidth=0.3683, OverallDepth=0.3556, WebThickness=0.011176,
                                FlangeThickness=0.018034, FilletRadius=0.01524), 3.6576, name="W14X90")
assert families.type_detail(m, w14.GlobalId)["dims"] == [0.3683, 0.3556, 3.6576], \
    families.type_detail(m, w14.GlobalId)

# every parameterised profile the table covers is measurable, and the bound is the OUTER extent
cases = [
    ("IfcCircleProfileDef", {"Radius": 0.15}, (0.3, 0.3)),
    ("IfcCircleHollowProfileDef", {"Radius": 0.1, "WallThickness": 0.008}, (0.2, 0.2)),
    ("IfcRectangleHollowProfileDef", {"XDim": 0.3, "YDim": 0.6, "WallThickness": 0.0127}, (0.3, 0.6)),
    ("IfcEllipseProfileDef", {"SemiAxis1": 0.2, "SemiAxis2": 0.1}, (0.4, 0.2)),
    ("IfcTShapeProfileDef", {"Depth": 0.2, "FlangeWidth": 0.15, "WebThickness": 0.01,
                             "FlangeThickness": 0.012}, (0.15, 0.2)),
    ("IfcUShapeProfileDef", {"Depth": 0.25, "FlangeWidth": 0.09, "WebThickness": 0.008,
                             "FlangeThickness": 0.012}, (0.09, 0.25)),
    ("IfcCShapeProfileDef", {"Depth": 0.2, "Width": 0.08, "WallThickness": 0.004, "Girth": 0.02}, (0.08, 0.2)),
    ("IfcZShapeProfileDef", {"Depth": 0.2, "FlangeWidth": 0.07, "WebThickness": 0.006,
                             "FlangeThickness": 0.008}, (0.07, 0.2)),
    ("IfcTrapeziumProfileDef", {"BottomXDim": 0.4, "TopXDim": 0.25, "YDim": 0.3}, (0.4, 0.3)),
]
for cls, attrs, expect in cases:
    mm = _model()
    t = _swept(mm, mm.create_entity(cls, ProfileType="AREA", **attrs), 2.0, name=cls)
    got = families.type_detail(mm, t.GlobalId)["dims"]
    assert got == [round(expect[0], 4), round(expect[1], 4), 2.0], (cls, got, expect)

# an equal-leg angle omits Width entirely — it must fall back to Depth, not read as sizeless
ml = _model()
tl = _swept(ml, ml.create_entity("IfcLShapeProfileDef", ProfileType="AREA", Depth=0.1,
                                 Thickness=0.01), 2.0, name="L4X4")
assert families.type_detail(ml, tl.GlobalId)["dims"] == [0.1, 0.1, 2.0]

# arbitrary swept profiles (much third-party content) measure from the polyline bounding box
ma = _model()
pts = ma.create_entity("IfcPolyline", Points=[
    ma.create_entity("IfcCartesianPoint", Coordinates=(x, y))
    for x, y in ((0.0, 0.0), (0.8, 0.0), (0.8, 0.25), (0.0, 0.25), (0.0, 0.0))])
ta = _swept(ma, ma.create_entity("IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=pts),
            1.5, name="Arb")
assert families.type_detail(ma, ta.GlobalId)["dims"] == [0.8, 0.25, 1.5]

# a profile kind we genuinely cannot measure still reports null rather than a guess
mu = _model()
tu = _swept(mu, mu.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=0.1), 1.0, name="U")
tu.RepresentationMaps[0].MappedRepresentation.Items[0].SweptArea = mu.create_entity(
    "IfcArbitraryClosedProfileDef", ProfileType="AREA",
    OuterCurve=mu.create_entity("IfcPolyline", Points=[
        mu.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))]))   # 1 point → no extent
assert families.type_detail(mu, tu.GlobalId)["dims"] is None

# ============ DEFECT 2 — resizing APPENDED a box instead of replacing ================================
# geometry.assign_representation appends. A resize on non-box geometry left the original solid in
# place and drew a box through it: the type rendered both, and every take-off counted both.
m2 = _model()
t2 = _swept(m2, m2.create_entity("IfcIShapeProfileDef", ProfileType="AREA", OverallWidth=0.3,
                                 OverallDepth=0.3, WebThickness=0.01, FlangeThickness=0.015), 3.0)
assert len(t2.RepresentationMaps) == 1
res = families.edit_type_params(m2, t2.GlobalId, dims=[0.4, 0.4, 3.0])
assert len(t2.RepresentationMaps) == 1, list(t2.RepresentationMaps)
assert t2.RepresentationMaps[0].MappedRepresentation.Items[0].SweptArea.is_a() == "IfcRectangleProfileDef"
# and it SAYS it swapped a real section for a box rather than letting that pass silently
assert res["geometry_replaced"] == ["IfcIShapeProfileDef"], res
assert families.type_detail(m2, t2.GlobalId)["dims"] == [0.4, 0.4, 3.0]

# ============ DEFECT 3 — a hollow section was silently resized as a box ==============================
# is_a("IfcRectangleProfileDef") is TRUE for IfcRectangleHollowProfileDef, so the box path grabbed
# HSS tubes: it rewrote the outer dims, kept the wall thickness, and left the type carrying a
# catalog name like "HSS24X12X3/4" that no longer described it — a section in no steel catalog,
# presented as a standard one. A null is honest; that was a plausible wrong answer.
m3 = _model()
hss = _swept(m3, m3.create_entity("IfcRectangleHollowProfileDef", ProfileType="AREA", XDim=0.3048,
                                  YDim=0.6096, WallThickness=0.0177), 3.6576, name="HSS24X12X3/4")
prof_before = hss.RepresentationMaps[0].MappedRepresentation.Items[0].SweptArea
assert families._rep_solid(hss) is None, "a hollow section must not present as an editable box"
assert families._rep_solid(hss, box_only=False) is not None, "…but it must still be readable"
r3 = families.edit_type_params(m3, hss.GlobalId, dims=[0.5, 0.5, 3.0])
assert r3["geometry_replaced"] == ["IfcRectangleHollowProfileDef"], r3
assert prof_before.WallThickness == 0.0177          # the original profile was NOT mutated in place
kinds = [rm.MappedRepresentation.Items[0].SweptArea.is_a() for rm in hss.RepresentationMaps]
assert kinds == ["IfcRectangleProfileDef"], kinds

# a plain rectangle IS still resized in place — that is the GUID-stable propagation path
m4 = _model()
g = families.create_type(m4, "IfcFurnitureType", "Desk", dims=[1.4, 0.7, 0.75])
# NB compare STEP ids, not object identity — ifcopenshell rebuilds the entity_instance wrapper on
# every access, so `is` would be False even for the very same entity.
solid_before = families._rep_solid(m4.by_guid(g)).id()
r4 = families.edit_type_params(m4, g, dims=[1.6, 0.8, 0.75])
assert families.type_detail(m4, g)["dims"] == [1.6, 0.8, 0.75]
assert len(m4.by_guid(g).RepresentationMaps) == 1
assert families._rep_solid(m4.by_guid(g)).id() == solid_before, \
    "box resize must mutate the SAME solid in place — that is what propagates to occurrences"
assert "geometry_replaced" not in r4, r4          # nothing was discarded, so nothing is reported

# ============ DEFECT 4 — variant names were hardcoded metric =========================================
# The type name is what appears in schedules, the picker and drawings. "0.9144×0.0508×2.1336 m" is
# not a size anyone can act on in an imperial project.
imperial = _model(unit="FEET", metric=False)
assert families._variant_name("Door", [0.9144, 0.0508, 2.1336], imperial) == \
    "Door 3'-0\" × 0'-2\" × 7'-0\"", families._variant_name("Door", [0.9144, 0.0508, 2.1336], imperial)
# fractional inches reduce properly (0.10478 m = 4 1/8")
assert families._feet_inches(0.10478) == "0'-4 1/8\"", families._feet_inches(0.10478)
assert families._feet_inches(0.0254) == "0'-1\""
assert families._feet_inches(3.6576) == "12'-0\""
mmm = _model(unit="MILLIMETERS")
assert families._variant_name("Door", [0.9144, 0.0508, 2.1336], mmm) == "Door 914.4×50.8×2133.6 mm"
assert families._variant_name("Desk", [1.4, 0.7, 0.75], _model()) == "Desk 1.4×0.7×0.75 m"
assert families._variant_name("Desk", [1.4, 0.7, 0.75], None) == "Desk 1.4×0.7×0.75 m"  # no model
# ensure_type names its variant in the project's units
d_imp = families.ensure_type(imperial, "desk", dims=[1.4, 0.7, 0.75])
assert "'-" in (d_imp.Name or ""), d_imp.Name

# ============ the external pack shelf ===============================================================
import json  # noqa: E402
import shutil  # noqa: E402

# Use a PRIVATE shelf, not the shipped one. This test writes a pack and rewrites manifest.json;
# doing that in `services/data/families/external/` races any other test that reads the real shelf
# under the parallel runner, and the loser sees a half-written manifest.
os.environ["AEC_FAMILY_SHELF"] = os.path.abspath("./_shelf_famgeom")
ext = family_packs.external_dir()
ext.mkdir(parents=True, exist_ok=True)
PACK = ext / "_test_pack_famgeom.ifc"
MANIFEST = ext / "manifest.json"

# a small real pack: two types with genuine section geometry
pm = _model()
_swept(pm, pm.create_entity("IfcIShapeProfileDef", ProfileType="AREA", OverallWidth=0.2,
                            OverallDepth=0.4, WebThickness=0.01, FlangeThickness=0.015),
       4.0, ifc_class="IfcBeamType", name="Test W-Beam")
_swept(pm, pm.create_entity("IfcCircleHollowProfileDef", ProfileType="AREA", Radius=0.05,
                            WallThickness=0.005), 3.0, ifc_class="IfcColumnType", name="Test Pipe")
pm.write(str(PACK))

try:
    MANIFEST.write_text(json.dumps({"packs": [
        {"file": PACK.name, "discipline": "test-structural", "families": 2, "types": 2,
         "licence": "CC0-1.0", "tiers": ["L300"]}]}), encoding="utf-8")

    shelf = family_packs.list_packs()
    entry = next(p for p in shelf["packs"] if p["name"] == PACK.name)
    assert entry["described"] is True and entry["discipline"] == "test-structural", entry
    assert entry["licence"] == "CC0-1.0" and entry["types"] == 2, entry
    assert shelf["manifest"] is True and shelf["totals"]["packs"] >= 1
    # NB assert about THIS pack, never shelf-wide totals: the shelf is a real directory an operator
    # installs into (40 generated packs live there in a working checkout), so any absolute count here
    # would be asserting on the environment rather than on behaviour.
    # Content you redistribute needs a licence you can point at, so a pack declaring none is COUNTED
    # rather than shown as a blank column nobody notices — checked as a delta.
    before = family_packs.list_packs()["totals"]["unlicensed"]
    MANIFEST.write_text(json.dumps({"packs": [{"file": PACK.name, "discipline": "test-structural",
                                               "types": 2}]}), encoding="utf-8")
    after = family_packs.list_packs()["totals"]
    assert after["unlicensed"] == before + 1, (before, after["unlicensed"])
    assert not next(p for p in family_packs.list_packs()["packs"]
                    if p["name"] == PACK.name).get("licence")
    # ---- a licence declared for the LIBRARY covers the packs in it ---------------------------------
    # A library states its terms once at the top; repeating them on every row is the exception, not
    # the rule. Reading only the per-pack key made 57 packs that were licensed the whole time report
    # as `unlicensed` — a shape mismatch presented as a compliance problem. `licence_source` keeps the
    # two claims distinguishable, because "this pack says CC0" and "the library it came from says CC0"
    # are different assurances even when the string matches.
    MANIFEST.write_text(json.dumps({
        "library": "test-lib", "version": "9.9.9",
        "licensing": {"content": "CC0-1.0", "code": "MIT",
                      "attribution": "test-lib", "url": "https://example.invalid/LICENSE",
                      "notice": "https://example.invalid/NOTICE"},
        "packs": [{"file": PACK.name, "discipline": "test-structural", "types": 2}],
    }), encoding="utf-8")
    inherited = next(p for p in family_packs.list_packs()["packs"] if p["name"] == PACK.name)
    assert inherited["licence"] == "CC0-1.0", inherited
    assert inherited["licence_source"] == "library", inherited
    assert inherited["attribution"] == "test-lib" and inherited["licence_url"], inherited
    assert family_packs.list_packs()["totals"]["unlicensed"] == before, "inheritance clears the count"
    # the terms follow the content into the audit trail — reconstructing them after an import means
    # re-reading a manifest that may since have moved on
    assert family_packs.read(PACK.name)[1]["licence"] == "CC0-1.0"
    assert family_packs.read(PACK.name)[1]["code_licence"] == "MIT"

    # a pack's OWN claim wins over the library's, and is labelled as its own
    MANIFEST.write_text(json.dumps({
        "licensing": {"content": "CC0-1.0"},
        "packs": [{"file": PACK.name, "types": 2, "license": "Apache-2.0"}],
    }), encoding="utf-8")
    own = next(p for p in family_packs.list_packs()["packs"] if p["name"] == PACK.name)
    assert own["licence"] == "Apache-2.0" and own["licence_source"] == "pack", own

    # SPDX gets written singular or plural; a LIST is alternatives, so keep all of them. Collapsing
    # to the first would quietly drop terms a redistributor is entitled to choose.
    MANIFEST.write_text(json.dumps({"packs": [
        {"file": PACK.name, "types": 2, "licenses": ["CC0-1.0", "MIT", "CC0-1.0"]}]}), encoding="utf-8")
    plural = next(p for p in family_packs.list_packs()["packs"] if p["name"] == PACK.name)
    assert plural["licence"] == "CC0-1.0 OR MIT", plural           # deduped, order preserved
    # an empty list is not a licence — it must not read as one
    MANIFEST.write_text(json.dumps({"packs": [
        {"file": PACK.name, "types": 2, "licenses": [], "license": "  "}]}), encoding="utf-8")
    assert family_packs.list_packs()["totals"]["unlicensed"] == before + 1

    MANIFEST.write_text(json.dumps({"packs": [
        {"file": PACK.name, "discipline": "test-structural", "families": 2, "types": 2,
         "licence": "CC0-1.0", "tiers": ["L300"]}]}), encoding="utf-8")

    data, prov = family_packs.read(PACK.name)
    assert len(data) == PACK.stat().st_size and len(prov["sha256"]) == 64
    assert prov["declared_types"] == 2 and prov["described"] is True

    # a pack the manifest does not describe is still listed and importable — but says nothing is claimed
    UNDESC = ext / "_test_undescribed_famgeom.ifc"
    shutil.copyfile(PACK, UNDESC)
    try:
        u = next(p for p in family_packs.list_packs()["packs"] if p["name"] == UNDESC.name)
        assert u["described"] is False and "discipline" not in u, u
    finally:
        UNDESC.unlink()

    # resolve() takes a NAME, never a path — traversal, separators and non-ifc are all refused
    for bad in ("../../../etc/passwd", "sub/dir.ifc", r"..\..\secret.ifc", "notes.txt",
                "", "   ", ".hidden.ifc", "nope.ifc"):
        try:
            family_packs.resolve(bad)
            raise AssertionError(f"resolve accepted {bad!r}")
        except ValueError:
            pass

    # ---- the route: import a shelf pack WITHOUT a round-trip upload -------------------------------
    from fastapi.testclient import TestClient  # noqa: E402

    from aec_api.db import SessionLocal  # noqa: E402
    from aec_api.main import app  # noqa: E402
    from aec_api.models import Project  # noqa: E402
    from aec_data import massing  # noqa: E402

    HOST = os.path.abspath("./_famgeom_host.ifc")
    massing.generate_blank_ifc(HOST, name="FamHost", storeys=1)

    with TestClient(app) as c:
        pid = c.post("/projects", json={"name": "FamGeom"}).json()["id"]
        with SessionLocal() as db:
            db.get(Project, pid).source_ifc = HOST
            db.commit()

        lib = c.get("/families/library").json()
        assert "shelf" in lib and any(p["name"] == PACK.name for p in lib["shelf"]["packs"])
        assert any(p["name"] == PACK.name for p in lib["external"])      # legacy shape preserved

        r = c.post(f"/projects/{pid}/families/import-pack", json={"pack": PACK.name})
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["count"] == 2 and j["sha256"] == prov["sha256"], j
        assert j["discipline"] == "test-structural"
        assert "note" not in j, j            # manifest declared 2, 2 arrived → nothing to flag

        # the imported types carry READABLE dims — the whole point of the geometry fixes
        with SessionLocal() as db:
            src = db.get(Project, pid).source_ifc
        got = ifcopenshell.open(src)
        beam = next(t for t in got.by_type("IfcTypeProduct") if (t.Name or "") == "Test W-Beam")
        assert families.type_detail(got, beam.GlobalId)["dims"] == [0.2, 0.4, 4.0]

        # an unknown pack 404s instead of 500ing, and traversal is refused at the route too
        assert c.post(f"/projects/{pid}/families/import-pack", json={"pack": "nope.ifc"}).status_code == 404
        assert c.post(f"/projects/{pid}/families/import-pack",
                      json={"pack": "../../../../etc/passwd"}).status_code == 404

        # a manifest that over-promises is REPORTED, not smoothed over
        MANIFEST.write_text(json.dumps({"packs": [
            {"file": PACK.name, "discipline": "test-structural", "types": 99}]}), encoding="utf-8")
        j2 = c.post(f"/projects/{pid}/families/import-pack", json={"pack": PACK.name}).json()
        assert "note" in j2 and "99" in j2["note"], j2
    if os.path.exists(HOST):
        os.remove(HOST)
finally:
    shutil.rmtree(ext, ignore_errors=True)
    os.environ.pop("AEC_FAMILY_SHELF", None)

print("FAMILY-GEOM OK - type sizes now read from ANY swept section (13 parameterised profiles + "
      "arbitrary polyline bounds), so imported W-shapes, tubes and pipes are no longer sizeless; a "
      "resize on non-box geometry REPLACES rather than appending a second solid (which used to render "
      "both and count both in take-off) and reports the section it discarded; a hollow section is no "
      "longer silently reshaped as a box while keeping a catalog name that no longer describes it; "
      "variant names follow the project's units (3'-0\" in an imperial job, mm in a millimetre job); "
      "and the external shelf is now server-side importable with manifest metadata, sha256 provenance "
      "in the audit trail, name-only resolution that refuses traversal, and an honest note when a "
      "manifest declares more types than actually arrive.")
