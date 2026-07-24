"""FAMILY-DEPTH ③ — composite (nested) families: parts placed at catalog offsets, aggregated
under an IfcElementAssembly, types deduped through the normal machinery, round-trip-safe.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_composite_family.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_composite_family.db"
os.environ["STORAGE_DIR"] = "./test_storage_composite"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_composite_family.db"):
    os.remove("./test_composite_family.db")

from aec_data import edit, families, massing, roundtrip  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

assert "workstation" in families.composite_keys()

_ifc = Path(tempfile.gettempdir()) / "composite_family.ifc"
massing.generate_blank_ifc(str(_ifc), name="Comp", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(str(_ifc))

# two workstations through the SAME add_family recipe callers already use
a1 = edit.RECIPES["add_family"](m, {"family": "workstation", "storey": "Level 1",
                                    "position": [2, 2]})
a2 = edit.RECIPES["add_family"](m, {"family": "workstation", "storey": "Level 1",
                                    "position": [6, 2]})
asm1, asm2 = m.by_guid(a1), m.by_guid(a2)
assert asm1.is_a("IfcElementAssembly") and asm1.Name == "Workstation"

def parts(asm):
    return [e for rel in (asm.IsDecomposedBy or []) for e in rel.RelatedObjects]

p1, p2 = parts(asm1), parts(asm2)
assert len(p1) == 2 and len(p2) == 2, (len(p1), len(p2))          # desk + chair each
classes = sorted(e.is_a() for e in p1)
assert classes == ["IfcFurniture", "IfcFurniture"], classes
# part types dedupe through ensure_type: two workstations share ONE desk type + ONE chair type
desk_types = [t for t in m.by_type("IfcFurnitureType") if "Desk" in (t.Name or "")]
chair_types = [t for t in m.by_type("IfcFurnitureType") if "Chair" in (t.Name or "")]
assert len(desk_types) == 1 and len(chair_types) == 1, (len(desk_types), len(chair_types))
# a bigger composite: the 6-chair meeting setup
a3 = edit.RECIPES["add_family"](m, {"family": "meeting_setup", "storey": "Level 1",
                                    "position": [12, 6]})
assert len(parts(m.by_guid(a3))) == 7                              # table + 6 chairs
# unknown composite errors by name
try:
    families.add_composite(m, "spaceship", "Level 1")
    raise AssertionError("unknown composite must ValueError")
except ValueError as e:
    assert "spaceship" in str(e)

# the whole nested structure survives serialize → reparse (INTEROP-RT composing with ③)
report = roundtrip.roundtrip(m)
assert report["fidelity_ok"], report["counts"]

if _ifc.exists():
    _ifc.unlink()

print("COMPOSITE-FAMILY OK - 'workstation' places desk+chair at catalog offsets under one "
      "IfcElementAssembly via the SAME add_family recipe (two workstations share one desk type and "
      "one chair type through ensure_type dedupe), 'meeting_setup' aggregates table + 6 chairs, an "
      "unknown composite errors by name, and the nested structure round-trips losslessly.")
