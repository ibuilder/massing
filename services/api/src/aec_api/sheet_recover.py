"""R27-LAYOUT ①(b) — recover a **received** sheet's layout layer from its vectors.

`sheet_layout.sheet_regions()` answers "what occupies which rectangle" for sheets *we* drew, by
keeping the numbers `compose_viewports` already computed. Every sheet that arrives from a consultant
had no such answer: `sheet_extract` reads the text layer and regexes sheet numbers out of it with no
notion of **where on the page** anything sits, so a note, a takeoff and a revision could only ever be
attached to a page number.

**Why deterministic geometry and not a document-layout model.** The layout-analysis paper this ring is
built on reports that pre-training on general document layout *hurts* on construction sheets — 0.589
against 0.727 for the same architecture randomly initialised. Construction sheets are not documents
with unusual furniture, they are a different distribution, and a model that has learned "this is a
paragraph" is confidently wrong about them. Meanwhile the regions on a vector sheet are not inferred
at all: titleblock borders, viewport frames and table rules are literally `re` operators in the
content stream. Detection is what you need once the vectors have been thrown away. Mostly they have
not, and where they have, this says `unknown` rather than guessing.

**What this deliberately does not do.** It never returns a `to_page` transform. The page←world affine
cannot be recovered from a received sheet — the drawing's scale text is a *claim printed on paper*,
not a measured mapping — so `to_page` stays `None` and `measurable` stays `False`. An identity here
would silently report page points as metres, which is the failure `sheet_regions` already refuses.
Any scale text found is reported as a **proposal** for a human or a calibration step to accept: a
takeoff calibrated by a machine that was wrong is worse than one nobody calibrated, because it looks
finished.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

#: Below this many square points a rectangle is a tick, a hatch cell or a table rule, not a region.
_MIN_AREA = 2000.0
#: Rectangles whose corners agree to within this (points) are the same rectangle drawn twice —
#: stroke-then-fill, or a border redrawn per layer. Merging them keeps the count honest.
_SAME = 2.0
#: A drawing border is a rectangle inset from the page by the SAME margin on all four sides. Nearly
#: every sheet has one, and it is furniture: it bounds the content rather than being a region of it.
#: Testing "covers most of the page" alone is not enough — 0.98 lets a border inset by 10pt on an A4
#: sail straight through, which is exactly what happened the first time this ran.
_BORDER_AREA_FRAC = 0.80
_BORDER_MARGIN_TOL = 4.0

#: ADIRO-style vocabulary, matched against the text that falls INSIDE a rectangle. Order matters:
#: the first match wins, so the specific ones precede the generic.
_KINDS: list[tuple[str, str, re.Pattern[str]]] = [
    ("revision_table", "Revision table", re.compile(r"\bREV(?:ISION)?S?\b", re.I)),
    ("key_plan", "Key plan", re.compile(r"\bKEY\s*PLAN\b", re.I)),
    ("legend", "Legend", re.compile(r"\bLEGEND\b|\bSYMBOLS?\b", re.I)),
    ("general_notes", "General notes", re.compile(r"\bGENERAL\s+NOTES\b|\bNOTES\b", re.I)),
    ("scale_bar", "Scale bar", re.compile(r"\bGRAPHIC\s+SCALE\b", re.I)),
    ("titleblock", "Titleblock", re.compile(r"\bSHEET\s*(?:NO|NUMBER|#)|\bDRAWN\s+BY\b|\bPROJECT\s+N[O°]\b", re.I)),
]
#: A scale printed on the sheet: "1:100", "1/4\" = 1'-0\"", "SCALE: 1:50".
_SCALE_RE = re.compile(r"\b1\s*[:/]\s*(\d{1,5})\b")


def _mul(m: tuple, n: tuple) -> tuple:
    """Concatenate two PDF affine matrices [a b c d e f] — m applied first, then n."""
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (a * a2 + b * c2, a * b2 + b * d2,
            c * a2 + d * c2, c * b2 + d * d2,
            e * a2 + f * c2, e * b2 + f * d2)


def _apply(m: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _rects(page: Any, reader: Any) -> list[tuple[float, float, float, float]]:
    """Every axis-aligned rectangle in the page's content stream, in PAGE points.

    Walks `re` operators through the CTM stack (`q`/`Q`/`cm`). A rectangle drawn inside a scaled or
    translated graphics state is meaningless in its own coordinates — reading `re` operands raw is the
    obvious version of this function and it is wrong on every sheet whose views are placed with `cm`,
    which is most of them.
    """
    from pypdf.generic import ContentStream

    try:
        content = ContentStream(page.get_contents(), reader)
    except Exception:
        return []
    ctm: tuple = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    stack: list[tuple] = []
    out: list[tuple[float, float, float, float]] = []
    for operands, op in content.operations:
        try:
            if op == b"q":
                stack.append(ctm)
            elif op == b"Q":
                ctm = stack.pop() if stack else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            elif op == b"cm" and len(operands) >= 6:
                ctm = _mul(tuple(float(v) for v in operands[:6]), ctm)
            elif op == b"re" and len(operands) >= 4:
                x, y, w, h = (float(v) for v in operands[:4])
                # Transform both corners: a negative width or a flipped CTM must still yield a
                # normalised rect, or every downstream containment test silently fails.
                x0, y0 = _apply(ctm, x, y)
                x1, y1 = _apply(ctm, x + w, y + h)
                out.append((min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))
        except (TypeError, ValueError, IndexError):
            continue        # one malformed operator must not lose the whole page
    return out


def _is_border(rect: tuple, pw: float, ph: float) -> bool:
    """A large rectangle inset by an equal margin on all four sides — the sheet's drawing border."""
    x, y, w, h = rect
    if not pw or not ph or w * h < pw * ph * _BORDER_AREA_FRAC:
        return False
    m = (x, pw - (x + w), y, ph - (y + h))
    return max(m) - min(m) <= _BORDER_MARGIN_TOL


