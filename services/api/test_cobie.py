"""COBie model-derived tabs — Contact / Zone / System extraction from an in-memory IFC.
Confirms the new spatial-and-functional grouping sheets pull the right rows (a bare IFC that lacks
these still round-trips as empty tabs, exercised in test_closeout).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_cobie.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

os.environ.setdefault("DATABASE_URL", "sqlite:///./_tcobie.db")
os.environ.setdefault("STORAGE_DIR", "./_stcobie")

import ifcopenshell  # noqa: E402
import ifcopenshell.guid as guid  # noqa: E402

from aec_data import cobie  # noqa: E402

f = ifcopenshell.file(schema="IFC4")
f.create_entity("IfcProject", GlobalId=guid.new(), Name="Museum")

# --- Contact: an organization (with email) + a named person -------------------
email = f.create_entity("IfcTelecomAddress", ElectronicMailAddresses=["info@acme.design"])
f.create_entity("IfcOrganization", Name="Acme Design", Addresses=[email])
f.create_entity("IfcPerson", GivenName="Grace", FamilyName="Hopper")

# --- Zone groups a Space ------------------------------------------------------
space = f.create_entity("IfcSpace", GlobalId=guid.new(), Name="Room 101")
zone = f.create_entity("IfcZone", GlobalId=guid.new(), Name="North Wing", LongName="Occupancy")
f.create_entity("IfcRelAssignsToGroup", GlobalId=guid.new(), RelatedObjects=[space], RelatingGroup=zone)

# --- System groups a Component ------------------------------------------------
term = f.create_entity("IfcFlowTerminal", GlobalId=guid.new(), Name="AHU-1")
system = f.create_entity("IfcDistributionSystem", GlobalId=guid.new(), Name="HVAC-1", PredefinedType="VENTILATION")
f.create_entity("IfcRelAssignsToGroup", GlobalId=guid.new(), RelatedObjects=[term], RelatingGroup=system)

sheets = cobie.cobie_sheets(f)

# every new tab is present
for tab in ("Contact", "Zone", "System"):
    assert tab in sheets, sheets.keys()

# Contact: the org row carries Company + its email; the person row carries the name
contacts = sheets["Contact"]
assert any(c["Company"] == "Acme Design" and c["Email"] == "info@acme.design" for c in contacts), contacts
assert any(c["GivenName"] == "Grace" and c["FamilyName"] == "Hopper" for c in contacts), contacts

# Zone lists its member space
zrow = next(r for r in sheets["Zone"] if r["Name"] == "North Wing")
assert "Room 101" in zrow["SpaceNames"] and zrow["Category"] == "Occupancy", zrow

# System (a distribution system) lists its member component + carries its predefined type
srow = next(r for r in sheets["System"] if r["Name"] == "HVAC-1")
assert "AHU-1" in srow["ComponentNames"] and srow["Category"] == "VENTILATION", srow

print("COBIE OK - Contact (org email + person), Zone (space membership), System (IfcDistributionSystem "
      "component membership + predefined type) tabs extract from the IFC")
