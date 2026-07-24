"""CRE-T12 (R20) — **trailing-twelve normalization, with a gate that refuses to guess.**

A seller's T-12 arrives on the seller's chart of accounts. Before it can price anything it has to
land on ours, with one-time items separated from run-rate and capital separated from operating.
The mapping is the easy half. The half that matters is the **tie-out gate**:

> income, expense and NOI must reconcile *before* and *after* mapping, or the engine stops and
> lists the reconciling items. It does not publish an adjusted NOI on top of a mapping that lost
> money.

That ordering is the whole discipline — an adjusted NOI shown before the source totals tie is how a
$40k reclass disappears into a rounding narrative. Everything here is deterministic arithmetic over
a structured T-12 (the shipped CSV/XLSX importer is how one gets here; parsing a scanned PDF is not
this platform's job).

The operating chart of accounts below is intentionally separate from `accounting.COA`, which is a
*construction* chart (contract revenue, construction costs) and cannot express vacancy loss or a
management fee.
"""
from __future__ import annotations

import re
from typing import Any

# category -> (label, kind, operating). `operating` False = below the NOI line.
OPERATING_COA: dict[str, tuple[str, str, bool]] = {
    "gross_potential_rent": ("Gross potential rent", "income", True),
    "vacancy_loss": ("Vacancy loss", "income", True),
    "concessions": ("Concessions", "income", True),
    "bad_debt": ("Bad debt", "income", True),
    "other_income": ("Other income", "income", True),
    "payroll": ("Payroll", "expense", True),
    "repairs_maintenance": ("Repairs & maintenance", "expense", True),
    "turnover": ("Turnover / make-ready", "expense", True),
    "contract_services": ("Contract services", "expense", True),
    "utilities": ("Utilities", "expense", True),
    "marketing": ("Marketing", "expense", True),
    "administrative": ("General & administrative", "expense", True),
    "management_fee": ("Management fee", "expense", True),
    "insurance": ("Insurance", "expense", True),
    "property_taxes": ("Property taxes", "expense", True),
    "capital_expenditure": ("Capital expenditure", "expense", False),
    "debt_service": ("Debt service", "expense", False),
    "non_operating": ("Non-operating / other", "expense", False),
    "unmapped": ("UNMAPPED", "expense", False),
}

_ALIASES: dict[str, tuple[str, ...]] = {
    "gross_potential_rent": ("gross potential", "gpr", "scheduled rent", "market rent", "rental income",
                             "base rent", "rent income", "gross rent"),
    "vacancy_loss": ("vacancy", "vacancy loss", "physical vacancy", "loss to vacancy"),
    "concessions": ("concession", "free rent", "rent abatement", "loss to lease"),
    "bad_debt": ("bad debt", "write off", "writeoff", "delinquen", "uncollect"),
    "other_income": ("other income", "ancillary", "laundry", "parking income", "pet fee",
                     "application fee", "late fee", "storage income", "utility reimbursement", "rubs"),
    "payroll": ("payroll", "salaries", "wages", "onsite staff", "benefits", "labor"),
    "repairs_maintenance": ("repair", "maintenance", "r m", "r&m", "grounds", "landscap", "pest"),
    "turnover": ("turnover", "make ready", "makeready", "unit prep", "cleaning", "carpet"),
    "contract_services": ("contract service", "contract", "trash", "snow", "elevator", "security"),
    "utilities": ("utilit", "electric", "water", "sewer", "gas", "power"),
    "marketing": ("marketing", "advertis", "leasing commission", "locator", "promotion"),
    "administrative": ("administrat", "g a", "general", "office", "legal", "accounting",
                       "telephone", "bank fee", "software"),
    "management_fee": ("management fee", "property management", "asset management", "mgmt fee"),
    "insurance": ("insurance",),
    "property_taxes": ("tax", "property tax", "real estate tax", "ad valorem"),
    "capital_expenditure": ("capital", "capex", "replacement", "roof replacement", "improvement"),
    "debt_service": ("debt service", "interest expense", "mortgage", "principal"),
    "non_operating": ("depreciation", "amortization", "owner draw", "distribution", "partnership"),
}

_ONE_TIME = ("one time", "onetime", "settlement", "insurance proceed", "legal settlement",
             "hurricane", "storm", "fire damage", "casualty", "true up", "trueup", "prior year",
             "catch up", "catchup", "retro", "non recurring", "nonrecurring")

