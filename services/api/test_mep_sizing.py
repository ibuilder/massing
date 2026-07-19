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

# ── pressure loss (friction) — empirical round-duct + Hazen-Williams, per-system balancing view ────
m2 = open_model(TMP)
pl = mep_sizing.pressure_loss(m2)
# only runs with size+flow+length are checked (the no-flow Exhaust duct is skipped)
assert pl["checked"] == 4, pl["checked"]
by_guid = {x["guid"]: x for x in pl["runs"]}
# hand-check the 300 mm/1000 CFM duct: rate = 0.109136·CFM^1.9/De^5.02, loss = rate·L_ft/100
de = 300.0 / 25.4
rate_expected = 0.109136 * 1000.0 ** 1.9 / de ** 5.02
duct_runs = [x for x in pl["runs"] if x["kind"] == "duct"]
d300 = next(x for x in duct_runs if x["size_mm"] == 300.0)
assert abs(d300["friction_rate"] - round(rate_expected, 4)) < 5e-4, (d300["friction_rate"], rate_expected)
assert abs(d300["length_ft"] - round(8.0 / 0.3048, 1)) < 0.1, d300["length_ft"]
assert abs(d300["loss"] - round(rate_expected * (8.0 / 0.3048) / 100.0, 4)) < 1e-3, d300["loss"]
# 300 mm at 1000 CFM ≈ 0.23 in.wg/100ft — over the 0.10 equal-friction budget → fail (real physics!)
assert d300["status"] == "fail", d300
# the 50 mm/20 GPM pipe: Hazen-Williams ≈ 1.06 ft/100ft < 4 → pass; the 25 mm/50 GPM → far over
d_in = 50.0 / 25.4
hw = 0.2083 * (100.0 / 140.0) ** 1.852 * 20.0 ** 1.852 / d_in ** 4.8655
p50 = next(x for x in pl["runs"] if x["kind"] == "pipe" and x["size_mm"] == 50.0)
assert abs(p50["friction_rate"] - round(hw, 4)) < 5e-3 and p50["status"] == "pass", p50
p25 = next(x for x in pl["runs"] if x["kind"] == "pipe" and x["size_mm"] == 25.0)
assert p25["status"] == "fail" and p25["friction_rate"] > 100.0, p25
# systems: series-sum totals + the index (largest-loss) run named
sysmap = {s["system"]: s for s in pl["systems"]}
sa = sysmap["Supply Air"]
assert sa["runs"] == 2 and sa["index_run"]["guid"] in by_guid, sa
assert abs(sa["total_loss"] - round(sum(x["loss"] for x in duct_runs), 3)) < 2e-3, sa
assert sysmap["Domestic Cold Water"]["all_within_budget"] is False
assert pl["runs"][0]["status"] == "fail", "failures sort first"
assert "Hazen-Williams" in pl["disclaimer"] and "series sum" in pl["disclaimer"]

# ── per-conductor tray fill (NEC 392.22 from actual cable diameters) ───────────────────────────────
massing.generate_blank_ifc(TMP, name="Trays", storeys=1, storey_height=4.0, ground_size=30.0)
mt = open_model(TMP)
st2 = mt.by_type("IfcBuildingStorey")[0].Name
# a 300 mm tray with 3×30 mm cables on "Power": allowable = 7/6·11.81 ≈ 13.78 in², used ≈ 3.29 → pass
edit.add_mep_run(mt, "IfcCableCarrierSegment", [0, 0], [8, 0], size=0.30, storey=st2,
                 system="Power", discipline="electrical")
for i in range(3):
    edit.add_mep_run(mt, "IfcCableSegment", [0, i], [8, i], size=0.03, storey=st2,
                     system="Power", discipline="electrical")
# a 100 mm tray with 6×40 mm cables on "Feeders": allowable ≈ 4.59 in², used ≈ 11.7 → FAIL
edit.add_mep_run(mt, "IfcCableCarrierSegment", [0, 5], [8, 5], size=0.10, storey=st2,
                 system="Feeders", discipline="electrical")
for i in range(6):
    edit.add_mep_run(mt, "IfcCableSegment", [10, i], [18, i], size=0.04, storey=st2,
                     system="Feeders", discipline="electrical")
# a tray with no cables on its system → info
edit.add_mep_run(mt, "IfcCableCarrierSegment", [0, 8], [8, 8], size=0.20, storey=st2,
                 system="Spare", discipline="electrical")
