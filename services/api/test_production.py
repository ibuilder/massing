"""R22-PRODUCTION — field-installed quantity reconciled against the MODEL takeoff.

The load-bearing assertions here are not that the arithmetic works. They are the four refusals, because
a percent-complete drives a pay application and every one of these failure modes produces a *plausible*
number rather than an obvious error:

1. a trade unit is never silently equated with a model dimension (SF read as m² is a 10.76x error);
2. over-installation is reported, never clamped to a healthy-looking 100%;
3. an uncoded takeoff says so instead of returning an empty reconciliation that reads as "nothing to
   report";
4. field quantities against codes the model lacks are NAMED, not counted.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_production.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.production import (  # noqa: E402
    MATCH_EXACT,
    MATCH_INHERITED,
    MATCH_MIXED,
    STATUS_NOT_STARTED,
    STATUS_OK,
    STATUS_OVER,
    STATUS_UNIT_MISMATCH,
    STATUS_UNMATCHED,
    normalise_unit,
    reconcile,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def line_for(res, code):
    return next(ln for ln in res["lines"] if ln["cost_code"] == code)


# A takeoff row as `aec_data.qto.takeoff()` actually emits it — shape copied from the engine, not
# invented: {guid, ifc_class, storey, length, area, volume, weight, cost_code, unit, ...}
def t(guid, code, unit, **q):
    return {"guid": guid, "ifc_class": "IfcWall", "cost_code": code, "unit": unit,
            "cost_description": f"{code} desc", **q}


# --- 1. the ordinary case still has to be right ------------------------------------------------------
MODEL = [t("w1", "03 30 00", "area", area=100.0), t("w2", "03 30 00", "area", area=100.0)]
res = reconcile(MODEL, [{"cost_code": "03 30 00", "quantity": 50.0, "unit": "m2"}])
ln = line_for(res, "03 30 00")
check("modelled quantity sums across elements", ln["modeled"] == 200.0, ln["modeled"])
check("  installed is read from the field record", ln["installed"] == 50.0, ln["installed"])
check("  percent complete is installed/modelled", ln["pct_complete"] == 25.0, ln["pct_complete"])
check("  remaining is the balance", ln["remaining"] == 150.0, ln["remaining"])
check("  and the line reconciles", ln["status"] == STATUS_OK, ln["status"])

# --- 2. THE UNIT TRAP: a trade unit is not a dimension -----------------------------------------------
# 500 SF is 46.45 m², not 500. Equating them because both are "area-ish" is a 10.76x overstatement.
sf = reconcile([t("w1", "09 91 00", "area", area=100.0)],
               [{"cost_code": "09 91 00", "quantity": 500.0, "unit": "SF"}])
l_sf = line_for(sf, "09 91 00")
check("SF is CONVERTED to m², not taken at face value",
      abs(l_sf["installed"] - 46.4515) < 0.001, l_sf["installed"])
check("  and the factor is reported, so the conversion can be checked",
      l_sf["conversions"][0]["factor"] == 0.09290304, l_sf["conversions"])

# A unit that is not an area at all must not produce a percentage.
bad = reconcile([t("w1", "09 91 00", "area", area=100.0)],
                [{"cost_code": "09 91 00", "quantity": 12.0, "unit": "EA"}])
l_bad = line_for(bad, "09 91 00")
check("counting EACHes against an AREA line is refused, not divided",
      l_bad["status"] == STATUS_UNIT_MISMATCH, l_bad["status"])
check("  no percentage is emitted at all", l_bad["pct_complete"] is None, l_bad["pct_complete"])
check("  and the offending unit is named", l_bad["unmatched_units"] == ["EA"], l_bad)

for junk in ("furlongs", "", None, 7, "sq ftt"):
    j = reconcile([t("w1", "09 91 00", "area", area=100.0)],
                  [{"cost_code": "09 91 00", "quantity": 5.0, "unit": junk}])
    check(f"an unrecognised unit ({junk!r}) refuses rather than assuming a factor of 1.0",
          line_for(j, "09 91 00")["status"] == STATUS_UNIT_MISMATCH,
          line_for(j, "09 91 00")["status"])

check("normalise_unit returns None for the unknown, never a default",
      normalise_unit("furlongs") is None and normalise_unit("m2") == ("area", 1.0))
check("  and is tolerant of case/spacing that a human types",
      normalise_unit(" SF ") == normalise_unit("sf") == ("area", 0.09290304))

# A mixed line — one good unit, one bad — must refuse WHOLE, not silently drop the bad row.
mixed = reconcile([t("w1", "09 91 00", "area", area=100.0)],
                  [{"cost_code": "09 91 00", "quantity": 10.0, "unit": "m2"},
                   {"cost_code": "09 91 00", "quantity": 12.0, "unit": "EA"}])
l_mix = line_for(mixed, "09 91 00")
check("a line with ANY unusable unit refuses whole — a partial sum looks complete and is not",
      l_mix["status"] == STATUS_UNIT_MISMATCH and l_mix["installed"] is None, l_mix)

# --- 3. over-installation is REPORTED, never clamped -------------------------------------------------
over = reconcile([t("w1", "03 30 00", "area", area=100.0)],
                 [{"cost_code": "03 30 00", "quantity": 150.0, "unit": "m2"}])
l_over = line_for(over, "03 30 00")
check("installing more than the model contains reports >100%",
      l_over["pct_complete"] == 150.0, l_over["pct_complete"])
check("  it is NOT clamped to 100 — that would hide a bad join or a stale model",
      l_over["status"] == STATUS_OVER, l_over["status"])
check("  and remaining goes negative rather than to zero",
      l_over["remaining"] == -50.0, l_over["remaining"])

# --- 4. absence is absence ---------------------------------------------------------------------------
none_yet = reconcile([t("w1", "05 12 00", "weight", weight=1000.0)], [])
l_ns = line_for(none_yet, "05 12 00")
check("a modelled code with no field record is `not_started`",
      l_ns["status"] == STATUS_NOT_STARTED, l_ns["status"])
check("  installed is None, not 0.0 — nothing was measured, so nothing is claimed",
      l_ns["installed"] is None, l_ns["installed"])
check("  but the remaining work is still known", l_ns["remaining"] == 1000.0, l_ns["remaining"])

orphan = reconcile([t("w1", "03 30 00", "area", area=100.0)],
                   [{"cost_code": "99 99 00", "quantity": 5.0, "unit": "m2"}])
l_or = line_for(orphan, "99 99 00")
check("field work against a code the model lacks is NAMED, not just counted",
      l_or["status"] == STATUS_UNMATCHED and l_or["cost_code"] == "99 99 00", l_or)
check("  and it claims no percentage of a model line that does not exist",
      l_or["pct_complete"] is None and l_or["modeled"] is None, l_or)

# --- 5. THE CONFIDENT EMPTY: an uncoded takeoff -------------------------------------------------------
# `qto.takeoff()` sets cost_code=None for every element when no cost map is loaded. A reconciliation
# over that matches nothing — which reads as "nothing to report" and means "the model was never coded".
uncoded = reconcile([t("w1", None, "area", area=100.0), t("w2", None, "area", area=50.0)],
                    [{"cost_code": "03 30 00", "quantity": 5.0, "unit": "m2"}])
check("an uncoded model reports its uncoded element count",
      uncoded["model"]["uncoded_elements"] == 2, uncoded["model"])
check("  and says so in `basis` rather than returning a clean empty result",
      "no cost-coded model quantities" in uncoded["basis"].lower(), uncoded["basis"])
check("  overall completion is None, not 0% and not 100%",
      uncoded["overall"]["pct_complete"] is None, uncoded["overall"])

# --- 6. coverage — the number that stops a true-but-misleading headline --------------------------------
part = reconcile([t("a", "03 30 00", "area", area=100.0), t("b", "09 91 00", "area", area=900.0)],
                 [{"cost_code": "03 30 00", "quantity": 97.0, "unit": "m2"}])
check("overall percent is weighted across COMPARABLE lines only",
      part["overall"]["pct_complete"] == 97.0, part["overall"])
check("  and `covered_pct` reveals it covers only 10% of the coded model — the headline in context",
      part["overall"]["covered_pct"] == 10.0, part["overall"])

# --- 7. junk field rows are reported, never coerced -----------------------------------------------------
junky = reconcile([t("w1", "03 30 00", "area", area=100.0)], [
    {"cost_code": "03 30 00", "quantity": True, "unit": "m2"},     # JSON true is not 1.0
    {"cost_code": "03 30 00", "quantity": "lots", "unit": "m2"},
    {"cost_code": None, "quantity": 5.0, "unit": "m2"},
    {"cost_code": "03 30 00", "quantity": float("inf"), "unit": "m2"},
])
check("non-numeric / absurd field quantities are all rejected",
      len(junky["unusable_field_rows"]) == 4, junky["unusable_field_rows"])
check("  and the line reads as not_started rather than inventing a quantity",
      line_for(junky, "03 30 00")["status"] == STATUS_NOT_STARTED,
      line_for(junky, "03 30 00")["status"])

# --- 8. a count line counts elements, it does not measure them -------------------------------------------
cnt = reconcile([t("d1", "08 11 00", "count"), t("d2", "08 11 00", "count"),
                 t("d3", "08 11 00", "count")],
                [{"cost_code": "08 11 00", "quantity": 2.0, "unit": "EA"}])
l_cnt = line_for(cnt, "08 11 00")
check("three count-billed elements model as a quantity of 3",
      l_cnt["modeled"] == 3.0, l_cnt["modeled"])
check("  and two installed reads as 66.67%", l_cnt["pct_complete"] == 66.67, l_cnt["pct_complete"])

# --- 9. the payload explains its own statuses ------------------------------------------------------------
check("every status used is documented in the payload",
      set(res["by_status"]) <= set(res["status_meaning"]), res["by_status"])
check("  and `not_started` is documented as absence, not a measured zero",
      "absence of a record" in res["status_meaning"][STATUS_NOT_STARTED])

# --- 10. HOW a code was matched travels with the quantity ------------------------------------------
# `qto.cost_code_for()` matches by IFC class INCLUDING ancestors and reports the key it hit. A quantity
# priced through an ancestor is a weaker claim than one priced exactly, and summing hides the
# difference — the same reason the takeoff surfaces the key at all, one layer up.
def tm(guid, code, unit, ifc_class, matched, **q):
    return {"guid": guid, "ifc_class": ifc_class, "matched_class": matched, "cost_code": code,
            "unit": unit, "cost_description": None, **q}


ex = reconcile([tm("w1", "03 30 00", "area", "IfcWall", "IfcWall", area=100.0)], [])
check("an exactly-matched code reports `exact`",
      line_for(ex, "03 30 00")["match_basis"] == MATCH_EXACT, line_for(ex, "03 30 00"))
check("  and names the key that priced it",
      line_for(ex, "03 30 00")["matched_keys"] == ["IfcWall"], line_for(ex, "03 30 00"))

inh = reconcile([tm("w1", "03 30 00", "area", "IfcWallStandardCase", "IfcWall", area=100.0)], [])
check("a code priced through an ANCESTOR key reports `inherited`, not `exact`",
      line_for(inh, "03 30 00")["match_basis"] == MATCH_INHERITED, line_for(inh, "03 30 00"))

# THE CASE THIS EXISTS FOR: one cost code reached by two different keys. Summed, the line would read
# as a single confident quantity while half its denominator rests on a general key.
mix = reconcile([tm("w1", "03 30 00", "area", "IfcWall", "IfcWall", area=100.0),
                 tm("w2", "03 30 00", "area", "IfcWallStandardCase", "IfcWall", area=100.0)], [])
l_mixb = line_for(mix, "03 30 00")
check("one code matched BOTH exactly and by inheritance reports `mixed`",
      l_mixb["match_basis"] == MATCH_MIXED, l_mixb["match_basis"])
check("  the quantities still sum — mixed is a caveat on the number, not a refusal",
      l_mixb["modeled"] == 200.0, l_mixb["modeled"])
check("  and the affected codes are NAMED at the top level, not just counted",
      mix["inherited_codes"] == ["03 30 00"], mix["inherited_codes"])
check("an exactly-matched code is NOT listed as inherited", ex["inherited_codes"] == [],
      ex["inherited_codes"])

# Silence is unstated, never `exact`. A takeoff predating `matched_class` said nothing about how it
# matched, and reading silence as the strongest option is how a weak claim gets quoted as a strong one.
old = reconcile([t("w1", "03 30 00", "area", area=100.0)], [])
check("a takeoff with no `matched_class` reports basis None — unstated, NOT `exact`",
      line_for(old, "03 30 00")["match_basis"] is None, line_for(old, "03 30 00")["match_basis"])
check("  and claims no matched key it was never given",
      line_for(old, "03 30 00")["matched_keys"] == [], line_for(old, "03 30 00")["matched_keys"])
check("  while the quantity itself is unaffected — provenance is missing, the measurement is not",
      line_for(old, "03 30 00")["modeled"] == 100.0)
check("every basis used is documented in the payload",
      MATCH_MIXED in mix["match_meaning"] and MATCH_INHERITED in mix["match_meaning"])

print()
if FAILED:
    print(f"production: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("production: all checks passed")
