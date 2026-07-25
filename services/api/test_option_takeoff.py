"""GEN-SCORE depth — an elemental (5D) takeoff behind each option, so carbon comes from QUANTITIES
rather than a typology benchmark.

The claim being tested isn't precision — massing-stage assemblies aren't precise. It's that the
number is DECOMPOSED and its basis is stated, so two options that a benchmark would call identical
are told apart, and a ranking never silently mixes derived figures with benchmark ones.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_option_takeoff.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_option_takeoff.db"
os.environ["STORAGE_DIR"] = "./test_storage_option_takeoff"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_option_takeoff.db"):
    os.remove("./test_option_takeoff.db")

from aec_api import option_score as osc  # noqa: E402
from aec_api import option_takeoff as ot  # noqa: E402

# a 40 x 30 m plate, 10 floors — 12,000 m2 GFA
M = {"buildable_gfa_m2": 12000.0, "floors": 10, "building_height_m": 35.0,
     "footprint_m2": 1200.0, "plate_w": 40.0, "plate_d": 30.0}

# ---- quantities scale off real geometry, not off GFA alone ----------------------------------------
q = ot.quantities(M)
assert q["concrete_m3"] == 3120.0, q["concrete_m3"]            # 12000 × 0.26
assert q["rebar_kg"] == 264000, q["rebar_kg"]                  # 12000 × 22
assert "steel_kg" not in q, q                                  # a concrete frame carries no steel line
# façade = perimeter(140) × height(35) = 4900 m2, split 40/60 by the default WWR
assert q["glazing_m2"] == 1960.0 and q["opaque_wall_m2"] == 2940.0, (q["glazing_m2"], q["opaque_wall_m2"])
assert q["roof_m2"] == 1200.0 and q["mep_m2"] == 12000.0

# a steel frame swaps the structural quantities; mass timber adds a timber line
st = ot.quantities(M, structure="steel_composite")
assert st["steel_kg"] == 660000 and st["concrete_m3"] == 1200.0, (st["steel_kg"], st["concrete_m3"])
tim = ot.quantities(M, structure="mass_timber")
assert tim["timber_m3"] == 1920.0, tim
assert "timber_m3" not in q, "a concrete frame must not report timber"

# ---- THE POINT: geometry a benchmark can't see -----------------------------------------------------
# Same GFA, same type. One squat plate, one slender tower. A whole-building kgCO₂e/m² benchmark gives
# these an IDENTICAL carbon intensity; a quantity takeoff does not, because the tower has far more
# façade per square metre — which is the trade-off the scorer exists to expose.
SQUAT = {"buildable_gfa_m2": 12000.0, "floors": 4, "building_height_m": 14.0,
         "footprint_m2": 3000.0, "plate_w": 60.0, "plate_d": 50.0}
TOWER = {"buildable_gfa_m2": 12000.0, "floors": 30, "building_height_m": 105.0,
         "footprint_m2": 400.0, "plate_w": 20.0, "plate_d": 20.0}
t_sq, t_tw = ot.takeoff(SQUAT), ot.takeoff(TOWER)
assert t_sq["basis"] == "quantity" and t_tw["basis"] == "quantity"
assert t_tw["facade_m2_per_gfa_m2"] > t_sq["facade_m2_per_gfa_m2"] * 1.5, \
    (t_tw["facade_m2_per_gfa_m2"], t_sq["facade_m2_per_gfa_m2"])
assert t_tw["carbon_intensity_kgco2e_m2"] > t_sq["carbon_intensity_kgco2e_m2"], \
    (t_tw["carbon_intensity_kgco2e_m2"], t_sq["carbon_intensity_kgco2e_m2"])
assert t_tw["cost"]["total"] > t_sq["cost"]["total"], "more façade must cost more"

# ---- coverage is reported: a bottom-up number over 60% of a building is not one over 95% ------------
c = t_sq["carbon"]
assert c["total_kgco2e"] > 0 and c["covered_elements"] >= 5, c
assert set(c["uncovered_elements"]) <= {"roof_m2", "finishes_m2", "mep_m2", "vertical_core_m2"}, c
# elements with no EPD factor are NAMED, never folded in at zero as though they were carbon-free
assert "mep_m2" in c["uncovered_elements"], c["uncovered_elements"]
assert all(x["kgco2e"] > 0 for x in c["lines"]), c["lines"]

# every priced element carries its own rate and extension, so the total is auditable
costed = t_sq["cost"]
assert costed["unpriced"] == [], costed["unpriced"]
assert abs(sum(x["cost"] for x in costed["lines"]) - costed["total"]) < 0.01
line = next(x for x in costed["lines"] if x["element"] == "concrete_m3")
assert abs(line["quantity"] * line["rate"] - line["cost"]) < 0.01, line

# ---- a takeoff is refused, not faked, when the geometry can't support one ---------------------------
for bad in ({}, {"buildable_gfa_m2": 0, "floors": 5}, {"buildable_gfa_m2": 500}):
    r = ot.takeoff(bad)
    assert r["basis"] == "none" and r["cost"] is None and r["carbon"] is None, (bad, r)
    assert "no takeoff" in r["note"], r["note"]
assert ot.quantities({}) == {}

# bad levers are refused rather than silently clamped
for kw, why in (({"structure": "unobtainium"}, "unknown structure"),
                ({"wwr": 1.4}, "wwr over 1"), ({"wwr": -0.1}, "negative wwr")):
    try:
        ot.takeoff(M, **kw)
        raise AssertionError(f"expected refusal: {why}")
    except ValueError:
        pass

# an unpriced element is named rather than dropped into a total that looks complete
sparse = ot.price({"concrete_m3": 10.0, "unobtanium_kg": 5.0})
assert sparse["unpriced"] == ["unobtanium_kg"] and sparse["total"] == 3800.0, sparse

# overriding a rate moves the total, so the defaults are genuinely levers
dear = ot.takeoff(M, rates={"concrete_m3": 760.0})
assert dear["cost"]["total"] > ot.takeoff(M)["cost"]["total"]

# ---- the scorer consumes it, and reports which basis each option used -------------------------------
BASE = {"lot_width": 60.0, "lot_depth": 50.0, "far": 3.0, "height_limit": 60.0,
        "floor_to_floor": 3.5, "efficiency": 0.82, "building_type": "multifamily",
        "coverage_max": 0.6}
scored = osc.score_options([{**BASE, "label": "A"}, {**BASE, "far": 2.0, "label": "B"}])
assert len(scored["options"]) == 2
for r in scored["options"]:
    assert r["carbon_basis"] == "hybrid", r["carbon_basis"]
    assert r["takeoff"]["basis"] == "quantity" and r["takeoff"]["quantities"], r["takeoff"]
    # hybrid: shell (quantities) + fit-out (type benchmark) — see option_score
    assert r["carbon_intensity_kgco2e_m2"] > r["takeoff"]["carbon_intensity_kgco2e_m2"], r
assert scored["carbon_basis"] == ["hybrid"] and scored["carbon_basis_mixed"] is False, scored
assert "like-for-like" in scored["note"], scored["note"]

# ---- a refusal that reaches the RESPONSE BODY is a literal, not an exception's text ---------------
# _evaluate catches the takeoff's OptionError and reports it as `note` in the scored option — which is
# response body, not a log line. The note must therefore be selected from option_score's own table by
# the exception's `code`; an exception's message is written for a traceback and can carry detail from
# wherever it was raised.
LEVERS = {"lot_width": 60.0, "lot_depth": 50.0, "far": 3.0, "height_limit": 60.0,
          "floor_to_floor": 3.5, "efficiency": 0.82, "building_type": "multifamily",
          "coverage_max": 0.6}
row = osc.score_options([{**LEVERS, "structure": "unobtainium"}])["options"][0]
assert row["takeoff"]["basis"] == "none", row["takeoff"]
assert row["takeoff"]["note"] in osc.TAKEOFF_REFUSALS.values(), row["takeoff"]["note"]
assert row["takeoff"]["note"] == osc.TAKEOFF_REFUSALS["structure"], row["takeoff"]["note"]
assert "unobtainium" not in row["takeoff"]["note"], "the caller's raw token must not be echoed back"
# the option still scores off the benchmark rather than being dropped
assert row["carbon_basis"] == "benchmark" and row["composite"] >= 0, row

for kw, code in ((("structure", "unobtainium"), "structure"), (("wwr", 1.4), "wwr")):
    try:
        ot.takeoff(M, **{kw[0]: kw[1]})
        raise AssertionError(f"expected refusal for {kw[0]}")
    except ot.OptionError as e:
        assert e.code == code, (e.code, code)
        assert code in osc.TAKEOFF_REFUSALS, code

# ---- the one refusal that reaches the API is a constant, not a stringified exception -------------
# Every OptionError the takeoff raises is caught per-option and turned into basis="none", so exactly
# one message escapes score_options. The router answers with the constant rather than str(e): a
# caught exception's text comes from wherever it was raised, and an API handler cannot vouch for that.
try:
    osc.score_options([])
    raise AssertionError("empty option set must be refused")
except osc.OptionError as e:
    assert str(e) == osc.EMPTY_OPTIONS, (str(e), osc.EMPTY_OPTIONS)
assert "at least one" in osc.EMPTY_OPTIONS, osc.EMPTY_OPTIONS

# ---- THE HONESTY GATE: a mixed set says so, because the ranking isn't like-for-like -----------------
rows = [dict(r) for r in scored["options"]]
rows[1]["carbon_basis"] = "benchmark"                 # simulate one option falling back
bases = {r["carbon_basis"] for r in rows}
assert len(bases) > 1
mixed = osc.score_options([{**BASE, "label": "A"}])   # sanity: a single-basis set is not "mixed"
assert mixed["carbon_basis_mixed"] is False

# drive the real mixed path through the engine: an option whose massing yields no floors falls back
import aec_api.option_takeoff as _ot  # noqa: E402

_real = _ot.takeoff
try:
    calls = {"n": 0}

    def _flaky(massing, **kw):
        calls["n"] += 1
        if calls["n"] == 2:                            # the second option gets no takeoff
            return {"basis": "none", "quantities": {}, "cost": None, "carbon": None, "note": "x"}
        return _real(massing, **kw)
    _ot.takeoff = _flaky
    mix = osc.score_options([{**BASE, "label": "A"}, {**BASE, "far": 2.0, "label": "B"}])
finally:
    _ot.takeoff = _real
assert mix["carbon_basis_mixed"] is True, mix["carbon_basis"]
assert sorted(mix["carbon_basis"]) == ["benchmark", "hybrid"], mix["carbon_basis"]
assert "MIXED" in mix["note"] and "not like-for-like" in mix["note"], mix["note"]
assert "1 of 2" in mix["note"], mix["note"]
# the fallback option still scores — it is flagged, not dropped
assert all(r["composite"] >= 0 for r in mix["options"])
assert {r["carbon_basis"] for r in mix["options"]} == {"hybrid", "benchmark"}

print("GEN-SCORE DEPTH OK - an elemental takeoff now sits behind each option: quantities off the real "
      "massing geometry (perimeter × height for façade, not GFA alone), priced element by element with "
      "each rate and extension auditable, and run through the platform's OWN EPD factor table rather "
      "than a second copy. The payoff is what a benchmark structurally cannot do: a squat plate and a "
      "slender tower with identical GFA and type get identical benchmark carbon, while the takeoff "
      "tells them apart because the tower carries far more façade per m². Coverage is reported and "
      "elements with no EPD factor are NAMED rather than folded in at zero as though carbon-free; a "
      "takeoff is refused (basis='none') rather than faked when the geometry can't support one; bad "
      "levers raise. And the model is deliberately HYBRID: the takeoff sees only geometry, so on its "
      "own it gives a warehouse and a hospital with the same envelope identical carbon, which is "
      "false — the difference lives in MEP and fit-out, exactly the elements it reports as "
      "uncovered. Shell comes from quantities, the programme-driven remainder from the type "
      "benchmark, and a set mixing that with a pure benchmark is flagged as not like-for-like "
      "instead of being averaged over.")
