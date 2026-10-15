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


def _label_kind(rev: Any) -> str:
    """`blank`, `alpha` (letters only: A, B, C) or `numeric` (contains a digit: 0, 1, P1, C2).

    SET-REVISED. The two kinds cannot be ordered against each other from the labels alone, and which
    one is "later" is a FIRM CONVENTION, not a fact: some sets number the milestone issues and letter
    the post-issue revisions, others do the reverse. `register` reports a sheet whose labels mix the
    two instead of ranking them silently -- the only place the ordering is load-bearing.
    """
    t = str(rev or "").strip()
    if not t:
        return "blank"
    return "numeric" if any(c.isdigit() for c in t) else "alpha"


def _rev_key(rev: Any) -> tuple:
    """Sortable revision key. Blank lowest, then ALPHA-only revs (A<B<C), then revs containing a
    number, by that number then its letters ('P1' < 'C2').

    **The docstring used to claim the opposite** -- "numeric revs sort numerically; alpha revs
    (A<B<C) after" -- while the body put alpha at rank 1 and numeric at rank 2, i.e. alpha BEFORE
    numeric. Measured: `sorted(["", "A", "B", "C", "0", "1", "2", "10"], key=_rev_key)` leaves `10`
    last, and a sheet whose records read `1, 2, A, B` named rev `2` current with `A` and `B` listed
    as "superseded by 2". The order here is now the one the code performs, and because the choice
    between the two kinds is a convention rather than a fact, `register` REPORTS a sheet that mixes
    them rather than trusting this ranking on it. *Correcting the comment to match the code is only
    safe once something flags the cases where the code's choice cannot be justified.*
    """
    s = str(rev or "").strip()
    if not s:
        return (0, 0, "")
    nums = re.findall(r"\d+", s)
    letters = re.sub(r"[^A-Za-z]", "", s).upper()
    n = int(nums[-1]) if nums else 0
    # alpha-only revs (A,B,C) rank by letter; numeric revs by number
    return (1 if (letters and not nums) else 2, n, letters)


def _record_history(d: dict, data: dict, sheet: str) -> list[dict]:
    """Every revision ONE drawing record knows about, oldest first.

    SET-REVISED. `revise` keeps one record per sheet and APPENDS to `data["revisions"]`, so a
    sheet's revision history lives INSIDE the record, not across records. `register` classified
    issuance by counting records -- `"new" if len(revs) == 1` -- so a sheet revised twice through
    this application's own endpoint, with ASI and CCD deltas recorded against it, came back
    `change: "new", revisions: 1, revised_count: 0, superseded_count: 0`. `revisions()` in this same
    file reads the same `data["revisions"]` and reports both deltas with their instruments: **two
    engines over one record, disagreeing about whether the sheet was ever revised.**

    It reached the field. `transmittal_pdf` renders `s["change"].title()` as the issuance column, so
    the transmittal told subcontractors a revised sheet was New -- which is the flag that decides
    whether they re-check their shop drawings against it.

    The delta list is the authority on ORDER as well as on count: `revise` appends chronologically,
    so no label ranking is involved inside a record. `_rev_key` is needed only ACROSS records that
    share a sheet number (a drawing-log import), which is the one place the convention question
    arises.
    """
    base = {"ref": d.get("ref"), "sheet_number": sheet, "title": data.get("title"),
            "discipline": data.get("discipline"), "status": d.get("workflow_state")}
    out: list[dict] = []
    for delta in (data.get("revisions") or []):
        out.append({**base, "revision": str(delta.get("rev") or ""), "rev_date": delta.get("date"),
                    "description": delta.get("description"),
                    "instrument": delta.get("instrument") or None, "source": "delta"})
    cur = data.get("revision")
    # The record's stated `revision` wins when it is not the last recorded delta -- an import, or a
    # record whose revision was set without one. APPENDED rather than substituted: dropping the
    # deltas would re-create the undercount this function exists to fix.
    if cur not in (None, "") and (not out or out[-1]["revision"] != str(cur)):
        out.append({**base, "revision": str(cur), "source": "record"})
    if not out:
        out.append({**base, "revision": cur, "source": "record"})
    return out


