"""R27-LAYOUT (b): recover a RECEIVED sheet's layout layer from its vectors.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sheet_recover.py"""
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from reportlab.pdfgen import canvas  # noqa: E402

from aec_api import sheet_recover as sr  # noqa: E402

PW, PH = 842.0, 595.0        # A4 landscape, points
ok = 0


def check(cond, label, detail=""):
    global ok
    assert cond, f"FAIL  {label}  {detail}"
    ok += 1
    print(f"PASS  {label}" + (f"   {detail}" if detail else ""))


def sheet(*, with_cm=False, blank=False) -> bytes:
    """A synthetic received sheet, drawn by reportlab — a THIRD-PARTY writer.

    The point of generating rather than fixturing: the bytes are produced by reportlab and parsed by
    pypdf, two independent implementations of the PDF spec. A round-trip through one library's own
    writer+reader pair passes just as happily on a wrong understanding of the format — that is exactly
    how the 4D binding shipped encoding the wrong IFC relation while its own test round-tripped
    perfectly.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PW, PH))
    if blank:                                   # a "scan": one image-less page with no vector rects
        c.drawString(40, 40, "scanned sheet")
        c.showPage(); c.save(); return buf.getvalue()

    c.rect(10, 10, PW - 20, PH - 20)            # full-bleed border — furniture, must be dropped
    # titleblock: tall band down the right edge, with the words a titleblock has
    c.rect(PW - 200, 20, 180, PH - 40)
    c.setFont("Helvetica", 8)
    c.drawString(PW - 190, PH - 60, "SHEET NO: A-101")
    c.drawString(PW - 190, PH - 80, "SCALE: 1:100")
    c.drawString(PW - 190, PH - 100, "DRAWN BY: MME")
    # revision table, inside the titleblock column
    c.rect(PW - 195, 40, 170, 90)
    c.drawString(PW - 190, 115, "REV  DATE  DESCRIPTION")
    if with_cm:
        # A viewport placed through a scaled+translated graphics state. Reading `re` operands raw
        # would report this rectangle in the wrong place (or the wrong size) entirely.
        c.saveState()
        c.translate(60, 60)
        c.scale(2.0, 2.0)
        c.rect(0, 0, 150, 120)                  # → page rect (60,60,300,240)
        c.restoreState()
    else:
        c.rect(60, 60, 300, 240)
    c.showPage(); c.save()
    return buf.getvalue()


# ---- vector recovery ------------------------------------------------------------------------------
out = sr.recover_regions(sheet())
check(out["page"] == (PW, PH), "page size is read from the MediaBox", f"got {out['page']}")
check(out["region_count"] >= 3, "the sheet's rectangles are recovered", f"{out['region_count']} regions")
check(all(r["basis"] == "vector" for r in out["regions"]),
      "every recovered region is labelled basis=vector", "not 'authored' — we read these, we did not draw them")
kinds = {r["kind"] for r in out["regions"]}
check("titleblock" in kinds, "the titleblock is classified", f"kinds={sorted(kinds)}")
check("revision_table" in kinds, "the revision table is classified by its own words")
check("viewport" in kinds, "the drawing area is classified as a viewport")

# The drawing border must NOT survive as a region. Assert against the rect we actually DREW
# (10, 10, PW-20, PH-20), not against a fraction-of-page threshold: the first version of this check
# re-used the implementation's own 0.98 constant and passed while the border sat in the output
# classified as a viewport. A test that restates the code's threshold measures nothing.
check(not any(abs(r["rect"][0] - 10) < 2 and abs(r["rect"][1] - 10) < 2
              and abs(r["rect"][2] - (PW - 20)) < 2 and abs(r["rect"][3] - (PH - 20)) < 2
              for r in out["regions"]),
      "the drawing border is dropped",
      f"drew (10,10,{PW - 20:.0f},{PH - 20:.0f}); got {[tuple(round(v) for v in r['rect']) for r in out['regions']]}")

# ---- the honesty rules ----------------------------------------------------------------------------
check(all(r["to_page"] is None for r in out["regions"]),
      "to_page is null for EVERY region", "the page<-world affine is not recoverable from a received sheet")
check(all(r["measurable"] is False for r in out["regions"]),
      "nothing claims to be measurable")
tb = next(r for r in out["regions"] if r["kind"] == "titleblock")
check(tb["scale_denom_proposed"] == 100, "the printed scale is recovered as a PROPOSAL",
      f"scale_text={tb['scale_text']!r}")
check(tb["scale_denom"] is None, "...and scale_denom stays null until something accepts it",
      "a takeoff auto-calibrated wrong looks finished, which is worse than uncalibrated")

# ---- the CTM path: a rect drawn inside a scaled graphics state ------------------------------------
cm = sr.recover_regions(sheet(with_cm=True))
vp = [r for r in cm["regions"] if r["kind"] == "viewport"]
check(bool(vp), "a viewport placed through `cm` is still found")
hit = [r for r in vp if abs(r["rect"][2] - 300) < 3 and abs(r["rect"][3] - 240) < 3]
check(bool(hit), "...and reported at its PAGE size, not its local one",
      f"expected 300x240 after a 2x scale of 150x120; got {[(round(r['rect'][2]), round(r['rect'][3])) for r in vp]}")

# ---- unknown, never empty -------------------------------------------------------------------------
blank = sr.recover_regions(sheet(blank=True))
check(blank["regions"] and blank["regions"][0]["kind"] == "unknown",
      "a sheet with no vectors returns a stated unknown", "never an empty region list")
check(blank["basis_counts"] == {"unknown": 1}, "...counted as unknown")
check("not the same as the sheet having none" in blank["note"],
      "...and says so", "unknown != none is the rule ten engines already enforce")

bad = sr.recover_regions(b"this is not a pdf")
check(bad["regions"][0]["basis"] == "unknown", "an unreadable file is unknown, not an exception")

# ---- sidecar beats recovery -----------------------------------------------------------------------
from aec_data.sheet_layout import compose_viewports  # noqa: E402

lay = compose_viewports([], [{"label": "PLAN", "kind": "plan", "polylines": []}], page="A1")
side = sr.recover_regions(sheet(), sidecar=lay)
check(all(r["basis"] == "sidecar" for r in side["regions"]),
      "an authored layout is used when we have one", "numbers we recorded beat numbers we recovered")
check(side["region_count"] == len(lay["views"]) + 2,
      "...and it is the authored region set, not the recovered one",
      f"{side['region_count']} regions for {len(lay['views'])} view(s) + titleblock + drawable")

print(f"\ntest_sheet_recover OK  ({ok} checks)")
print("R27-LAYOUT (b): a received sheet's regions are read from its own content stream, so a note, a "
      "takeoff and a revision can attach to a VIEW rather than to a page number. Deterministic vector "
      "geometry, not a document-layout model - the paper's ablation shows general document pre-training "
      "is a NEGATIVE prior on construction sheets (0.589 vs 0.727 randomly initialised), and the regions "
      "are literally `re` operators anyway. Rectangles are transformed through the CTM stack, because "
      "reading `re` operands raw is the obvious version and it is wrong on every sheet whose views are "
      "placed with `cm`. to_page is null for every region and never identity: the page<->world mapping "
      "cannot be recovered from a received sheet, and an identity would report page points as metres. A "
      "printed scale is a PROPOSAL, never applied. A page with no vectors returns a stated unknown "
      "rather than an empty list, because an empty list is a claim about the drawing while unknown is a "
      "claim about us.")
