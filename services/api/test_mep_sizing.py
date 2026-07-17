"""MEP-SIZE: engineering size checks over authored MEP — flow velocity in each duct/pipe from the design
size + flow (Pset_Massing_MEPSizing) vs accepted limits (ASHRAE air, erosion-limit water), pass/fail.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_mep_sizing.py"""
import math
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing, mep_sizing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_mep_sizing_test.ifc")
massing.generate_blank_ifc(TMP, name="MEP Size", storeys=1, storey_height=4.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a well-sized supply duct (300 mm round, 1000 CFM -> ~1316 fpm < 2500)  → PASS
edit.add_mep_run(m, "IfcDuctSegment", [0, 0], [8, 0], shape="round", size=0.30, storey=st,
                 system="Supply Air", discipline="hvac", flow=1000.0, flow_unit="CFM")
# a badly undersized duct (100 mm round, 1000 CFM -> ~11820 fpm >> 2500)  → FAIL
edit.add_mep_run(m, "IfcDuctSegment", [0, 2], [8, 2], shape="round", size=0.10, storey=st,
                 system="Supply Air", discipline="hvac", flow=1000.0, flow_unit="CFM")
# a well-sized pipe (50 mm, 20 GPM -> ~2.1 ft/s < 8)  → PASS
edit.add_mep_run(m, "IfcPipeSegment", [0, 4], [8, 4], shape="round", size=0.05, storey=st,
                 system="Domestic Cold Water", discipline="plumbing", flow=20.0, flow_unit="GPM")
# an over-driven pipe (25 mm, 50 GPM -> ~21 ft/s > 8)  → FAIL
edit.add_mep_run(m, "IfcPipeSegment", [0, 6], [8, 6], shape="round", size=0.025, storey=st,
                 system="Domestic Cold Water", discipline="plumbing", flow=50.0, flow_unit="GPM")
# a run with no design flow  → INFO (can't size-check)
edit.add_mep_run(m, "IfcDuctSegment", [0, 8], [8, 8], shape="round", size=0.30, storey=st,
                 system="Exhaust", discipline="hvac")
m.write(TMP)

r = mep_sizing.sizing_check(open_model(TMP))
assert r["checked"] == 5, r["checked"]
assert r["passed"] == 2 and r["failed"] == 2 and r["info"] == 1, (r["passed"], r["failed"], r["info"])
assert r["all_pass"] is False, "two runs fail the velocity limit"

by = {c["status"]: [] for c in r["checks"]}
for c in r["checks"]:
    by.setdefault(c["status"], []).append(c)
# failures sort first
assert r["checks"][0]["status"] == "fail", r["checks"][0]["status"]

# the well-sized 300 mm duct at 1000 CFM: V = Q / (π/4·d²); check the reported velocity matches the physics
d_ft = (300.0 / 25.4) / 12.0
v_expected = 1000.0 / (math.pi / 4.0 * d_ft * d_ft)
duct_pass = next(c for c in r["checks"] if c["parameter"] == "air velocity" and c["status"] == "pass")
assert abs(duct_pass["value_fpm"] - round(v_expected, 0)) < 2, (duct_pass["value_fpm"], v_expected)
assert duct_pass["limit_fpm"] == 2500.0 and duct_pass["system"] == "Supply Air", duct_pass

# the over-driven 25 mm pipe at 50 GPM: V = 0.408·Q/d²
d_in = 25.0 / 25.4
v_pipe = 0.408 * 50.0 / (d_in * d_in)
pipe_fail = next(c for c in r["checks"] if c["parameter"] == "water velocity" and c["status"] == "fail")
assert abs(pipe_fail["value_fps"] - round(v_pipe, 2)) < 0.05, (pipe_fail["value_fps"], v_pipe)
assert pipe_fail["value_fps"] > 8.0 and "increase the pipe" in pipe_fail["note"], pipe_fail

# tightening the air limit flips the good duct to a fail (limits are overridable)
strict = mep_sizing.sizing_check(open_model(TMP), duct_max_fpm=1000.0)
assert strict["failed"] >= 3, "a 1000 fpm limit fails both ducts w/ flow"
assert strict["limits"]["duct_max_fpm"] == 1000.0

# no MEP -> a clean empty result, no crash
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
empty = mep_sizing.sizing_check(open_model(TMP))
assert empty["checked"] == 0 and empty["all_pass"] is False, empty

assert "licensed professional engineer" in r["disclaimer"]

if os.path.exists(TMP):
    os.remove(TMP)

print("MEP-SIZE OK - sizing_check reads Pset_Massing_MEPSizing off each authored duct/pipe, computes the "
      "flow velocity (air V=Q/A, water V=0.408·Q/d²) and checks it against accepted limits (ASHRAE ~2500 "
      "fpm air, ~8 ft/s water) pass/fail like the IBC checks: a 300 mm/1000 CFM duct passes (~1316 fpm), a "
      "100 mm/1000 CFM duct fails, a 50 mm/20 GPM pipe passes, a 25 mm/50 GPM pipe fails (~21 ft/s); runs "
      "with no design flow return info; limits are overridable; empty models don't crash; every result "
      "carries the not-a-PE disclaimer.")
