"""Drawing-set register — derives the controlled current set from the `drawing` module records:
for each sheet number the highest revision is *current*, earlier ones *superseded*. Produces a sheet
index, revision history and discipline rollup (Procore/ACC "Drawings" parity). Pure over the dicts."""
from __future__ import annotations

import re
from typing import Any

# NCS (US National CAD Standard) sheet-type designator — the digit after the discipline letter.
_SHEET_TYPE = {"0": "General", "1": "Plans", "2": "Elevations", "3": "Sections",
               "4": "Large-scale views", "5": "Details", "6": "Schedules & Diagrams",
               "7": "User-defined", "8": "User-defined", "9": "3D / isometric"}
_SHEET_ID_RE = re.compile(r"^([A-Z]{1,2})[\s\-.]?(\d)(\d{1,3})?", re.I)


def parse_sheet_id(sheet_number: Any) -> dict[str, Any] | None:
    """Parse an NCS Sheet Identification (discipline designator + sheet-type digit + sequence), e.g.
    'A-101' -> {discipline 'A' (Architectural), sheet type '1' (Plans), sequence '01'}. The first letter
    is the NCS level-1 discipline (level-2 designators like 'AD' fold to 'A'). Returns None if the sheet
    number doesn't follow the pattern."""
    m = _SHEET_ID_RE.match(str(sheet_number or "").strip())
    if not m:
        return None
    from . import classification as cls
    letters, typ, seq = m.group(1).upper(), m.group(2), m.group(3) or ""
    # honour distinct 2-letter series (FA Fire Alarm, FP Fire Protection) before folding to level-1
    code = letters if letters in cls.SHEET_SERIES else letters[:1]
    return {"discipline_code": code, "discipline": cls.sheet_series(letters),
            "sheet_type": typ, "sheet_type_name": _SHEET_TYPE.get(typ), "sequence": seq}


def _rev_key(rev: Any) -> tuple:
    """Sortable revision key. Numeric revs sort numerically; alpha revs (A<B<C) after; blank lowest.
    Handles 'P1'/'C2' style by (number, letters)."""
    s = str(rev or "").strip()
    if not s:
        return (0, 0, "")
    nums = re.findall(r"\d+", s)
    letters = re.sub(r"[^A-Za-z]", "", s).upper()
    n = int(nums[-1]) if nums else 0
    # alpha-only revs (A,B,C) rank by letter; numeric revs by number
    return (1 if (letters and not nums) else 2, n, letters)


def register(drawings: list[dict]) -> dict[str, Any]:
    """drawings: each `drawing` record's data + ref/workflow_state. Returns the controlled set."""
    by_sheet: dict[str, list[dict]] = {}
    for d in drawings:
        data = d.get("data") or d
        sheet = (data.get("sheet_number") or data.get("number") or d.get("ref") or "?").strip()
        by_sheet.setdefault(sheet, []).append({
            "ref": d.get("ref"), "sheet_number": sheet,
            "title": data.get("title"), "discipline": data.get("discipline"),
            "revision": data.get("revision"), "status": d.get("workflow_state"),
            "_k": _rev_key(data.get("revision")),
        })
    current_set, superseded, index = [], [], []
    by_discipline: dict[str, int] = {}
    for sheet, revs in sorted(by_sheet.items()):
        revs.sort(key=lambda r: r["_k"])
        cur = revs[-1]
        for r in revs[:-1]:
            r2 = {k: v for k, v in r.items() if k != "_k"}
            r2["superseded_by"] = cur["revision"]
            superseded.append(r2)
        cur_clean = {k: v for k, v in cur.items() if k != "_k"}
        current_set.append(cur_clean)
        sid = parse_sheet_id(sheet)          # NCS Sheet ID → discipline + sheet-type + sequence
        disc = cur.get("discipline") or (sid and sid["discipline"]) or "Uncategorized"
        by_discipline[disc] = by_discipline.get(disc, 0) + 1
        # issuance classification: a single revision is a new sheet; more than one means it was revised
        change = "new" if len(revs) == 1 else "revised"
        index.append({"sheet_number": sheet, "title": cur.get("title"), "discipline": disc,
                      "sheet_id": sid, "current_revision": cur.get("revision"),
                      "revisions": len(revs), "change": change})
    # order the sheet index the way a drawing set is bound: by NCS discipline, then sheet number
    from . import classification as cls
    _order = {d["name"]: i for i, d in enumerate(cls.disciplines())}
    index.sort(key=lambda s: (_order.get(s["discipline"], 99), s["sheet_number"]))
    new_count = sum(1 for s in index if s["change"] == "new")
    return {
        "sheet_count": len(by_sheet),
        "current_count": len(current_set),
        "superseded_count": len(superseded),
        "new_count": new_count,
        "revised_count": len(index) - new_count,
        "by_discipline": dict(sorted(by_discipline.items())),
        "sheet_index": index,
        "current_set": current_set,
        "superseded": superseded,
    }


