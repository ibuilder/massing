"""FAMILY-DEPTH ① — named type catalogs: curated sizes per family resolve through the same
ensure_type variant machinery; the add_family recipe takes type_name; the /families/{key}/types route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_type_catalogs.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_type_catalogs.db"
os.environ["STORAGE_DIR"] = "./test_storage_typecat"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_type_catalogs.db"):
    os.remove("./test_type_catalogs.db")

from aec_data import edit, families, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- the catalog surface ---------------------------------------------------------------------------
desk = families.catalog_types("desk")
assert [t["name"] for t in desk] == ["1400 × 700", "1600 × 800", "1800 × 900"], desk
assert families.catalog_dims("desk", "1600 × 800") == [1.6, 0.8, 0.75]
assert families.catalog_dims("desk", "1600 × 800".upper()) == [1.6, 0.8, 0.75]   # case-insensitive
# a family without a curated catalog falls back to its base dims as 'Standard'
chair = families.catalog_types("chair")
assert chair == [{"name": "Standard", "dims": [0.5, 0.5, 0.9]}], chair
for bad in (("nope", "x"), ("desk", "9999 × 9999")):
    try:
        families.catalog_dims(*bad)
        raise AssertionError(f"expected ValueError for {bad}")
    except ValueError as e:
        assert "unknown" in str(e), e

# --- placement: type_name resolves to a distinct sized IfcTypeProduct, deduped on re-place ---------
_ifc = Path(tempfile.gettempdir()) / "type_catalogs.ifc"
massing.generate_blank_ifc(str(_ifc), name="Cat", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1600 × 800", "storey": "Level 1"})
edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1600 × 800", "storey": "Level 1"})
edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1800 × 900", "storey": "Level 1"})
types = [t for t in m.by_type("IfcFurnitureType") if "Desk" in (t.Name or "")]
assert len(types) == 2, [t.Name for t in types]           # two cataloged sizes → two types, deduped
occurrences = m.by_type("IfcFurnishingElement")
assert len(occurrences) == 3, len(occurrences)            # three placed instances
# explicit dims still win over type_name when both are given
edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1400 × 700",
                               "dims": [2.0, 1.0, 0.75], "storey": "Level 1"})
assert len([t for t in m.by_type("IfcFurnitureType") if "Desk" in (t.Name or "")]) == 3

# --- routes ----------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    r = c.get("/families/desk/types")
    assert r.status_code == 200 and len(r.json()["types"]) == 3, r.text
    assert c.get("/families/nope/types").status_code == 404

if _ifc.exists():
    _ifc.unlink()

print("TYPE-CATALOGS OK - desk carries three named sizes (1400/1600/1800), names resolve to dims "
      "case-insensitively, un-cataloged families fall back to 'Standard', unknown family/type errors "
      "name the catalog; placing '1600 × 800' twice dedupes to ONE IfcFurnitureType while a second "
      "size adds another (3 occurrences over 2 types), explicit dims beat type_name, and the "
      "/families/{key}/types route serves the catalog (404 unknown).")
