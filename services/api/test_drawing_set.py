"""Compiled drawing-set PDF: the whole set (cover + per-storey plans + schedules) merged into ONE
multi-page PDF — the single-file handover deliverable.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_drawing_set.py"""
import io
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import drawingset  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402
from pypdf import PdfReader  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "_drawing_set_test.ifc")
# a 3-storey model with walls + a door/window (so the schedules page has rows)
massing.generate_blank_ifc(TMP, name="Set Test", storeys=3, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
w = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st)
edit.add_opening(m, w, width=0.9, height=2.1, kind="door")
edit.add_opening(m, w, width=1.5, height=1.2, sill=0.9, kind="window", position=[3, 0])
edit.add_spaces(m, rooms_per_storey=2, ceiling_height=3.0)
m.write(TMP)

# --- the whole set compiles to one multi-page PDF ---------------------------------------------------
pdf = drawingset.compiled_set_pdf(TMP, "Set Test Tower", scale=200, max_sheets=16)
assert pdf[:5] == b"%PDF-", pdf[:16]
pages = len(PdfReader(io.BytesIO(pdf)).pages)
# 1 cover + 3 storey plans + 1 schedules = 5 pages
assert pages == 5, f"expected 5 pages (cover + 3 plans + schedules), got {pages}"

# --- a tall tower samples storeys evenly, capped by max_sheets --------------------------------------
massing.generate_blank_ifc(TMP, name="Tall", storeys=30, storey_height=3.0, ground_size=20.0)
tall = drawingset.compiled_set_pdf(TMP, "Tall Tower", scale=400, max_sheets=8, include_schedules=False)
tall_pages = len(PdfReader(io.BytesIO(tall)).pages)
# cover + 8 sampled plans = 9 (30 storeys sampled down to 8; no schedules)
assert tall_pages == 9, f"expected 9 pages (cover + 8 sampled plans), got {tall_pages}"

# --- schedules can be omitted -----------------------------------------------------------------------
massing.generate_blank_ifc(TMP, name="Two", storeys=2, storey_height=3.0, ground_size=15.0)
no_sched = drawingset.compiled_set_pdf(TMP, "Two", scale=200, max_sheets=16, include_schedules=False)
assert len(PdfReader(io.BytesIO(no_sched)).pages) == 3, "cover + 2 plans, no schedules"

if os.path.exists(TMP):
    os.remove(TMP)

print("DRAWING-SET OK - compiled_set_pdf merges the whole set into ONE multi-page PDF: a cover / "
      "sheet-index, a floor plan per storey (A-1xx), and the door/window/room schedules (A-601) — 3-storey "
      "model -> 5 pages. A 30-storey tower samples storeys evenly down to max_sheets (cover + 8 = 9 pages); "
      "schedules can be omitted. Reuses the proven single-sheet renderers + pypdf merge. The GC/architect "
      "handover deliverable.")
