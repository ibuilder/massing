"""W11 C1 plan SVG generator: derive a schematic plan drawing from element footprints (walls/columns/
slabs) — the first slice of the construction-document set, no geometry kernel needed.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_drawing.py"""
import os
import re
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import detailing, drawing, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_drawing_test.ifc")
massing.generate_blank_ifc(TMP, name="Drawing Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# a rectangular room of 4 walls + a column
w1 = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st)
edit.add_wall(m, [6, 4], [0, 4], 3.0, 0.2, st)
edit.add_wall(m, [0, 4], [0, 0], 3.0, 0.2, st)
col = edit.add_column(m, [3, 2], 3.0, 0.4, 0.4, st)
# Track-D codes on two elements → keynotes on the plan
detailing.classify(m, [w1], "MasterFormat", "04 20 00", "Unit Masonry")
detailing.classify(m, [col], "MasterFormat", "05 12 00", "Structural Steel Framing")

r = drawing.plan_svg(m, scale=100)
svg = r["svg"]
# drawn elements: 4 walls + 1 column + the blank model's ground slab = 6, each a polygon
assert r["elements"] == 6, r
assert svg.count("<polygon") == 6, svg.count("<polygon")
# valid SVG root + class-styled linework (walls, column, and the slab all present)
assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), svg[:60]
assert svg.count('class="el IfcWall"') == 4 and 'class="el IfcColumn"' in svg and 'class="el IfcSlab"' in svg
assert "PLAN 1:100" in svg
# has real paper dimensions (mm) and a viewBox
assert re.search(r'width="[\d.]+mm"', svg) and 'viewBox="0 0 ' in svg, svg[:200]
# bounds cover the 6×4 m room
assert r["bounds"]["max"][0] - r["bounds"]["min"][0] >= 6.0, r["bounds"]

# C2 dimensions: overall width/height dimension strings present with metric text
assert '<g class="dim">' in svg and svg.count('<g class="dim">') == 2, svg.count('<g class="dim">')
assert 'class="dimt"' in svg and " m<" in svg, "no dimension text"

# C2 keynotes: the two coded elements → 2 legend entries + numbered bubbles + a KEYNOTES legend header
assert r["keynotes"] == 2, r
assert "KEYNOTES" in svg and "04 20 00" in svg and "05 12 00" in svg, "keynote legend missing codes"
assert svg.count('class="kn"') >= 2, "keynote bubbles missing"

# D5 detail callouts: attach a detail drawing to the column → a callout + DETAILS legend keyed to it
detailing.attach_document(m, [col], "Column base detail", location="details/S-501.pdf")
rd = drawing.plan_svg(m, scale=100)
assert rd["details"] == 1, rd
svgd = rd["svg"]
assert "DETAILS" in svgd and "Column base detail" in svgd, "detail legend missing"
assert svgd.count('class="dc"') >= 2, "detail callout symbol(s) missing (plan + legend)"
# D5: the divided-circle bubble carries a REAL sheet ref (from the doc Location basename, not "—")
assert ">S-501<" in svgd, "callout should show the derived sheet number S-501"
# an explicit Identification (detail/sheet key) wins over the location basename (attach to a wall so it
# owns its own callout — a second doc on the column would be secondary and not drawn)
detailing.attach_document(m, [w1], "Anchor bolt detail", identification="A-541/3")
sref = drawing.plan_svg(m, scale=100)["svg"]
assert "A-541/3" in sref, "explicit detail identification should reach the bubble"
# SHEET-LINK: the SVG callout bubble is an anchor carrying its target sheet
assert 'class="sheet-link"' in sref and 'data-sheet="S-501"' in sref, "callout should be an SVG anchor"
# D5 PDF path: a sheet with an attached detail renders the callouts + DETAILS legend without error
_boxes: list = []
pdf_det = drawing.sheet_pdf(m, project="Drawing Test", number="A-101", link_out=_boxes)
assert pdf_det[:5] == b"%PDF-" and len(pdf_det) > 800, "detail-bearing sheet PDF should render"
# SHEET-LINK: the PDF path reports each bubble's hit-box + target sheet for the compiled-set binder
assert _boxes and all(len(b["rect"]) == 4 for b in _boxes), _boxes
assert {b["sheet"] for b in _boxes} >= {"S-501"}, _boxes
# a plan with no attached details reports zero and omits the DETAILS legend
assert "DETAILS" not in svg and r["details"] == 0, "unattached plan should have no details"
# details can be turned off
nod = drawing.plan_svg(m, scale=100, details=False)
assert nod["details"] == 0 and "DETAILS" not in nod["svg"]

