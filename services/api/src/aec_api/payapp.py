"""Pay-application ↔ lien-waiver exchange — the accountability layer between billing and payment.

Missed lien waivers are how GCs get double-paid or hit with a mechanic's lien (Siteline / Trimble Pay /
Procore Pay exist entirely for this). This reconciles what was **paid** (`sub_invoice`) against the
**lien waivers** on file (`lien_waiver`) per vendor, and surfaces the exposure: money paid out that no
*unconditional* waiver yet covers. Deterministic, offline; it doesn't move money (that's a licensed
processor via `payments_bridge`) — it enforces the paperwork discipline that protects the GC.

Convention: a waiver is *conditional* (effective only when payment clears) or *unconditional* (final,
after funds received), and *progress* or *final*. We match by substring on `waiver_type` so it works
with whatever labels a deployment uses."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as me


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _is_unconditional(wt: str) -> bool:
    return "unconditional" in (wt or "").lower()


def reconcile(db: Session, project_id: str) -> dict:
    """Per-vendor billed / paid / waiver coverage + lien exposure, and a project rollup."""
    invoices = me.list_records(db, "sub_invoice", project_id, limit=100_000) if "sub_invoice" in me.TABLES else []
    waivers = me.list_records(db, "lien_waiver", project_id, limit=100_000) if "lien_waiver" in me.TABLES else []

    vend: dict[str, dict] = {}

    def V(name: str) -> dict:
        return vend.setdefault(name or "(unknown)", {
            "vendor": name or "(unknown)", "billed": 0.0, "paid": 0.0, "retainage": 0.0,
            "waived_unconditional": 0.0, "waived_conditional": 0.0,
            "paid_invoices": 0, "waivers": 0})

    for r in invoices:
        d = r.get("data", {})
        v = V(d.get("vendor"))
        amt = _num(d.get("amount"))
        ret = amt * _num(d.get("retainage_pct")) / 100.0
        state = r.get("workflow_state")
        if state in ("approved", "paid"):
            v["billed"] += amt
            v["retainage"] += ret
        if state == "paid":
            v["paid"] += amt
            v["paid_invoices"] += 1

    for r in waivers:
        d = r.get("data", {})
        if r.get("workflow_state") not in ("received", "closed"):
            continue                                             # only waivers actually on file count
        v = V(d.get("vendor"))
        amt = _num(d.get("amount"))
        v["waivers"] += 1
        if _is_unconditional(d.get("waiver_type")):
            v["waived_unconditional"] += amt
        else:
            v["waived_conditional"] += amt

    rows = []
    for v in vend.values():
        exposure = round(max(0.0, v["paid"] - v["waived_unconditional"]), 2)
        v["exposure"] = exposure
        v["status"] = ("clear" if exposure <= 0.005 else
                       "conditional_only" if v["waived_conditional"] >= exposure else "no_waiver")
        for k in ("billed", "paid", "retainage", "waived_unconditional", "waived_conditional"):
            v[k] = round(v[k], 2)
        rows.append(v)
    rows.sort(key=lambda x: -x["exposure"])

    total_exposure = round(sum(r["exposure"] for r in rows), 2)
    at_risk = [r["vendor"] for r in rows if r["exposure"] > 0.005]
    return {"vendors": rows, "vendor_count": len(rows),
            "total_lien_exposure": total_exposure, "vendors_at_risk": at_risk,
            "message": (None if not at_risk else
                        f"{len(at_risk)} vendor(s) paid without an unconditional lien waiver on file — "
                        "collect waivers to close the exposure.")}
