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

# --- DRIFT: ASCE 7 §12.8.6 + §12.12 story-drift screen (hand-computed on the ELF result above) ---------
# 3 stories, each hsx = 10 ft = 120 in; Risk Cat II → Δa = 0.020·120 = 2.4 in per story.
d0 = L.drift_check(s, risk_category="II")
assert d0["demand_evaluated"] is False and d0["passes"] is None, d0        # allowable envelope only
assert d0["allowable_ratio"] == 0.020 and all(r["allowable_in"] == 2.4 for r in d0["stories"]), d0
assert all("design_drift_in" not in r for r in d0["stories"]), "no demand without stiffness/ratio"
# Risk Cat IV tightens Δa to 0.010·120 = 1.2 in
assert L.drift_check(s, risk_category="IV")["stories"][0]["allowable_in"] == 1.2

# demand via story stiffness: δxe = shear ÷ k, Δ = Cd·δxe/Ie (Cd=5.5, Ie=1). Story1 shear 37.5, k=100 →
# δxe=0.375, Δ=2.0625 in ≤ 2.4 → PASS; ratio = 2.0625/120 = 0.01719
dk = L.drift_check(s, story_stiffness_kip_in=[100, 100, 100], cd=5.5, ie=1.0, risk_category="II")
s1 = dk["stories"][0]
assert s1["design_drift_in"] == 2.062 and s1["drift_ratio"] == 0.0172 and s1["pass"] is True, s1
assert dk["demand_evaluated"] is True and dk["passes"] is True, dk         # all three stories pass
assert dk["max_drift_ratio"] == 0.0172, dk["max_drift_ratio"]
# a soft structure (k=50) doubles δxe → Δ=4.125 in > 2.4 → FAILS
soft = L.drift_check(s, story_stiffness_kip_in=[50, 50, 50], cd=5.5, ie=1.0)
assert soft["stories"][0]["design_drift_in"] == 4.125 and soft["stories"][0]["pass"] is False
assert soft["passes"] is False, "soft story exceeds the §12.12 allowable"
# demand via a target elastic drift ratio: δxe = 0.005·120 = 0.6, Δ = 5.5·0.6 = 3.3 in > 2.4 → fail
dr = L.drift_check(s, target_elastic_drift_ratio=0.005, cd=5.5, ie=1.0)
assert dr["stories"][0]["design_drift_in"] == 3.3 and dr["passes"] is False, dr

# --- torsional irregularity (ASCE 7 §12.3.2.1): δmax/δavg → Type 1a (>1.2) / 1b (>1.4) ----------------
assert L.torsional_check(1.0, 1.0) == {"ratio": 1.0, "irregularity": None, "amplification_Ax": 1.0,
                                       "note": L.torsional_check(1.0, 1.0)["note"]}
t1a = L.torsional_check(1.3, 1.0)
assert t1a["irregularity"] == "Type 1a (torsional irregularity)" and abs(t1a["amplification_Ax"] - 1.174) < 0.002
t1b = L.torsional_check(1.5, 1.0)      # Ax = (1.5/1.2)² = 1.5625
assert "Type 1b" in t1b["irregularity"] and abs(t1b["amplification_Ax"] - 1.5625) < 0.002, t1b
assert L.torsional_check(1.0, 0.0)["ratio"] is None, "zero average displacement is guarded"

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
# drift screen is emitted on every model result (allowable envelope by default; no demand without stiffness)
assert r["drift"]["allowable_ratio"] == 0.020 and len(r["drift"]["stories"]) == r["story_count"]
assert r["drift"]["demand_evaluated"] is False and "torsion" not in r
# with a target drift ratio + end displacements, the model result carries a demand check + torsional flag
r2 = L.lateral_from_model(m, area_sf=10000.0, seismic={"sds": 1.0, "sd1": 0.6, "r": 8.0},
                          wind={"speed_mph": 130.0, "exposure": "C", "width_ft": 100.0},
                          drift={"target_elastic_drift_ratio": 0.004, "risk_category": "IV",
                                 "delta_max": 1.45, "delta_avg": 1.0})
assert r2["drift"]["demand_evaluated"] is True and r2["drift"]["passes"] is not None
assert r2["torsion"]["irregularity"] and "Type 1b" in r2["torsion"]["irregularity"], r2["torsion"]

if os.path.exists(TMP):
    os.remove(TMP)

print("STRUCT-LATERAL OK - ASCE 7 §12.8 seismic ELF hand-verified (3×100 kip @ 10/20/30 ft, SDS=1/R=8 → "
      "Cs=0.125, V=37.5 kip, Fx=6.25/12.5/18.75, shears 37.5/31.25/18.75, OTM=875 kip·ft); the §12.8-5 "
      "floor + §12.8-3 upper bound on Cs both verified; simplified wind MWFRS qz via the Kz power law, base "
      "shear = Σ story forces and grows with V²; lateral_from_model reads stories + estimates weight, runs "
      "both, and picks the governing base shear; not-a-PE disclaimer on every result. DRIFT: §12.12 "
      "allowable Δa=coeff·hsx by Risk Category (II 2.4in / IV 1.2in per 10ft story), design drift "
      "Δ=Cd·δxe/Ie from story shear ÷ stiffness (k=100→pass, k=50→fail) or a target elastic ratio; "
      "§12.3.2.1 torsional flag δmax/δavg → Type 1a(>1.2)/1b(>1.4) with the Ax amplification.")
