"""Contract / subcontract / change-order / exhibit document generation (AIA-shaped, PDF).

Produces real instruments from the config-driven contract records — A401-style subcontract, prime
contract, G701-style change order, and an Exhibit A scope of work composed from the scope_library —
with merge fields and signature blocks. Built with reportlab Platypus (already a dep). The generic
modules `record_pdf` is just a field dump; these are the negotiated documents you route + sign.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import scope_library as sl
from .models import Project


def _money(v: Any) -> str:
    try:
        return f"${float(v or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _context(db: Session, key: str, pid: str, rid: str) -> tuple[dict, dict, dict]:
    """(record, data, merge-context) for a contract record — folds in project + prime-contract data."""
    rec = me.get_record(db, key, pid, rid)
    d = rec.get("data") or {}
    p = db.get(Project, pid)
    primes = me.list_records(db, "prime_contract", pid, limit=1) if "prime_contract" in me.TABLES else []
    prime = (primes[0].get("data") if primes else {}) or {}
    ctx = {
        "project": p.name if p else pid,
        "vendor": d.get("vendor") or d.get("name") or "the Subcontractor",
        "owner": d.get("owner") or prime.get("owner") or "the Owner",
        "trade": d.get("trade") or "",
        "value": _money(d.get("value") or d.get("amount")),
        "retainage": f"{d.get('retainage_pct', prime.get('retainage_pct', 10) or 10)}%",
        "scope": d.get("scope") or "",
        "prime_value": prime.get("value"),
    }
    return rec, d, ctx


# --- reportlab building blocks ----------------------------------------------
def _styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("DocTitle", parent=ss["Title"], fontSize=18, spaceAfter=4))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], textColor=(0.35, 0.35, 0.35), spaceAfter=10))
    ss.add(ParagraphStyle("H", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=10, leading=14, spaceAfter=6))
    return ss


def _build(flowables) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, topMargin=0.9 * inch, bottomMargin=0.8 * inch,
                      leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                      title="Contract document").build(flowables)
    return buf.getvalue()


def _signature_block(ss, parties: list[tuple[str, str]], signatures: list[dict]):
    """A signature table: one row per party (label, signed name/date or blank lines)."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    by_party = {s.get("party"): s for s in (signatures or [])}
    rows = [[Paragraph("<b>Signatures</b>", ss["Body"]), ""]]
    for label, party in parties:
        s = by_party.get(party)
        sig = (f"{s.get('name', '')}  ·  {s.get('signed_at', '')}" if s else "________________________")
        rows.append([Paragraph(f"{label} ({party})", ss["Body"]), Paragraph(sig, ss["Body"])])
    t = Table(rows, colWidths=[200, 300])
    t.setStyle(TableStyle([("LINEBELOW", (1, 1), (1, -1), 0.5, colors.grey),
                           ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                           ("TOPPADDING", (0, 1), (-1, -1), 14)]))
    return [Spacer(1, 16), t]


# --- documents ---------------------------------------------------------------
def _exhibit_flowables(ss, ctx: dict, clause_ids: list[str] | None):
    from reportlab.platypus import Paragraph, Spacer
    ids = clause_ids or sl.default_ids(ctx.get("trade"))
    out = [Paragraph("Exhibit A — Scope of Work", ss["DocTitle"]),
           Paragraph(f"{ctx['project']} · {ctx['vendor']}", ss["Sub"])]
    for c in sl.clauses_by_ids(ids):
        out.append(Paragraph(sl.merge(c["title"], ctx), ss["H"]))
        out.append(Paragraph(sl.merge(c["body"], ctx), ss["Body"]))
    if len(out) <= 2:
        out.append(Paragraph("No scope clauses selected.", ss["Body"]))
    out.append(Spacer(1, 8))
    return out


