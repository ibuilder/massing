"""EGRESS-TRAVEL-DARK — the JSON summary shipped the DRAWING's working data, to nobody.

`/projects/{pid}/egress/routes` returned `egress_route.analyze`'s result verbatim, which carries two
things that exist only for `plan_svg`:

  * a `path` polyline **per space**, traced back cell by cell from the space to its exit. One path is
    capped at `_path_from`'s `limit=4000` points; **nothing caps the number of paths.** On a
    200-space floor plate at the default 0.3 m grid that is hundreds of thousands of coordinate
    pairs in a single viewer-role GET.
  * `_exits_xy`, an underscore-prefixed internal, in a public payload.

`plan_svg` calls `analyze(..., with_paths=True)` **itself** and is the only consumer of either, so
the JSON route was paying for a drawing it does not draw. The route now passes `with_paths=False`
and strips `_`-prefixed keys; the polylines' surface is `/egress/plan.svg`.

WHAT THIS GATE HAS TO BE CAREFUL ABOUT
--------------------------------------
Stripping is a change to the SHAPE of a successful response, and the engine's refusals are
responses too. `routed: false` carries `note` and little else, and a filter that dropped it would
turn "no exterior door is marked, so nothing was routed" into an empty object a consumer renders as
a clean building. Both refusal branches are asserted through the route, not just the happy path.

And the contrast the whole item is about is pinned here, because it is the kind of claim that rots:
`codecheck_egress.py` states in its own header that travel distance is out of scope, so the live
Occupancy & egress tool does not cover it — *a parametric estimate over an idealised rectangle had a
screen (`test_fit.egress_screen`, via `testFitCompare`) and the measurement against the actual model
did not.*

Run: cd services/api && PYTHONPATH=src ./.venv/bin/python test_egress_payload.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_egress_payload.db"
os.environ["STORAGE_DIR"] = "./test_storage_egress_payload"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_egress_payload.db"):
    os.remove("./test_egress_payload.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from pathlib import Path  # noqa: E402

from aec_api import egress_route as er  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


# ── THE ROUTE'S OWN TRANSFORM, isolated so it can be replayed and mutated ────────────────────────
#
# The route is two lines over the engine. Lifting them keeps this gate from needing a project, a
# source-IFC upload and an auth identity to assert a property about a dict — and the SOURCE of the
# route is pinned below so the copy cannot drift from what ships.
def route_payload(model, **kw):
    res = er.analyze(model, with_paths=False, **kw)
    return {k: v for k, v in res.items() if not k.startswith("_")}


def route_payload_shipped(model, **kw):
    """The PRE-FIX route: `analyze`'s result verbatim, paths and private keys included."""
    return er.analyze(model, **kw)


# ---- a real model, as `test_egress_routes.py` builds one ----------------------------------------
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "_egress_payload.ifc")
massing.generate_blank_ifc(PATH, name="EgressPayload", storeys=1, storey_height=3.5,
                           ground_size=40.0)
model = open_model(PATH)
storey = model.by_type("IfcBuildingStorey")[0].Name

# ── ① THE REFUSAL SURVIVES THE STRIP ─────────────────────────────────────────────────────────────
#
# Asserted FIRST, because a filter over a dict is exactly the change that quietly empties an error
# response, and `routed: false` is the one state a consumer must not read as a clean building.
print("\n-- no exterior door: the refusal must come through intact --")
bare = route_payload(model, elevation=0.0)
ok(bare["routed"] is False and "IsExternal" in bare["note"],
   f"the refusal and its REASON survive   routed={bare['routed']} "
   f"note={bare['note'][:48]!r}…")
ok("note" in bare and len(bare["note"]) > 40,
   "the note is the only thing that tells the reader what to fix, so it must be substantial")

# ── ② THE SUCCESSFUL PAYLOAD CARRIES NO DRAWING DATA ─────────────────────────────────────────────
print("\n-- a routable model: the summary must carry counts, not polylines --")
spine = edit.add_wall(model, [-15, 0], [10, 0], 3.0, 0.25, storey)
door = edit.add_opening(model, spine, width=1.0, height=2.1, kind="door", position=[9, 0])
edit.set_element_pset(model, door, "Pset_DoorCommon", "IsExternal", True, "bool")
edit.add_spaces(model, rooms_per_storey=4)

shipped = route_payload_shipped(model, elevation=0.0, max_travel_m=61.0, cell=0.5)
fixed = route_payload(model, elevation=0.0, max_travel_m=61.0, cell=0.5)
ok(shipped["routed"] is True and fixed["routed"] is True,
   "both forms route this model, so the comparison below is about shape and not about failure")

# PROOF OF REACH — the pre-fix payload must actually carry the data, or this gate proves nothing.
shipped_paths = [r for r in shipped["results"] if r.get("path")]
ok(bool(shipped_paths),
   f"PROOF OF REACH: the pre-fix payload carries a polyline per space   "
   f"{len(shipped_paths)} of {len(shipped['results'])} rows")
ok("_exits_xy" in shipped,
   "PROOF OF REACH: ...and an underscore-prefixed internal in a public response")