def register(drawings: list[dict]) -> dict[str, Any]:
    """drawings: each `drawing` record's data + ref/workflow_state. Returns the controlled set."""
    by_sheet: dict[str, list[dict]] = {}
    for d in drawings:
        data = d.get("data") or d
        sheet = (data.get("sheet_number") or data.get("number") or d.get("ref") or "?").strip()
        hist = _record_history(d, data, sheet)
        by_sheet.setdefault(sheet, []).append({"history": hist, "_k": _rev_key(hist[-1]["revision"])})
    current_set, superseded, index = [], [], []
    by_discipline: dict[str, int] = {}
    ambiguous: list[str] = []
    for sheet, recs in sorted(by_sheet.items()):
        recs.sort(key=lambda r: r["_k"])
        cur = recs[-1]["history"][-1]
        # Every revision known for this sheet. The COUNT is over distinct labels so neither model
        # double-counts: one record per revision (an import) and one record carrying a delta list
        # (this app's own `revise`) both answer "how many revisions has this sheet had".
        every = [e for r in recs for e in r["history"]]
        labels = {str(e["revision"]) for e in every if e["revision"] not in (None, "")}
        seen: set[tuple] = set()
        for e in every:
            if e is cur:
                continue
            k = (e.get("ref"), str(e["revision"]), e.get("source"))
            if k in seen:
                continue
            seen.add(k)
            superseded.append({**e, "superseded_by": cur["revision"]})
        current_set.append(dict(cur))
        sid = parse_sheet_id(sheet)          # NCS Sheet ID → discipline + sheet-type + sequence
        disc = cur.get("discipline") or (sid and sid["discipline"]) or "Uncategorized"
        by_discipline[disc] = by_discipline.get(disc, 0) + 1
        # issuance classification: ONE known revision is a new sheet; more than one means revised.
        rev_count = max(len(labels), 1)
        change = "new" if rev_count == 1 else "revised"
        # The ordering question only arises ACROSS records -- inside one, `revise` appended in order.
        kinds = {_label_kind(e["revision"]) for e in every} - {"blank"}
        order_ambiguous = len(recs) > 1 and kinds == {"alpha", "numeric"}
        if order_ambiguous:
            ambiguous.append(sheet)
        index.append({"sheet_number": sheet, "title": cur.get("title"), "discipline": disc,
                      "sheet_id": sid, "current_revision": cur.get("revision"),
                      "revisions": rev_count, "change": change,
                      "order_ambiguous": order_ambiguous})
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
        # SET-REVISED. Sheets whose revision labels mix alpha-only and numeric ACROSS records, where
        # which kind is later is a firm convention rather than a fact. Reported rather than ranked
        # silently: `_rev_key` still returns a deterministic order so the register stays stable, and
        # this names the sheets where that order is the thing to check before issuing.
        "order_ambiguous_sheets": sorted(ambiguous),
        "order_note": (
            f"{len(ambiguous)} sheet(s) carry both lettered and numbered revisions across separate "
            "records. Which is later is a set convention, not something these labels state, so the "
            "current revision on those sheets is this register's ranking rather than a recorded "
            "fact -- check them before issuing."
            if ambiguous else
            "Every sheet's revision order is recorded: within a record the revision deltas are in "
            "the order they were made, and no sheet mixes lettered and numbered revisions across "
            "records."),
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
def _lock_key(pid: str, drawing_id: str) -> str:
    """The serialisation key for one sheet's revision block and its carried-forward markups.

    Namespaced like `connections._lock_key`: `pid_lock` is named for projects, but `advisory_key`
    hashes any string into one namespace, so the prefix keeps this out of the project id space. Keyed
    per SHEET rather than per project, because revisions to two different sheets are independent and
    a project-wide key would serialise them for nothing. A function rather than an inline f-string so
    a second writer of this block cannot be added on a different key -- which reads as locked and
    protects nothing.
    """
    return f"drawing:{pid}:{drawing_id}"


