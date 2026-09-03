"""Starter family library: catalog shape + build/place into a generated massing model.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_families.py"""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

from aec_data import families, massing  # noqa: E402

# --- catalog contract --------------------------------------------------------
cat = families.catalog()
assert len(cat) >= 25, len(cat)
cats = {c["category"] for c in cat}
assert {"Furniture", "Sanitary", "Appliance", "Plant",
        "Lighting", "MEP", "Structural"} <= cats, cats
assert len({c["key"] for c in cat}) == len(cat), "catalog keys must be unique"
for c in cat:
    assert c["key"] and c["label"] and c["ifc_class"].startswith("Ifc") and len(c["dims"]) == 3, c

# --- build + place into a real (generated) model -----------------------------
try:
    import ifcopenshell  # noqa: F401
    _have_ifc = True
except ImportError:
    _have_ifc = False

if _have_ifc:
    from aec_data.ifc_loader import open_model
    m = massing.compute_massing({"lot_width": 30, "lot_depth": 20, "far": 2.0, "floor_to_floor": 3.5})
    fd, path = tempfile.mkstemp(suffix=".ifc"); os.close(fd)
    try:
        massing.generate_ifc(m, path)
        model = open_model(path)
        before_types = len(model.by_type("IfcTypeProduct"))

        # place a few families on the ground storey
        guids = []
        for key in ("desk", "chair", "toilet", "fridge", "tree"):
            g = families.add_family(model, key, position=[2.0, 2.0])
            assert g, f"add_family({key}) returned no GUID"
            guids.append(g)

        # types were created (one per distinct family), occurrences placed + type-assigned
        types = families.catalog()
        assert len(model.by_type("IfcTypeProduct")) == before_types + 5, model.by_type("IfcTypeProduct")
        assert len(model.by_type("IfcFurniture")) == 2, "desk + chair occurrences"
        assert len(model.by_type("IfcSanitaryTerminal")) == 1
        assert len(model.by_type("IfcElectricAppliance")) == 1
        assert len(model.by_type("IfcGeographicElement")) == 1
        # the placed element resolves its type (assign_type mapped the geometry)
        import ifcopenshell.util.element as ue
        placed = next(e for e in model.by_type("IfcFurniture") if e.GlobalId == guids[0])
        assert ue.get_type(placed) is not None, "placed family has no type"

        # re-placing the same family reuses the existing type (dedup)
        families.add_family(model, "desk", position=[5.0, 5.0])
        assert len(model.by_type("IfcTypeProduct")) == before_types + 5, "desk type should be reused"
        assert len(model.by_type("IfcFurniture")) == 3, "second desk occurrence"

        # --- parametric type variant: a custom-sized desk is a NEW, distinctly-named type --------
        gv = families.add_family(model, "desk", position=[7.0, 7.0], dims=[2.0, 0.8, 0.75])
        assert gv, "parametric desk returned no GUID"
        assert len(model.by_type("IfcTypeProduct")) == before_types + 6, "sized variant is a new type"
        variant = ue.get_type(next(e for e in model.by_type("IfcFurniture") if e.GlobalId == gv))
        assert variant.Name == "Desk 2×0.8×0.75 m", variant.Name        # Revit-style sized name
        # the variant's geometry is actually 2.0 m wide (parametric sizing took effect)
        import ifcopenshell.geom
        sh = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(),
                                            next(e for e in model.by_type("IfcFurniture") if e.GlobalId == gv))
        xs = sh.geometry.verts[0::3]
        assert abs((max(xs) - min(xs)) - 2.0) < 0.05, f"variant width {max(xs)-min(xs):.3f} m ≠ 2.0"
        # re-placing the same size reuses the variant; bad dims are rejected
        families.add_family(model, "desk", position=[8.0, 8.0], dims=[2.0, 0.8, 0.75])
        assert len(model.by_type("IfcTypeProduct")) == before_types + 6, "same-size variant reused"
        try:
            families.add_family(model, "desk", dims=[0, 1, 1]); raise AssertionError("expected ValueError")
        except ValueError:
            pass

        # --- import external IFC type content (manufacturer/3rd-party families) ------------------
        import ifcopenshell
        import ifcopenshell.api
        lib = ifcopenshell.file(schema="IFC4")
        ifcopenshell.api.run("root.create_entity", lib, ifc_class="IfcProject", name="Vendor lib")
        ifcopenshell.api.run("unit.assign_unit", lib)
        lctx = ifcopenshell.api.run("context.add_context", lib, context_type="Model")
        lbody = ifcopenshell.api.run("context.add_context", lib, context_type="Model",
                                     context_identifier="Body", target_view="MODEL_VIEW", parent=lctx)
        for nm in ("Acme Task Chair", "Acme Desk 1600"):
            vt = ifcopenshell.api.run("root.create_entity", lib, ifc_class="IfcFurnitureType", name=nm)
            vpos = lib.create_entity("IfcAxis2Placement2D", Location=lib.create_entity("IfcCartesianPoint", (0., 0.)),
                                     RefDirection=lib.create_entity("IfcDirection", (1., 0.)))
            vpr = lib.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=vpos, XDim=0.6, YDim=0.6)
            vrep = ifcopenshell.api.run("geometry.add_profile_representation", lib, context=lbody, profile=vpr, depth=0.9)
            ifcopenshell.api.run("geometry.assign_representation", lib, product=vt, representation=vrep)
        ifcopenshell.api.run("root.create_entity", lib, ifc_class="IfcFurnitureType")  # nameless → skipped

        types_before = len(model.by_type("IfcTypeProduct"))
        imp = families.import_types_from_ifc(model, lib)
        assert len(imp) == 2, imp                                  # 2 named types, nameless skipped
        assert {i["name"] for i in imp} == {"Acme Task Chair", "Acme Desk 1600"}, imp
        assert all(i["guid"] and i["ifc_class"] == "IfcFurnitureType" for i in imp), imp
        assert len(model.by_type("IfcTypeProduct")) == types_before + 2, "imported types added"
        # an imported type is placeable via the normal place_type flow (by its GUID)
        from aec_data.edit import place_type
        gimp = place_type(model, imp[0]["guid"], None, [4.0, 4.0])
        assert gimp, "imported family not placeable"
        # re-importing is idempotent (dedup by class+name)
        assert families.import_types_from_ifc(model, lib) == [], "re-import should add nothing"

        # round-trips through a write/read
        out_fd, out = tempfile.mkstemp(suffix=".ifc"); os.close(out_fd)
        try:
            model.write(out)
            rt = open_model(out)
            assert len(rt.by_type("IfcFurniture")) == 6, len(rt.by_type("IfcFurniture"))
            print(f"FAMILIES OK - {len(cat)} catalog entries; placed occurrences + a parametric variant "
                  f"+ imported 2 external types ({len(rt.by_type('IfcTypeProduct')) - before_types} new types), round-tripped")
        finally:
            os.remove(out)
    finally:
        os.remove(path)
else:
    print(f"FAMILIES OK - {len(cat)} catalog entries (IFC placement SKIPPED: no ifcopenshell)")