def subcontract_agreement(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    from reportlab.platypus import Paragraph, Spacer
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    f = [Paragraph("Subcontract Agreement", ss["DocTitle"]),
         Paragraph(f"AIA A401-style · {rec.get('ref', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"This Subcontract is entered into for the Project <b>{ctx['project']}</b> between the "
                   f"General Contractor and <b>{ctx['vendor']}</b> (“Subcontractor”) for the "
                   f"<b>{ctx['trade'] or 'specified'}</b> work.", ss["Body"]),
         Paragraph("Article 1 — The Work", ss["H"]),
         Paragraph("The Subcontractor shall perform the work described in <b>Exhibit A — Scope of Work</b> "
                   "attached hereto and made a part of this Subcontract.", ss["Body"]),
         Paragraph("Article 2 — Subcontract Sum", ss["H"]),
         Paragraph(f"The General Contractor shall pay the Subcontractor the Subcontract Sum of "
                   f"<b>{ctx['value']}</b>, subject to {ctx['retainage']} retainage and the terms below.", ss["Body"]),
         Paragraph("Article 3 — Conditions", ss["H"])]
    for c in sl.clauses_by_ids([x for x in sl.default_ids(ctx.get("trade")) if x not in
                                {s["id"] for s in sl.CLAUSES if s["category"] == "Scope"}]):
        f.append(Paragraph(sl.merge(c["title"], ctx), ss["H"]))
        f.append(Paragraph(sl.merge(c["body"], ctx), ss["Body"]))
    f += _signature_block(ss, [("General Contractor", "GC"), ("Subcontractor", "Subcontractor")], (d.get("signatures") or []))
    f.append(Spacer(1, 12))
    f += _exhibit_flowables(ss, ctx, clause_ids)
    return _build(f)


def prime_contract(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    from reportlab.platypus import Paragraph
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    f = [Paragraph("Prime Contract", ss["DocTitle"]),
         Paragraph(f"{rec.get('ref', '')} · {d.get('type', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Agreement between <b>{ctx['owner']}</b> (“Owner”) and the General Contractor for "
                   f"the Project <b>{ctx['project']}</b>.", ss["Body"]),
         Paragraph("Article 1 — Contract Sum", ss["H"]),
         Paragraph(f"The Contract Sum is <b>{_money(d.get('value'))}</b> ({d.get('type', 'Lump Sum')}), "
                   f"subject to {ctx['retainage']} retainage.", ss["Body"]),
         Paragraph("Article 2 — General Conditions", ss["H"])]
    for c in sl.clauses_by_ids([x for x in sl.default_ids(None) if x not in
                                {s["id"] for s in sl.CLAUSES if s["category"] == "Scope"}]):
        f.append(Paragraph(sl.merge(c["title"], ctx), ss["H"]))
        f.append(Paragraph(sl.merge(c["body"], ctx), ss["Body"]))
    f += _signature_block(ss, [("Owner", "Owner"), ("General Contractor", "GC")], (d.get("signatures") or []))
    return _build(f)


def change_order(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    amount = float(d.get("amount") or 0)
    original = float(ctx.get("prime_value") or 0)
    revised = original + amount
    rows = [["", "Amount"],
            ["Original Contract Sum", _money(original)],
            ["This Change Order", _money(amount)],
            ["Revised Contract Sum", _money(revised)]]
    t = Table(rows, colWidths=[300, 150])
    t.setStyle(TableStyle([("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.grey),
                           ("LINEABOVE", (0, 3), (-1, 3), 1, colors.black),
                           ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                           ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    f = [Paragraph("Change Order", ss["DocTitle"]),
         Paragraph(f"AIA G701-style · {rec.get('ref', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Project: <b>{ctx['project']}</b>", ss["Body"]),
         Paragraph("Description of Change", ss["H"]),
         Paragraph(f"<b>{d.get('subject', '')}</b>", ss["Body"]),
         Paragraph(d.get("justification") or d.get("reason") or "See attached documentation.", ss["Body"]),
         Paragraph("Adjustment to the Contract", ss["H"]), t,
         Paragraph(f"The Contract Time will be {'adjusted by ' + str(d.get('schedule_days')) + ' days' if d.get('schedule_days') else 'unchanged'} by this Change Order.", ss["Body"])]
    f += _signature_block(ss, [("Owner", "Owner"), ("Architect", "Architect"),
                               ("General Contractor", "GC"), ("Subcontractor", "Subcontractor")],
                          (d.get("signatures") or []))
    return _build(f)


def exhibit(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    _, _, ctx = _context(db, key, pid, rid)
    return _build(_exhibit_flowables(_styles(), ctx, clause_ids))


def asi_instruction(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    """AIA G710-style Architect's Supplemental Instruction — a clarification issued by the architect
    with no change to the contract sum or time (unless flagged)."""
    from reportlab.platypus import Paragraph
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    impact = d.get("cost_time_impact") or "No cost or schedule impact (G710)"
    refs = " · ".join(x for x in (d.get("drawing_ref"), d.get("spec_ref")) if x)
    f = [Paragraph("Architect's Supplemental Instructions", ss["DocTitle"]),
         Paragraph(f"AIA G710-style · {rec.get('ref', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Project: <b>{ctx['project']}</b>", ss["Body"]),
         Paragraph("Instruction", ss["H"]),
         Paragraph(f"<b>{d.get('subject', '')}</b>", ss["Body"]),
         Paragraph(d.get("instruction") or "", ss["Body"])]
    if refs:
        f.append(Paragraph(f"References: {refs}", ss["Body"]))
    f.append(Paragraph(f"<b>Contract impact:</b> {impact}. The Contractor shall carry out this "
                       "instruction; it does not authorize a change in the Contract Sum or Time unless "
                       "so noted, in which case a Change Order or Construction Change Directive follows.",
                       ss["Body"]))
    f += _signature_block(ss, [("Architect", "Architect"), ("Contractor (received)", "GC")],
                          (d.get("signatures") or []))
    return _build(f)


def bulletin_notice(db: Session, key: str, pid: str, rid: str, clause_ids: list[str] | None = None) -> bytes:
    """A design Bulletin cover sheet — a formal revision to the contract documents; if it carries cost
    or time impact it routes to a change event / change order for pricing."""
    from reportlab.platypus import Paragraph
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    impact = d.get("cost_time_impact") or "No cost or schedule impact"
    f = [Paragraph("Design Bulletin", ss["DocTitle"]),
         Paragraph(f"{rec.get('ref', '')} · {d.get('discipline', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Project: <b>{ctx['project']}</b>", ss["Body"]),
         Paragraph("Description of Revision", ss["H"]),
         Paragraph(f"<b>{d.get('subject', '')}</b>", ss["Body"]),
         Paragraph(d.get("description") or "", ss["Body"])]
    if d.get("drawings_affected"):
        f += [Paragraph("Drawings Affected", ss["H"]), Paragraph(d["drawings_affected"], ss["Body"])]
    if d.get("spec_sections"):
        f.append(Paragraph(f"Spec sections affected: {d['spec_sections']}", ss["Body"]))
    f.append(Paragraph(f"<b>Contract impact:</b> {impact}. Where cost or time is affected, submit pricing "
                       "for a Change Order.", ss["Body"]))
    f += _signature_block(ss, [("Architect", "Architect"), ("General Contractor", "GC")],
                          (d.get("signatures") or []))
    return _build(f)


def construction_change_directive(db: Session, key: str, pid: str, rid: str,
                                  clause_ids: list[str] | None = None) -> bytes:
    """AIA G714-style Construction Change Directive — directs a change before cost/time are agreed;
    signed by Owner + Architect, the Contractor signs later to confirm. Renders a `directive` record."""
    from reportlab.platypus import Paragraph
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    nte = d.get("not_to_exceed")
    f = [Paragraph("Construction Change Directive", ss["DocTitle"]),
         Paragraph(f"AIA G714-style · {rec.get('ref', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Project: <b>{ctx['project']}</b>", ss["Body"]),
         Paragraph("Directed Change", ss["H"]),
         Paragraph(f"<b>{d.get('subject', '')}</b>", ss["Body"]),
         Paragraph(d.get("scope") or "", ss["Body"]),
         Paragraph(f"Pricing basis: {d.get('basis') or 'to be determined'}"
                   + (f" · Not-to-exceed {_money(nte)}" if nte else ""), ss["Body"]),
         Paragraph("The Contractor shall proceed with the change described above. The adjustment to the "
                   "Contract Sum and Time is not yet agreed; when agreed, this directive is superseded by "
                   "a Change Order. The Owner and Architect authorize the Work below.", ss["Body"])]
    f += _signature_block(ss, [("Owner", "Owner"), ("Architect", "Architect"),
                               ("Contractor (agreement to follow)", "GC")], (d.get("signatures") or []))
    return _build(f)


def certificate_substantial_completion(db: Session, key: str, pid: str, rid: str,
                                       clause_ids: list[str] | None = None) -> bytes:
    """AIA G704-style Certificate of Substantial Completion — certified by the Architect, with the
    outstanding punch list attached, and signed by Owner + Contractor. Rendered from a
    completion_certificate record (type=Substantial)."""
    from reportlab.platypus import Paragraph

    from . import turnover
    rec, d, ctx = _context(db, key, pid, rid)
    ss = _styles()
    r = turnover.readiness(db, pid)
    p = r["punch"]
    rmv = d.get("record_model_version")
    f = [Paragraph("Certificate of Substantial Completion", ss["DocTitle"]),
         Paragraph(f"AIA G704-style · {rec.get('ref', '')} · {date.today().isoformat()}", ss["Sub"]),
         Paragraph(f"Project: <b>{ctx['project']}</b>", ss["Body"]),
         Paragraph(d.get("scope") or "The Work performed under this Contract has been reviewed and is "
                   "found, to the Architect's knowledge, to be substantially complete.", ss["Body"]),
         Paragraph("Date of Substantial Completion", ss["H"]),
         Paragraph(f"{d.get('date') or date.today().isoformat()}"
                   + (f" · Owner to occupy on {d['occupancy_date']}" if d.get("occupancy_date") else ""),
                   ss["Body"]),
         Paragraph("Punch List (items to complete or correct)", ss["H"]),
         Paragraph(f"{p['count']} item(s) · {p['open']} open · {p['verified']} verified"
                   + (f" · {p['complete_pct']}% complete" if p['complete_pct'] is not None else "")
                   + (f" · est. cost to complete {_money(p['open_cost'])}" if p['open_cost'] else ""),
                   ss["Body"]),
         Paragraph("A list of items to be completed or corrected is attached. The failure to include an "
                   "item does not alter the responsibility of the Contractor to complete the Work.", ss["Body"]),
         Paragraph("Record (As-Built) Model", ss["H"]),
         Paragraph(f"Record model version: <b>{rmv if rmv is not None else '—'}</b>. "
                   "The as-built model at this version is the record model for turnover.", ss["Body"]),
         Paragraph("The Architect certifies that the Work is substantially complete as of the date above.",
                   ss["Body"])]
    f += _signature_block(ss, [("Architect (certifies)", "Architect"), ("Owner", "Owner"),
                               ("Contractor", "GC")], (d.get("signatures") or []))
    return _build(f)


# doc type -> generator
GENERATORS = {
    "agreement": subcontract_agreement,
    "prime": prime_contract,
    "co": change_order,
    "exhibit": exhibit,
    "asi": asi_instruction,
    "bulletin": bulletin_notice,
    "ccd": construction_change_directive,
    "g704": certificate_substantial_completion,
}


def render(db: Session, key: str, pid: str, rid: str, doc: str, clause_ids: list[str] | None = None) -> bytes:
    gen = GENERATORS.get(doc)
    if not gen:
        raise ValueError(f"unknown document type {doc!r}")
    return gen(db, key, pid, rid, clause_ids)