def revise_sheet(db, pid: str, drawing_id: str, rev: str, description: str = "",
                 rev_date: str | None = None, instrument_type: str = "", instrument_ref: str = "",
                 actor: str = "reviser", party: str | None = "GC") -> dict[str, Any]:
    """Record a revision (delta) on a sheet: append it to the sheet's revision block and bump the
    sheet's current revision. Optionally cite the change instrument that drove it (ASI-003, Add 2, …)."""
    from datetime import date

    from . import pid_lock

    # RMW-REVISE. TWO read-modify-writes, and the whole function is ONE logical edit, so a single
    # lock spans both: `revisions` on the drawing record, and `data` on each markup carried forward.
    #
    # **The sweep ledger keyed this site on `m.data`, and that is the LESS severe half.** The markup
    # tag is guarded by `"carried_from" not in d2`, so a concurrent repeat is a no-op, and nothing
    # else in the tree read-modify-writes that column. The half that loses real work is `revisions`:
    # two revisions recorded on one sheet at once each append their own delta to the same pre-image,
    # and the later write stores the list WITHOUT the earlier delta -- so a revision that was
    # accepted, with an incremented `delta_count` in its own response, is absent from the sheet and
    # from the cross-sheet register `revisions()` builds. *A derivation keyed by attribute names the
    # site it matched, not the worst thing happening inside it.*
    #
    # The read is INSIDE the lock: re-reading after the wait is the point, and `get_record` runs a
    # Core `select` rather than an ORM load, so it really does see the winner's committed row and
    # not a session identity-map pre-image.
    #
    # Inline rather than a `_revise_sheet_locked` helper, and that was not a style choice: the first
    # draft hoisted the body out, which moved the `with` into the CALLER -- and `test_rmw_sweep`'s
    # `under_pid_lock` reds on exactly that, because a lock it cannot see in the function it is
    # asked about is a lock it cannot verify. *A refactor that relocates a guard out of the scope a
    # checker examines turns a verified claim into an asserted one.*
    with pid_lock.mutating(_lock_key(pid, drawing_id)):
        from . import modules as me
        rec = me.get_record(db, "drawing", pid, drawing_id)          # 404 if missing
        data = rec.get("data") or {}
        revs = list(data.get("revisions") or [])
        delta: dict[str, Any] = {"rev": str(rev), "date": rev_date or date.today().isoformat(),
                                 "description": description}
        if instrument_ref:
            delta["instrument"] = {"type": instrument_type, "ref": instrument_ref}
        revs.append(delta)
        old_rev = data.get("revision")
        me.update_record(db, "drawing", pid, drawing_id,
                         {"revision": str(rev), "revisions": revs}, actor, party)
        # MARKUP-2a (slip-sheet): every existing markup on this sheet now predates the new revision — tag
        # it `carried_from` so reviewers verify it against the revised sheet. Markups keep rendering (a
        # located comment is never dropped); the tag is the honest "carried forward — re-check" state.
        # REVISE-DARK. `carried` used to be incremented in the loop and returned whatever the loop
        # reached, while `db.commit()` sat INSIDE the `except Exception: pass` below. Measured by
        # injecting a failure on this commit: the response came back
        # `201 {"revision": "1", "delta_count": 1, "markups_carried": 3}` with **0 of 3 markups
        # actually tagged**. The revision landing anyway is correct and deliberate; claiming the
        # carried-forward flags are in place when they are not is backwards on a slip-sheet, where
        # that flag is the entire point — the reviewer is told to re-check and the marks say nothing.
        #
        # So the count is taken AFTER the commit returns, the attempted count is published beside
        # it, and the partial mutations are rolled back rather than left pending in a session that
        # some later commit in the same request could flush. *A count computed before the write that
        # persists it is a count of intentions.*
        attempted = carried = 0
        carry_failed: str | None = None
        try:
            from .models import DrawingMarkup
            base = str(data.get("sheet_number") or data.get("number") or rec.get("ref") or "").strip()
            if base:
                for m in (db.query(DrawingMarkup)
                            .filter(DrawingMarkup.project_id == pid,
                                    DrawingMarkup.sheet_id.in_([base, f"{base}#pdf"])).all()):
                    d2 = dict(m.data or {})
                    if d2.get("rev") != str(rev) and "carried_from" not in d2:
                        d2["carried_from"] = str(d2.get("rev") or old_rev or "prior")
                        m.data = d2
                        attempted += 1
                if attempted:
                    db.commit()
                    carried = attempted
        except Exception as exc:                         # noqa: BLE001 — tagging must never block a revision
            # The TYPE, not the message: a caller needs to know the tagging did not land and which
            # failure it was, and the message can carry row content.
            carry_failed = type(exc).__name__
            try:
                db.rollback()
            except Exception:                            # noqa: BLE001 — a failed rollback is not the caller's problem
                pass
        return {"drawing_id": drawing_id, "revision": str(rev), "delta_count": len(revs),
                "markups_carried": carried, "markups_to_carry": attempted,
                "markups_carry_failed": carry_failed}


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