# DISC-poché: by_discipline tints the fills with the canonical discipline colors + a legend
dp = drawing.plan_svg(m, scale=100, by_discipline=True)
assert dp["by_discipline"] is True and "DISCIPLINES" in dp["svg"], "discipline legend missing"
assert '.disc .IfcWall{fill:#4B5563' in dp["svg"], "architectural tint missing"      # A grey-blue
assert '.disc .IfcColumn{fill:#2E5A88' in dp["svg"], "structural tint missing"       # S blue
assert '<g class="disc">' in dp["svg"], "poché group missing"
# off by default — the classic monochrome poché is untouched
assert drawing.plan_svg(m, scale=100)["by_discipline"] is False

# keynotes/dimensions can be turned off
plain = drawing.plan_svg(m, scale=100, dimensions=False, keynotes=False)
assert plain["keynotes"] == 0 and '<g class="dim">' not in plain["svg"] and "KEYNOTES" not in plain["svg"]

# plan now also exposes inner content + paper size (for sheet composition)
assert "inner" in r and isinstance(r["paper"], list) and len(r["paper"]) == 2, r.keys()

# --- C3 sheet: ARCH-D border + titleblock, plan nested in a scaled viewport --------------------------
sh = drawing.sheet_svg(m, scale=100, project="Riverside Mixed-Use", number="A-101", title="FIRST FLOOR PLAN")
ssvg = sh["svg"]
assert ssvg.startswith("<svg") and 'width="914.0mm"' in ssvg and 'height="610.0mm"' in ssvg, "not ARCH-D"
# titleblock content
assert ">MASSING<" in ssvg and "Riverside Mixed-Use" in ssvg, "titleblock project missing"
assert ">A-101<" in ssvg and "FIRST FLOOR PLAN" in ssvg and "SCALE 1:100" in ssvg, "titleblock fields missing"
# a north arrow + a nested plan viewport carrying the plan content (keynote legend inside)
assert ">N<" in ssvg and 'preserveAspectRatio="xMidYMid meet"' in ssvg, "no plan viewport"
assert "KEYNOTES" in ssvg, "plan (with keynotes) not embedded in the sheet"
assert sh["number"] == "A-101" and sh["plan"]["elements"] == 6, sh

# --- C3b sheet PDF: valid PDF bytes rendered via reportlab -------------------------------------------
pdf = drawing.sheet_pdf(m, scale=100, project="Riverside Mixed-Use", number="A-101", title="FIRST FLOOR PLAN")
assert isinstance(pdf, (bytes, bytearray)) and pdf[:5] == b"%PDF-", pdf[:16]
assert b"%%EOF" in pdf[-1024:], "PDF not finalized"
assert len(pdf) > 1500, f"PDF too small ({len(pdf)} bytes)"
# a bogus storey → still a valid (border+titleblock-only) PDF, no crash
pdf_empty = drawing.sheet_pdf(m, storey="Nonexistent Level")
assert pdf_empty[:5] == b"%PDF-", "empty-storey PDF invalid"

