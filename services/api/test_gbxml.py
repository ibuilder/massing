"""IFC -> gbXML export builder — deterministic test of the XML structure (spaces + envelope
surfaces) by stubbing the two geometry sources, so it needs no IFC fixture.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_gbxml.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from aec_data import gbxml, spaces, energy   # noqa: E402
from defusedxml.ElementTree import fromstring  # noqa: E402


class _Areas:
    wall, window, door, roof, floor, footprint = 100.0, 20.0, 5.0, 80.0, 80.0, 80.0


# stub the geometry extractors (unit-test the builder, not ifcopenshell)
spaces.space_schedule = lambda _m: [
    {"name": "Office", "number": "101", "storey": "L1", "net_area": 40.0, "volume": 120.0, "occupancy": 4},
    {"name": "Lobby", "number": "102", "storey": "L1", "net_area": 25.0, "volume": 75.0, "occupancy": None},
]
energy.envelope_areas = lambda _m: _Areas()

xml = gbxml.to_gbxml(None, "Test Project")
root = fromstring(xml.encode())            # valid + safe XML


def _local(e):
    return e.tag.rsplit("}", 1)[-1]


assert _local(root) == "gbXML", root.tag
spaces_el = [e for e in root.iter() if _local(e) == "Space"]
surfaces = [e for e in root.iter() if _local(e) == "Surface"]
openings = [e for e in root.iter() if _local(e) == "Opening"]
people = [e for e in root.iter() if _local(e) == "PeopleNumber"]
assert len(spaces_el) == 2, len(spaces_el)
# ExteriorWall + Roof + UndergroundSlab (door area is not a standalone surface here)
stypes = {s.get("surfaceType") for s in surfaces}
assert stypes == {"ExteriorWall", "Roof", "UndergroundSlab"}, stypes
assert len(openings) == 1, len(openings)          # the window opening on the exterior wall
assert len(people) == 1, len(people)              # only the occupied Office
# total building area = sum of space net areas
barea = next(e for e in root.iter() if _local(e) == "Area")
assert abs(float(barea.text) - 65.0) < 0.01, barea.text

print("GBXML OK - valid gbXML: 2 spaces (area/volume), 3 exterior surfaces (wall+window opening / "
      "roof / slab), 1 PeopleNumber (occupied space only), building area 65.0 m2; parses as safe XML")