def transmittal_pdf(reg: dict, project_name: str, recipients: list[str] | None = None,
                    note: str = "") -> bytes:
    """A drawing transmittal of the controlled current set — sheets grouped by discipline with their
    current revision + issuance status (New / Revised), recipients, and a note."""
    import io
    from datetime import date as _date

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    flow = [Paragraph("Drawing Transmittal", ss["Title"]),
            Paragraph(f"{project_name} · {_date.today().isoformat()} · "
                      f"{reg['current_count']} sheets ({reg['new_count']} new · {reg['revised_count']} revised)",
                      ss["Normal"])]
    if recipients:
        flow.append(Paragraph("<b>To:</b> " + ", ".join(recipients), ss["Normal"]))
    if note:
        flow.append(Paragraph("<b>Note:</b> " + note, ss["Normal"]))
    flow.append(Spacer(1, 10))
    head = ["Sheet", "Title", "Discipline", "Rev", "Status"]
    body = [[s["sheet_number"], s.get("title") or "", s.get("discipline") or "",
             s.get("current_revision") or "", s["change"].title()] for s in reg["sheet_index"]]
    t = Table([head] + (body or [["(no sheets)"] + [""] * 4]), repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b3a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")])]))
    flow += [t, Spacer(1, 14),
             Paragraph("Issued for the use of the recipient(s) named above. Verify you are working "
                       "from the current revision; superseded revisions are void.", ss["Italic"])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, title="Drawing Transmittal", topMargin=0.7 * inch).build(flow)
    return buf.getvalue()


def drawing_set(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    drawings = me.list_records(db, "drawing", pid, limit=100000) if "drawing" in me.TABLES else []
    return register(drawings)


# --- revision / delta register (AIA: each sheet carries a revision block of deltas, each often driven
# by an Addendum / ASI / CCD / Bulletin) -----------------------------------------------------------
def revise_sheet(db, pid: str, drawing_id: str, rev: str, description: str = "",
                 rev_date: str | None = None, instrument_type: str = "", instrument_ref: str = "",
                 actor: str = "reviser", party: str | None = "GC") -> dict[str, Any]:
    """Record a revision (delta) on a sheet: append it to the sheet's revision block and bump the
    sheet's current revision. Optionally cite the change instrument that drove it (ASI-003, Add 2, …)."""
    from datetime import date

    from . import modules as me
    rec = me.get_record(db, "drawing", pid, drawing_id)          # 404 if missing
    data = rec.get("data") or {}
    revs = list(data.get("revisions") or [])
    delta: dict[str, Any] = {"rev": str(rev), "date": rev_date or date.today().isoformat(),
                             "description": description}
    if instrument_ref:
        delta["instrument"] = {"type": instrument_type, "ref": instrument_ref}
    revs.append(delta)
    me.update_record(db, "drawing", pid, drawing_id,
                     {"revision": str(rev), "revisions": revs}, actor, party)
    return {"drawing_id": drawing_id, "revision": str(rev), "delta_count": len(revs)}


def revisions(db, pid: str) -> dict[str, Any]:
    """The cross-sheet revision register — every delta on every sheet (newest first), with the driving
    change instrument. The 'what changed, when, and why' log a drawing set carries."""
    from . import modules as me
    drawings = me.list_records(db, "drawing", pid, limit=100000) if "drawing" in me.TABLES else []
    out = []
    by_instrument: dict[str, int] = {}
    for d in drawings:
        data = d.get("data") or {}
        sn = (data.get("sheet_number") or data.get("number") or d.get("ref") or "").strip()
        for delta in (data.get("revisions") or []):
            inst = delta.get("instrument") or {}
            key = (inst.get("ref") or "").strip()
            if key:
                by_instrument[key] = by_instrument.get(key, 0) + 1
            out.append({"sheet_number": sn, "title": data.get("title"),
                        "discipline": data.get("discipline"), "rev": delta.get("rev"),
                        "date": delta.get("date"), "description": delta.get("description"),
                        "instrument": inst or None})
    out.sort(key=lambda r: (str(r["date"]), str(r["sheet_number"])), reverse=True)
    return {"delta_count": len(out), "by_instrument": dict(sorted(by_instrument.items())),
            "revisions": out}


def _cover_pdf(project_name: str, sheet_index: list[dict], subtitle: str = "Drawing Set") -> bytes:
    """A cover / sheet-index page (ARCH-D, matching the sheets) for the compiled set."""
    from io import BytesIO

    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    w, h = 914.0, 610.0
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w * mm, h * mm))
    c.setLineWidth(1)
    c.rect(8 * mm, 8 * mm, (w - 16) * mm, (h - 16) * mm)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(28 * mm, (h - 55) * mm, (project_name or "Project")[:60])
    c.setFont("Helvetica", 15)
    c.drawString(28 * mm, (h - 72) * mm, subtitle)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(28 * mm, (h - 96) * mm, "SHEET")
    c.drawString(70 * mm, (h - 96) * mm, "TITLE")
    c.setFont("Helvetica", 10)
    y = h - 106
    for s in sheet_index:
        c.drawString(28 * mm, y * mm, str(s.get("number", "")))
        c.drawString(70 * mm, y * mm, str(s.get("title", ""))[:80])
        y -= 6.5
        if y < 24:
            break
    c.showPage()
    c.save()
    return buf.getvalue()


