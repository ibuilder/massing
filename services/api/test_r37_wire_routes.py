"""R37-TESTED-UNWIRED — the last two WIRE items reach a route, at their siblings' altitude.

## What "wired" means here, precisely

Neither `mep.block_cooling_load` nor `takeoff_scope.scope_annotations` was missing a *product*
feature. Each was **the one function in its module that its own router did not call**, while every
sibling in the same module was routed:

* `routers/design.py::mep_size` is a five-branch dispatcher over `mep.py`. It called `size_duct`,
  `size_pipe`, `size_cooling` and `hanger_spacing`. `block_cooling_load` was reachable by nothing.
  One of five missing from a five-branch dispatcher is a gap, not a design.
* `routers/analysis.py::takeoff_2d` called `takeoff_scope.scope` and `check_calibration`.
  `scope_annotations` — R27-LAYOUT ③'s own named deliverable — was reachable by nothing.

**So the bar is parity with the siblings, and this file asserts that and nothing more.** Neither
`/projects/{pid}/mep/size` nor the `layout` half of `/projects/{pid}/takeoff/2d` has a web caller —
that was true of all six sibling functions before this change and is unchanged by it. Saying so here
because "wired" could otherwise be read as "reachable from the UI", and a later reader deserves to
know which claim was actually tested.

## The two refusals, which are the load-bearing part

`mep.block_cooling_load` clamps with `max(gfa, 0.0)` and `max(sf_per_ton, 1.0)`. Both clamps turn a
missing or nonsensical input into a **confident number**:

* an unloaded project answers `tons: 0.0` — a figure an engineer could read straight into a plant
  schedule, and zero tons of cooling is not a first pass, it is a missing input wearing an answer;
* `sf_per_ton=0` clamps to 1, returning **350x** the intended tonnage for the same building.

The engine is not changed — the clamps are its business and other callers may want them. The route
refuses first, which is where a request can still be told what is wrong with it.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_r37_wire_routes.py
"""
from __future__ import annotations

import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_r37_wire_routes.db"
os.environ["STORAGE_DIR"] = "./test_storage_r37_wire_routes"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_r37_wire_routes.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi import HTTPException  # noqa: E402

from aec_api import energy  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.routers.analysis import takeoff_2d  # noqa: E402
from aec_api.routers.design import mep_size  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


PID = "r37-wire"
with SessionLocal() as db:
    db.add(Project(id=PID, name="R37 wire"))
    db.commit()


def size(**kw):
    with SessionLocal() as db:
        return mep_size(PID, db=db, _="tester", **kw)


_real_gfa = energy.project_gfa_sf

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. mep.block_cooling_load
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Anti-vacuity: the dispatcher must still answer for the four branches that already worked, or a
# "block_cooling reaches the engine" result would prove nothing about the dispatch.
check("the four already-routed kinds still dispatch",
      "diameter_in" in str(size(kind="duct", flow=1000)) or "duct" in str(size(kind="duct", flow=1000)),
      str(size(kind="duct", flow=1000))[:70])
check("...including `cooling`, the branch block_cooling must NOT be confused with",
      size(kind="cooling", load=120_000)["tons"] == 10.0, str(size(kind="cooling", load=120_000)))

# The distinction the roadmap entry rested on: `cooling` converts a KNOWN load, `block_cooling`
# ESTIMATES the load from area. Same module, opposite direction, and neither substitutes.
blk = size(kind="block_cooling", gfa_sf=35_000)
check("block_cooling reaches the engine and estimates FROM AREA",
      blk["tons"] == 100.0 and blk["gfa_sf"] == 35_000, str(blk))
check("...reporting the rule of thumb it used, so the number can be argued with",
      blk["sf_per_ton"] == 350.0, str(blk.get("sf_per_ton")))
check("...and the load it implies, which is what `cooling` would have been given",
      blk["load_btuh"] == 1_200_000, str(blk.get("load_btuh")))
check("a caller's own sf_per_ton is honoured",
      size(kind="block_cooling", gfa_sf=35_000, sf_per_ton=250)["tons"] == 140.0)

