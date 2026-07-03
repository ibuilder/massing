"""Accounting export — hand construction costs to the books without re-keying.

GC finance modules (`sub_invoice`, `direct_cost`, `commitment`) are useless to the accountant if they're
siloed; every competitor integrates with QuickBooks / Sage. This produces two standard, offline exports
the accountant can import directly:
  - a **general-ledger CSV** (date / account / vendor / cost code / debit / credit) — universal, and
  - a **QuickBooks IIF** bills file (AP bills from subcontractor invoices).
Live two-way sync (QBO / Sage APIs) is the job of the connection framework (`connectors.py`, which already
has `quickbooks`/`sage` connection types) — this covers the 80% case that just needs a clean import file.

Deterministic, no external calls. Amounts are dollars; dates pass through as ISO/whatever the record holds."""
from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from . import modules as me

# Default account mapping — a deployment can override via cost-code / settings later.
AP_ACCOUNT = "Accounts Payable"
COST_ACCOUNT = "Construction Costs"


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _fmt_date(v) -> str:
    return str(v or "")[:10]


def journal(db: Session, project_id: str) -> list[dict]:
    """Flatten AP bills (sub_invoice) + posted costs (direct_cost) into GL lines."""
    entries: list[dict] = []
    for r in (me.list_records(db, "sub_invoice", project_id, limit=100_000) if "sub_invoice" in me.TABLES else []):
        d = r.get("data", {})
        amt = _num(d.get("amount"))
        if amt == 0:
            continue
        entries.append({
            "kind": "bill", "ref": r.get("ref"), "date": _fmt_date(d.get("invoice_date")),
            "vendor": d.get("vendor") or "", "cost_code": d.get("cost_code") or "",
            "memo": f"Sub invoice {r.get('ref') or ''} {d.get('period') or ''}".strip(),
            "amount": round(amt, 2), "status": r.get("workflow_state")})
    for r in (me.list_records(db, "direct_cost", project_id, limit=100_000) if "direct_cost" in me.TABLES else []):
        d = r.get("data", {})
        amt = _num(d.get("amount"))
        if amt == 0:
            continue
        entries.append({
            "kind": "cost", "ref": r.get("ref"), "date": _fmt_date(d.get("date")),
            "vendor": d.get("vendor") or "", "cost_code": d.get("cost_code") or "",
            "memo": (d.get("description") or "")[:80], "amount": round(amt, 2),
            "status": r.get("workflow_state")})
    return entries


def to_gl_csv(entries: list[dict]) -> str:
    """Double-entry GL: each cost debits Construction Costs and credits AP (universal import format)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Ref", "Account", "Vendor", "CostCode", "Memo", "Debit", "Credit"])
    for e in entries:
        w.writerow([e["date"], e["ref"], COST_ACCOUNT, e["vendor"], e["cost_code"], e["memo"], f"{e['amount']:.2f}", ""])
        w.writerow([e["date"], e["ref"], AP_ACCOUNT, e["vendor"], e["cost_code"], e["memo"], "", f"{e['amount']:.2f}"])
    return buf.getvalue()


def to_iif_bills(entries: list[dict]) -> str:
    """QuickBooks IIF bills (AP): one BILL transaction per sub invoice, cost split by cost code."""
    lines = ["\t".join(["!TRNS", "TRNSTYPE", "DATE", "ACCNT", "NAME", "AMOUNT", "MEMO"]),
             "\t".join(["!SPL", "TRNSTYPE", "DATE", "ACCNT", "NAME", "AMOUNT", "MEMO"]),
             "!ENDTRNS"]
    for e in (x for x in entries if x["kind"] == "bill"):
        amt = e["amount"]
        lines.append("\t".join(["TRNS", "BILL", e["date"], AP_ACCOUNT, e["vendor"], f"-{amt:.2f}", e["memo"]]))
        lines.append("\t".join(["SPL", "BILL", e["date"], COST_ACCOUNT, e["vendor"], f"{amt:.2f}",
                                f"{e['cost_code']} {e['memo']}".strip()]))
        lines.append("ENDTRNS")
    return "\n".join(lines) + "\n"