# order the index the way a set is bound (NCS binding order); names come from classification (DISC-SSOT)
_SERIES_ORDER = ["G", "C", "L", "S", "A", "I", "Q", "F", "FP", "FA", "P", "M", "E", "T"]


def _series_name(series: str) -> str:
    """Display name for a sheet-series prefix, from the classification SSOT (FA/FP honoured)."""
    from . import classification as _cls
    return _cls.sheet_series(series) or series


def _series_of(number: str) -> str:
    """The NCS discipline-series prefix of a sheet number (e.g. 'A-101' → 'A', 'FP-201' → 'FP'). A distinct
    2-letter series (FA/FP, per the classification SSOT) is kept; any other 2-letter designator folds to
    its level-1 discipline letter."""
    from . import classification as _cls
    m = re.match(r"^([A-Z]{1,2})", str(number or "").strip().upper())
    if not m:
        return "G"
    pre = m.group(1)
    return pre if (len(pre) == 1 or pre in _cls.SHEET_SERIES) else pre[:1]


def _footprint_polylines(model, cut_z: float = 1.2):
    """Ground-plan cut polylines (list of (n,2) arrays, world XY) for a small key-plan on the cover —
    a genuinely *rendered* thumbnail, not text. Best-effort: any failure yields no thumbnail."""
    try:
        from aec_data import drawings as _dwg  # type: ignore
        meshes = _dwg.bake(model)
        return _dwg.cut_baked(meshes, "plan", cut_z)
    except Exception:  # noqa: BLE001 — the thumbnail is optional; the index is the essential content
        return []