# ---- the GFA default: one definition of gross area, not a second -----------------------------------
energy.project_gfa_sf = lambda db, pid: 21_000.0                  # noqa: E731 — focused seam
try:
    auto = size(kind="block_cooling")
    check("with no gfa_sf it uses the PROJECT's gross area", auto["gfa_sf"] == 21_000.0, str(auto))
    check("...and an explicit gfa_sf still overrides it, for a massing that is not the model",
          size(kind="block_cooling", gfa_sf=1_000)["gfa_sf"] == 1_000.0)
finally:
    energy.project_gfa_sf = _real_gfa

# ---- THE REFUSALS ----------------------------------------------------------------------------------
# `max(gfa, 0.0)` makes an unloaded project answer 0.0 tons. Zero tons of cooling is not a first
# pass; it is a missing input wearing an answer, and it would be read into a plant schedule.
energy.project_gfa_sf = lambda db, pid: None                       # noqa: E731
try:
    try:
        out = size(kind="block_cooling")
        check("a project with no GFA is refused, not answered with 0.0 tons", False,
              f"returned {out}")
    except HTTPException as e:
        check("a project with no GFA is refused, not answered with 0.0 tons", e.status_code == 422,
              str(e.status_code))
        check("...and the refusal says how to proceed, not just that it failed",
              "gfa_sf" in str(e.detail) and "load a model" in str(e.detail), str(e.detail)[:80])
finally:
    energy.project_gfa_sf = _real_gfa

for bad in (0.0, -1.0, float("nan"), float("inf")):
    try:
        size(kind="block_cooling", gfa_sf=bad)
        check(f"a gfa_sf of {bad} is refused", False, "no HTTPException")
    except HTTPException as e:
        check(f"a gfa_sf of {bad} is refused", e.status_code == 422, str(e.status_code))

# sf_per_ton=0 clamps to 1.0 in the engine — 350x the tonnage for the same building.
for bad in (0.0, -5.0, float("nan"), float("inf")):
    try:
        size(kind="block_cooling", gfa_sf=35_000, sf_per_ton=bad)
        check(f"an sf_per_ton of {bad} is refused", False, "no HTTPException")
    except HTTPException as e:
        check(f"an sf_per_ton of {bad} is refused", e.status_code == 422, str(e.status_code))

# The engine still clamps, deliberately — other callers may want that, and this file is not licensed
# to change it. Asserted so "the route refuses" cannot quietly become "the engine was edited".
from aec_api import mep  # noqa: E402

check("the ENGINE still clamps, so the refusal is the route's and the engine is untouched",
      mep.block_cooling_load(0.0)["tons"] == 0.0
      and mep.block_cooling_load(350.0, 0.0)["sf_per_ton"] == 1.0)

# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. takeoff_scope.scope_annotations
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Same two viewports as `test_takeoff_scope.py`, in PAGE POINTS: a plan at 1:100 and a detail at 1:20.
LAYOUT = {
    "page": (2384, 1684),
    "regions": [
        {"kind": "titleblock", "label": "Titleblock", "rect": (36, 36, 2312, 90)},
        {"kind": "viewport", "index": 0, "label": "LEVEL 1 PLAN", "rect": (50, 200, 1000, 800),
         "scale_denom": 100, "measurable": True, "to_page": {"sx": 1, "sy": -1, "tx": 0, "ty": 0}},
        {"kind": "viewport", "index": 1, "label": "DETAIL A", "rect": (1200, 200, 600, 500),
         "scale_denom": 20, "measurable": True, "to_page": {"sx": 1, "sy": -1, "tx": 0, "ty": 0}},
    ],
}
PPP = 2.0                                    # screen pixels per page point
VP0 = LAYOUT["regions"][1]                   # the plan viewport, reused by the malformed-layout cases
TRACE = {"category": "generic_area",         # inside viewport 0, in SCREEN PIXELS
         "points": [[200, 500], [600, 500], [600, 900], [200, 900]]}


def takeoff(**extra):
    with SessionLocal() as db:
        return takeoff_2d(PID, body={"scale_units_per_px": 0.05, "regions": [TRACE], **extra},
                          db=db, _sec="tester")


# ---- absent unless asked for: the untouched path -----------------------------------------------
plain = takeoff()
check("a takeoff with no layout is unchanged — no scope, no annotation_scope",
      "scope" not in plain and "annotation_scope" not in plain, str(sorted(plain))[:90])
