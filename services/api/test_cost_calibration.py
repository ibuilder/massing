"""COST-CALIBRATE — the calibration factor, the clamp that hides its own unreliability, and the
parameter its advice used to name.

`GET /projects/{pid}/cost/calibration` is the "learns from historical cost data" half of COST-AGENT.
It shipped in v0.3.475, `docs/roadmap-completed.md` records it under "P2 ring (shipped through 492)",
and **no client ever called it** — the route reachability gate read its leaf `calibration` as live
because `apps/web/src/vendor/massingpdf/` uses the word for PDF *scale* calibration. Nothing here is
about wiring, which is a web-side change; these are the two claims the route makes about itself that
a screen has to be able to rely on.

  1. THE CLAMP CAN RETURN A BOUNDARY RATHER THAN A MEASUREMENT. `max(0.5, min(2.0, observed/estimate))`
     turns one posted invoice on a whole-building estimate into a confident-looking `0.5`. The route
     reports `raw_ratio` and `clamped` so a caller never has to reconstruct that verdict — it cannot
     do so correctly, because the factor is computed from UNROUNDED totals while the response
     quantizes them to cents, and the two disagree exactly at the band edge. Asserted, not assumed.

  2. `benchmark_factor` IS NOT THE WAY TO APPLY IT, and the old `apply_hint` said it was. That
     parameter aligns the GFA benchmark's DOLLAR-YEAR; feeding it a calibration ratio raises the
     benchmark and pushes `recommended` away from the model. Asserted on the pure function, because
     that is where the direction can be shown rather than argued.

Run from services/api:
  PYTHONPATH=src:../data/src AEC_TRUST_XUSER=1 ./.venv/bin/python test_cost_calibration.py
"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

os.environ["DATABASE_URL"] = "sqlite:///./test_cost_calibration.db"
os.environ["STORAGE_DIR"] = "./test_storage_calib"
os.environ["IFC_DIR"] = "./_ifc_calib"        # writable; the default /app/ifc is read-only in CI
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_cost_calibration.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import estimate as est  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED = []
HDR = {"X-User": "estimator"}
TMP = "./_calib_source.ifc"


def check(label, ok, detail=None):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. benchmark_factor's REAL job, and what a calibration ratio would do to it -------------------
# Pure function, no HTTP: 20 elements so `element_count >= 10` holds and only the benchmark moves.
#
# The numbers are derived from the engine's own constants, not picked until the test passed:
# `DEFAULT_RATES["IfcWall"]` is $160/m² and `DEFAULT_PSF` is $220/sf, so 20 x 50 m² = $160,000 of
# model total against a 1,500 sf benchmark of $330,000. `trustworthy` needs `total >= 0.4 *
# benchmark` = $132,000, which $160,000 clears — so the BASE case must recommend "model", and a
# fixture that did not was the first thing this file caught, in its own first run.
_ROWS = [{"ifc_class": "IfcWall", "area": 50.0} for _ in range(20)]
_GFA_SF = 1_500.0
_base = est.estimate_from_takeoff(_ROWS, gfa_sf=_GFA_SF)
check("a model with structure and a plausible total is recommended over the GFA benchmark",
      _base.get("recommended") == "model", _base.get("recommended"))

# Now pass a calibration-shaped factor — "this project came in 1.9x the model" — as benchmark_factor,
# which is exactly what the old apply_hint told an estimator to do.
_calibrated = est.estimate_from_takeoff(_ROWS, gfa_sf=_GFA_SF, benchmark_factor=1.9)
check("benchmark_factor moves the BENCHMARK, never the model total",
      _calibrated["total"] == _base["total"]
      and _calibrated["gfa_benchmark"]["amount"] > _base["gfa_benchmark"]["amount"],
      (_base["total"], _calibrated["total"]))
check("...so an under-pricing factor pushes `recommended` AWAY from the model — the wrong way",
      _base["recommended"] == "model" and _calibrated["recommended"] == "gfa",
      (_base["recommended"], _calibrated["recommended"]))
check("...and `recommended_total` then reports the inflated benchmark, not the calibrated estimate",
      _calibrated["recommended_total"] == _calibrated["gfa_benchmark"]["amount"]
      and _calibrated["recommended_total"] != _base["total"],
      _calibrated["recommended_total"])

# --- a model to calibrate against -----------------------------------------------------------------
massing.generate_blank_ifc(TMP, name="Calibration Tower", storeys=1, storey_height=3.0,
                           ground_size=30.0)
m = open_model(TMP)
_st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [10, 0], 3.0, 0.2, _st)
edit.add_wall(m, [10, 0], [10, 10], 3.0, 0.2, _st)
edit.add_slab(m, [[0, 0], [10, 0], [10, 10], [0, 10]], thickness=0.2, storey=_st)
m.write(TMP)

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "COST-CALIBRATE"}, headers=HDR).json()["id"]

    # No source IFC → 409, because the comparison is against the MODEL estimate.
    check("refuses without a source IFC rather than calibrating against nothing",
          c.get(f"/projects/{pid}/cost/calibration", headers=HDR).status_code == 409)

    with open(TMP, "rb") as fh:
        up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                    files={"file": ("calib.ifc", fh, "application/octet-stream")}, headers=HDR)
    check("source IFC uploads", up.status_code == 200, up.text[:200])

    # --- 2. no history → no factor, and the hint says what to do about it --------------------------
    cal0 = c.get(f"/projects/{pid}/cost/calibration", headers=HDR).json()
    check("no commitments and no actuals → basis null, factor null",
          cal0["basis"] is None and cal0["calibration_factor"] is None, cal0)
    est_total = cal0["estimate_total"]
    check("the model estimate is a real number to divide by", est_total > 0, est_total)

    # --- 3. THE APPLY HINT no longer sends an estimator to benchmark_factor -----------------------
    # Behavioural, not a source grep: this is the text a client actually receives and might act on.
    #
    # The rule is not "never say the word" — naming it in order to warn against it is the whole
    # point of the correction. The rule is that it must never be named as the WAY TO APPLY the
    # factor, so a mention has to come with an explicit negation.
    def hint_is_safe(hint: str) -> bool:
        h = hint.lower()
        if "benchmark_factor" not in h:
            return True
        return "is not it" in h or "not it" in h

    check("a hint that tells you to pass benchmark_factor is REFUSED by this check",
          not hint_is_safe("pass benchmark_factor to estimate_from_takeoff / re-run the estimate"))
    check("...and a hint that never mentions it is accepted",
          hint_is_safe("award subcontracts or post direct costs to enable calibration"))
    check("...and one that names it only to warn against it is accepted",
          hint_is_safe("carry it by hand; benchmark_factor is not it"))
    check("the shipped hint with no factor is safe", hint_is_safe(cal0["apply_hint"]),
          cal0["apply_hint"])

    # --- 4. a committed basis inside the band: measured, not clamped -------------------------------
    c.post(f"/projects/{pid}/modules/subcontract", json={"data": {
        "vendor": "Acme Concrete", "trade": "Concrete", "value": est_total * 1.2}}, headers=HDR)
    cal1 = c.get(f"/projects/{pid}/cost/calibration", headers=HDR).json()
    check("an awarded subcontract gives a committed basis",
          cal1["basis"] == "committed", cal1["basis"])
    check("...and the factor is the ratio, to 3dp",
          abs(cal1["calibration_factor"] - 1.2) < 0.02, cal1["calibration_factor"])
    check("...and the raw ratio a client recomputes agrees with it — so the clamp did NOT fire",
          abs(cal1["committed_total"] / cal1["estimate_total"] - cal1["calibration_factor"]) < 0.02,
          (cal1["committed_total"], cal1["estimate_total"], cal1["calibration_factor"]))
    check("...and the route reports that verdict rather than leaving it to be inferred",
          cal1["clamped"] is False and abs(cal1["raw_ratio"] - 1.2) < 0.02, cal1)

    # --- 4b. WHY THE ROUTE MUST REPORT THE CLAMP RATHER THAN THE CLIENT RECONSTRUCTING IT ---------
    # The factor is computed from UNROUNDED totals; the response quantizes all three to cents. At
    # the band edge the two disagree, and the reconstruction is the one that says "not clamped".
    _est, _committed = 100.01, 200.021
    check("a ratio just above the band is clamped by the route",
          round(max(0.5, min(2.0, _committed / _est)), 3) == 2.0 and _committed / _est > 2.0)
    check("...but recomputing from the CENT-ROUNDED totals lands exactly on 2.0 and reads as clean",
          round(_committed, 2) / round(_est, 2) <= 2.0,
          (round(_committed, 2) / round(_est, 2)))
    check("...so `raw_ratio`/`clamped` are the route's answer, not a convenience",
          "raw_ratio" in cal1 and "clamped" in cal1, sorted(cal1))
    check("the shipped hint WITH a real factor is safe too — the branch that used to be wrong",
          hint_is_safe(cal1["apply_hint"]), cal1["apply_hint"])

    # --- 5. THE DEFECT: one small posted cost outranks every commitment and the clamp hides it -----
    # `cost.py` picks ("actual", actual) if actual > 0 else ("committed", committed) — ANY posted
    # direct cost, however small, outranks every awarded subcontract. That preference is right at
    # completion and wrong at the start, and the clamp turns the resulting absurd ratio into a
    # plausible-looking 0.5 rather than letting it look absurd.
    c.post(f"/projects/{pid}/modules/direct_cost", json={"data": {
        "description": "First mobilisation invoice", "amount": 500.0}}, headers=HDR)
    cal2 = c.get(f"/projects/{pid}/cost/calibration", headers=HDR).json()
    check("ONE $500 invoice flips the basis from committed to actual",
          cal2["basis"] == "actual" and cal2["actual_total"] == 500.0, cal2)
    raw = cal2["actual_total"] / cal2["estimate_total"]
    check("...the true ratio is far below the clamp floor", raw < 0.5, raw)
    check("...but the reported factor is exactly the floor — a boundary, not a measurement",
          cal2["calibration_factor"] == 0.5, cal2["calibration_factor"])
    check("...and the ROUTE says so itself: raw_ratio is reported and clamped is True",
          abs(cal2["raw_ratio"] - raw) < 1e-12 and cal2["clamped"] is True, cal2)
    check("...which a client no longer has to reconstruct — all three totals still come back too",
          cal2["estimate_total"] > 0 and cal2["committed_total"] > 0 and cal2["actual_total"] > 0,
          cal2)
    check("...and the note tells a reader the clamp can do this and how to undo it",
          "boundary" in cal2["note"] and "estimate_total" in cal2["note"], cal2["note"])
    # The committed total is still reported, which is what makes "more committed than posted →
    # the job is still running" decidable client-side.
    check("the committed total survives the switch to an actuals basis",
          cal2["committed_total"] > cal2["actual_total"],
          (cal2["committed_total"], cal2["actual_total"]))

for _f in (TMP,):
    if os.path.exists(_f):
        os.remove(_f)

print()
if FAILED:
    print(f"cost_calibration: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("cost_calibration: all checks passed — the factor is measured when it is inside the band and a "
      "clamp boundary when it is not, all three totals come back so a caller can tell which, and the "
      "apply_hint no longer sends an estimator to benchmark_factor, whose job is the GFA benchmark's "
      "dollar-year and which moves `recommended` the wrong way when fed a calibration ratio.")
