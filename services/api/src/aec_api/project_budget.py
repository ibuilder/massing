"""GC project budget (GMP) — the relational on-budget view a project executive lives in.

Assembles the agreed-upon GMP from its parts and tracks each against reality:

  Direct trade work (cost codes, grouped by CSI division, tied to bid packages)
  + General Requirements (CSI Division 01 cost codes + GR staffing)
  + General Conditions (project-team staffing projections)
  + Overhead  (overhead_pct of cost)
  + Fee / Profit (fee_pct of cost)
  + GC Contingency (contingency_pct of direct)
  = GMP

Every line carries budget vs committed (buyout) vs actual vs forecast vs variance, keyed off the same
cost codes / commitments / subcontracts / direct costs the rest of the portal uses. Reconciles to the
prime-contract value and to the developer proforma's construction hard-cost line, so the GC budget and
the developer's underwriting are one relational number.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pdate(v: Any):
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _records(db: Session, key: str, pid: str) -> list[dict]:
    if key not in me.TABLES:
        return []
    return me.list_records(db, key, pid, limit=1_000_000)


def staffing_cost(data: dict) -> float:
    """Projected cost of a staffing line = headcount × rate × periods(on-site → off-site)."""
    count = _n(data.get("count")) or 1
    rate = _n(data.get("rate"))
    if not rate:
        return 0.0
    s, f = _pdate(data.get("start")), _pdate(data.get("finish"))
    period = (data.get("rate_period") or "Month").lower()
    if s and f and f > s:
        days = (f - s).days
        units = days / 30.4 if period == "month" else days / 7 if period == "week" else days * 8
    else:
        units = 1.0
    return round(count * rate * units, 2)


def _line(name: str, budget: float, committed: float = 0.0, actual: float = 0.0,
          eac: float | None = None, **extra: Any) -> dict:
    # EAC (estimate at completion) = the PX's keyed forecast if any, else the worst of
    # committed/actual/budget once anything is committed or spent, else the budget. ETC = left to go.
    if eac and eac > 0:
        eac_val = eac
    elif committed or actual:
        eac_val = max(committed, actual, budget)
    else:
        eac_val = budget
    eac_val = round(eac_val, 2)
    etc = round(max(eac_val - actual, 0.0), 2)
    return {"name": name, "budget": round(budget, 2), "committed": round(committed, 2),
            "actual": round(actual, 2), "forecast": eac_val, "eac": eac_val, "etc": etc,
            "variance": round(budget - eac_val, 2), **extra}


def _category(key: str, name: str, lines: list[dict], **extra: Any) -> dict:
    agg = {k: round(sum(_n(l[k]) for l in lines), 2) for k in ("budget", "committed", "actual", "forecast", "eac", "etc")}
    agg["variance"] = round(agg["budget"] - agg["eac"], 2)
    return {"key": key, "name": name, "lines": lines, **agg, **extra}


def gmp_budget(db: Session, pid: str, proforma_hard: float | None = None) -> dict:
    """Build the full GMP budget. `proforma_hard` is the developer proforma's hard-cost total for the
    reconciliation line (the caller passes it from the project's dev_budget)."""
    # --- maps keyed by the referenced cost_code record id -----------------------
    budget_by_cc: dict[str, float] = {}
    forecast_by_cc: dict[str, float] = {}      # PX's keyed cost-at-completion per cost code (EAC)
    for r in _records(db, "budget", pid):
        d = r.get("data") or {}
        cc = d.get("cost_code")
        amt = _n(d.get("revised")) or _n(d.get("original")) or _n(d.get("budget"))
        if cc:
            budget_by_cc[cc] = budget_by_cc.get(cc, 0.0) + amt
            forecast_by_cc[cc] = forecast_by_cc.get(cc, 0.0) + _n(d.get("forecast"))

    committed_by_cc: dict[str, float] = {}
    for r in _records(db, "commitment", pid):
        d = r.get("data") or {}
        if r.get("workflow_state") in ("executed", "closed") and d.get("cost_code"):
            committed_by_cc[d["cost_code"]] = committed_by_cc.get(d["cost_code"], 0.0) + _n(d.get("amount"))
    for r in _records(db, "subcontract", pid):
        d = r.get("data") or {}
        if r.get("workflow_state") == "executed" and d.get("cost_code"):
            committed_by_cc[d["cost_code"]] = committed_by_cc.get(d["cost_code"], 0.0) + _n(d.get("value"))

    actual_by_cc: dict[str, float] = {}
    for r in _records(db, "direct_cost", pid):
        d = r.get("data") or {}
        if d.get("cost_code"):
            actual_by_cc[d["cost_code"]] = actual_by_cc.get(d["cost_code"], 0.0) + _n(d.get("amount"))

    # --- classify cost codes: Division 01/00 → General Requirements; else direct trade work ----
    direct_groups: dict[str, list[dict]] = {}
    gr_costcode_lines: list[dict] = []
    for r in _records(db, "cost_code", pid):
        d = r.get("data") or {}
        cid = r.get("id")
        div = str(d.get("division") or "").strip()
        code = d.get("code") or r.get("ref") or ""
        line = _line(f"{code} {d.get('description') or ''}".strip(),
                     budget_by_cc.get(cid, 0.0), committed_by_cc.get(cid, 0.0),
                     actual_by_cc.get(cid, 0.0), eac=forecast_by_cc.get(cid) or None,
                     code=code, division=div, ref=r.get("ref"), cost_code_id=cid)
        if div[:2] in ("00", "01"):
            gr_costcode_lines.append(line)
        else:
            direct_groups.setdefault(div or "—", []).append(line)

    # --- staffing projections split into General Conditions / General Requirements ----
    gc_staff, gr_staff = [], []
    for r in _records(db, "staffing", pid):
        d = r.get("data") or {}
        cost = staffing_cost(d)
        line = _line(f"{d.get('role') or 'Staff'} ×{int(_n(d.get('count')) or 1)}", cost, cost, 0.0,
                     role=d.get("role"), ref=r.get("ref"))
        (gr_staff if d.get("category") == "General Requirements" else gc_staff).append(line)

    # --- assemble categories ----------------------------------------------------
    direct_group_cats = [
        _category(f"div-{div}", f"Division {div}" if div != "—" else "Uncoded",
                  sorted(lines, key=lambda l: l["name"]))
        for div, lines in sorted(direct_groups.items())
    ]
    direct = _category("direct", "Direct Work (Trades)",
                       [{**g, "is_group": True} for g in direct_group_cats], groups=direct_group_cats)
    general_conditions = _category("general_conditions", "General Conditions", gc_staff)
    general_requirements = _category("general_requirements", "General Requirements",
                                     gr_costcode_lines + gr_staff)

    cost_of_work = direct["budget"] + general_conditions["budget"] + general_requirements["budget"]

    # --- markups from the prime contract (PX sets the rates) ---------------------
    pc = next(iter(_records(db, "prime_contract", pid)), None)
    pcd = (pc or {}).get("data") or {}
    oh_pct, fee_pct, cont_pct = _n(pcd.get("overhead_pct")), _n(pcd.get("fee_pct")), _n(pcd.get("contingency_pct"))
    gmp_value = _n(pcd.get("value"))

    overhead_amt = round(cost_of_work * oh_pct / 100, 2)
    fee_amt = round((cost_of_work + overhead_amt) * fee_pct / 100, 2)
    contingency_amt = round(direct["budget"] * cont_pct / 100, 2)
    overhead = _category("overhead", f"Overhead ({oh_pct}%)", [_line("Home-office overhead", overhead_amt)])
    fee = _category("fee", f"Fee / Profit ({fee_pct}%)", [_line("Fee", fee_amt)])
    contingency = _category("contingency", f"GC Contingency ({cont_pct}%)", [_line("Contingency", contingency_amt)])

    # approved/executed change orders adjust the GMP (original contract + approved COs = revised GMP)
    changes_total = changes_alloc = 0.0
    for r in _records(db, "cor", pid):
        if r.get("workflow_state") in ("approved", "executed"):
            amt = _n((r.get("data") or {}).get("amount"))
            changes_total += amt
            if (r.get("data") or {}).get("cost_code"):
                changes_alloc += amt
    changes_total, changes_alloc = round(changes_total, 2), round(changes_alloc, 2)

    categories = [direct, general_requirements, general_conditions, overhead, fee, contingency]
    totals = {k: round(sum(_n(c[k]) for c in categories), 2)
              for k in ("budget", "committed", "actual", "forecast", "eac", "etc")}
    totals["variance"] = round(totals["budget"] - totals["eac"], 2)     # variance at completion (VAC)
    gmp_computed = totals["budget"]
    # forward-looking completion picture: cost-to-complete (ETC) + projected over/under at finish
    completion = {"bac": totals["budget"], "eac": totals["eac"], "etc": totals["etc"],
                  "actual_to_date": totals["actual"],
                  "projected_over_under": round(totals["budget"] - totals["eac"], 2),
                  "pct_spent": round(totals["actual"] / totals["eac"] * 100, 1) if totals["eac"] else 0.0}

    # --- bid-package buyout tracking + savings (estimate vs awarded bid) ----------
    awarded_by_pkg: dict[str, float] = {}
    for r in _records(db, "bid_submission", pid):
        d = r.get("data") or {}
        if d.get("status") == "Awarded" and d.get("package"):
            amt = _n(d.get("amount")) or _n(d.get("base_bid"))
            awarded_by_pkg[d["package"]] = awarded_by_pkg.get(d["package"], 0.0) + amt
    bid_packages = []
    for r in _records(db, "bid_package", pid):
        d = r.get("data") or {}
        bud = _n(d.get("budget")) or _n(d.get("estimate"))
        awarded = round(awarded_by_pkg.get(r.get("id"), 0.0), 2)
        bid_packages.append({"ref": r.get("ref"), "name": r.get("title") or d.get("name"),
                             "trade": d.get("trade"), "budget": round(bud, 2),
                             "awarded": awarded, "bought_out": awarded > 0,
                             "savings": round(bud - awarded, 2) if (bud and awarded) else 0.0,
                             "submissions": _n(d.get("submission_count"))})
    buyout = {
        "packages": len(bid_packages),
        "bought_out": sum(1 for b in bid_packages if b["bought_out"]),
        "budget": round(sum(b["budget"] for b in bid_packages), 2),
        "awarded": round(sum(b["awarded"] for b in bid_packages), 2),
        # savings on bought-out packages roll to contingency (negative = overrun on buyout)
        "savings": round(sum(b["savings"] for b in bid_packages), 2),
    }

    return {
        "gmp": {"contract_value": round(gmp_value, 2), "computed": round(gmp_computed, 2),
                "reconciliation": round(gmp_value - gmp_computed, 2) if gmp_value else None,
                "cost_of_work": round(cost_of_work, 2),
                "approved_changes": changes_total, "unallocated_changes": round(changes_total - changes_alloc, 2),
                "revised": round(gmp_computed + changes_total, 2),
                "markups": {"overhead_pct": oh_pct, "fee_pct": fee_pct, "contingency_pct": cont_pct}},
        "categories": categories,
        "totals": totals,
        "completion": completion,
        "bid_packages": bid_packages,
        "buyout": buyout,
        "staffing": {"projected": round(general_conditions["budget"] + sum(_n(l["budget"]) for l in gr_staff), 2),
                     "headcount_roles": len(gc_staff) + len(gr_staff)},
        "proforma": ({"hard_cost": round(_n(proforma_hard), 2),
                      "gmp_vs_hard": round(gmp_computed - _n(proforma_hard), 2)}
                     if proforma_hard is not None else None),
    }