scoped = takeoff(layout=LAYOUT, px_per_point=PPP)
check("a layout alone still scopes the TRACES, as it always did",
      scoped["scope"]["regions"][0]["viewport"] == 0, str(scoped["scope"]["regions"][0]))
check("...and annotation_scope is ABSENT, not an empty finding",
      "annotation_scope" not in scoped, str(sorted(scoped))[:90])

# ---- the wiring ---------------------------------------------------------------------------------
NOTES = [
    {"id": "N1", "kind": "note", "x": 400, "y": 700},          # pts (200,350) → viewport 0
    {"id": "N2", "kind": "keynote", "x": 2600, "y": 700},      # pts (1300,350) → viewport 1
    {"id": "S1", "kind": "stamp", "x": 400, "y": 120},         # pts (200,60) → titleblock
]
ann = takeoff(layout=LAYOUT, px_per_point=PPP, annotations=NOTES)["annotation_scope"]
rows = {r["annotation_id"]: r for r in ann["regions"]}
check("a note over the plan is attached to the PLAN, not to the sheet",
      rows["N1"]["viewport"] == 0 and rows["N1"]["scope"] == "scoped", str(rows["N1"]))
check("...a keynote over the detail to the DETAIL — the whole point, since they are centimetres "
      "apart on the same page", rows["N2"]["viewport"] == 1, str(rows["N2"]))
check("...and each carries the scale of the view it governs",
      rows["N1"]["scale_denom"] == 100 and rows["N2"]["scale_denom"] == 20,
      f"{rows['N1'].get('scale_denom')} / {rows['N2'].get('scale_denom')}")
check("the annotation's own id rides back, so a caller can match rows to its notes",
      set(rows) == {"N1", "N2", "S1"}, str(sorted(rows)))
check("...and its kind, which is what tells a keynote from a stamp",
      rows["N2"]["kind"] == "keynote" and rows["S1"]["kind"] == "stamp")

# `unscoped` is CORRECT for a titleblock stamp, not a failure — it governs the sheet, not a view.
check("a titleblock stamp is UNSCOPED, which is the right answer rather than a miss",
      rows["S1"]["scope"] == "unscoped", str(rows["S1"]))
check("...and the note says so, so nobody reads it as a placement failure",
      "legitimate answer" in ann["note"], ann["note"][:70])

# ---- traces and annotations do not contaminate each other ----------------------------------------
check("the traces are still scoped alongside, in their own key",
      takeoff(layout=LAYOUT, px_per_point=PPP,
              annotations=NOTES)["scope"]["regions"][0]["viewport"] == 0)
check("...and annotation_scope counts the ANNOTATIONS, not the traces",
      len(ann["regions"]) == 3, str(len(ann["regions"])))

# A revision cloud is a polygon, and falls out of the same ratio test with no special case.
cloud = [{"id": "C1", "kind": "cloud",
          "points": [[2500, 500], [2700, 500], [2700, 700], [2500, 700]]}]
cl = takeoff(layout=LAYOUT, px_per_point=PPP, annotations=cloud)["annotation_scope"]
check("a revision CLOUD scopes as a polygon, no special case",
      cl["regions"][0]["viewport"] == 1, str(cl["regions"][0]))

# ---- the coordinate contract, shared with `scope` and not reimplemented --------------------------
# Without px_per_point the two spaces cannot be related. Reporting `unknown` is the honest answer;
# assuming 1:1 would put every note in the page corner and report it confidently.
no_ppp = takeoff(layout=LAYOUT, annotations=NOTES)["annotation_scope"]
check("without px_per_point every annotation is UNKNOWN, not confidently misplaced",
      all(r["scope"] == "unknown" for r in no_ppp["regions"]), str(no_ppp["regions"][0]))
check("...the same failure mode `scope` reports, because it IS `scope` underneath",
      takeoff(layout=LAYOUT)["scope"]["regions"][0]["scope"] == "unknown")