def _cover_pdf(project_name: str, sheet_index: list[dict], subtitle: str = "Drawing Set",
               footprint=None, issue_date: str | None = None,
               link_out: list[dict] | None = None) -> bytes:
    """A rendered cover + drawing-index sheet (ARCH-D, matching the sheets) for the compiled set: a
    title block with issue metadata, a key-plan footprint thumbnail rendered from the model, and the
    drawing index grouped by NCS discipline with section headers. The index paginates onto extra pages."""
    from io import BytesIO

    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    w, h = 914.0, 610.0
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w * mm, h * mm))

    def _border():
        c.setLineWidth(1.4)
        c.rect(8 * mm, 8 * mm, (w - 16) * mm, (h - 16) * mm)
        c.setLineWidth(0.6)
        c.rect(12 * mm, 12 * mm, (w - 24) * mm, (h - 24) * mm)

    # ---- page 1: title block + key plan + the first slice of the index ----
    _border()
    c.setFont("Helvetica-Bold", 34)
    c.drawString(28 * mm, (h - 52) * mm, (project_name or "Project")[:52])
    c.setFont("Helvetica", 15)
    c.drawString(28 * mm, (h - 68) * mm, subtitle)
    c.setLineWidth(0.8)
    c.line(28 * mm, (h - 74) * mm, (w - 28) * mm, (h - 74) * mm)
    c.setFont("Helvetica", 10)
    meta = f"{len(sheet_index)} sheet(s)"
    if issue_date:
        meta += f"   ·   Issued {issue_date}"
    c.drawString(28 * mm, (h - 82) * mm, meta)

    # key-plan thumbnail (rendered footprint), boxed at the lower-left
    kp_x, kp_y, kp_w, kp_h = 28.0, 28.0, 180.0, 150.0
    c.setLineWidth(0.6)
    c.rect(kp_x * mm, kp_y * mm, kp_w * mm, kp_h * mm)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(kp_x * mm, (kp_y + kp_h + 3) * mm, "KEY PLAN")
    polys = [p for p in (footprint or []) if len(p) >= 2]
    if polys:
        import numpy as _np
        allpts = _np.vstack(polys)
        mn, mx = allpts.min(axis=0), allpts.max(axis=0)
        span = _np.maximum(mx - mn, 1e-6)
        pad = 14.0
        s = min((kp_w - 2 * pad) / span[0], (kp_h - 2 * pad) / span[1])
        ox = kp_x + (kp_w - span[0] * s) / 2.0
        oy = kp_y + (kp_h - span[1] * s) / 2.0
        c.setLineWidth(0.5)
        for poly in polys:
            pts = [((ox + (p[0] - mn[0]) * s) * mm, (oy + (p[1] - mn[1]) * s) * mm) for p in poly]
            c.lines([(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)])
    else:
        c.setFont("Helvetica-Oblique", 9)
        c.drawCentredString((kp_x + kp_w / 2) * mm, (kp_y + kp_h / 2) * mm, "(no plan geometry)")

    # ---- drawing index, grouped by discipline, paginated ----
    def _grouped(index):
        buckets: dict[str, list[dict]] = {}
        for sh in index:
            buckets.setdefault(_series_of(sh.get("number", "")), []).append(sh)
        ordered = [k for k in _SERIES_ORDER if k in buckets] + [k for k in buckets if k not in _SERIES_ORDER]
        return [(k, buckets[k]) for k in ordered]

    col_x, title_x = 232.0, 300.0          # index sits to the right of the key plan on page 1
    top_y, bot_y = h - 96.0, 30.0
    y = top_y
    cover_page = 0                          # which cover page an index row lands on (SHEET-LINK)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(col_x * mm, (y + 6) * mm, "DRAWING INDEX")

    def _header_row(yy):
        c.setFont("Helvetica-Bold", 9)
        c.drawString(col_x * mm, yy * mm, "SHEET")
        c.drawString(title_x * mm, yy * mm, "TITLE")
        c.setLineWidth(0.4)
        c.line(col_x * mm, (yy - 2) * mm, (w - 28) * mm, (yy - 2) * mm)

    _header_row(y)
    y -= 8
    for series, rows in _grouped(sheet_index):
        if y < bot_y + 12:                 # overflow → a fresh full-width index page
            c.showPage()
            cover_page += 1
            _border()
            c.setFont("Helvetica-Bold", 12)
            c.drawString(28 * mm, (h - 24) * mm, "DRAWING INDEX (cont.)")
            col_x, title_x = 28.0, 96.0
            top_y = h - 36.0
            y = top_y
            _header_row(y)
            y -= 8
        c.setFont("Helvetica-Bold", 10)
        c.drawString(col_x * mm, y * mm, _series_name(series))
        y -= 6.5
        c.setFont("Helvetica", 10)
        for sh in rows:
            c.drawString((col_x + 4) * mm, y * mm, str(sh.get("number", "")))
            c.drawString(title_x * mm, y * mm, str(sh.get("title", ""))[:70])
            if link_out is not None and sh.get("number"):    # SHEET-LINK: the row rect, in points
                link_out.append({"page": cover_page, "sheet": str(sh["number"]),
                                 "rect": ((col_x + 2) * mm, (y - 1.6) * mm,
                                          (w - 28) * mm, (y + 4.4) * mm)})
            y -= 6.2
            if y < bot_y:
                c.showPage()
                cover_page += 1
                _border()
                c.setFont("Helvetica-Bold", 12)
                c.drawString(28 * mm, (h - 24) * mm, "DRAWING INDEX (cont.)")
                col_x, title_x = 28.0, 96.0
                y = h - 36.0
                _header_row(y)
                y -= 8
                c.setFont("Helvetica", 10)
    c.showPage()
    c.save()
    return buf.getvalue()


