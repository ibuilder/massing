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

# A minimal standard construction chart of accounts (code -> name, type, normal balance). Enough to post
# job cost + WIP as balanced double-entry journal entries and produce a trial balance.
COA: dict[str, dict[str, str]] = {
    "1200": {"name": "Accounts Receivable", "type": "Asset", "normal": "debit"},
    "1300": {"name": "Contract Asset — Costs in Excess of Billings", "type": "Asset", "normal": "debit"},
    "2000": {"name": "Accounts Payable", "type": "Liability", "normal": "credit"},
    "2300": {"name": "Contract Liability — Billings in Excess of Costs", "type": "Liability", "normal": "credit"},
    "4000": {"name": "Contract Revenue", "type": "Revenue", "normal": "credit"},
    "5000": {"name": "Construction Costs", "type": "Expense", "normal": "debit"},
}


def chart_of_accounts() -> list[dict]:
    """The standard construction chart of accounts (code, name, type, normal balance)."""
    return [{"code": c, **v} for c, v in sorted(COA.items())]


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


def _acct(code: str) -> str:
    return f"{code} {COA[code]['name']}"


def journal_entries(db: Session, project_id: str) -> dict:
    """**Balanced double-entry journal** posted from job cost + billing + the WIP percentage-of-completion
    adjustment. Each entry's debits equal its credits:
      • direct cost / sub bill → Dr Construction Costs (5000)  Cr Accounts Payable (2000)
      • owner invoice          → Dr Accounts Receivable (1200) Cr Contract Revenue (4000)
      • WIP POC adjustment     → recognizes earned≠billed: under-billing Dr Contract Asset (1300) Cr
        Revenue (4000); over-billing Dr Revenue (4000) Cr Contract Liability (2300).
    So total Contract Revenue nets to **earned** (billed + under-billings − over-billings)."""
    from . import wip
    ents: list[dict] = []

    def je(date: str, ref: str, memo: str, lines: list[tuple[str, float, float]]) -> None:
        rows = [{"account": _acct(c), "code": c, "debit": round(d, 2), "credit": round(cr, 2)}
                for c, d, cr in lines if round(d, 2) or round(cr, 2)]
        ents.append({"date": date, "ref": ref, "memo": memo, "lines": rows,
                     "debit_total": round(sum(x["debit"] for x in rows), 2),
                     "credit_total": round(sum(x["credit"] for x in rows), 2)})

    for e in journal(db, project_id):                         # costs + sub bills → cost / AP
        je(e["date"], e["ref"] or "", e["memo"], [("5000", e["amount"], 0), ("2000", 0, e["amount"])])
    for r in (me.list_records(db, "owner_invoice", project_id, limit=100_000) if "owner_invoice" in me.TABLES else []):
        d = r.get("data", {})
        amt = _num(d.get("amount"))
        if amt:
            je(_fmt_date(d.get("period")), r.get("ref") or "", f"Owner invoice {d.get('number') or ''}".strip(),
               [("1200", amt, 0), ("4000", 0, amt)])
    w = wip.schedule(db, project_id)
    if w["under_billing"]:
        je(w.get("data_date", ""), "WIP-ADJ", "POC revenue recognition — costs in excess of billings",
           [("1300", w["under_billing"], 0), ("4000", 0, w["under_billing"])])
    if w["over_billing"]:
        je(w.get("data_date", ""), "WIP-ADJ", "POC deferral — billings in excess of costs",
           [("4000", w["over_billing"], 0), ("2300", 0, w["over_billing"])])
    return {"entries": ents,
            "debit_total": round(sum(e["debit_total"] for e in ents), 2),
            "credit_total": round(sum(e["credit_total"] for e in ents), 2),
            "balanced": abs(sum(e["debit_total"] for e in ents) - sum(e["credit_total"] for e in ents)) < 0.01,
            "note": "Double-entry job cost + billing + WIP POC adjustment. Contract Revenue nets to earned "
                    "(billed + under-billings − over-billings)."}


def trial_balance(db: Session, project_id: str) -> dict:
    """Aggregate the journal into a trial balance — debits and credits per account, which must tie."""
    je = journal_entries(db, project_id)
    by: dict[str, dict] = {}
    for ent in je["entries"]:
        for ln in ent["lines"]:
            a = by.setdefault(ln["code"], {"code": ln["code"], "account": COA[ln["code"]]["name"],
                                           "type": COA[ln["code"]]["type"], "debit": 0.0, "credit": 0.0})
            a["debit"] += ln["debit"]; a["credit"] += ln["credit"]
    rows = []
    for c in sorted(by):
        a = by[c]; net = round(a["debit"] - a["credit"], 2)
        rows.append({**a, "debit": round(a["debit"], 2), "credit": round(a["credit"], 2),
                     "balance": abs(net), "balance_side": "debit" if net >= 0 else "credit"})
    td = round(sum(r["debit"] for r in rows), 2); tc = round(sum(r["credit"] for r in rows), 2)
    return {"accounts": rows, "debit_total": td, "credit_total": tc, "balanced": abs(td - tc) < 0.01,
            "note": "Trial balance — total debits must equal total credits. Sourced from the double-entry "
                    "journal (job cost + billing + WIP adjustment)."}


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
