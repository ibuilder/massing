"""R27-LAYOUT ② — a takeoff belongs to the view it was traced on.

`takeoff2d.quantify` applies ONE scale to a whole sheet. That is right for a sheet holding a single
drawing and quietly wrong for every other one: a plan at 1:100 beside a detail at 1:20 gets the
detail priced five times over, and nothing checked a traced polygon was even on a drawing rather than
in the titleblock.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_takeoff_scope.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_takeoff_scope.db"
os.environ["STORAGE_DIR"] = "./test_storage_takeoff_scope"
if os.path.exists("./test_takeoff_scope.db"):
    os.remove("./test_takeoff_scope.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import takeoff_scope as ts  # noqa: E402

# Two viewports in PAGE POINTS: a plan at 1:100 on the left, a detail at 1:20 on the right.
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
PPP = 2.0                              # the sheet was rasterised at 2 screen pixels per page point
def box(x, y, w, h):                   # a traced rectangle in SCREEN PIXELS
    return {"category": "generic_area",
            "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}

# --- pixels are not points -----------------------------------------------------------------------
def test_without_the_render_factor_nothing_is_checked():
    # Assuming 1:1 would put every trace in the page corner and report it confidently.
    r = ts.scope([box(200, 500, 100, 100)], LAYOUT)
    assert r["regions"][0]["scope"] == "unknown", r["regions"]
    assert r["priceable"] == 0 and not r["all_scoped"]
    assert "NOTHING was checked" in r["note"], r["note"]
    assert "page corner" in r["regions"][0]["detail"]

# --- the ordinary case ---------------------------------------------------------------------------
def test_a_trace_inside_one_viewport_is_scoped_and_carries_its_scale():
    r = ts.scope([box(200, 500, 400, 400)], LAYOUT, px_per_point=PPP)   # → pts (100,250)-(300,450)
    row = r["regions"][0]
    assert row["scope"] == "scoped" and row["viewport"] == 0, row
    assert row["scale_denom"] == 100 and row["viewport_label"] == "LEVEL 1 PLAN", row
    assert r["priceable"] == 1 and r["all_scoped"], r

def test_the_detail_is_scoped_to_its_own_scale_not_the_plan_s():
    # The whole point: one sheet, two scales. Pricing the detail at 1:100 overstates it fivefold.
    r = ts.scope([box(2500, 500, 200, 200)], LAYOUT, px_per_point=PPP)  # → pts (1250,250)-(1350,350)
    assert r["regions"][0]["viewport"] == 1 and r["regions"][0]["scale_denom"] == 20, r["regions"]

# --- the two refusals ------------------------------------------------------------------------------
def test_a_trace_off_every_drawing_is_UNSCOPED_never_quietly_priced():
    # In the titleblock band. A quantity measured off a legend is not a quantity.
    r = ts.scope([box(200, 100, 100, 40)], LAYOUT, px_per_point=PPP)
    assert r["regions"][0]["scope"] == "unscoped", r["regions"]
    assert r["priceable"] == 0 and not r["all_scoped"]
    assert "not a quantity" in r["regions"][0]["detail"]

def test_a_trace_crossing_two_viewports_is_AMBIGUOUS():
    # Two scales apply to one polygon; choosing either is a coin toss presented as a measurement.
    r = ts.scope([box(1900, 500, 700, 200)], LAYOUT, px_per_point=PPP)  # spans pts 950 → 1300
    row = r["regions"][0]
    assert row["scope"] == "ambiguous", row
    assert row["candidates"] == [0, 1], row
    assert r["priceable"] == 0

def test_none_of_the_three_non_pass_states_counts_as_a_pass():
    r = ts.scope([box(200, 500, 400, 400), box(200, 100, 100, 40)], LAYOUT, px_per_point=PPP)
    assert r["priceable"] == 1 and len(r["regions"]) == 2
    assert not r["all_scoped"], "one scoped out of two is not all scoped"
    assert "none of the three is a pass" in r["note"]

def test_an_empty_trace_is_unknown_not_unscoped():
    r = ts.scope([{"category": "generic_area", "points": []}], LAYOUT, px_per_point=PPP)
    assert r["regions"][0]["scope"] == "unknown", r["regions"]

def test_a_stray_vertex_does_not_fail_an_otherwise_clean_trace():
    # Hand traces nick a border by a pixel routinely; failing on that makes the check something
    # operators route around rather than use.
    poly = {"category": "generic_area",
            "points": [[200, 500], [1000, 500], [1000, 900], [200, 900],
                       [2500, 520]]}          # one stray point in the other viewport (1 of 5 = 20%)
    r = ts.scope([poly], LAYOUT, px_per_point=PPP)
    assert r["regions"][0]["scope"] == "ambiguous", "20% in another viewport is genuinely ambiguous"
    # ...but a SINGLE stray vertex out of twenty (5%) still has one clean home. This is the case the
    # ratio exists for, and asserting `ambiguous` here would contradict the test's own name.
    tight = {"category": "generic_area",
             "points": [[200, 500]] * 19 + [[2500, 520]]}
    row = ts.scope([tight], LAYOUT, px_per_point=PPP)["regions"][0]
    assert row["scope"] == "scoped" and row["viewport"] == 0, row

# --- checking a calibration against a scale we already know ------------------------------------------
def test_a_matching_calibration_agrees():
    # 1 page point = 0.352778 mm; at 1:100 that is 35.2778 mm = 0.0352778 m per point, ÷2 px/pt.
    expect = (0.352778 * 100 / 1000.0) / PPP
    c = ts.check_calibration(expect, 100, px_per_point=PPP)
    assert c["checked"] and c["agrees"], c
    assert "matches the scale this sheet was drawn at" in c["detail"]

def test_a_wrong_calibration_is_REPORTED_not_silently_overridden():
    expect = (0.352778 * 100 / 1000.0) / PPP
    c = ts.check_calibration(expect * 1.5, 100, px_per_point=PPP)
    assert c["checked"] and c["agrees"] is False, c
    assert c["relative_error"] > 0.4, c
    # The authored number is NOT substituted: the raster may genuinely have been rescaled on import,
    # and replacing a measurement without saying so would hide that.
    assert "NOT substituted automatically" in c["detail"], c["detail"]

def test_small_disagreement_is_noise_not_a_finding():
    expect = (0.352778 * 100 / 1000.0) / PPP
    assert ts.check_calibration(expect * 1.005, 100, px_per_point=PPP)["agrees"] is True

def test_a_fit_to_rect_viewport_has_no_authored_number_to_check():
    c = ts.check_calibration(0.01, None, px_per_point=PPP)
    assert c["checked"] is False and c["agrees"] is None, c
    assert "no fixed paper scale" in c["detail"]

def test_without_the_render_factor_no_comparison_is_possible():
    c = ts.check_calibration(0.01, 100)
    assert c["checked"] is False and c["agrees"] is None, c


# --- R27-LAYOUT (3): a note attaches to the view it governs -------------------------------------------
def test_a_note_is_attached_to_the_view_it_governs_not_the_sheet():
    # A note about the plan and a note about the section sit centimetres apart on one page; a sheet
    # number cannot tell them apart, which is what keeps received drawings out of every engine.
    r = ts.scope_annotations(
        [{"id": "N1", "kind": "keynote", "x": 400, "y": 700},      # → pt (200,350), in the plan
         {"id": "N2", "kind": "keynote", "x": 2600, "y": 700}],    # → pt (1300,350), in the detail
        LAYOUT, px_per_point=PPP)
    assert r["regions"][0]["viewport"] == 0 and r["regions"][0]["annotation_id"] == "N1", r["regions"]
    assert r["regions"][1]["viewport"] == 1 and r["regions"][1]["kind"] == "keynote", r["regions"]

def test_a_revision_cloud_scopes_by_its_outline():
    cloud = {"id": "R1", "kind": "cloud",
             "points": [[400, 700], [800, 700], [800, 900], [400, 900]]}
    assert ts.scope_annotations([cloud], LAYOUT, px_per_point=PPP)["regions"][0]["viewport"] == 0

def test_a_sheet_wide_stamp_is_UNSCOPED_and_that_is_correct_not_a_failure():
    # A drawing-number stamp governs the sheet, not any one view. `unscoped` is the right answer here.
    r = ts.scope_annotations([{"id": "S1", "kind": "stamp", "x": 400, "y": 120}],
                             LAYOUT, px_per_point=PPP)
    assert r["regions"][0]["scope"] == "unscoped", r["regions"]
    assert "governs the sheet rather than any one view" in r["note"], r["note"]

def test_annotation_scoping_reuses_the_SAME_engine_as_traces():
    # An annotation and a traced polygon pose the identical question -- which drawing is this on. A
    # second placement routine would give two answers to one question and guarantee they drift.
    note = {"id": "N", "x": 400, "y": 700}
    as_region = box(400, 700, 0, 0)
    a = ts.scope_annotations([note], LAYOUT, px_per_point=PPP)["regions"][0]
    b = ts.scope([as_region], LAYOUT, px_per_point=PPP)["regions"][0]
    assert a["scope"] == b["scope"] and a["viewport"] == b["viewport"], (a, b)

def test_annotations_without_the_render_factor_are_unknown_too():
    r = ts.scope_annotations([{"id": "N", "x": 400, "y": 700}], LAYOUT)
    assert r["regions"][0]["scope"] == "unknown" and r["priceable"] == 0, r["regions"]


for name, fn in sorted(list(globals().items())):
    if name.startswith("test_") and callable(fn):
        fn()

print("R27-LAYOUT (2)+(3) OK - a takeoff now belongs to the VIEW it was traced on. takeoff2d applies ONE "
      "scale to a whole sheet, which is right for a sheet holding one drawing and quietly wrong for "
      "every other: a plan at 1:100 beside a detail at 1:20 prices the detail fivefold, and nothing "
      "checked a polygon was even ON a drawing rather than in the titleblock. PIXELS ARE NOT POINTS - "
      "traces come from a raster in screen pixels and viewports are in PDF points, so without the "
      "render factor this REFUSES to scope rather than assuming 1:1, which would put every trace in "
      "the page corner and report it confidently. Three outcomes and only one is priceable: inside "
      "exactly one viewport is SCOPED and carries that viewport's own scale; off every drawing is "
      "UNSCOPED, never quietly priced, because a quantity measured off a legend is not a quantity; "
      "and crossing two viewports is AMBIGUOUS, because two scales apply to one polygon and choosing "
      "either is a coin toss presented as a measurement. A stray vertex does not fail an otherwise "
      "clean trace, since hand traces nick borders routinely and a check operators route around is "
      "worth nothing. And on a sheet WE drew, the scale is not something to measure but something we "
      "already know: a calibration that disagrees is REPORTED, and the authored number is NOT "
      "substituted automatically - the raster may genuinely have been rescaled on import, and "
      "overriding a measurement without saying so would hide that. AND (3): notes, keynotes "
      "and revision clouds now attach to the VIEW they govern rather than to a sheet number - "
      "a note about the plan and a note about the section sit centimetres apart on one page. "
      "That reuses the SAME engine as traces rather than growing a parallel one, because an "
      "annotation and a polygon pose the identical question and two placement routines would "
      "give two answers to it and drift. A sheet-wide stamp comes back `unscoped`, which is "
      "the correct answer and not a failure: it governs the sheet, not any one view.")
