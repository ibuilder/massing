"""Subcontractor prequalification scoring + insurance (COI) expiry tracking.

A single sub default costs a GC 1.5-3x the subcontract value, so GCs increasingly score and monitor
their trade partners (Procore Prequal, Autodesk TradeTapp, COMPASS). This computes a deterministic,
transparent Q-score (0-100) from the fields the `prequalification` module already captures — safety
(EMR), financial capacity (revenue / bonding), experience, rating, and currency — and a COI-expiry
feed from the `coi` module so lapsed insurance is caught before it's a problem. No AI, no external
data — explainable by design (every point is traceable to a factor), which is what a risk decision needs."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from . import modules as me


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


# Factor weights (sum 100). Transparent + tunable; each returns (points, note).
def _emr_score(emr: float | None) -> tuple[float, str]:
    """Experience Modification Rate — workers-comp safety proxy. 1.0 = industry average; lower is safer."""
    if emr is None:
        return 15.0, "EMR not provided (half credit)"          # unknown -> partial, flagged
    if emr <= 0.8:
        return 30.0, f"EMR {emr:.2f} — excellent safety"
    if emr <= 1.0:
        return 24.0, f"EMR {emr:.2f} — at/below average"
    if emr <= 1.2:
        return 14.0, f"EMR {emr:.2f} — above average (watch)"
    return 4.0, f"EMR {emr:.2f} — high (safety risk)"


def _financial_score(revenue: float | None, bonding: float | None, project_size: float | None) -> tuple[float, str]:
    """Financial capacity: bondable + revenue large enough that this project isn't an outsized share."""
    pts, notes = 0.0, []
    if bonding and bonding > 0:
        pts += 12.0
        notes.append(f"bondable to ${bonding:,.0f}")
        if project_size and bonding < project_size:
            pts -= 4.0
            notes.append("bonding below project size")
    else:
        notes.append("no bonding capacity given")
    if revenue and project_size:
        share = project_size / revenue if revenue else 9
        if share <= 0.15:
            pts += 13.0; notes.append("project ≤15% of revenue")
        elif share <= 0.35:
            pts += 8.0; notes.append("project 15-35% of revenue")
        else:
            pts += 2.0; notes.append("project >35% of revenue (concentration risk)")
    elif revenue:
        pts += 8.0; notes.append(f"revenue ${revenue:,.0f}")
    return min(pts, 25.0), "; ".join(notes) or "no financials"


def _experience_score(refs, largest: float | None, project_size: float | None) -> tuple[float, str]:
    n_refs = len(refs) if isinstance(refs, list) else (1 if refs else 0)
    pts = min(n_refs, 3) * 3.0                                  # up to 9 for references
    note = f"{n_refs} reference(s)"
    if largest and project_size:
        if largest >= project_size:
            pts += 11.0; note += "; has built work of this size"
        elif largest >= project_size * 0.5:
            pts += 6.0; note += "; largest ~half this size"
        else:
            pts += 2.0; note += "; largest well below this size"
    elif largest:
        pts += 6.0; note += f"; largest ${largest:,.0f}"
    return min(pts, 20.0), note


def _rating_score(rating) -> tuple[float, str]:
    """An explicit reviewer rating if present (A/B/C/D or 1-5 or 0-100)."""
    if rating in (None, ""):
        return 7.0, "no explicit rating"
    r = str(rating).strip().upper()
    letter = {"A": 15.0, "B": 11.0, "C": 6.0, "D": 2.0}
    if r in letter:
        return letter[r], f"rating {r}"
    n = _num(rating)
    if n is None:
        return 7.0, f"rating {rating}"
    scaled = n / 5 * 15 if n <= 5 else n / 100 * 15
    return max(0.0, min(15.0, scaled)), f"rating {rating}"


def score_record(rec: dict, project_size: float | None = None, today: date | None = None) -> dict:
    """Compute a 0-100 Q-score + risk band + factor breakdown + flags for one prequalification record."""
    today = today or datetime.now(timezone.utc).date()
    d = rec.get("data", rec)
    emr_p, emr_n = _emr_score(_num(d.get("emr")))
    fin_p, fin_n = _financial_score(_num(d.get("annual_revenue")), _num(d.get("bonding_capacity")), project_size)
    exp_p, exp_n = _experience_score(d.get("references"), _num(d.get("largest_project")), project_size)
    rat_p, rat_n = _rating_score(d.get("rating"))
    expires = _to_date(d.get("expires"))
    cur_p, cur_n = (10.0, "prequal current") if not expires or expires >= today else (0.0, "prequal EXPIRED")

    score = round(emr_p + fin_p + exp_p + rat_p + cur_p, 1)
    band = "low" if score >= 75 else "medium" if score >= 50 else "high"
    flags = []
    if _num(d.get("emr")) and _num(d.get("emr")) > 1.0:
        flags.append("EMR above 1.0")
    if not _num(d.get("bonding_capacity")):
        flags.append("no bonding capacity")
    if expires and expires < today:
        flags.append("prequalification expired")
    if d.get("status") and str(d.get("status")).lower() == "rejected":
        flags.append("marked rejected")
    return {
        "company": d.get("company"), "trade": d.get("trade"), "ref": rec.get("ref"),
        "score": score, "risk_band": band,
        "factors": [{"factor": "Safety (EMR)", "points": emr_p, "of": 30, "note": emr_n},
                    {"factor": "Financial", "points": round(fin_p, 1), "of": 25, "note": fin_n},
                    {"factor": "Experience", "points": round(exp_p, 1), "of": 20, "note": exp_n},
                    {"factor": "Rating", "points": rat_p, "of": 15, "note": rat_n},
                    {"factor": "Currency", "points": cur_p, "of": 10, "note": cur_n}],
        "flags": flags}


def score_project(db: Session, project_id: str, project_size: float | None = None) -> dict:
    """Score every prequalification record in a project, worst risk first."""
    recs = me.list_records(db, "prequalification", project_id, limit=100_000) if "prequalification" in me.TABLES else []
    scored = [score_record(r, project_size) for r in recs]
    scored.sort(key=lambda s: s["score"])
    return {"subs": scored, "count": len(scored),
            "high_risk": sum(1 for s in scored if s["risk_band"] == "high")}


def coi_expiry(db: Session, project_id: str, soon_days: int = 30) -> dict:
    """Certificates of insurance that are expired or expiring within `soon_days` — plus prequals lapsing."""
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    horizon = today + timedelta(days=soon_days)
    expired, expiring = [], []
    for r in (me.list_records(db, "coi", project_id, limit=100_000) if "coi" in me.TABLES else []):
        d = r.get("data", {})
        exp = _to_date(d.get("expires"))
        if not exp:
            continue
        row = {"vendor": d.get("vendor"), "coverage_type": d.get("coverage_type"),
               "carrier": d.get("carrier"), "expires": exp.isoformat(), "ref": r.get("ref"),
               "days": (exp - today).days}
        if exp < today:
            expired.append(row)
        elif exp <= horizon:
            expiring.append(row)
    expired.sort(key=lambda x: x["expires"])
    expiring.sort(key=lambda x: x["expires"])
    return {"expired": expired, "expiring_soon": expiring, "soon_days": soon_days,
            "expired_count": len(expired), "expiring_count": len(expiring)}