def compiled_set_pdf(source_ifc: str, project_name: str, scale: int = 200, max_sheets: int = 16,
                     include_schedules: bool = True) -> bytes:
    """Compile the WHOLE drawing set into ONE multi-page PDF — a cover / sheet-index, a floor plan per
    storey (A-1xx), and the door/window/room schedules (A-601) — by rendering each single sheet with the
    proven `drawing.sheet_pdf`/`schedule_pdf` and merging with pypdf. The handover deliverable a GC or
    architect issues. Tall towers sample storeys evenly to keep the set a reasonable size."""

    from . import pdfops
    from .apppaths import add_data_src_to_path
    add_data_src_to_path()
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

    from datetime import date as _date
    footprint = _footprint_polylines(model)
    cover_links: list[dict] = []
    parts: list[bytes] = [_cover_pdf(project_name, index, footprint=footprint,
                                     issue_date=_date.today().isoformat(), link_out=cover_links)]
    sheet_links: list[tuple[int, list[dict]]] = []   # (part index, that sheet's callout link boxes)
    for sp in specs:
        try:
            boxes: list[dict] = []
            parts.append(drawing.sheet_pdf(model, storey=sp["storey"], scale=scale,
                                           project=project_name, number=sp["number"], title=sp["title"],
                                           link_out=boxes))
            if boxes:
                sheet_links.append((len(parts) - 1, boxes))
        except Exception:  # noqa: BLE001 — one bad storey never aborts the whole set
            pass
    if include_schedules:
        try:
            parts.append(drawing.schedule_pdf(model, project=project_name, number="A-601"))
        except Exception:  # noqa: BLE001 — a model with no doors/windows/rooms simply omits schedules
            pass
    merged = pdfops.merge(parts)
    return _bind_goto_links(merged, parts, specs, include_schedules, cover_links, sheet_links)


def _bind_goto_links(merged: bytes, parts: list[bytes], specs: list[dict], include_schedules: bool,
                     cover_links: list[dict], sheet_links: list[tuple[int, list[dict]]]) -> bytes:
    """SHEET-LINK: bind the cover-index rows (and any callout bubble whose target sheet is in this
    set) to real PDF GoTo links, so the compiled set navigates like a hyperlinked document. Returns
    the linked PDF — or `merged` untouched when anything fails, because links are an enhancement and
    the un-linked set is still a correct deliverable."""
    try:
        import io as _io

        from pypdf import PdfReader, PdfWriter
        from pypdf.annotations import Link

        part_pages = [len(PdfReader(_io.BytesIO(b)).pages) for b in parts]
        part_start = [sum(part_pages[:i]) for i in range(len(parts))]
        # sheet number → absolute page index: specs are parts 1..N in order, schedules last
        page_of: dict[str, int] = {}
        for i, sp in enumerate(specs):
            page_of[sp["number"]] = part_start[1 + i] if 1 + i < len(part_start) else 0
        if include_schedules and len(part_start) > 1 + len(specs):
            page_of["A-601"] = part_start[1 + len(specs)]

        writer = PdfWriter(clone_from=_io.BytesIO(merged))
        added = 0
        for ln in cover_links:
            tgt = page_of.get(ln["sheet"])
            if tgt is not None:
                writer.add_annotation(page_number=ln["page"],
                                      annotation=Link(rect=ln["rect"], target_page_index=tgt))
                added += 1
        for part_idx, boxes in sheet_links:
            for b in boxes:
                tgt = page_of.get(b["sheet"])
                if tgt is not None:
                    writer.add_annotation(page_number=part_start[part_idx],
                                          annotation=Link(rect=b["rect"], target_page_index=tgt))
                    added += 1
        if added:
            out = _io.BytesIO()
            writer.write(out)
            return out.getvalue()
    except Exception:  # noqa: BLE001 — links are an enhancement; the un-linked set is still correct
        pass
    return merged
