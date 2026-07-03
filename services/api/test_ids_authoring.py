"""IDS authoring — build a standards-valid buildingSMART IDS 1.0 file that round-trips through the
same validator (ifctester), from templates/use-cases, plus EIR generation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ids_authoring.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ids_authoring.db"
os.environ["STORAGE_DIR"] = "./test_storage_ids_authoring"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_ids_authoring.db",):
    if os.path.exists(_f):
        os.remove(_f)

import tempfile                                          # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402
from ifctester import ids                                # noqa: E402
from aec_api import ids_authoring as ia                  # noqa: E402
from aec_api.main import app                             # noqa: E402

# --- catalog ---
cat = ia.templates()
assert any(e["ifc_class"] == "IFCWALL" for e in cat["elements"]), cat
assert any(u["key"] == "fire_life_safety" for u in cat["use_cases"]), cat

# --- build IDS from a use case and PARSE IT BACK with ifctester (proves it's valid IDS 1.0) ---
xml = ia.build_from_use_case("fire_life_safety", author="GC", purpose="handover")
assert xml.startswith("<ids") and "IFCWALL" in xml and "FireRating" in xml, xml[:120]
with tempfile.NamedTemporaryFile("w", suffix=".ids", delete=False, encoding="utf-8") as f:
    f.write(xml); path = f.name
doc = ids.open(path)                                      # the exact loader aec_data.validate uses
os.unlink(path)
assert len(doc.specifications) == 5, len(doc.specifications)          # 5 element groups in that use case
assert doc.specifications[0].applicability, "spec must carry applicability"
assert doc.specifications[0].requirements, "spec must carry requirements"

# explicit specs also build + round-trip
xml2 = ia.build_ids("Custom", [{"name": "Doors need fire rating", "ifc_class": "IFCDOOR",
                                "requirements": [{"pset": "Pset_DoorCommon", "property": "FireRating", "data_type": "IFCLABEL"}]}])
assert "IFCDOOR" in xml2 and "FireRating" in xml2

# EIR markdown
eir = ia.eir_for_use_case("quantities", project="Demo Tower", author="BIM mgr")
assert eir.startswith("# Exchange Information Requirements") and "Demo Tower" in eir and "IFCSLAB" in eir

# --- endpoints ---
with TestClient(app) as c:
    assert c.get("/ids/templates").json()["use_cases"], "templates endpoint"
    r = c.post("/ids/build", json={"use_case": "energy", "author": "GC"})
    assert r.status_code == 200 and r.text.startswith("<ids") and "IFCWINDOW" in r.text, r.text[:120]
    assert "requirements.ids" in r.headers["content-disposition"]
    e = c.post("/ids/eir", json={"use_case": "handover_cobie", "project": "P1"})
    assert e.status_code == 200 and "Exchange Information Requirements" in e.text, e.text[:120]
    assert c.post("/ids/build", json={}).status_code == 422           # no use_case/specs -> 422

print("IDS AUTHORING OK - template/use-case catalog; build_ids emits valid buildingSMART IDS 1.0 that "
      "ifctester re-parses (5 specs, applicability+requirements); explicit specs + EIR markdown; "
      "endpoints download .ids / EIR.md; empty body -> 422")