# ---- malformed input is answered, not crashed on -------------------------------------------------
# Every coordinate here is caller-supplied, and `float("abc")` raised straight out of `scope`'s
# comprehension and left the route as a **500**: the wrong status for bad input, and it failed a whole
# forty-trace takeoff over one malformed entry. The gap was PRE-EXISTING and symmetric — the `regions`
# path did the same thing — so it is fixed once, in `scope`, where both paths converge. Fixing only
# the annotations half would have been worse than leaving it: a caller would learn that malformed
# input is handled, then meet a 500 on the other key.
BAD_ROWS = {
    "a coordinate that is not a number": [{"id": "B1", "x": "abc", "y": 5}],
    "points that are not pairs":         [{"id": "B2", "points": [[1]]}],
    "points that are not a list":        [{"id": "B3", "points": "xy"}],
    "an entry that is not an object":    [5],
    "a null entry":                      [None],
}
for label, rows in BAD_ROWS.items():
    try:
        got = takeoff(layout=LAYOUT, px_per_point=PPP, annotations=rows)["annotation_scope"]
        row = got["regions"][0]
        check(f"{label} is reported UNKNOWN, not raised", row["scope"] == "unknown", str(row)[:90])
    except Exception as e:                                      # noqa: BLE001 — the point of the test
        check(f"{label} is reported UNKNOWN, not raised", False, f"{type(e).__name__}: {e}")

# The same guard covers the pre-existing `regions` path, which is why it lives in `scope`.
bad_trace = {"category": "generic_area", "points": [["abc", 5], [1, 2]]}
with SessionLocal() as db:
    fixed = takeoff_2d(PID, body={"scale_units_per_px": 0.05, "regions": [bad_trace],
                                  "layout": LAYOUT, "px_per_point": PPP}, db=db, _sec="tester")
check("...and a malformed TRACE too — the gap was pre-existing and is fixed once, not twice",
      fixed["scope"]["regions"][0]["scope"] == "unknown", str(fixed["scope"]["regions"][0])[:90])

# One bad row must not take the good ones with it: that is the whole reason this is `unknown` per
# row rather than a 422 for the request.
mixed = takeoff(layout=LAYOUT, px_per_point=PPP,
                annotations=[{"id": "OK", "x": 400, "y": 700}, {"id": "BAD", "x": None, "y": None}])
by = {r["annotation_id"]: r for r in mixed["annotation_scope"]["regions"]}
check("a good annotation beside a bad one is still scoped",
      by["OK"]["viewport"] == 0 and by["BAD"]["scope"] == "unknown", str(by))

# A wrong TYPE for the whole field IS refused — a caller who cannot be answered at all, as opposed
# to one bad note among good ones.
# FALSEY non-list values are refused too, and that is why the type guard runs BEFORE the truthiness
# test rather than inside it: `if annotations:` alone would wave "" and 0 and {} straight past, and
# the caller would get a silent no-op instead of being told their field is the wrong shape.
for bad in ("not a list", "", 0, {}):
    try:
        takeoff(layout=LAYOUT, px_per_point=PPP, annotations=bad)
        check(f"a non-list annotations field ({bad!r}) is refused", False, "no HTTPException")
    except HTTPException as e:
        check(f"a non-list annotations field ({bad!r}) is refused", e.status_code == 422,
              str(e.status_code))

# An EMPTY list is not malformed — it means "no annotations", and must pass through to the untouched
# response rather than being refused alongside the wrong-type values above.
check("an empty annotations list is not refused, and adds no key",
      "annotation_scope" not in takeoff(layout=LAYOUT, px_per_point=PPP, annotations=[]))

# ---- the LAYOUT is caller-supplied too, and was the other half of the same gap -------------------
# Hardening the traces and annotations and leaving the viewport rectangles was the same mistake in
# miniature: `float()` over a `rect` that is a string, short, missing or null-bearing raised out of
# the hit loop and left the route as a 500. Seven paths, all reachable by a caller.
BAD_LAYOUTS = {
    "a rect that is a string":  {"page": (1, 1), "regions": [{**VP0, "rect": "abc"}]},
    "a rect that is too short": {"page": (1, 1), "regions": [{**VP0, "rect": (1, 2)}]},
    "a rect that is missing":   {"page": (1, 1),
                                 "regions": [{k: v for k, v in VP0.items() if k != "rect"}]},
    "a rect containing null":   {"page": (1, 1), "regions": [{**VP0, "rect": (1, 2, None, 4)}]},
    "regions that is a string": {"page": (1, 1), "regions": "nope"},
    "regions containing null":  {"page": (1, 1), "regions": [None, VP0]},
}
for label, lay in BAD_LAYOUTS.items():
    try:
        with SessionLocal() as db:
            r = takeoff_2d(PID, body={"scale_units_per_px": 0.05, "regions": [TRACE],
                                      "layout": lay, "px_per_point": PPP}, db=db, _sec="tester")
        check(f"{label} is answered, not raised", "scope" in r, str(sorted(r))[:70])
    except Exception as e:                                      # noqa: BLE001 — the point of the test
        check(f"{label} is answered, not raised", False, f"{type(e).__name__}: {e}")