mt.write(TMP)
tf = mep_sizing.tray_fill(open_model(TMP))
assert tf["checked"] == 3 and tf["failed"] == 1, (tf["checked"], tf["failed"])
byst = {t["system"]: t for t in tf["trays"]}
power = byst["Power"]
allow_expected = (7.0 / 6.0) * (300.0 / 25.4)
area_cable = math.pi / 4.0 * (30.0 / 25.4) ** 2
assert abs(power["allowable_fill_in2"] - round(allow_expected, 2)) < 0.02, power
assert power["conductors"] == 3 and abs(power["used_fill_in2"] - round(3 * area_cable, 2)) < 0.05
assert power["status"] == "pass" and power["fill_ratio"] < 0.5, power
feeders = byst["Feeders"]
assert feeders["status"] == "fail" and feeders["fill_ratio"] > 1.0 and feeders["conductors"] == 6, feeders
assert byst["Spare"]["status"] == "info" and "add_wire" in byst["Spare"]["note"]
assert tf["trays"][0]["status"] == "fail", "failures sort first"
assert "392.22" in power["citation"]

# ── space thermal loads (W/sf screen vs the block estimate) ────────────────────────────────────────
import ifcopenshell.api  # noqa: E402

for name, area in (("Office 101", 100.0), ("Conference A", 30.0), ("Mechanical", 20.0)):
    sp = ifcopenshell.api.run("root.create_entity", mt, ifc_class="IfcSpace", name=name)
    q = ifcopenshell.api.run("pset.add_qto", mt, product=sp, name="Qto_SpaceBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", mt, qto=q, properties={"NetFloorArea": area})
mt.write(TMP)
tl = mep_sizing.thermal_loads(open_model(TMP))
assert len(tl["spaces"]) == 3 and tl["skipped_no_area"] == 0, tl["spaces"]
rows = {s["name"]: s for s in tl["spaces"]}
off = rows["Office 101"]
# hand-check the office: 100 m² = 1076.39 sf; people = round(sf/150); internal + envelope per formula
sf = 100.0 * 10.7639
people = max(1, round(sf / 150.0))
internal = people * 450.0 + sf * (0.9 + 1.0) * 3.412
envelope = sf * 12.0
assert off["type"] == "office" and off["people"] == people, off
assert abs(off["total_btuh"] - round(internal + envelope, 0)) < 2, (off["total_btuh"], internal + envelope)
assert rows["Conference A"]["type"] == "conference" and rows["Mechanical"]["type"] == "back-of-house"
# conference density: 30 m² ≈ 323 sf → ~22 people (15 sf/person) — far denser than the office
assert rows["Conference A"]["people"] > off["people"]
assert tl["tons"] == round(sum(s["tons"] for s in tl["spaces"]), 1) or abs(
    tl["tons"] - sum(s["total_btuh"] for s in tl["spaces"]) / 12000.0) < 0.1
assert tl["block_tons"] == round(tl["total_area_sf"] / 350.0, 1), tl["block_tons"]
assert tl["delta_vs_block_pct"] is not None and "heat-balance" in tl["disclaimer"]
assert "space_types" in tl["assumptions"]

# no MEP -> a clean empty result, no crash
massing.generate_blank_ifc(TMP, name="Empty", storeys=1, storey_height=3.0, ground_size=10.0)
empty = mep_sizing.sizing_check(open_model(TMP))
assert empty["checked"] == 0 and empty["all_pass"] is False, empty
assert mep_sizing.pressure_loss(open_model(TMP))["checked"] == 0
assert mep_sizing.tray_fill(open_model(TMP))["checked"] == 0
assert mep_sizing.thermal_loads(open_model(TMP))["spaces"] == []

assert "licensed professional engineer" in r["disclaimer"]

if os.path.exists(TMP):
    os.remove(TMP)

print("MEP-SIZE OK - sizing_check reads Pset_Massing_MEPSizing off each authored duct/pipe, computes the "
      "flow velocity (air V=Q/A, water V=0.408·Q/d²) and checks it against accepted limits (ASHRAE ~2500 "
      "fpm air, ~8 ft/s water) pass/fail like the IBC checks: a 300 mm/1000 CFM duct passes (~1316 fpm), a "
      "100 mm/1000 CFM duct fails, a 50 mm/20 GPM pipe passes, a 25 mm/50 GPM pipe fails (~21 ft/s); runs "
      "with no design flow return info; limits are overridable; empty models don't crash; every result "
      "carries the not-a-PE disclaimer. DEPTH: pressure_loss matches the hand-computed empirical duct rate "
      "(300 mm/1000 CFM ≈ 0.23 in.wg/100ft → over the 0.10 equal-friction budget) + Hazen-Williams pipe "
      "rates, series-sums per system and names the index run; tray_fill computes per-conductor NEC 392.22 "
      "fill from authored cable diameters (3×30 mm in a 300 mm tray passes, 6×40 mm in a 100 mm tray "
      "fails, no cables → info); thermal_loads screens space-by-space W/sf loads (office/conference/"
      "back-of-house densities, hand-checked office total) vs the GFA÷350 block estimate.")
