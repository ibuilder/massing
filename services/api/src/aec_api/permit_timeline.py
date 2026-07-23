"""PERMIT-TIMELINE (R17 Sprint E) — deterministic **days-to-issue analytics** over cached building-permit
records, turned into a pro-forma driver.

We already ingest permit feeds (offline-cacheable); the missing bridge is the *timeline model* between the
raw feed and the underwriting. For a jurisdiction × permit-type (× valuation band) this computes the
days-to-issue distribution (p25 / median / p75) + a seasonal issuance profile, then `estimate()` returns the
**median** (expected) and **p75** (conservative) duration to plug into the pro-forma as the entitlement /
permit carry-cost driver — broadening the cohort automatically when a specific one is too thin.

Pure aggregation over the records the caller supplies (from the permit connector's cache); no live fetch.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

_BANDS = [(0, 1e5, "<$100k"), (1e5, 1e6, "$100k–1M"), (1e6, 1e7, "$1M–10M"), (1e7, math.inf, ">$10M")]
_MIN_SAMPLE = 5     # below this, broaden the cohort for a stable estimate


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _band(valuation: float) -> str:
    for lo, hi, label in _BANDS:
        if lo <= valuation < hi:
            return label
    return "unknown"


def _pct(vals: list[float], p: float) -> float | None:
    """Linear-interpolation percentile (p in 0..100) over a sorted-in-place copy."""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return round(s[0], 1)
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return round(s[int(k)], 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def _rows(permits: list[dict]) -> list[dict]:
    """Normalize permits → [{jurisdiction, type, band, valuation, days, issued_month}] for issued permits."""
    out = []
    for p in permits or []:
        if not isinstance(p, dict):
            continue
        filed = _date(p.get("filed") or p.get("filed_date") or p.get("applied_date") or p.get("application_date"))
        issued = _date(p.get("issued") or p.get("issued_date") or p.get("issue_date"))
        if filed is None or issued is None or issued < filed:
            continue
        val = _num(p.get("valuation") or p.get("value") or p.get("job_value") or p.get("estimated_cost"))
        out.append({
            "jurisdiction": _norm(p.get("jurisdiction") or p.get("city") or p.get("ahj")) or "—",
            "type": _norm(p.get("type") or p.get("permit_type") or p.get("permittype")) or "—",
            "band": _band(val), "valuation": val,
            "days": (issued - filed).days, "issued_month": issued.month,
        })
    return out


def _summarize(days: list[float]) -> dict[str, Any]:
    return {"n": len(days), "p25": _pct(days, 25), "median": _pct(days, 50), "p75": _pct(days, 75),
            "min": round(min(days), 1) if days else None, "max": round(max(days), 1) if days else None,
            "mean": round(sum(days) / len(days), 1) if days else None}


def estimate(rows: list[dict], jurisdiction: str | None, ptype: str | None,
             valuation: float | None) -> dict[str, Any]:
    """Median (expected) + p75 (conservative) days-to-issue for a target, broadening the cohort — band →
    type → jurisdiction — until the sample is stable."""
    j, t, b = _norm(jurisdiction).lower(), _norm(ptype).lower(), _band(_num(valuation)) if valuation else None
    cohorts = [
        ("jurisdiction × type × band", lambda r: (not j or r["jurisdiction"].lower() == j)
         and (not t or r["type"].lower() == t) and (b is None or r["band"] == b)),
        ("jurisdiction × type", lambda r: (not j or r["jurisdiction"].lower() == j)
         and (not t or r["type"].lower() == t)),
        ("jurisdiction", lambda r: (not j or r["jurisdiction"].lower() == j)),
        ("all permits", lambda r: True),
    ]
    for basis, pred in cohorts:
        days = [r["days"] for r in rows if pred(r)]
        if len(days) >= _MIN_SAMPLE or basis == "all permits":
            s = _summarize(days)
            return {"expected_days": s["median"], "conservative_days": s["p75"],
                    "expected_months": round(s["median"] / 30.4, 1) if s["median"] else None,
                    "conservative_months": round(s["p75"] / 30.4, 1) if s["p75"] else None,
                    "sample_size": s["n"], "basis": basis,
                    "note": "Median = expected entitlement duration; p75 = the conservative carry the "
                            "pro-forma should underwrite. Cohort broadened until the sample was stable."}
    return {"expected_days": None, "sample_size": 0, "basis": "no data"}


def analyze(permits: list[dict], target: dict | None = None) -> dict[str, Any]:
    """Days-to-issue distribution by jurisdiction × type (+ band) + a seasonal issuance profile, and — when
    `target` is given — the pro-forma estimate for that jurisdiction/type/valuation."""
    rows = _rows(permits)
    groups: dict[tuple, list[float]] = {}
    for r in rows:
        groups.setdefault((r["jurisdiction"], r["type"], r["band"]), []).append(r["days"])
    group_rows = [{"jurisdiction": k[0], "type": k[1], "band": k[2], **_summarize(v)}
                  for k, v in groups.items()]
    group_rows.sort(key=lambda g: -g["n"])

    seasonal: dict[int, list[float]] = {}
    for r in rows:
        seasonal.setdefault(r["issued_month"], []).append(r["days"])
    season_rows = [{"month": m, "issued": len(v), "median_days": _pct(v, 50)}
                   for m, v in sorted(seasonal.items())]

    out = {
        "permit_count": len(permits or []), "measured": len(rows),
        "overall": _summarize([r["days"] for r in rows]),
        "groups": group_rows, "seasonal": season_rows,
        "note": "Days-to-issue = issued − filed, over the cached permit records (no live fetch). Grouped by "
                "jurisdiction × type × valuation band; median feeds the pro-forma as the entitlement "
                "duration, p75 as the conservative carry-cost driver.",
    }
    if target:
        out["estimate"] = estimate(rows, target.get("jurisdiction"), target.get("type"), target.get("valuation"))
    return out
