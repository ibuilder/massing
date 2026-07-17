"""STRUCT-SOLVE: apply a gravity load case to the W10-7 analytical curve members and run a determinate
member-by-member statics solve (reactions, max shear/moment, indicative deflection + diagrams).
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_struct_solve.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import struct_solve  # noqa: E402
from aec_data import analytical, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_struct_solve_test.ifc")
massing.generate_blank_ifc(TMP, name="Solve Test", storeys=1, storey_height=4.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a portal frame: two vertical columns + one horizontal beam spanning between them (the beam is the member
# the statics solve exercises; the columns are classified as vertical and carry axial, not bending)
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [6, 0], 4.0, 0.4, 0.4, st)
edit.add_beam(m, [0, 0], [6, 0], 0.3, 0.5, st)
analytical.derive_analytical(m)      # solve reads the IfcStructuralCurveMembers off the model

# --- no analytical model -> a clean, explicit "run derive first" result, no crash --------------------
# (a separate blank file: the open_model cache keys on path+mtime, so re-opening TMP would return the same
# in-memory model we just derived onto — use a distinct path with no frame and no derive)
TMP_EMPTY = os.path.join(tempfile.gettempdir(), "_struct_solve_empty.ifc")
massing.generate_blank_ifc(TMP_EMPTY, name="No Frame", storeys=1, storey_height=3.0, ground_size=10.0)
none_r = struct_solve.solve(open_model(TMP_EMPTY))
assert none_r["has_analytical"] is False and "derive_analytical" in none_r["message"], none_r

# --- solve with explicit line loads so the statics are exactly checkable ------------------------------
# w_dead=1.0 klf, w_live=0.5 klf -> service w=1.5 klf; a simply-supported UDL beam:
#   Vmax = wL/2 (= end reaction), Mmax = wL^2/8 (at midspan)
WD, WL = 1.0, 0.5
r = struct_solve.solve(m, line_dead_klf=WD, line_live_klf=WL)
assert r["has_analytical"] is True, r
assert r["counts"]["beams"] == 1 and r["counts"]["columns"] == 2, r["counts"]
lc = r["load_case"]
assert lc["dead_klf"] == 1.0 and lc["live_klf"] == 0.5 and lc["service_klf"] == 1.5, lc

gb = r["governing_beam"]
L = gb["length_ft"]                   # reported rounded to 2dp; the solve itself uses full precision
assert L > 0, gb
w = 1.5
exp_v = w * L / 2.0
exp_m = w * L * L / 8.0
sv = gb["service"]
assert abs(sv["shear_max_kip"] - exp_v) < 0.05, (sv["shear_max_kip"], exp_v)
assert abs(sv["moment_max_kipft"] - exp_m) < 0.1, (sv["moment_max_kipft"], exp_m)
assert sv["reaction_kip"] == sv["shear_max_kip"], "end reaction of a UDL beam == wL/2 == Vmax"

# diagram: shear is +wL/2 at the left support and -wL/2 at the right; moment is ~0 at the ends and max mid
diag = sv["diagram"]
assert len(diag) == 9, diag
assert abs(diag[0]["shear_kip"] - exp_v) < 0.05, diag[0]
assert abs(diag[-1]["shear_kip"] + exp_v) < 0.05, diag[-1]
assert abs(diag[0]["moment_kipft"]) < 0.05 and abs(diag[-1]["moment_kipft"]) < 0.05, "M=0 at supports"
mid = diag[len(diag) // 2]
assert abs(mid["moment_kipft"] - exp_m) < 0.1, (mid, exp_m)           # peak moment at midspan
# deflection is positive at midspan and zero at the supports; the L/360 check returns a bool
assert diag[0]["deflection_in"] == 0.0 and mid["deflection_in"] > 0, diag
assert isinstance(sv["deflection_ok"], bool) and sv["deflection_limit_in"] > 0, sv

# --- factored uses the ASCE 7 governing combination (1.2D+1.6L = 1.2+0.8 = 2.0 klf here) --------------
assert lc["factored_lrfd_klf"] == 2.0, lc                            # max of the LRFD combos for D=1,L=0.5
fm = gb["factored"]["moment_max_kipft"]
assert abs(fm - 2.0 * L * L / 8.0) < 0.1, (fm, L)
assert "1.2D+1.6L" in lc["governing_combo"], lc["governing_combo"]

# --- the psf/tributary path derives the live load from the occupancy table (office = 50 psf) ----------
r2 = struct_solve.solve(m, live_occupancy="office", tributary_ft=10.0, slab_thickness_in=8.0, sdl_psf=20.0)
# dead psf = 8/12*150 + 20 = 120; live psf(office)=50; over a 10 ft strip -> 1.20 klf dead, 0.50 klf live
assert r2["load_case"]["dead_klf"] == 1.2 and r2["load_case"]["live_klf"] == 0.5, r2["load_case"]
assert r2["load_case"]["live_psf"] == 50.0 and r2["load_case"]["tributary_ft"] == 10.0, r2["load_case"]

# a different occupancy pulls a different live load (assembly = 100 psf)
r3 = struct_solve.solve(m, live_occupancy="assembly", tributary_ft=10.0)
assert r3["load_case"]["live_psf"] == 100.0 and r3["load_case"]["live_klf"] == 1.0, r3["load_case"]

# --- column tributary axial is best-effort context and, when present, is positive ---------------------
if r["columns_axial"]:
    assert r["columns_axial"]["service_total_kip"] > 0, r["columns_axial"]
    assert r["columns_axial"]["factored_lrfd_kip"] >= r["columns_axial"]["service_total_kip"], r["columns_axial"]

assert "licensed professional engineer" in r["disclaimer"], "must carry the not-a-PE disclaimer"

for f in (TMP, TMP_EMPTY):
    if os.path.exists(f):
        os.remove(f)

print("STRUCT-SOLVE OK - reads the W10-7 analytical curve members, classifies vertical->column / "
      "horizontal->beam, applies an ASCE 7 gravity load case (dead+live, occupancy psf x tributary strip "
      "or explicit klf), and solves each beam as a determinate simply-supported element: reaction=wL/2, "
      "Vmax=wL/2, Mmax=wL^2/8, indicative deflection vs L/360, with shear/moment/deflection diagrams "
      "(M peaks at midspan, V flips sign at the supports); factored forces use the governing LRFD "
      "combination; columns carry a tributary axial; missing-analytical returns a clean 'derive first' "
      "message; the not-a-PE disclaimer rides every result.")
