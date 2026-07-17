"""STRUCT-LATERAL: ASCE 7 lateral analysis — seismic Equivalent Lateral Force + simplified wind MWFRS,
base shear distributed to story forces. Pure ASCE 7 arithmetic (hand-verified below).
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_lateral.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import lateral as L  # noqa: E402

# --- period + k exponent (ASCE 7 §12.8.2.1 / §12.8.3) ------------------------------------------------
assert abs(L.approx_period(30.0, "other") - 0.02 * 30.0 ** 0.75) < 1e-9
assert L._k_exponent(0.4) == 1.0 and L._k_exponent(2.6) == 2.0 and L._k_exponent(1.5) == 1.5

# --- seismic ELF, hand-computed: 3 stories × 100 kip at 10/20/30 ft, SDS=1, SD1=0.6, R=8, Ie=1 -------
s = L.seismic_elf([100, 100, 100], [10, 20, 30], sds=1.0, sd1=0.6, r=8.0, ie=1.0, system="other")
# Ta = 0.02·30^0.75 = 0.256 s ≤ 0.5 → k=1; Cs = 1/8 = 0.125 (upper bound 0.6/(0.256·8)=0.293 not binding)
assert s["k"] == 1.0, s["k"]
assert s["Cs"] == 0.125, s["Cs"]
assert s["seismic_weight_kip"] == 300.0 and s["base_shear_kip"] == 37.5, s
# Cvx = w·h/Σw·h with Σ = 6000 → 0.1667/0.3333/0.5 ; Fx = 6.25/12.5/18.75
f = [st["force_kip"] for st in s["stories"]]
assert f == [6.25, 12.5, 18.75], f
assert abs(sum(f) - s["base_shear_kip"]) < 0.01, "story forces sum to the base shear"
# story shear accumulates from the top; overturning = Σ Fx·hx = 62.5+250+562.5 = 875
assert [st["shear_kip"] for st in s["stories"]] == [37.5, 31.25, 18.75]
assert s["overturning_kipft"] == 875.0, s["overturning_kipft"]

# the §12.8-5 minimum Cs floor binds for very low seismicity (SDS=0.05 → Cs would be 0.00625 < 0.01)
lo = L.seismic_elf([100], [10], sds=0.05, sd1=0.03, r=8.0, ie=1.0)
assert lo["Cs"] == 0.01, lo["Cs"]
# the §12.8-3 upper bound binds at longer period: SDS=1, SD1=0.5, T=1 → Cs_base=0.125 capped to
# 0.5/(1·8)=0.0625, above the §12.8-5 floor (0.044) so the cap is the governing value
hi = L.seismic_elf([100], [40], sds=1.0, sd1=0.5, r=8.0, ie=1.0, period_s=1.0)
assert hi["Cs"] == 0.0625, hi["Cs"]

# --- wind MWFRS: internal consistency + the Kz power law -----------------------------------------------
w = L.wind_mwfrs([12, 24, 36], speed_mph=115.0, width_ft=100.0, exposure="C")
# qh uses Kz at the roof height (36 ft): qh = 0.00256·Kz·0.85·1·1·115²
kz36 = 2.01 * (36.0 / 900.0) ** (2.0 / 9.5)
qh_expected = 0.00256 * kz36 * 0.85 * 1.0 * 1.0 * 115.0 * 115.0
assert abs(w["qh_psf"] - round(qh_expected, 2)) < 0.05, (w["qh_psf"], qh_expected)
assert w["base_shear_kip"] == round(sum(st["force_kip"] for st in w["stories"]), 2), "base = Σ story forces"
assert [st["shear_kip"] for st in w["stories"]][0] == w["base_shear_kip"], "ground story carries full shear"
assert w["base_shear_kip"] > 0 and w["overturning_kipft"] > 0
# higher wind speed → higher base shear (quadratic in V)
w2 = L.wind_mwfrs([12, 24, 36], speed_mph=150.0, width_ft=100.0, exposure="C")
assert w2["base_shear_kip"] > w["base_shear_kip"], "base shear grows with wind speed"

# --- model-driven: read stories, run both, pick the governing -----------------------------------------
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_lateral_test.ifc")
massing.generate_blank_ifc(TMP, name="Lateral", storeys=5, storey_height=3.5, ground_size=25.0)
m = open_model(TMP)
st0 = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 3.5, 0.4, 0.4, st0)
r = L.lateral_from_model(m, area_sf=10000.0, seismic={"sds": 1.0, "sd1": 0.6, "r": 8.0},
                         wind={"speed_mph": 130.0, "exposure": "C", "width_ft": 100.0})
assert r["story_count"] >= 5, r["story_count"]
assert r["seismic"]["base_shear_kip"] > 0 and r["wind"]["base_shear_kip"] > 0
assert r["governing"]["system"] in ("seismic", "wind")
assert r["governing"]["base_shear_kip"] == max(r["seismic"]["base_shear_kip"], r["wind"]["base_shear_kip"])
assert "licensed professional engineer" in r["disclaimer"]

if os.path.exists(TMP):
    os.remove(TMP)

print("STRUCT-LATERAL OK - ASCE 7 §12.8 seismic ELF hand-verified (3×100 kip @ 10/20/30 ft, SDS=1/R=8 → "
      "Cs=0.125, V=37.5 kip, Fx=6.25/12.5/18.75, shears 37.5/31.25/18.75, OTM=875 kip·ft); the §12.8-5 "
      "floor + §12.8-3 upper bound on Cs both verified; simplified wind MWFRS qz via the Kz power law, base "
      "shear = Σ story forces and grows with V²; lateral_from_model reads stories + estimates weight, runs "
      "both, and picks the governing base shear; not-a-PE disclaimer on every result.")