def compiled_set_pdf(source_ifc: str, project_name: str, scale: int = 200, max_sheets: int = 16,
                     include_schedules: bool = True) -> bytes:
    """Compile the WHOLE drawing set into ONE multi-page PDF — a cover / sheet-index, a floor plan per
    storey (A-1xx), and the door/window/room schedules (A-601) — by rendering each single sheet with the
    proven `drawing.sheet_pdf`/`schedule_pdf` and merging with pypdf. The handover deliverable a GC or
    architect issues. Tall towers sample storeys evenly to keep the set a reasonable size."""
    import sys as _sys
    from pathlib import Path as _Path

    from . import pdfops

    _ds = _Path(__file__).resolve().parents[3] / "data" / "src"
    if str(_ds) not in _sys.path:
        _sys.path.insert(0, str(_ds))
    from aec_data import drawing  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    model = open_model(source_ifc)
    storeys = [s.Name for s in model.by_type("IfcBuildingStorey") if getattr(s, "Name", None)]
    if max_sheets and len(storeys) > max_sheets:                 # sample evenly on a tall tower
        step = len(storeys) / max_sheets
        storeys = [storeys[min(len(storeys) - 1, int(i * step))] for i in range(max_sheets)]

    specs = [{"storey": lvl, "number": f"A-1{i + 1:02d}", "title": f"{lvl} — FLOOR PLAN"}
             for i, lvl in enumerate(storeys)]
    index = list(specs)
    if include_schedules:
        index.append({"number": "A-601", "title": "SCHEDULES — DOOR / WINDOW / ROOM"})

    parts: list[bytes] = [_cover_pdf(project_name, index)]
    for sp in specs:
        try:
            parts.append(drawing.sheet_pdf(model, storey=sp["storey"], scale=scale,
                                           project=project_name, number=sp["number"], title=sp["title"]))
        except Exception:  # noqa: BLE001 — one bad storey never aborts the whole set
            pass
    if include_schedules:
        try:
            parts.append(drawing.schedule_pdf(model, project=project_name, number="A-601"))
        except Exception:  # noqa: BLE001 — a model with no doors/windows/rooms simply omits schedules
            pass
    return pdfops.merge(parts)