# **The count is the load-bearing part.** Skipping a bad viewport SILENTLY would be worse than the
# crash: a trace over a drawing whose rectangle could not be read would report `unscoped` — "not on
# any drawing" — when the truth is "we could not read the drawing". That is a wrong answer in the
# confident direction, which is the failure this whole module exists to avoid.
with SessionLocal() as db:
    unread = takeoff_2d(PID, body={"scale_units_per_px": 0.05, "regions": [TRACE],
                                   "layout": {"page": (1, 1), "regions": [{**VP0, "rect": "abc"}]},
                                   "px_per_point": PPP}, db=db, _sec="tester")["scope"]
check("an unreadable viewport is COUNTED, so `unscoped` cannot be misread as 'not on a drawing'",
      unread["unreadable_viewports"] == 1, str(unread["unreadable_viewports"]))
check("...and the note says what that means for the traces",
      "could not see" in unread["note"], unread["note"][-80:])
check("a well-formed layout reports ZERO unreadable — the twin, without which the count is free",
      scoped["scope"]["unreadable_viewports"] == 0, str(scoped["scope"]["unreadable_viewports"]))

# A good viewport beside a bad one still scopes: one unreadable rectangle costs that viewport only.
with SessionLocal() as db:
    mixed_vp = takeoff_2d(PID, body={
        "scale_units_per_px": 0.05, "regions": [TRACE], "px_per_point": PPP,
        "layout": {"page": (1, 1), "regions": [VP0, {**VP0, "index": 9, "rect": "abc"}]},
    }, db=db, _sec="tester")["scope"]
check("a readable viewport beside an unreadable one still scopes its traces",
      mixed_vp["regions"][0]["scope"] == "scoped" and mixed_vp["unreadable_viewports"] == 1,
      str(mixed_vp["regions"][0]["scope"]))

# A wrong TYPE for the whole layout is refused, exactly as for `annotations`.
for bad in ("nope", [1, 2, 3], 5):
    try:
        with SessionLocal() as db:
            takeoff_2d(PID, body={"scale_units_per_px": 0.05, "regions": [TRACE], "layout": bad,
                                  "px_per_point": PPP}, db=db, _sec="tester")
        check(f"a non-dict layout ({bad!r}) is refused", False, "no HTTPException")
    except HTTPException as e:
        check(f"a non-dict layout ({bad!r}) is refused", e.status_code == 422, str(e.status_code))

# ---- and the route no longer keeps its own copy of the viewport filter ---------------------------
# The last crash survived hardening the engine because `takeoff_2d` had `_viewports`' body inlined
# for its calibration block. Two derivations of one question, one of them unhardened. Asserted by
# behaviour: the calibration check must see exactly the viewports `scope` did.
with SessionLocal() as db:
    cal = takeoff_2d(PID, body={
        "scale_units_per_px": 0.05, "regions": [TRACE], "px_per_point": PPP,
        "layout": {"page": (1, 1), "regions": [VP0, {**VP0, "index": 9, "rect": "abc"}]},
    }, db=db, _sec="tester")
check("calibration_check covers the READABLE viewports only, from the shared helper",
      len(cal["calibration_check"]) == 1 and cal["calibration_check"][0]["viewport"] == 0,
      str(cal["calibration_check"]))

engine.dispose()
for _f in ("./test_r37_wire_routes.db",):
    if os.path.exists(_f):
        os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("R37 WIRE ROUTES OK - `mep.block_cooling_load` and `takeoff_scope.scope_annotations` were each "
      "the one function in their module their own router did not call, while every sibling was "
      "routed. Both now dispatch at that same altitude. The block load REFUSES a missing or "
      "nonsensical input rather than returning the engine's clamped 0.0 tons or 350x tonnage, and "
      "the engine's clamps are asserted intact so the refusal is provably the route's. Annotations "
      "ride on the layout the traces already use - one coordinate contract, not two.")