_TOL = 0.01           # dollars — totals must tie to the cent


def _num(v: Any) -> float:
    if v in (None, ""):
        return 0.0
    s = str(v).replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        return -float(s) if neg else float(s)
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z ]+", " ", str(s or "").lower())


def classify(description: str) -> dict[str, Any]:
    """One source line's house category + treatment. Longest alias wins, so 'management fee'
    beats the bare 'fee' inside another phrase."""
    text = _norm(description)
    best_cat, best_len = "unmapped", 0
    for cat, phrases in _ALIASES.items():
        for p in phrases:
            if p in text and len(p) > best_len:
                best_cat, best_len = cat, len(p)
    label, kind, operating = OPERATING_COA[best_cat]
    treatment = "recurring"
    if best_cat == "capital_expenditure":
        treatment = "capital"
    elif any(p in text for p in _ONE_TIME):
        treatment = "one_time"
    elif best_cat == "unmapped":
        treatment = "reclass"
    return {"category": best_cat, "category_label": label, "kind": kind,
            "operating": operating, "treatment": treatment}


def map_lines(lines: list[dict]) -> list[dict[str, Any]]:
    """Each source line, its original description preserved, plus category and treatment.
    `amount` may be given directly or as 12 `months`; both are carried."""
    out = []
    for ln in lines or []:
        desc = ln.get("description") or ln.get("line") or ln.get("account") or ""
        months = [_num(m) for m in (ln.get("months") or [])]
        amount = _num(ln.get("amount")) if ln.get("amount") not in (None, "") else sum(months)
        c = classify(desc)
        out.append({"description": desc, "amount": round(amount, 2),
                    "months": [round(m, 2) for m in months] or None,
                    "last_3_annualized": round(sum(months[-3:]) * 4, 2) if len(months) >= 3 else None,
                    **c})
    return out


def _totals(rows: list[dict]) -> dict[str, float]:
    inc = sum(r["amount"] for r in rows if r["kind"] == "income" and r["operating"])
    exp = sum(r["amount"] for r in rows if r["kind"] == "expense" and r["operating"])
    return {"income": round(inc, 2), "expense": round(exp, 2), "noi": round(inc - exp, 2)}


def normalize(t12: dict, units: int | None = None) -> dict[str, Any]:
    """Map a T-12 to the house chart and reconcile. Returns the mapping, the tie-out, the
    one-time items, the run-rate view and the add-back questions — **but no adjusted NOI unless
    the tie-out passes.**

    `t12` = {lines: [{description, amount | months[12]}], totals?: {income, expense, noi}}. When
    the caller supplies source totals they are the reference the mapping must reproduce; without
    them the sum of the source lines is.
    """
    rows = map_lines(t12.get("lines") or [])
    src = t12.get("totals") or {}
    source_totals = {
        "income": round(_num(src.get("income")), 2) if src.get("income") not in (None, "") else
                  round(sum(r["amount"] for r in rows if r["kind"] == "income" and r["operating"]), 2),
        "expense": round(_num(src.get("expense")), 2) if src.get("expense") not in (None, "") else
                   round(sum(r["amount"] for r in rows if r["kind"] == "expense" and r["operating"]), 2),
    }
    source_totals["noi"] = round(source_totals["income"] - source_totals["expense"], 2) \
        if src.get("noi") in (None, "") else round(_num(src.get("noi")), 2)
    mapped_totals = _totals(rows)

    deltas = {k: round(mapped_totals[k] - source_totals[k], 2) for k in ("income", "expense", "noi")}
    reconciles = all(abs(v) <= _TOL for v in deltas.values())
    unmapped = [r for r in rows if r["category"] == "unmapped"]

    result: dict[str, Any] = {
        "line_count": len(rows), "lines": rows,
        "source_totals": source_totals, "mapped_totals": mapped_totals,
        "tie_out": {"reconciles": reconciles, "deltas": deltas, "tolerance": _TOL},
        "unmapped_count": len(unmapped),
        "unmapped": [{"description": r["description"], "amount": r["amount"]} for r in unmapped[:50]],
    }
    if not reconciles:
        result["stopped"] = True
        result["adjusted_noi"] = None
        result["reconciling_items"] = (
            [{"issue": "unmapped line", "description": r["description"], "amount": r["amount"]}
             for r in unmapped[:50]]
            or [{"issue": "totals disagree", "detail": deltas}])
        result["note"] = ("STOPPED: source and mapped totals do not reconcile, so no adjusted NOI "
                          "is published. Resolve the reconciling items and re-run — an adjusted "
                          "number on top of a lossy mapping is how a reclass disappears.")
        return result

    # --- only past the gate do we compute anything derived ---------------------------------------
    by_category: dict[str, dict[str, Any]] = {}
    for r in rows:
        b = by_category.setdefault(r["category"], {
            "category": r["category"], "label": r["category_label"], "kind": r["kind"],
            "operating": r["operating"], "amount": 0.0, "run_rate": 0.0, "line_count": 0})
        b["amount"] = round(b["amount"] + r["amount"], 2)
        b["run_rate"] = round(b["run_rate"] + (r["last_3_annualized"] or r["amount"]), 2)
        b["line_count"] += 1
    one_time = [r for r in rows if r["treatment"] == "one_time"]
    capital = [r for r in rows if r["treatment"] == "capital"]
    ot_income = sum(r["amount"] for r in one_time if r["kind"] == "income" and r["operating"])
    ot_expense = sum(r["amount"] for r in one_time if r["kind"] == "expense" and r["operating"])

    result["adjusted_noi"] = round(mapped_totals["noi"] - ot_income + ot_expense, 2)
    result["one_time_items"] = [{"description": r["description"], "amount": r["amount"],
                                 "kind": r["kind"], "category": r["category"]} for r in one_time]
    result["capital_items"] = [{"description": r["description"], "amount": r["amount"]}
                               for r in capital]
    result["by_category"] = [by_category[k] for k in sorted(by_category)]
    result["run_rate_vs_trailing"] = [
        {"category": b["category"], "label": b["label"], "trailing": b["amount"],
         "run_rate": b["run_rate"], "delta": round(b["run_rate"] - b["amount"], 2)}
        for b in result["by_category"] if b["operating"]]
    result["add_back_questions"] = add_back_questions(by_category, mapped_totals, units)
    result["note"] = ("Tie-out passed, so the derived views are safe to read. Adjusted NOI removes "
                      "one-time income and adds back one-time expense; capital is below the line. "
                      "Add-backs are surfaced as questions and never applied silently.")
    return result


