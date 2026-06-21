"""Starter family library: catalog shape + build/place into a generated massing model.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_families.py"""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

from aec_data import families, massing  # noqa: E402

# --- catalog contract --------------------------------------------------------
cat = families.catalog()
assert len(cat) >= 12, len(cat)
cats = {c["category"] for c in cat}
assert {"Furniture", "Sanitary", "Appliance", "Plant"} <= cats, cats
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

        # round-trips through a write/read
        out_fd, out = tempfile.mkstemp(suffix=".ifc"); os.close(out_fd)
        try:
            model.write(out)
            rt = open_model(out)
            assert len(rt.by_type("IfcFurniture")) == 3
            print(f"FAMILIES OK - {len(cat)} catalog entries; placed 6 occurrences "
                  f"({len(rt.by_type('IfcTypeProduct')) - before_types} new types) into a generated model, round-tripped")
        finally:
            os.remove(out)
    finally:
        os.remove(path)
else:
    print(f"FAMILIES OK - {len(cat)} catalog entries (IFC placement SKIPPED: no ifcopenshell)")