def _dedupe(rects: list[tuple], pw: float, ph: float) -> list[tuple]:
    """Drop slivers, drop the page border, and merge rectangles drawn more than once."""
    keep: list[tuple] = []
    for r in rects:
        x, y, w, h = r
        if w * h < _MIN_AREA:
            continue
        if _is_border(r, pw, ph):
            continue
        if any(abs(x - k[0]) <= _SAME and abs(y - k[1]) <= _SAME
               and abs(w - k[2]) <= _SAME and abs(h - k[3]) <= _SAME for k in keep):
            continue
        keep.append(r)
    keep.sort(key=lambda r: r[2] * r[3], reverse=True)
    return keep


def _texts(page: Any) -> list[tuple[float, float, str]]:
    """Text with page positions, via pypdf's text visitor."""
    found: list[tuple[float, float, str]] = []

    def visit(text: str, _cm: Any, tm: Any, _font: Any, _size: Any) -> None:
        s = (text or "").strip()
        if not s:
            return
        try:
            found.append((float(tm[4]), float(tm[5]), s))
        except (TypeError, ValueError, IndexError):
            return

    try:
        page.extract_text(visitor_text=visit)
    except Exception:
        return []
    return found


def _contains(outer: tuple, inner: tuple) -> bool:
    """Is `inner` strictly inside `outer`? (Same rect fails — it is not its own child.)"""
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ix >= ox - _SAME and iy >= oy - _SAME
            and ix + iw <= ox + ow + _SAME and iy + ih <= oy + oh + _SAME
            and iw * ih < ow * oh)


def _inside(rect: tuple, texts: list[tuple[float, float, str]]) -> str:
    x, y, w, h = rect
    return " ".join(t for tx, ty, t in texts if x <= tx <= x + w and y <= ty <= y + h)


def _own(rect: tuple, rects: list[tuple], texts: list[tuple]) -> str:
    """The text a region owns: what falls inside it but not inside one of its children.

    Sheets nest. A revision table sits inside the titleblock column, a legend inside a view. Reading
    all contained text lets the innermost box's vocabulary classify every ancestor — on a real sheet
    that makes the titleblock a "revision table", because the words REV / DATE / DESCRIPTION are
    inside it too. Charging text to the smallest box that holds it is what "which region is this?"
    actually means.
    """
    kids = [r for r in rects if _contains(rect, r)]
    x, y, w, h = rect
    return " ".join(t for tx, ty, t in texts
                    if x <= tx <= x + w and y <= ty <= y + h
                    and not any(kx <= tx <= kx + kw and ky <= ty <= ky + kh for kx, ky, kw, kh in kids))


