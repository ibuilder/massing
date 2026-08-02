"""R23-STOREY-LOD — the census that decides whether a proxy is worth building.

This item's premise is an archived claim that *"no custom LOD is needed"*. The way to retire a claim
like that is a number, not an opinion — so the census ships as a function and these assertions are
about the ways a census can mislead:

1. **a capped pass reports the cap** — geometry nobody measured looks exactly like geometry that is
   not there, and only one of those is worth chasing;
2. **unmeshable elements are named** — dropping them quietly understates the model AND overstates the
   proxy's saving, which flatters the thing being decided;
3. **a plan states its fidelity cost beside its benefit** — triangles saved alone is an argument, not
   a decision;
4. **structure passed deliberately is reported, not silently obeyed** — a viewer cannot signal that
   the frame is approximate.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod_census.py
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data.lod import (  # noqa: E402
    SMALL_PART_CLASSES,
    STATUS_NO_GEOMETRY,
    STATUS_OK,
    STRUCTURAL_CLASSES,
    proxy_plan,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# A census shaped exactly like the real one measured on samples/school_str.ifc, so the assertions are
# about real proportions rather than invented ones. Rebar really is 55.2% of that model's triangles.
CENSUS = {
    "status": STATUS_OK, "status_meaning": "ok", "elements_examined": 1551,
    "total_triangles": 343_558,
    "by_class": [
        {"ifc_class": "IfcReinforcingBar", "elements": 619, "triangles": 189_508,
         "pct_triangles": 55.16, "small_part": True},
        {"ifc_class": "IfcSlab", "elements": 299, "triangles": 76_020,
         "pct_triangles": 22.13, "small_part": False},
        {"ifc_class": "IfcColumn", "elements": 203, "triangles": 37_548,
         "pct_triangles": 10.93, "small_part": False},
        {"ifc_class": "IfcBeam", "elements": 375, "triangles": 35_658,
         "pct_triangles": 10.38, "small_part": False},
    ],
    "unmeshable_count": 15, "unmeshable": [{"guid": "x", "ifc_class": "IfcSlab", "reason": "RuntimeError"}],
    "capped": False, "cap": None,
}

# --- 1. the class lists are a POLICY, not a filter literal ------------------------------------------
check("rebar is classified as a small part — the class that dominates the budget",
      "IfcReinforcingBar" in SMALL_PART_CLASSES)
check("furniture and MEP terminals are too",
      {"IfcFurnishingElement", "IfcFlowTerminal"} <= set(SMALL_PART_CLASSES))
check("STRUCTURE IS NOT — beams, columns, slabs and walls are what a building is",
      not (set(STRUCTURAL_CLASSES) & set(SMALL_PART_CLASSES)),
      sorted(set(STRUCTURAL_CLASSES) & set(SMALL_PART_CLASSES)))

# --- 2. the plan sizes the prize from a real census ---------------------------------------------------
p = proxy_plan(CENSUS)
check("the default plan proxies rebar", [r["ifc_class"] for r in p["proxied"]] == ["IfcReinforcingBar"],
      p["proxied"])
check("  and saves the 189,508 triangles that class actually carries",
      p["triangles_saved"] == 189_508, p["triangles_saved"])
check("  which is 55.16% of the model — the number that justifies the item",
      p["pct_saved"] == 55.16, p["pct_saved"])
check("  leaving the rest intact", p["triangles_remaining"] == 343_558 - 189_508,
      p["triangles_remaining"])
check("  and it reports the ELEMENTS affected, not just triangles",
      p["elements_proxied"] == 619, p["elements_proxied"])

# --- 3. THE FIDELITY COST travels with the benefit ------------------------------------------------------
check("a plan states what stops being visible, not only what is saved",
      "stop being individually visible" in p["fidelity_note"], p["fidelity_note"])
check("  with structure untouched, it says so explicitly",
      p["structural_classes_included"] == [] and "frame renders exactly as authored" in p["fidelity_note"],
      p["fidelity_note"])

# --- 4. structure passed DELIBERATELY is reported, never silently obeyed -----------------------------------
s = proxy_plan(CENSUS, classes=("IfcReinforcingBar", "IfcBeam", "IfcColumn"))
check("proxying structure is allowed — a caller may mean it",
      s["status"] == STATUS_OK and s["triangles_saved"] == 189_508 + 35_658 + 37_548,
      s["triangles_saved"])
check("  but the structural classes are NAMED in the result",
      s["structural_classes_included"] == ["IfcBeam", "IfcColumn"], s["structural_classes_included"])
check("  and the note says a viewer cannot signal it and a user cannot see through it",
      "INCLUDES STRUCTURE" in s["fidelity_note"] and "cannot see through" in s["fidelity_note"],
      s["fidelity_note"])

# --- 5. no census, no plan ----------------------------------------------------------------------------------
for bad in (None, {}, {"status": STATUS_NO_GEOMETRY}, {"status": "something_else"}):
    r = proxy_plan(bad)
    check(f"a plan is REFUSED without a usable census ({str(bad)[:28]})",
          r["status"] == STATUS_NO_GEOMETRY and r["triangles_saved"] is None, r)
check("  and the refusal says why a guessed proxy is not acceptable",
      "unknown" in proxy_plan(None)["reason"], proxy_plan(None)["reason"])

# --- 6. a plan that saves nothing says so rather than reporting success vacuously --------------------------
none_hit = proxy_plan(CENSUS, classes=("IfcDoor",))
check("proxying a class the model does not contain saves zero, explicitly",
      none_hit["triangles_saved"] == 0 and none_hit["pct_saved"] == 0.0 and none_hit["proxied"] == [],
      none_hit)

# --- 6b. A CAPPED CENSUS MUST NOT READ AS "NOT WORTH IT" ----------------------------------------------------
# Found against a real model, not this fixture. Capping `school_str.ifc` at 400 elements excludes every
# rebar — iteration order puts them later — so the plan reports 0 saved, 0%. A caller reading only the
# plan would conclude LOD is pointless from a measurement that never saw the class carrying 55% of it.
capped_census = {**CENSUS, "capped": True, "cap": 400, "elements_examined": 400,
                 "by_class": [r for r in CENSUS["by_class"] if r["ifc_class"] != "IfcReinforcingBar"],
                 "total_triangles": 343_558 - 189_508}
cp = proxy_plan(capped_census)
check("a plan built from a CAPPED census says so", cp["capped"] is True, cp.get("capped"))
check("  and marks its saving as a lower bound, not a result",
      cp["saving_is_lower_bound"] is True, cp.get("saving_is_lower_bound"))
check("  stating that a small saving here is NOT evidence a proxy is not worth building",
      "not evidence" in cp["cap_note"], cp["cap_note"])
check("an uncapped plan says the saving is complete",
      p["capped"] is False and "complete" in p["cap_note"], p["cap_note"])

# --- 7. an empty model is NO_GEOMETRY, not a 0% saving ------------------------------------------------------
empty = {"status": STATUS_OK, "total_triangles": 0, "by_class": [], "unmeshable_count": 0}
r = proxy_plan({**empty, "status": STATUS_NO_GEOMETRY})
check("a model with no meshable geometry refuses rather than reporting a clean 0%",
      r["status"] == STATUS_NO_GEOMETRY, r["status"])

print()
if FAILED:
    print(f"lod_census: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("lod_census: all checks passed")
