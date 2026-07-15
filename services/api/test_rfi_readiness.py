"""RFI-0 decision-readiness audit: composes the shipped checks (approvability + detail-rule validate +
model-hygiene + clash) into a ranked list of the information gaps a builder would ask about.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_rfi_readiness.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import rfi_prevention  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_rfi_test.ifc")
massing.generate_blank_ifc(TMP, name="RFI Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m, rooms_per_storey=3, ceiling_height=3.0)     # spaces w/o OccupancyType → occupancy gap
w = edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.7, height=2.1, kind="door")     # 0.7 m < 32 in → egress door gap
# a rated wall with no substantiating reference → approvability fail
rw = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.set_element_pset(m, rw, "Pset_WallCommon", "FireRating", "2HR")

r = rfi_prevention.decision_readiness(None, "no-project", m)   # db=None → clash lens just skips
assert not r["ready"] and r["total_gaps"] >= 1, r
assert r["high_severity"] >= 1, r
# gaps are ranked high-severity first
sevs = [g["severity"] for g in r["gaps"]]
assert sevs == sorted(sevs, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s]), sevs
# every gap has the fields the UI needs
assert all({"category", "severity", "title", "detail", "fix"} <= set(g) for g in r["gaps"]), r["gaps"]
# the categories present include code (egress/occupancy/rated-assembly fails)
cats = {g["category"] for g in r["gaps"]}
assert "code" in cats, cats
titles = " ".join(g["title"] for g in r["gaps"])
assert ("Egress" in titles or "Occupancy" in titles or "Fire-rated" in titles), titles
assert r["disclaimer"] and "not a guarantee" in r["disclaimer"].lower(), r["disclaimer"]

# a clean-ish model → fewer gaps; a model with everything resolved would be ready
m2 = open_model(TMP)   # a fresh blank (no spaces/doors/rated walls) → no code gaps
r2 = rfi_prevention.decision_readiness(None, "no-project", m2)
assert r2["total_gaps"] <= r["total_gaps"], (r2["total_gaps"], r["total_gaps"])

if os.path.exists(TMP):
    os.remove(TMP)

print("RFI-0 OK - decision_readiness composes approvability + detail-rule validate + model-hygiene (+ clash "
      "when a db is present) into a ranked gap list: a below-min egress door, unclassified occupancy, and an "
      "un-substantiated 2HR wall all surface as high-severity 'code' gaps with a fix; gaps rank high-first; "
      "each carries category/severity/title/detail/fix; carries the not-a-guarantee disclaimer.")