def _classify(rect: tuple, body: str, pw: float, ph: float) -> tuple[str, str]:
    for kind, label, pat in _KINDS:
        if pat.search(body):
            return kind, label
    x, y, w, h = rect
    # A tall band down the right edge or a wide band along the bottom is a titleblock even when its
    # headings are drawn as vectors rather than text — a scanned-in border with no words inside it.
    if w < pw * 0.30 and h > ph * 0.55 and x + w > pw * 0.66:
        return "titleblock", "Titleblock"
    if h < ph * 0.22 and w > pw * 0.55 and y < ph * 0.25:
        return "titleblock", "Titleblock"
    return "viewport", "View"


def _unknown(pw: float, ph: float, why: str) -> dict:
    """A sheet we cannot read returns a stated unknown, never an empty region list.

    An empty list reads as "this sheet has no regions", which is a claim about the drawing. This is a
    claim about *us* — the same unknown ≠ none rule the fact spine enforces everywhere else.
    """
    return {"page": (pw, ph),
            "regions": [{"kind": "unknown", "label": "Layout not recoverable",
                         "rect": (0.0, 0.0, pw, ph), "basis": "unknown", "reason": why,
                         "scale_text": None, "scale_denom": None,
                         "to_page": None, "measurable": False}],
            "region_count": 1, "viewport_count": 0, "unmeasurable": ["Layout not recoverable"],
            "basis_counts": {"unknown": 1},
            "note": "No vector regions were recoverable from this page; the layout is unknown, "
                    "which is not the same as the sheet having none."}


def recover_regions(pdf: bytes, page_index: int = 0, *, sidecar: dict | None = None) -> dict:
    """Recover the layout layer of a received sheet. Mirrors `sheet_layout.sheet_regions()`'s shape.

    `sidecar` — an authored layout for this same sheet, if we happen to have one. When given, its
    regions are returned instead with `basis: "sidecar"`: numbers we recorded beat numbers we
    recovered, every time, and saying which is which is the entire point of carrying a `basis`.
    """
    if sidecar:
        from aec_data.sheet_layout import sheet_regions
        out = sheet_regions(sidecar)
        for r in out["regions"]:
            r["basis"] = "sidecar"
        out["basis_counts"] = {"sidecar": len(out["regions"])}
        out["note"] = ("`basis: sidecar` — these are the authored numbers for this sheet, not a "
                       "recovery from its rendered output.")
        return out

    from pypdf import PdfReader
    try:
        reader = PdfReader(BytesIO(pdf))
        page = reader.pages[page_index]
        box = page.mediabox
        pw, ph = float(box.width), float(box.height)
    except Exception as exc:                       # unreadable / encrypted / not a PDF
        return _unknown(0.0, 0.0, f"page could not be opened ({type(exc).__name__})")

    rects = _dedupe(_rects(page, reader), pw, ph)
    if not rects:
        # Almost always a scan: the page is one big image and the borders are pixels.
        return _unknown(pw, ph, "no vector rectangles on the page (likely a raster scan)")

    texts = _texts(page)
    regions: list[dict] = []
    for r in rects:
        body = _own(r, rects, texts)
        kind, label = _classify(r, body, pw, ph)
        # The scale is read from the region's OWN text for the same reason its kind is: a titleblock
        # must not inherit the scale printed inside a detail bubble nested in it.
        m = _SCALE_RE.search(body)
        regions.append({
            "kind": kind, "label": label, "rect": r, "basis": "vector",
            # Proposed, never applied. A scale is a claim printed on the sheet; treating it as a
            # measurement is how a takeoff ends up confidently wrong.
            "scale_text": m.group(0) if m else None,
            "scale_denom_proposed": int(m.group(1)) if m else None,
            "scale_denom": None,
            # The world mapping is NOT recoverable from a received sheet. Never identity.
            "to_page": None, "measurable": False,
        })
    counts: dict[str, int] = {}
    for r in regions:
        counts[r["basis"]] = counts.get(r["basis"], 0) + 1
    return {"page": (pw, ph), "regions": regions, "region_count": len(regions),
            "viewport_count": sum(1 for r in regions if r["kind"] == "viewport"),
            "unmeasurable": [r["label"] for r in regions if not r["measurable"]],
            "basis_counts": counts,
            "note": ("`basis: vector` — rectangles read from the page's own content stream, in page "
                     "points. `to_page` is null for every region: the page←world mapping cannot be "
                     "recovered from a received sheet, and is never defaulted to identity. Any "
                     "`scale_denom_proposed` is the scale the sheet CLAIMS, offered for calibration "
                     "to accept — never applied on its own.")}