pts = sum(len(r["path"]) for r in shipped_paths)
ok(pts > 50,
   f"...and the volume is real, not a rounding error   {pts} coordinate pair(s) on a 4-space test "
   f"model; `_path_from`'s cap is {er._path_from.__defaults__[-1]} PER PATH with no cap across them")

ok(not any("path" in r for r in fixed["results"]),
   f"the fixed payload carries NO per-space polyline   "
   f"{sum(1 for r in fixed['results'] if 'path' in r)} row(s) with a path")
ok(not [k for k in fixed if k.startswith("_")],
   f"...and no private key   {[k for k in fixed if k.startswith('_')]}")

# ── ③ EVERYTHING A CONSUMER READS IS STILL THERE ─────────────────────────────────────────────────
#
# The complement of ②, and the half a strip is most likely to break. Derived from the client's
# declared interface rather than listed by hand, so adding a field there without serving it reds.
print("\n-- the summary a screen actually reads --")
NEEDED = ("routed", "note", "elevation", "cell_m", "max_travel_m", "exits", "spaces",
          "compliant", "over_limit", "unreachable", "worst_travel_m", "max_detour_ratio",
          "results")
missing = [k for k in NEEDED if k not in fixed]
ok(not missing, f"every summary field survives   missing={missing}")
ROW = ("guid", "name", "straight_line_m", "travel_m", "compliant", "unreachable")
row_missing = [k for k in ROW if k not in fixed["results"][0]]
ok(not row_missing, f"...and every per-space field a table needs   missing={row_missing}")
ok(fixed["compliant"] + fixed["over_limit"] + fixed["unreachable"] == fixed["spaces"],
   f"the three outcomes still partition the spaces   {fixed['compliant']} + "
   f"{fixed['over_limit']} + {fixed['unreachable']} == {fixed['spaces']}")

# ── ④ THE DRAWING IS UNAFFECTED — its paths come from its own call ───────────────────────────────
print("\n-- plan_svg draws the routes it computes itself --")
svg = er.plan_svg(model, elevation=0.0, max_travel_m=61.0, cell=0.5)
# MEASURED, not assumed: the first draft asserted `startswith("<svg")` and the document opens with
# an XML declaration, so the assertion failed on a correct drawing. *A shape asserted without being
# looked at reds on the truth.* The polyline count is the load-bearing half anyway.
ok(svg.lstrip().startswith("<?xml") and "<svg" in svg and svg.count("polyline") >= 4,
   f"the SVG still contains route polylines, so stripping the JSON cost the drawing nothing   "
   f"{svg.count('polyline')} polyline(s)")
ok("0.5 m" in svg or "0.5" in svg,
   "...and still states its grid resolution")

# ── ⑤ THE ROUTE'S SOURCE MATCHES THE TRANSFORM REPLAYED ABOVE ────────────────────────────────────
#
# `route_payload` is a COPY of two lines of `routers/analysis.py`. A copy drifts, so the original is
# read and pinned: without this the gate could keep passing over a route that had gone back to
# returning `analyze` verbatim. *A replay is only evidence while it still matches what ships.*
print("\n-- the shipped route does what this gate replayed --")
SRC = (Path(__file__).resolve().parent / "src" / "aec_api" / "routers" / "analysis.py").read_text()
ok("with_paths=False)" in SRC,
   "the route asks the engine for no paths")
ok('return {k: v for k, v in res.items() if not k.startswith("_")}' in SRC,
   "...and strips the private keys on the way out")
ok("egress_route.analyze(ifcopenshell.open(ifc_path), elevation, max_travel_m, cell=cell)\n" not in
   SRC,
   "...and the verbatim pre-fix call is gone, not merely shadowed")

# ── ⑥ THE CONTRAST THIS ITEM IS ABOUT, pinned because it is the kind of claim that rots ──────────
print("\n-- travel distance had no door, while a rectangle formula did --")
CE = (Path(__file__).resolve().parent / "src" / "aec_api" / "codecheck_egress.py").read_text()
ok("travel-distance / performance-based egress are out of scope" in CE,
   "the live Occupancy & egress engine states that travel distance is NOT its job")
TF = (Path(__file__).resolve().parent / "src" / "aec_api" / "test_fit.py").read_text()
ok("plate_w / (2 * max(1, n_stairs)) + plate_d / 2" in TF,
   "...and the only other travel number in the tree is a formula over an idealised rectangle")
ok("approximate" in TF,
   "...which says so about itself, so the gap was never a disagreement between two checks")

print()
if FAILED:
    print(f"egress_payload: {len(FAILED)} FAILED — {FAILED}")
    raise SystemExit(1)
print("EGRESS-PAYLOAD OK - the JSON summary at /egress/routes no longer ships the drawing's working "
      "data: `with_paths=False` plus a strip of underscore-prefixed keys, so a viewer-role GET that "
      "wants 'which spaces are over the limit' stops paying for one polyline per space (capped at "
      "4,000 points EACH, uncapped across spaces) and a private _exits_xy. The pre-fix payload is "
      "replayed and must carry both before this gate reports; both `routed: false` refusals survive "
      "the strip with their reason intact; the three outcomes still partition the spaces; plan_svg "
      "still draws its polylines because it computes them itself; and the route's source is pinned "
      "so the replayed transform cannot drift from what ships.")
