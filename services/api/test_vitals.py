"""R26-VITALS — the six numbers, and the one rule that makes them trustworthy.

The strip renders on every room, so its failure mode is not "wrong number" but **plausible number**.
Two properties carry the weight:

1. **A missing engine yields `None` with a reason, never `0`.** A zero float reads as "no slack" and
   a zero IRR reads as "worthless"; both are lies about a project that simply has not been scheduled
   or underwritten yet. This is the audit's finding 03 in miniature — never render an empty state as
   though it were data.
2. **LOD is the weakest link, not the average.** A set is only as documented as its least-documented
   element. Quoting LOD 400 because most walls reached 400 while the connections sit at 200 is how a
   "LOD 400 set" reaches a fabricator and stops being buildable.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_vitals.py
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_vitals.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_vitals")

from aec_api import vitals  # noqa: E402

FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)


FULL = {
    "lod_counts": {"total": 23, "counts": {"300": 20, "400": 3}},
    "scorecard": {"summary": {"scored": 10, "health_pct": 84.2}},
    "cpm": {"activities": [{"total_float": 4}, {"total_float": 0}, {"total_float": 9}]},
    "spaces": {"total_area_sf": 12500},
    "budget": 22_524_592.09,
    "irr": 0.184,
}

v = vitals.vitals(None, "p", **FULL)

# ---- the shape the strip renders -----------------------------------------------------------------
check("all six vitals are present", set(v["order"]) <= set(v), f"order={v['order']}")
check("...and there are exactly six", len(v["order"]) == 6, str(len(v["order"])))
check("every vital carries a unit", all(v[k].get("unit") for k in v["order"]))

# ---- 1. LOD is the WEAKEST link ------------------------------------------------------------------
check("LOD reports the lowest stage present, not the most common",
      v["lod"]["value"] == "300", f"got {v['lod']['value']!r} from 20x300 + 3x400")
mixed = vitals.vitals(None, "p", **{**FULL, "lod_counts": {"total": 10, "counts": {"200": 1, "500": 9}}})
check("...even when one straggler sits far below the rest",
      mixed["lod"]["value"] == "200", "9 elements at 500 do not make it a LOD 500 set")
unset = vitals.vitals(None, "p", **{**FULL, "lod_counts": {"total": 10, "counts": {"UNSET": 4, "300": 6}}})
check("unstaged elements make the LOD unknown, not optimistic", unset["lod"]["value"] is None)
check("...and it says how many are unstaged", "4 of 10" in (unset["lod"]["note"] or ""),
      unset["lod"]["note"] or "")

# ---- 2. a missing engine is None + a reason, NEVER zero -------------------------------------------
empty = vitals.vitals(None, "p")
for k in empty["order"]:
    check(f"{k}: no data -> None, never 0", empty[k]["value"] is None,
          f"got {empty[k]['value']!r}")
    check(f"{k}: ...and says what it is waiting on", bool(empty[k].get("note")),
          empty[k].get("note") or "MISSING NOTE")

# the distinction the whole module exists for
zero_float = vitals.vitals(None, "p", cpm={"activities": [{"total_float": 0}]})
check("a REAL zero float is 0, not None — no slack is a fact, not a gap",
      zero_float["float"]["value"] == 0, f"got {zero_float['float']['value']!r}")
check("...and carries no 'waiting on' note", not zero_float["float"].get("note"))
no_sched = vitals.vitals(None, "p", cpm=None)
check("...while an unscheduled project is None with a reason",
      no_sched["float"]["value"] is None and "schedule" in (no_sched["float"]["note"] or ""))

# ---- 3. $/sf is DERIVED, and refuses to divide by nothing ----------------------------------------
check("$/sf = budget / area, computed here rather than stored",
      abs(v["cost_sf"]["value"] - round(22_524_592.09 / 12500, 2)) < 0.01,
      str(v["cost_sf"]["value"]))
no_area = vitals.vitals(None, "p", budget=1_000_000, spaces=None)
check("no area -> no $/sf, not an infinity or a crash", no_area["cost_sf"]["value"] is None)
no_budget = vitals.vitals(None, "p", spaces={"total_area_sf": 1000})
check("no budget -> no $/sf", no_budget["cost_sf"]["value"] is None)

# ---- 4. health bands -----------------------------------------------------------------------------
check("health carries a band, so colour is decided once", v["health"]["band"] == "good",
      str(v["health"]["band"]))
for score, band in ((84.2, "good"), (80.0, "good"), (79.9, "warn"), (60.0, "warn"), (59.9, "poor")):
    got = vitals.vitals(None, "p", scorecard={"summary": {"scored": 3, "health_pct": score}})["health"]["band"]
    check(f"health {score} -> {band}", got == band, f"got {got}")

# ---- 5. IRR is a percentage, and a missing scenario is not 0% ------------------------------------
check("IRR renders as a percentage", v["irr"]["value"] == 18.4, str(v["irr"]["value"]))
check("an unsolved proforma is None, not 0% — those are different claims",
      empty["irr"]["value"] is None and "solved" in (empty["irr"]["note"] or ""))
check("a genuine 0% IRR is still reported", vitals.vitals(None, "p", irr=0.0)["irr"]["value"] == 0.0)

# ---- 5b. the key must be the one the scorecard actually emits -------------------------------------
# Written after the first draft read `score`/`overall`/`percent` — none of which exist — which would
# have left this cell blank forever while looking like a shipped feature.
real = vitals.vitals(None, "p", scorecard={"summary": {"scored": 3, "good": 0, "poor": 3, "health_pct": 0.0}})
check("health reads summary.health_pct, the key bim_kpi really emits",
      real["health"]["value"] == 0.0, f"got {real['health']['value']!r}")
check("...and a measured 0% is REPORTED, not treated as missing",
      real["health"]["value"] == 0.0 and not real["health"].get("note"))
check("...and bands as poor", real["health"]["band"] == "poor")
allna = vitals.vitals(None, "p", scorecard={"summary": {"scored": 0, "na": 10, "health_pct": 0.0}})
check("every category n/a is unknown, not 0%", allna["health"]["value"] is None,
      allna["health"].get("note") or "")

# ---- 6. area unit conversion ---------------------------------------------------------------------
m2 = vitals.vitals(None, "p", spaces={"total_area_m2": 100})
check("m² converts to ft² rather than being reported as ft²",
      m2["area"]["value"] == round(100 * 10.7639, 0), str(m2["area"]["value"]))

print()
if FAILED:
    print(f"test_vitals FAILED: {len(FAILED)}")
    for f in FAILED:
        print("   -", f)
    sys.exit(1)
print("test_vitals OK - the six vitals assemble from the engines that own them, a missing engine "
      "degrades to None WITH A REASON rather than to a plausible zero, and LOD reports the weakest "
      "link so a set is never described as better documented than its worst element.")
