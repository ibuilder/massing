"""Drawing issuance register — the AIA/CD-standard record of *what went out, when, for what purpose*.

A drawing set is released as dated **issuances** for a purpose (SD → DD → CD → Issued for Permit → Bid
→ Construction → Addendum → Conformed → Record). Each issuance **snapshots** the current set — which
sheets, at which revision — so you can always answer "what was in the permit set?" and produce the
sheet-index × issuance **matrix** every A/E project binds at the front of the set.

Issuances are `drawing_issuance` records; the snapshot (`[{sheet_number, revision, title, discipline}]`)
is stored on the record so the matrix is reconstructable even as sheets keep revising afterward."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import drawingset
from . import modules as me

# AIA/CD issuance purposes, in phase order (also the `drawing_issuance.purpose` select). Free text is
# allowed (validation is advisory), but these are the standard set the matrix orders columns by.
PURPOSES = [
    "Schematic Design", "Design Development", "Construction Documents",
    "Issued for Coordination", "Issued for Permit", "Issued for Bid",
    "Issued for Construction", "Addendum", "ASI", "Bulletin",
    "Conformed Set", "Record Drawings",
]
_PURPOSE_ABBR = {
    "Schematic Design": "SD", "Design Development": "DD", "Construction Documents": "CD",
    "Issued for Coordination": "Coord", "Issued for Permit": "Permit", "Issued for Bid": "Bid",
    "Issued for Construction": "IFC", "Addendum": "Add", "ASI": "ASI", "Bulletin": "Bull",
    "Conformed Set": "Conf", "Record Drawings": "Record",
}


def purposes() -> list[dict[str, str]]:
    return [{"name": p, "abbr": _PURPOSE_ABBR.get(p, p[:4])} for p in PURPOSES]


def _issuances(db: Session, pid: str) -> list[dict]:
    recs = me.list_records(db, "drawing_issuance", pid, limit=100000) if "drawing_issuance" in me.TABLES else []
    out = []
    for r in recs:
        d = r.get("data") or {}
        out.append({"id": r.get("id"), "ref": r.get("ref"), "number": d.get("number") or r.get("ref"),
                    "purpose": d.get("purpose") or "", "issue_date": d.get("issue_date") or "",
                    "description": d.get("description") or "", "recipients": d.get("recipients") or "",
                    "state": r.get("workflow_state"),
                    "sheets": d.get("sheets") or [], "sheet_count": len(d.get("sheets") or [])})
    # bind order: by issue date, then NCS purpose phase order
    out.sort(key=lambda i: (str(i["issue_date"]), PURPOSES.index(i["purpose"]) if i["purpose"] in PURPOSES else 99))
    return out


def issue(db: Session, pid: str, purpose: str, issue_date: str | None = None,
          description: str = "", recipients: str = "", actor: str = "issuance",
          party: str | None = "GC") -> dict[str, Any]:
    """Snapshot the current drawing set as a new issuance for `purpose`. Records each current sheet +
    its revision, so the issuance is a permanent record of exactly what was released."""
    reg = drawingset.drawing_set(db, pid)
    snapshot = [{"sheet_number": s.get("sheet_number"), "revision": s.get("revision") or "",
                 "title": s.get("title") or "", "discipline": s.get("discipline") or ""}
                for s in reg.get("current_set", [])]
    if not snapshot:
        raise HTTPException(409, "no drawings to issue — generate or add sheets first")
    n = 1 + len(_issuances(db, pid))
    abbr = _PURPOSE_ABBR.get(purpose, "ISS")
    rec = me.create_record(db, "drawing_issuance", pid, {"data": {
        "number": f"ISS-{n:03d} · {abbr}", "purpose": purpose,
        "issue_date": issue_date or date.today().isoformat(),
        "description": description, "recipients": recipients,
        "sheet_count": len(snapshot), "sheets": snapshot}}, actor=actor, party=party)
    return {"id": rec["id"], "ref": rec["ref"], "purpose": purpose,
            "issue_date": (rec.get("data") or {}).get("issue_date"), "sheet_count": len(snapshot)}


def register(db: Session, pid: str) -> dict[str, Any]:
    """The issuance history — every release, its purpose, date, sheet count and recipients."""
    iss = _issuances(db, pid)
    return {"issuance_count": len(iss),
            "by_purpose": _tally(i["purpose"] for i in iss),
            "issuances": [{k: v for k, v in i.items() if k != "sheets"} for i in iss]}


def matrix(db: Session, pid: str) -> dict[str, Any]:
    """The sheet-index × issuance grid — for each sheet, the revision it carried in each issuance (or
    null if it wasn't in that issue). The front-of-set 'issued' matrix every A/E drawing set includes."""
    iss = [i for i in _issuances(db, pid) if i["state"] != "void"]
    cols = [{"id": i["id"], "number": i["number"], "purpose": i["purpose"],
             "abbr": _PURPOSE_ABBR.get(i["purpose"], "ISS"), "issue_date": i["issue_date"]} for i in iss]
    # every sheet ever issued + every sheet current now, ordered by NCS discipline then number
    reg = drawingset.drawing_set(db, pid)
    meta: dict[str, dict] = {}
    for s in reg.get("current_set", []):
        meta[s["sheet_number"]] = {"title": s.get("title"), "discipline": s.get("discipline")}
    per_issue: list[dict[str, str]] = []
    for i in iss:
        m = {}
        for s in i["sheets"]:
            sn = s.get("sheet_number")
            m[sn] = s.get("revision") or "0"
            meta.setdefault(sn, {"title": s.get("title"), "discipline": s.get("discipline")})
        per_issue.append(m)
    from . import classification as cls
    order = {d["name"]: n for n, d in enumerate(cls.disciplines())}
    rows = []
    for sn in sorted(meta, key=lambda k: (order.get((meta[k].get("discipline") or ""), 99), k)):
        rows.append({"sheet_number": sn, "title": meta[sn].get("title"),
                     "discipline": meta[sn].get("discipline"),
                     "cells": [m.get(sn) for m in per_issue]})
    return {"issuances": cols, "sheet_count": len(rows), "rows": rows}


def _tally(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


def transmittal_pdf(db: Session, pid: str, issuance_id: str, project_name: str) -> bytes:
    """A transmittal for one issuance — stamped with its purpose + date, listing exactly the snapshot
    sheets/revisions that were released (reuses the drawing-set transmittal layout)."""
    iss = next((i for i in _issuances(db, pid) if i["id"] == issuance_id), None)
    if not iss:
        raise HTTPException(404, "issuance not found")
    # shape the snapshot into the register form transmittal_pdf expects
    reg = {"current_count": iss["sheet_count"], "new_count": iss["sheet_count"], "revised_count": 0,
           "sheet_index": [{"sheet_number": s["sheet_number"], "title": s.get("title"),
                            "discipline": s.get("discipline"), "current_revision": s.get("revision"),
                            "change": "new"} for s in iss["sheets"]]}
    recipients = [r.strip() for r in str(iss["recipients"]).split(",") if r.strip()]
    note = f"Issued for: {iss['purpose']} · {iss['issue_date']}" + (
        f" — {iss['description']}" if iss["description"] else "")
    return drawingset.transmittal_pdf(reg, project_name, recipients, note)


def sealed_transmittal_pdf(db: Session, pid: str, issuance_id: str, project_name: str,
                           sealer_name: str = "") -> tuple[bytes, bool]:
    """The issuance transmittal, digitally sealed (PAdES) by the professional of record when e-sign is
    configured — a tamper-evident seal that voids if the PDF is edited (what jurisdictions require for
    electronic permit/IFC submittal). Returns (pdf, sealed?) — unsealed when e-sign isn't configured."""
    from . import esign
    iss = next((i for i in _issuances(db, pid) if i["id"] == issuance_id), None)
    if not iss:
        raise HTTPException(404, "issuance not found")
    pdf = transmittal_pdf(db, pid, issuance_id, project_name)
    if not esign.is_configured():
        return pdf, False
    reason = f"Issued for {iss['purpose']} — {iss['issue_date']}"
    return esign.digitally_sign(pdf, reason=reason,
                                name=sealer_name or "Architect / Engineer of Record"), True
