"""A/E/C stamps — submittal review, inspection, status, and professional seals — rendered onto PDFs.

Two legally distinct classes of stamp, per US A/E/C practice:

  * **Review / action / inspection / status stamps** — informational annotations. A *submittal review*
    stamp carries reviewer, firm, design-professional-in-responsible-charge, date, and a **disposition**
    from a configurable vocabulary (EJCDC or CSI), plus the mandatory design-conformance **disclaimer**
    (tracks AIA A201-2017 4.2.7 / B101 3.6.4.2 — review is only for general conformance with the design
    concept; the contractor keeps responsibility for quantities, dimensions, fabrication, means/methods,
    and trade coordination).
  * **Professional seal + signature** — a licensee's seal block, rendered *visibly* AND then signed with
    a tamper-evident PAdES digital signature (``esign.digitally_sign``) applied **last**, so any later
    change is detectable. The self-signed platform certificate is tamper-evidence / demonstration, **not**
    board-accepted sealing — a licensee's own certificate (``ESIGN_P12``) under their exclusive control is
    required for regulatory compliance (NCEES Model Rules; state boards).

Rendering uses **reportlab** (BSD-ish permissive) to draw a page-sized overlay, composited with **pypdf**
(BSD). NO PyMuPDF (AGPL). Byte-in / byte-out; nothing here touches the DB.
"""
from __future__ import annotations

import io
from typing import Any

# --- Disposition vocabularies (seed both; a firm picks per stamp) -----------------------------------
# EJCDC-recommended action-submittal dispositions (Kevin O'Beirne, PE) + informational set.
DISPOSITIONS_EJCDC = ["Approved", "Approved as Noted", "Revise and Resubmit", "Rejected"]
DISPOSITIONS_EJCDC_INFO = ["Accepted", "Unacceptable"]
# The older CSI vocabulary, still in wide use.
DISPOSITIONS_CSI = ["No Exceptions Taken", "Make Corrections Noted", "Amend and Resubmit",
                    "Rejected", "For Record Only"]

# Standard design-conformance disclaimer (paraphrase tracking AIA A201 4.2.7 / EJCDC C-700 7.16.C).
DISCLAIMER = (
    "Review is only for general conformance with the design concept and general compliance with the "
    "Contract Documents. Markings do not authorize changes to the Contract Sum or Time. The Contractor "
    "remains responsible for confirming and correlating quantities and dimensions; selecting fabrication "
    "processes and construction means, methods, techniques, sequences and procedures; and coordinating "
    "the Work of all trades."
)

# Colors (r,g,b 0..1) by category / disposition tone.
_GREEN = (0.13, 0.55, 0.19)
_AMBER = (0.85, 0.55, 0.05)
_RED = (0.78, 0.13, 0.13)
_BLUE = (0.15, 0.32, 0.62)
_GREY = (0.30, 0.30, 0.30)


def _disposition_color(text: str) -> tuple[float, float, float]:
    t = (text or "").lower()
    if any(k in t for k in ("reject", "unacceptable", "not approv")):
        return _RED
    if any(k in t for k in ("revise", "resubmit", "corrections", "as noted", "amend")):
        return _AMBER
    if any(k in t for k in ("approv", "accept", "no exceptions", "for record")):
        return _GREEN
    return _GREY