# --- C4 schedules: door/window/room tables computed from the model ----------------------------------
# add a door + window so the schedules have rows
d1 = edit.add_opening(m, w1, width=0.9, height=2.1, kind="door")
wn1 = edit.add_opening(m, w1, width=1.5, height=1.2, sill=0.9, kind="window", position=[4.5, 0])
sch = drawing.schedules(m)
assert set(sch) == {"doors", "windows", "rooms"}, sch.keys()
assert sch["doors"]["columns"][:3] == ["Mark", "Width (m)", "Height (m)"], sch["doors"]["columns"]
assert len(sch["doors"]["rows"]) >= 1 and len(sch["windows"]["rows"]) >= 1, sch
# the door's width was captured from OverallWidth (0.90 m)
assert any(row[1] == "0.90" for row in sch["doors"]["rows"]), sch["doors"]["rows"]
assert any(row[1] == "1.50" for row in sch["windows"]["rows"]), sch["windows"]["rows"]
# W10-6: room schedule carries IfcElementQuantity depth (perimeter + volume columns from Qto)
assert sch["rooms"]["columns"] == ["No.", "Name", "Area (m²)", "Perimeter (m)", "Volume (m³)", "Level"], \
    sch["rooms"]["columns"]
# W10-6: the schedule exports to CSV (one kind + all-three)
dcsv = drawing.schedule_csv(m, "doors")
lines = [ln for ln in dcsv.splitlines() if ln]
assert lines[0] == "DOOR SCHEDULE" and lines[1].startswith("Mark,"), lines[:2]
assert any(",0.90," in ln for ln in lines), "door width in CSV"
allcsv = drawing.schedule_csv(m)
assert all(t in allcsv for t in ("DOOR SCHEDULE", "WINDOW SCHEDULE", "ROOM SCHEDULE")), "all three sections"
# render a schedule table SVG
dsvg = drawing.schedule_svg(m, "doors")
assert dsvg["svg"].startswith("<svg") and "DOOR SCHEDULE" in dsvg["svg"] and dsvg["rows"] >= 1
assert 'class="sc-h"' in dsvg["svg"] and 'class="sc-g"' in dsvg["svg"]      # header + grid
# unknown kind rejected
try:
    drawing.schedule_svg(m, "bogus")
    bad = False
except ValueError:
    bad = True
assert bad, "unknown schedule kind should raise"

# storey filter: a bogus storey name → no elements → empty-but-valid SVG
empty = drawing.plan_svg(m, storey="Nonexistent Level")
assert empty["elements"] == 0 and empty["svg"].startswith("<svg"), empty

# scale changes the paper size (1:50 is twice the mm of 1:100)
r50 = drawing.plan_svg(m, scale=50)
w100 = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
w50 = float(re.search(r'width="([\d.]+)mm"', r50["svg"]).group(1))
assert w50 > w100, (w50, w100)

# C6: schedules laid out on an issuable PDF sheet — add a door + rooms so the tables have rows
edit.add_opening(m, w1, width=0.9, height=2.1, kind="door")
edit.add_spaces(m, rooms_per_storey=2, ceiling_height=3.0)
sched_pdf = drawing.schedule_pdf(m, project="Drawing Test", number="A-601")
assert sched_pdf[:4] == b"%PDF" and len(sched_pdf) > 800, "schedule sheet should be a non-trivial PDF"
# a subset (rooms only) also renders
rooms_only = drawing.schedule_pdf(m, kinds=["rooms"])
assert rooms_only[:4] == b"%PDF", "rooms-only schedule PDF"
# and the plan sheet PDF still renders after the titleblock refactor
sheet_pdf = drawing.sheet_pdf(m, project="Drawing Test", number="A-101")
assert sheet_pdf[:4] == b"%PDF" and len(sheet_pdf) > 800, "plan sheet PDF"

if os.path.exists(TMP):
    os.remove(TMP)

print("DRAWING OK - plan_svg derives a schematic plan from footprints (4 walls + column + slab -> 6 "
      "class-styled polygons); C2 adds overall width/height DIMENSION strings (metric) + KEYNOTE bubbles "
      "+ legend from Track-D classification codes (04 20 00 / 05 12 00); C3 composes an ARCH-D SHEET with "
      "a titleblock (MASSING / project / A-101 / scale / north arrow) nesting the plan in a scaled viewport; "
      "storey filter -> empty sheet; scale drives paper size; dims/keynotes toggle off. No geometry kernel.")
