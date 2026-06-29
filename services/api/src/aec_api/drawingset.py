"""Drawing-set register — derives the controlled current set from the `drawing` module records:
for each sheet number the highest revision is *current*, earlier ones *superseded*. Produces a sheet
index, revision history and discipline rollup (Procore/ACC "Drawings" parity). Pure over the dicts."""
from __future__ import annotations

import re
from typing import Any


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
        disc = cur.get("discipline") or "Uncategorized"
        by_discipline[disc] = by_discipline.get(disc, 0) + 1
        # issuance classification: a single revision is a new sheet; more than one means it was revised
        change = "new" if len(revs) == 1 else "revised"
        index.append({"sheet_number": sheet, "title": cur.get("title"), "discipline": disc,
                      "current_revision": cur.get("revision"), "revisions": len(revs), "change": change})
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
