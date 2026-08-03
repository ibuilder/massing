"""R22-ENTITLEMENT ② — checking conditions against the model, and the unit conversion it shows.

Slice ① made conditions individually tracked. This is the entry's actual clause: conditions carried
into the model as constraints. The assertions are about the ways a compliance check does harm:

1. **an unevaluable condition is `not_checkable`, never passing** — a condition reported satisfied
   because nobody could evaluate it is a building put up out of compliance while the report said it
   was fine. Same rule as slice ①'s `unparsed`;
2. **units are converted explicitly and BOTH are reported.** "45 feet" against a metric model is
   how a 45 ft height limit silently becomes a 45 m one — a three-fold error that reads as a pass;
3. **a height limit is a MAXIMUM and a parking condition is a MINIMUM.** Reading one as the other
   inverts the finding, so both directions are asserted;
4. **the twin**: a real violation must actually be caught. A checker that never fails is a checker
   that never checked.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_condition_checks.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.approval_conditions import parse  # noqa: E402
from aec_api.condition_checks import (  # noqa: E402
    M_PER_FT,
    VERDICT_FAIL,
    VERDICT_NOT_CHECKABLE,
    VERDICT_PASS,
    check_all,
    check_condition,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


HEIGHT = parse("Maximum building height shall not exceed 45 feet.")[0]
PARKING = parse("Provide a minimum of 20 parking spaces.")[0]
STOREYS = parse("Building shall not exceed 3 storeys.")[0]
VAGUE = parse("Applicant shall satisfy the Director prior to issuance.")[0]
SETBACK = parse("Provide a minimum front setback of 20 ft.")[0]

# --- 2. UNITS ARE CONVERTED EXPLICITLY, AND BOTH ARE SHOWN ----------------------------------------------
# 45 ft = 13.716 m. A model 14 m tall EXCEEDS it — and would have "passed" against an unconverted 45.
tall = check_condition(HEIGHT, {"height_m": 14.0})
check("45 FEET IS CONVERTED TO METRES BEFORE COMPARISON",
      abs(tall["condition_value"] - 45 * M_PER_FT) < 1e-6, tall.get("condition_value"))
check("  a 14 m model EXCEEDS a 45 ft limit — the error an unconverted compare would have missed",
      tall["verdict"] == VERDICT_FAIL, tall["verdict"])
check("  the condition is reported AS WRITTEN as well as converted",
      tall["condition_as_written"] == "45.0 feet", tall.get("condition_as_written"))
check("  both units are named", tall["condition_unit"] == "m" and tall["model_unit"] == "m", tall)
check("  and the reason says why silent conversion is the danger",
      "45 ft limit becomes a 45 m one" in tall["reason"], tall["reason"])
check("a 13 m model is WITHIN a 45 ft limit",
      check_condition(HEIGHT, {"height_m": 13.0})["verdict"] == VERDICT_PASS)
check("  and 13.716 m exactly is within it, not over",
      check_condition(HEIGHT, {"height_m": 45 * M_PER_FT})["verdict"] == VERDICT_PASS)

# --- 3. DIRECTION: height is a MAXIMUM, parking is a MINIMUM ---------------------------------------------
check("a height limit is a maximum — over fails",
      check_condition(HEIGHT, {"height_m": 99.0})["verdict"] == VERDICT_FAIL)
check("PARKING IS A MINIMUM — fewer spaces than required FAILS",
      check_condition(PARKING, {"parking_spaces": 12})["verdict"] == VERDICT_FAIL,
      check_condition(PARKING, {"parking_spaces": 12}))
check("  and MORE spaces than required passes — the opposite direction to height",
      check_condition(PARKING, {"parking_spaces": 30})["verdict"] == VERDICT_PASS)
check("  exactly the required count passes",
      check_condition(PARKING, {"parking_spaces": 20})["verdict"] == VERDICT_PASS)
check("  the reason names the direction, since reading it backwards inverts the finding",
      "read as MINIMUMS" in check_condition(PARKING, {"parking_spaces": 30})["reason"])

check("a storey-count condition compares against storeys, not metres",
      check_condition(STOREYS, {"storeys": 5, "height_m": 2.0})["verdict"] == VERDICT_FAIL,
      check_condition(STOREYS, {"storeys": 5, "height_m": 2.0}))
check("  and passes when the model has fewer",
      check_condition(STOREYS, {"storeys": 2})["verdict"] == VERDICT_PASS)

# --- 1. WHAT CANNOT BE CHECKED NEVER PASSES ---------------------------------------------------------------
check("a SETBACK condition is not_checkable — no surveyed property line",
      check_condition(SETBACK, {"height_m": 10.0})["verdict"] == VERDICT_NOT_CHECKABLE,
      check_condition(SETBACK, {"height_m": 10.0})["verdict"])
check("  and says why rather than implying it passed",
      "dressed as a compliance finding" in check_condition(SETBACK, {})["reason"])
check("an untopiced condition is not_checkable",
      check_condition(VAGUE, {"height_m": 1.0})["verdict"] == VERDICT_NOT_CHECKABLE)
check("A MISSING MODEL FACT IS not_checkable, NOT a pass",
      check_condition(HEIGHT, {})["verdict"] == VERDICT_NOT_CHECKABLE,
      check_condition(HEIGHT, {})["verdict"])
check("  saying an absent fact cannot demonstrate compliance",
      "cannot demonstrate compliance" in check_condition(HEIGHT, {})["reason"])
check("  and a None fact is treated the same as an absent one",
      check_condition(HEIGHT, {"height_m": None})["verdict"] == VERDICT_NOT_CHECKABLE)
check("a parking condition with no count in the model is not_checkable, not failed",
      check_condition(PARKING, {"parking_spaces": None})["verdict"] == VERDICT_NOT_CHECKABLE)

# --- 4. THE TWIN AND THE ROLL-UP ---------------------------------------------------------------------------
allc = parse("""1. Maximum building height shall not exceed 45 feet.
2. Provide a minimum of 20 parking spaces.
3. Provide a minimum front setback of 20 ft.
4. Applicant shall satisfy the Director prior to issuance.""")
r = check_all(allc, {"height_m": 14.0, "parking_spaces": 12})
check("the roll-up catches BOTH real violations", r["exceeds_count"] == 2, r["counts"])
check("  and names them", {x["topic"] for x in r["exceeds"]} == {"height", "parking"},
      [x["topic"] for x in r["exceeds"]])
check("  counting what it could not check separately from what passed",
      r["not_checkable_count"] == 2 and r["checked_count"] == 2, r["counts"])
check("  it reports the facts it judged against, so a reader can audit the comparison",
      r["facts"]["height_m"] == 14.0, r["facts"])
clean = check_all(allc, {"height_m": 12.0, "parking_spaces": 25})
check("A COMPLIANT MODEL PASSES ITS CHECKABLE CONDITIONS — not a machine for saying no",
      clean["exceeds_count"] == 0 and clean["checked_count"] == 2, clean["counts"])
check("  but the unchecked two are still reported, not absorbed into a clean bill",
      clean["not_checkable_count"] == 2, clean["counts"])
check("no conditions at all is a clean empty result, not an error",
      check_all([], {"height_m": 1.0})["checks"] == [])

print()
if FAILED:
    print(f"condition_checks: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("condition_checks: all checks passed")