# --- Stamp template library (server = source of truth; the client fetches this) ---------------------
# Each template: id, name, category, optional dispositions, fields[{key,label,type,default}], color,
# disclaimer flag, and a size hint (points). ``type`` ∈ text | multiline | date | user.
LIBRARY: list[dict[str, Any]] = [
    {
        "id": "review-ejcdc", "name": "Submittal Review (EJCDC)", "category": "review",
        "dispositions": DISPOSITIONS_EJCDC + DISPOSITIONS_EJCDC_INFO, "disclaimer": True,
        "color": _BLUE, "size": [300, 150],
        "fields": [
            {"key": "firm", "label": "Reviewing Firm", "type": "text"},
            {"key": "reviewer", "label": "Reviewed By", "type": "user"},
            {"key": "responsible", "label": "In Responsible Charge", "type": "text"},
            {"key": "submittal", "label": "Submittal No.", "type": "text"},
            {"key": "spec_section", "label": "Spec Section", "type": "text"},
            {"key": "date", "label": "Date", "type": "date"},
        ],
    },
    {
        "id": "review-csi", "name": "Submittal Review (CSI)", "category": "review",
        "dispositions": DISPOSITIONS_CSI, "disclaimer": True,
        "color": _BLUE, "size": [300, 150],
        "fields": [
            {"key": "firm", "label": "Reviewing Firm", "type": "text"},
            {"key": "reviewer", "label": "Reviewed By", "type": "user"},
            {"key": "responsible", "label": "In Responsible Charge", "type": "text"},
            {"key": "submittal", "label": "Submittal No.", "type": "text"},
            {"key": "spec_section", "label": "Spec Section", "type": "text"},
            {"key": "date", "label": "Date", "type": "date"},
        ],
    },
    {
        "id": "inspection", "name": "Field Inspection", "category": "inspection",
        "dispositions": ["Pass", "Partial", "Fail"], "disclaimer": False,
        "color": _GREY, "size": [260, 110],
        "fields": [
            {"key": "inspector", "label": "Inspector", "type": "user"},
            {"key": "location", "label": "Location", "type": "text"},
            {"key": "date", "label": "Date", "type": "date"},
            {"key": "notes", "label": "Notes", "type": "multiline"},
        ],
    },
    {
        "id": "status", "name": "Status", "category": "status", "disclaimer": False,
        "dispositions": ["APPROVED", "FOR CONSTRUCTION", "NOT FOR CONSTRUCTION", "VOID",
                         "AS-BUILT", "PRELIMINARY", "SUPERSEDED"],
        "color": _RED, "size": [220, 74],
        "fields": [
            {"key": "by", "label": "By", "type": "user"},
            {"key": "date", "label": "Date", "type": "date"},
        ],
    },
    {
        "id": "seal-pe", "name": "Professional Engineer Seal", "category": "seal", "disclaimer": False,
        "discipline": "LICENSED PROFESSIONAL ENGINEER", "color": _BLUE, "size": [230, 150],
        "fields": [
            {"key": "name", "label": "Licensee", "type": "text"},
            {"key": "license_no", "label": "License No.", "type": "text"},
            {"key": "state", "label": "State", "type": "text"},
            {"key": "expiration", "label": "Expiration", "type": "text"},
        ],
    },
    {
        "id": "seal-ra", "name": "Registered Architect Seal", "category": "seal", "disclaimer": False,
        "discipline": "REGISTERED ARCHITECT", "color": _BLUE, "size": [230, 150],
        "fields": [
            {"key": "name", "label": "Licensee", "type": "text"},
            {"key": "license_no", "label": "License No.", "type": "text"},
            {"key": "state", "label": "State", "type": "text"},
            {"key": "expiration", "label": "Expiration", "type": "text"},
        ],
    },
]

_BY_ID = {t["id"]: t for t in LIBRARY}


def library() -> list[dict[str, Any]]:
    """JSON-serializable template library (colors → hex for the client)."""
    out = []
    for t in LIBRARY:
        r, g, b = (round(v * 255) for v in t["color"])
        out.append({**t, "color": f"#{r:02x}{g:02x}{b:02x}"})
    return out


def get_template(template_id: str) -> dict[str, Any] | None:
    return _BY_ID.get(template_id)


# --- Rendering --------------------------------------------------------------------------------------
def _page_size(data: bytes, page_index: int) -> tuple[float, float]:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    pg = r.pages[max(0, min(page_index, len(r.pages) - 1))]
    return float(pg.mediabox.width), float(pg.mediabox.height)


def _overlay(page_w: float, page_h: float, draw) -> bytes:
    """Run `draw(canvas)` on a page-sized reportlab canvas (bottom-left origin) → overlay PDF bytes."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    draw(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def _composite(data: bytes, page_index: int, overlay: bytes) -> bytes:
    """Merge a page-sized overlay onto one page of `data`."""
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(data))
    ov = PdfReader(io.BytesIO(overlay)).pages[0]
    w = PdfWriter()
    idx = max(0, min(page_index, len(reader.pages) - 1))
    for i, pg in enumerate(reader.pages):
        if i == idx:
            pg.merge_page(ov)
        w.add_page(pg)
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _wrap(text: str, width_chars: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > width_chars:
            if cur:
                lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        lines.append(cur)
    return lines


def _draw_block(c, x0: float, y0: float, w: float, h: float, tpl: dict, values: dict,
                disposition: str) -> None:
    """Draw a review/inspection/status stamp block. (x0,y0) = bottom-left of the block, in points."""
    cat = tpl["category"]
    accent = _disposition_color(disposition) if disposition else tpl["color"]
    # frame
    c.setLineWidth(1.6)
    c.setStrokeColorRGB(*accent)
    c.setFillColorRGB(1, 1, 1)
    c.rect(x0, y0, w, h, stroke=1, fill=1)
    pad = 6
    top = y0 + h - pad

    if cat == "status":
        c.setFillColorRGB(*accent)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(x0 + w / 2, y0 + h - 30, (disposition or tpl["name"]).upper())
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(*_GREY)
        meta = "  ".join(f"{f['label']}: {values.get(f['key'], '')}" for f in tpl["fields"])
        c.drawCentredString(x0 + w / 2, y0 + 8, meta)
        return

    # header band
    c.setFillColorRGB(*accent)
    c.rect(x0, y0 + h - 18, w, 18, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + pad, y0 + h - 13, tpl["name"])
    top = y0 + h - 18 - 12

    if disposition:
        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(*accent)
        c.drawString(x0 + pad, top - 4, disposition.upper())
        top -= 20

    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(0.12, 0.12, 0.12)
    for f in tpl["fields"]:
        val = values.get(f["key"], "")
        if not val:
            continue
        c.drawString(x0 + pad, top, f"{f['label']}: {val}")
        top -= 10

    if tpl.get("disclaimer"):
        c.setFont("Helvetica-Oblique", 5.4)
        c.setFillColorRGB(*_GREY)
        for ln in _wrap(DISCLAIMER, 78):
            if top < y0 + 6:
                break
            c.drawString(x0 + pad, top, ln)
            top -= 6.2


def apply_stamp(data: bytes, page_index: int, x: float, y: float, template_id: str,
                values: dict | None = None, disposition: str = "") -> bytes:
    """Composite a review/inspection/status stamp onto a page. (x,y) = TOP-LEFT of the stamp in PDF
    points measured from the page's TOP-LEFT (screen-intuitive; flipped to PDF space internally)."""
    tpl = get_template(template_id)
    if not tpl or tpl["category"] == "seal":
        raise ValueError(f"unknown stamp template: {template_id}")
    values = values or {}
    w, h = tpl["size"]
    pw, ph = _page_size(data, page_index)
    x0 = max(0, min(x, pw - w))
    y0 = ph - y - h  # top-left(from-top) → bottom-left origin
    y0 = max(0, min(y0, ph - h))
    overlay = _overlay(pw, ph, lambda c: _draw_block(c, x0, y0, w, h, tpl, values, disposition))
    return _composite(data, page_index, overlay)


