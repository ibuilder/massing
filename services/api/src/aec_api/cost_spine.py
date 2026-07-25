"""COST-SPINE — does one cost code carry the *same scope* from estimate through budget, commitment
and invoice, or does the identity break somewhere in between?

`margin.by_cost_code` already totals budget / committed / actual / billed per code. It answers "what
is the margin on 03-3000". It cannot answer the question underneath that one: **is 03-3000 the same
scope at every stage** — because a code that appears at one stage and not the next produces a row
that looks fine. Scope re-coded between the estimate and the buyout, or spend booked against a code
nobody budgeted, is invisible in a per-code total; margin erosion hides in exactly that seam.

So this engine reports **presence, not just amounts**:

  * per code, which stages it appears in and where the chain first breaks;
  * spend on codes that were never budgeted (the expensive direction);
  * budget with nothing behind it (the early-warning direction);
  * records carrying **no cost code at all** — the worst case, because that spend cannot be traced
    to any scope and silently never appears in a per-code report;
  * codes used on records but absent from the project's own cost-code register (free-typed, so two
    spellings of one code become two scopes).

The headline is **traceability**: what share of committed and actual money sits on a code that was
budgeted. A margin number computed over 70%-traceable spend is a different claim from one computed
over 100%, and the caller should not have to work that out.

Pure over the module records (DB read only, no writes).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# stage → (module key, the field holding the money). Order matters: it IS the chain, earliest first,
# and "where the chain first breaks" is read off it left to right.
STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("budget", "budget", ("revised", "budget", "original")),   # first non-zero wins (the control number)
    ("committed", "commitment", ("amount",)),
    ("actual", "direct_cost", ("amount",)),
    ("billed", "sub_invoice", ("amount",)),
)
STAGE_NAMES = tuple(s[0] for s in STAGES)
UNASSIGNED = "(unassigned)"


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _amount(d: dict, fields: tuple[str, ...]) -> float:
    for f in fields:
        v = _num(d.get(f))
        if v:
            return v
    return 0.0


def trace(db: Session, pid: str) -> dict[str, Any]:
    """Trace cost-code identity across the stages. Returns per-code rows, the breaks, and an honest
    traceability headline."""
    from . import modules as me
    from . import resolve_hint as rh

    register = {r["id"]: (r.get("data") or {}) for r in me.list_records(db, "cost_code", pid, limit=100_000)}

    def label(ref: Any) -> str:
        d = register.get(ref)
        if d:
            code = (d.get("code") or "").strip()
            desc = (d.get("description") or "").strip()
            return f"{code} · {desc}" if code and desc else (code or desc or str(ref))
        return str(ref) if ref else UNASSIGNED

    def bare(ref: Any) -> str:
        return ((register.get(ref) or {}).get("code") or "").strip()

    rows: dict[Any, dict[str, Any]] = {}
    unassigned: dict[str, dict[str, float]] = {}
    off_register: set[Any] = set()

    def row(ref: Any) -> dict[str, Any]:
        return rows.setdefault(ref, {"amounts": dict.fromkeys(STAGE_NAMES, 0.0),
                                     "counts": dict.fromkeys(STAGE_NAMES, 0)})

    for stage, module, fields in STAGES:
        try:
            records = me.list_records(db, module, pid, limit=100_000)
        except Exception:                          # noqa: BLE001 — module absent in this deployment
            continue
        for r in records:
            d = r.get("data") or {}
            ref = d.get("cost_code")
            amt = _amount(d, fields)
            if not ref:
                # spend with no code at all — the identity break that no per-code report can show
                u = unassigned.setdefault(stage, {"amount": 0.0, "count": 0})
                u["amount"] += amt
                u["count"] += 1
                continue
            if ref not in register:
                off_register.add(ref)              # a code used on records but not in the register
            e = row(ref)
            e["amounts"][stage] += amt
            e["counts"][stage] += 1

    out: list[dict[str, Any]] = []
    for ref, e in rows.items():
        present = [s for s in STAGE_NAMES if e["counts"][s] > 0]
        # the first stage that has nothing AFTER a stage that had something — where the chain drops
        first_break = None
        seen_any = False
        for s in STAGE_NAMES:
            if e["counts"][s]:
                seen_any = True
            elif seen_any and first_break is None:
                first_break = s
        budgeted = e["counts"]["budget"] > 0
        spend = e["amounts"]["committed"] + e["amounts"]["actual"]
        flags: list[str] = []
        if not budgeted and spend:
            flags.append("spend_without_budget")
        if budgeted and not any(e["counts"][s] for s in ("committed", "actual", "billed")):
            flags.append("budget_without_spend")
        if e["amounts"]["billed"] > e["amounts"]["committed"] + 0.005 and e["counts"]["committed"]:
            flags.append("billed_over_committed")
        if ref in off_register:
            flags.append("code_not_in_register")
        actions: list[dict] = []
        if "spend_without_budget" in flags:
            actions.append(rh.open_module("budget", "Add a budget line", bare(ref) or None))
        if "billed_over_committed" in flags:
            actions.append(rh.open_module("sub_invoice", "Review invoices", bare(ref) or None))
        out.append({
            "cost_code": label(ref), "code": bare(ref), "ref": ref,
            **{s: round(e["amounts"][s], 2) for s in STAGE_NAMES},
            "counts": e["counts"], "stages_present": present,
            "stage_count": len(present), "first_break": first_break,
            "traceable": budgeted, "flags": flags, "actions": actions,
        })

    # broken chains first, then by the money at stake — the rows worth a PM's attention lead
    out.sort(key=lambda r: (not r["flags"], -(r["committed"] + r["actual"])))

    total_spend = sum(r["committed"] + r["actual"] for r in out) + \
        sum(v["amount"] for k, v in unassigned.items() if k in ("committed", "actual"))
    traceable_spend = sum(r["committed"] + r["actual"] for r in out if r["traceable"])
    unassigned_total = sum(v["amount"] for v in unassigned.values())
    unassigned_count = sum(v["count"] for v in unassigned.values())

    # Register codes nobody ever used. Early on that is normal; late it means the estimate's scope
    # breakdown and the actual buyout have drifted apart.
    used = {r["ref"] for r in out}
    unused = sorted(label(ref) for ref in register if ref not in used)

    pct = round(100.0 * traceable_spend / total_spend, 1) if total_spend else None
    if not total_spend:
        note = "No committed or actual cost recorded yet — nothing to trace."
    elif pct == 100.0 and not unassigned_count:
        note = "Every committed and actual dollar sits on a budgeted cost code."
    else:
        bits = [f"{pct}% of committed+actual cost sits on a budgeted code"]
        if unassigned_count:
            bits.append(f"{unassigned_count} record(s) carry no cost code at all "
                        f"(${unassigned_total:,.0f})")
        note = " · ".join(bits) + ". Margin computed over this spend inherits that coverage."

    return {
        "rows": out,
        "code_count": len(out),
        "stages": list(STAGE_NAMES),
        "unassigned": unassigned,
        "unassigned_total": round(unassigned_total, 2),
        "unassigned_count": unassigned_count,
        "codes_not_in_register": sorted(str(r) for r in off_register),
        "unused_register_codes": unused,
        "traceability_pct": pct,
        "traceable_spend": round(traceable_spend, 2),
        "total_spend": round(total_spend, 2),
        "broken": [r["cost_code"] for r in out if r["flags"]],
        "note": note,
    }
