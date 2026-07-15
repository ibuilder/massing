"""Model Health — one composite scorecard over the model-quality checks that are otherwise scattered
across the Model Tools rail. It doesn't re-implement any check; it *composes* the existing engines into
a single 0–100 health score with per-lens drill-downs, so a coordinator sees at a glance where the model
stands and jumps straight to the tool that fixes it.

Lenses (each degrades to "n/a" when its inputs are missing, and n/a lenses are excluded from the mean):
  * Integrity / hygiene   — `model_qa` (duplicate GUIDs, overlaps, orphans, unenclosed, blanks, wrong-storey)
  * Information & delivery — `bim_kpi.scorecard` (the ISO 19650 10-category KPI health %)
  * Coordination          — `clash_intel.metrics` (clash-issue resolution rate)
  * Verified as-built      — `verified_progress` (verified-in-place %, and the trust gap vs claimed)
"""
from __future__ import annotations

from typing import Any

_WEIGHTS = {"hygiene": 0.25, "information": 0.25, "coordination": 0.20, "verified": 0.15, "readiness": 0.15}


def _status(score: float | None) -> str:
    if score is None:
        return "na"
    return "good" if score >= 80 else ("warn" if score >= 50 else "poor")


def _band(score: float | None) -> str:
    if score is None:
        return "no data"
    return "healthy" if score >= 80 else ("watch" if score >= 50 else "at risk")


def scorecard(db, pid: str, model=None, elements: list[dict] | None = None) -> dict[str, Any]:
    """Compose the model-quality engines into one health scorecard. `model`: an opened ifcopenshell model
    (enables the hygiene lens); `elements`: the published element index (enables the verified lens)."""
    from . import bim_kpi, clash_intel, model_qa, verified_progress

    lenses: list[dict] = []

    # 1. Integrity / hygiene — from the opened model
    hy: dict[str, Any] = {"key": "hygiene", "label": "Integrity & hygiene", "tool": "model_qa",
                          "score": None, "status": "na", "headline": "load a model to check"}
    if model is not None:
        try:
            q = model_qa.model_qa(model)
            ec = q["element_count"] or 0
            issues = q["total_issues"]
            score = 100.0 if q["clean"] else round(max(0.0, 100.0 * (1 - min(1.0, issues / max(1, ec)))), 1)
            worst = sorted(((k, v["count"]) for k, v in q["checks"].items() if v["count"]),
                          key=lambda kv: kv[1], reverse=True)
            hy.update({"score": score, "status": _status(score), "elements": ec, "issues": issues,
                       "headline": "clean — no integrity issues" if q["clean"]
                       else f"{issues} issue(s): " + ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in worst[:3]),
                       "detail": {k: v["count"] for k, v in q["checks"].items()}})
        except Exception:        # noqa: BLE001 — a malformed model shouldn't sink the whole scorecard
            hy["headline"] = "couldn't read the model"
    lenses.append(hy)

    # 2. Information & delivery — the ISO 19650 KPI health %
    inf: dict[str, Any] = {"key": "information", "label": "Information & delivery (ISO 19650)",
                           "tool": "bim_kpi", "score": None, "status": "na", "headline": "no KPI inputs"}
    try:
        sc = bim_kpi.scorecard(db, pid)
        s = sc["summary"]
        score = s.get("health_pct")
        inf.update({"score": score, "status": _status(score),
                    "headline": (f"{s['good']}/{s['scored']} KPI categories good" if s["scored"]
                                 else "no KPI inputs yet"),
                    "detail": {"good": s["good"], "warn": s["warn"], "poor": s["poor"], "na": s["na"]}})
    except Exception:            # noqa: BLE001
        pass
    lenses.append(inf)

    # 3. Coordination — clash-issue resolution
    co: dict[str, Any] = {"key": "coordination", "label": "Coordination (clash issues)",
                          "tool": "clash", "score": None, "status": "na", "headline": "no coordination issues"}
    try:
        m = clash_intel.metrics(db, pid)
        if m.get("total_issues"):
            score = m["resolution_rate"]
            co.update({"score": score, "status": _status(score),
                       "headline": f"{m['resolved']}/{m['total_issues']} resolved ({score}%)"
                                   + (f", {m['open']} open" if m.get("open") else ""),
                       "detail": {"open": m.get("open"), "resolved": m.get("resolved"),
                                  "reappeared": m.get("reappeared"), "reappearance_rate": m.get("reappearance_rate")}})
    except Exception:            # noqa: BLE001
        pass
    lenses.append(co)

    # 4. Verified as-built — verified-in-place % + the trust gap
    ve: dict[str, Any] = {"key": "verified", "label": "Verified as-built", "tool": "verified_progress",
                          "score": None, "status": "na", "headline": "no field verification yet"}
    try:
        vp = verified_progress.index(db, pid, elements or [])
        if vp.get("elements_total"):
            score = vp["verified_pct"]
            ve.update({"score": score, "status": _status(score),
                       "headline": f"{score}% verified in place vs {vp['claimed_pct']}% claimed "
                                   f"(trust gap {vp['trust_gap']})",
                       "detail": {"verified": vp["elements_verified"], "deviated": vp["elements_deviated"],
                                  "trust_gap": vp["trust_gap"], "coverage_pct": vp["coverage_pct"]}})
    except Exception:            # noqa: BLE001
        pass
    lenses.append(ve)

    # 5. Code & permit readiness — the plan-reviewer pre-flight pass rate (D8)
    rd: dict[str, Any] = {"key": "readiness", "label": "Code & permit readiness", "tool": "approvability",
                          "score": None, "status": "na", "headline": "load a model to check"}
    if model is not None:
        try:
            from . import codecheck
            ap = codecheck.approvability(model)
            sm = ap["summary"]
            if sm["gating"]:
                score = float(sm["score_pct"]) if sm["score_pct"] is not None else None
                fails = [c["check"] for c in ap["checks"] if c["status"] == "fail"]
                rd.update({"score": score, "status": _status(score),
                           "headline": ("permit-ready — all pre-flight checks pass" if sm["ready"]
                                        else f"{sm['failed']} check(s) to fix: " + ", ".join(fails[:2])),
                           "detail": {c["check"]: c["status"] for c in ap["checks"]}})
            else:
                rd["headline"] = "no gating checks apply yet (add spaces/doors/rated assemblies)"
        except Exception:        # noqa: BLE001 — a code-check failure shouldn't sink the scorecard
            rd["headline"] = "couldn't run the pre-flight"
    lenses.append(rd)

    # composite — weighted mean over the lenses that produced a score
    num = den = 0.0
    for ln in lenses:
        if ln["score"] is not None:
            w = _WEIGHTS.get(ln["key"], 0.0)
            num += ln["score"] * w
            den += w
    overall = round(num / den, 1) if den else None
    return {
        "overall_score": overall,
        "band": _band(overall),
        "lenses": lenses,
        "scored_lenses": sum(1 for ln in lenses if ln["score"] is not None),
        "model_available": model is not None,
        "note": "A composite of the model-quality checks (hygiene, ISO 19650 KPIs, clash coordination, "
                "verified-as-built, and code/permit readiness). Each lens links to the tool that acts on it; "
                "lenses with no inputs show 'n/a' and are excluded from the score rather than guessed.",
    }