def _draw_seal(c, x0: float, y0: float, w: float, h: float, tpl: dict, profile: dict) -> None:
    """Draw a circular professional seal + signature/date block. (x0,y0)=bottom-left, points."""
    import datetime
    r = min(w, h * 0.62) / 2 - 4
    cx, cy = x0 + w / 2, y0 + h - r - 6
    c.setStrokeColorRGB(*tpl["color"])
    c.setLineWidth(1.4)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.setLineWidth(0.7)
    c.circle(cx, cy, r - 4, stroke=1, fill=0)
    c.setFillColorRGB(*tpl["color"])
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(cx, cy + r - 12, tpl.get("discipline", ""))
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, cy + 3, (profile.get("name") or "").upper())
    c.setFont("Helvetica", 6.5)
    c.drawCentredString(cx, cy - 7, f"No. {profile.get('license_no', '')}")
    c.drawCentredString(cx, cy - r + 10, f"STATE OF {(profile.get('state') or '').upper()}")
    # signature + date block below the seal
    sy = y0 + 4
    c.setStrokeColorRGB(*_GREY)
    c.setLineWidth(0.6)
    c.line(x0 + 6, sy + 12, x0 + w - 6, sy + 12)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.1, 0.1, 0.4)
    c.drawString(x0 + 8, sy + 15, profile.get("name", ""))
    c.setFont("Helvetica", 5.5)
    c.setFillColorRGB(*_GREY)
    date = profile.get("date") or datetime.date.today().isoformat()
    exp = profile.get("expiration", "")
    c.drawString(x0 + 6, sy + 3, f"Signature & Date: {date}" + (f"   Exp: {exp}" if exp else ""))


def apply_seal(data: bytes, page_index: int, x: float, y: float, template_id: str,
               profile: dict, sign: bool = True) -> tuple[bytes, dict]:
    """Render a *visible* seal + signature block, then (if `sign`) apply a PAdES digital signature LAST
    so the sealed document is tamper-evident. Returns (pdf_bytes, meta). `meta.sealed` is True only when
    the crypto signature was applied; `meta.compliance` warns that the platform cert is demonstration."""
    from . import esign
    tpl = get_template(template_id)
    if not tpl or tpl["category"] != "seal":
        raise ValueError(f"unknown seal template: {template_id}")
    w, h = tpl["size"]
    pw, ph = _page_size(data, page_index)
    x0 = max(0, min(x, pw - w))
    y0 = max(0, min(ph - y - h, ph - h))
    overlay = _overlay(pw, ph, lambda c: _draw_seal(c, x0, y0, w, h, tpl, profile))
    visible = _composite(data, page_index, overlay)
    meta: dict[str, Any] = {
        "template": template_id, "licensee": profile.get("name", ""),
        "license_no": profile.get("license_no", ""), "state": profile.get("state", ""),
        "sealed": False,
    }
    if not sign:
        return visible, meta
    reason = (f"Sealed by {profile.get('name', '')}, {tpl.get('discipline', '')} "
              f"No. {profile.get('license_no', '')}").strip()
    signed = esign.digitally_sign(visible, reason=reason, name=profile.get("name", ""))
    meta.update(sealed=True, signer_fingerprint=esign.signer_fingerprint(),
                cert_kind=esign.status()["kind"],
                compliance=("Tamper-evident PAdES signature applied. NOTE: the platform self-signed "
                            "certificate is for demonstration / tamper-evidence, not board-accepted "
                            "sealing - configure the licensee's own certificate (ESIGN_P12) for "
                            "regulatory compliance."
                            if not esign.is_configured() else
                            "Tamper-evident PAdES signature applied with the configured certificate."))
    return signed, meta