def add_back_questions(by_category: dict[str, dict], totals: dict[str, float],
                       units: int | None = None) -> list[dict[str, Any]]:
    """The standard owner-operated tells. Each is a QUESTION with the number behind it — an
    owner-managed property that a third-party manager will run costs more than the T-12 shows, and
    underwriting that difference away is the classic 15–25% NOI miss."""
    q: list[dict[str, Any]] = []
    income = totals["income"] or 0.0

    def amt(cat: str) -> float:
        return (by_category.get(cat) or {}).get("amount", 0.0)

    mgmt = amt("management_fee")
    mgmt_pct = (mgmt / income * 100.0) if income else 0.0
    if income and mgmt_pct < 2.0:
        q.append({"check": "management_fee", "severity": "high",
                  "finding": (f"management fee is {mgmt_pct:.1f}% of income"
                              if mgmt else "no management fee in the statement"),
                  "question": "Is this owner-managed? Add a market management fee before pricing.",
                  "amount": round(mgmt, 2), "pct_of_income": round(mgmt_pct, 2)})
    if income and amt("payroll") <= 0:
        q.append({"check": "payroll", "severity": "high",
                  "finding": "no payroll line",
                  "question": "Who does on-site work today, and what will staffing cost you?",
                  "amount": 0.0})
    if units and units > 0:
        rm_per_unit = (amt("repairs_maintenance") + amt("turnover")) / units
        if rm_per_unit < 400:
            q.append({"check": "repairs_maintenance", "severity": "medium",
                      "finding": f"R&M + turnover is ${rm_per_unit:,.0f}/unit/yr",
                      "question": "Below-market maintenance often means deferred work — verify against the condition report.",
                      "amount": round(rm_per_unit, 2)})
    if income and amt("property_taxes") <= 0:
        q.append({"check": "property_taxes", "severity": "high", "finding": "no property-tax line",
                  "question": "Taxes reassess on sale — carry the reassessed basis, not the seller's.",
                  "amount": 0.0})
    if income and amt("insurance") <= 0:
        q.append({"check": "insurance", "severity": "medium", "finding": "no insurance line",
                  "question": "Confirm coverage is not carried at a portfolio level you won't inherit.",
                  "amount": 0.0})
    return q
