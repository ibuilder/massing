"""Discipline Spine D1 — the shared vocabularies (NCS disciplines + MasterFormat divisions + Uniformat
crosswalk) that thread model → sheets → specs → bid packages → budget together.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_disciplines.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_disciplines.db"
os.environ["STORAGE_DIR"] = "./test_storage_disciplines"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_disciplines.db"):
    os.remove("./test_disciplines.db")

from fastapi.testclient import TestClient            # noqa: E402
from aec_api import classification as c              # noqa: E402
from aec_api.main import app                         # noqa: E402

# --- discipline derived from IFC class via its MasterFormat section ---
assert c.discipline_of_ifc_class("IfcColumn") == "S", c.discipline_of_ifc_class("IfcColumn")   # 03 → Structural
assert c.discipline_of_ifc_class("IfcDuctSegment") == "M", c.discipline_of_ifc_class("IfcDuctSegment")  # 23 → Mech
assert c.discipline_of_ifc_class("IfcPipeSegment") == "P", c.discipline_of_ifc_class("IfcPipeSegment")  # 22 → Plumb
assert c.discipline_of_ifc_class("IfcDoor") == "A", c.discipline_of_ifc_class("IfcDoor")        # 08 → Architectural

# --- division / discipline helpers ---
assert c.division_of("03 30 00") == "03", c.division_of("03 30 00")
assert c.division_of("26 05 19") == "26"
assert c.discipline_of_division("05") == "S" and c.discipline_of_division("26") == "E"

# --- legacy free-text enum normalization (rfi's "MEP" / "Geotechnical" / "Low Voltage") ---
assert c.discipline_code("MEP") == "M" and c.discipline_code("Geotechnical") == "C"
assert c.discipline_code("Low Voltage") == "T" and c.discipline_code("Structural") == "S"
assert c.discipline_code("S") == "S" and c.discipline_code("") is None

# --- catalogs ---
disc = c.disciplines()
assert len(disc) == 11 and disc[0]["code"] == "G", len(disc)
struct = next(d for d in disc if d["code"] == "S")
assert struct["divisions"] == ["03", "04", "05"] and "A" in struct["uniformat"], struct
assert len(c.masterformat_divisions()) == 25
# Uniformat → MasterFormat crosswalk (concept budget → procurement budget)
xw = {x["code"]: x["masterformat_divisions"] for x in c.uniformat_crosswalk()}
assert xw["D30"] == ["23"] and xw["A"] == ["03", "31"], xw

# --- the reference endpoint the UI selects + spine joins read ---
with TestClient(app) as cl:
    r = cl.get("/reference/disciplines").json()
    assert len(r["disciplines"]) == 11 and len(r["masterformat_divisions"]) == 25, r
    assert any(d["code"] == "S" and d["name"] == "Structural" for d in r["disciplines"])
    assert len(r["uniformat_crosswalk"]) == 13

print("DISCIPLINES OK - NCS discipline vocabulary (11) + MasterFormat divisions (25) + Uniformat "
      "crosswalk (13); IFC-class->discipline (Column->S, Duct->M, Pipe->P, Door->A); legacy enum "
      "aliases (MEP->M, Geotechnical->C, Low Voltage->T) normalized; /reference/disciplines serves it")
