"""BIM KPI scorecard — the standard 10-category information-management scorecard, rolled up from data
the platform already holds, plus a handover data-drop acceptance gate.

The industry BIM-KPI framing (a practical composite of ISO 19650 / buildingSMART QA metrics) groups
delivery quality into ten categories: Information Requirements, Model Authoring Quality, openBIM
Exchange, Coordination Control, Issue Resolution, CDE Discipline, Asset Data Readiness, Construction
Data Readiness, Handover Assurance, Digital Twin Readiness. This engine grades each from what's on
hand — the CDE (cde.py), the model quality index (openbim_quality.py, when a model is loaded), and the
issue / asset / closeout modules — so a project can see, at a glance, where its information delivery is
strong or thin. Every category degrades to 'n/a' rather than guessing when its inputs aren't present."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import cde
from . import modules as me

GRADES = ("good", "warn", "poor", "na")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def _grade(pct: float | None, good: float, warn: float) -> str:
    if pct is None:
        return "na"
    return "good" if pct >= good else ("warn" if pct >= warn else "poor")


def _age_days(created) -> int | None:
    try:
        c = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
        return max(0, (date.today() - c).days)
    except (TypeError, ValueError):
        return None


def _openbim(pid: str) -> dict | None:
    """Model quality signals when a model is indexed; None otherwise (keeps the scorecard model-optional)."""
    try:
        from .routers.properties import _INDEX, _ensure_loaded
        from . import openbim_quality, ids_authoring
        _ensure_loaded(pid)
        idx = _INDEX.get(pid)
        if not idx:
            return None
        return openbim_quality.summary(idx, ids_authoring.specs_for_use_case("handover_cobie"))
    except Exception:                              # noqa: BLE001 — model quality is optional
        return None


def _issue_stats(db, pid: str, key: str, open_states: tuple, closed_states: tuple) -> dict:
    recs = me.list_records(db, key, pid, limit=100000)
    open_n = closed_n = aged = 0
    ages = []
    for r in recs:
        st = r.get("workflow_state")
        if st in closed_states:
            closed_n += 1
        elif st in open_states:
            open_n += 1
            a = _age_days(r.get("created_at"))
            if a is not None:
                ages.append(a)
                if a > 14:
                    aged += 1
    return {"total": len(recs), "open": open_n, "closed": closed_n, "aged_gt14": aged,
            "avg_open_age_days": round(sum(ages) / len(ages), 1) if ages else None,
            "resolved_pct": _pct(closed_n, len(recs))}


def _complete_pct(recs: list[dict], fields: tuple[str, ...]) -> float | None:
    if not recs:
        return None
    ok = sum(1 for r in recs if all((_d(r).get(f) or "").strip() if isinstance(_d(r).get(f), str)
                                    else _d(r).get(f) for f in fields))
    return _pct(ok, len(recs))


def scorecard(db, pid: str) -> dict[str, Any]:
    """The 10-category BIM KPI scorecard: each category graded good/warn/poor/na with a headline
    metric and supporting numbers."""
    cats: list[dict] = []
    cde_s = cde.status(db, pid)
    reqs = cde.requirements(db, pid)
    oq = _openbim(pid)

    # 1. Information Requirements — core docs on file + IDS compliance (if a model is scored)
    ids_pct = oq["ids"]["compliance_pct"] if oq and oq.get("ids") else None
    cats.append({"key": "information_requirements", "label": "Information Requirements",
                 "grade": "good" if reqs["core_coverage"]["complete"] else ("warn" if reqs["total"] else "na"),
                 "headline": "core docs complete" if reqs["core_coverage"]["complete"]
                 else (f"missing {', '.join(reqs['core_coverage']['missing'])}" if reqs["total"] else "no requirements yet"),
                 "metrics": {"requirements": reqs["total"], "ids_compliance_pct": ids_pct}})

    # 2. Model Authoring Quality — classification + property completeness (model-dependent)
    auth_pct = oq["bsdd"]["alignment_pct"] if oq else None
    cats.append({"key": "model_authoring_quality", "label": "Model Authoring Quality",
                 "grade": _grade(auth_pct, 90, 60),
                 "headline": f"{auth_pct}% classified" if auth_pct is not None else "load a model",
                 "metrics": {"classification_pct": auth_pct,
                             "loin_avg": oq["loin"]["avg_score"] if oq else None}})

    # 3. openBIM Exchange — export health + BCF traceability
    bcf = me.list_records(db, "coordination_issue", pid, limit=100000)
    exch_grade = (oq["export_health"]["overall"] if oq else "na")
    exch_grade = {"pass": "good", "warn": "warn", "fail": "poor"}.get(exch_grade, "na")
    cats.append({"key": "openbim_exchange", "label": "openBIM Exchange",
                 "grade": exch_grade,
                 "headline": (f"export {oq['export_health']['overall']}" if oq else "load a model"),
                 "metrics": {"proxy_count": oq["export_health"]["proxy_count"] if oq else None,
                             "bcf_issues": len(bcf)}})

    # 4. Coordination Control — coordination issue closure (clash density needs a run; report issues)
    coord = _issue_stats(db, pid, "coordination_issue", ("open", "assigned"), ("closed", "resolved"))
    cats.append({"key": "coordination_control", "label": "Coordination Control",
                 "grade": _grade(coord["resolved_pct"], 80, 50) if coord["total"] else "na",
                 "headline": (f"{coord['resolved_pct']}% resolved" if coord["total"] else "no coordination issues"),
                 "metrics": {"open": coord["open"], "resolved_pct": coord["resolved_pct"]}})

    # 5. Issue Resolution — RFI aging + closure
    rfi = _issue_stats(db, pid, "rfi", ("open", "draft"), ("answered", "closed"))
    cats.append({"key": "issue_resolution", "label": "Issue Resolution",
                 "grade": ("poor" if rfi["aged_gt14"] and rfi["open"] else _grade(rfi["resolved_pct"], 70, 40)) if rfi["total"] else "na",
                 "headline": (f"{rfi['open']} open, {rfi['aged_gt14']} aged >14d" if rfi["total"] else "no RFIs"),
                 "metrics": {"open": rfi["open"], "avg_open_age_days": rfi["avg_open_age_days"],
                             "resolved_pct": rfi["resolved_pct"]}})

    # 6. CDE Discipline — from cde.py
    md = cde_s["discipline"]["metadata_completeness_pct"]
    cats.append({"key": "cde_discipline", "label": "CDE Discipline",
                 "grade": _grade(md, 80, 50) if cde_s["total"] else "na",
                 "headline": (f"{md}% metadata complete" if md is not None else "no containers"),
                 "metrics": {"containers": cde_s["total"], "revision_control_pct": cde_s["discipline"]["revision_control_pct"],
                             "metadata_completeness_pct": md}})

    # 7. Asset Data Readiness — maintainable asset tags for handover
    assets = me.list_records(db, "asset_register", pid, limit=100000)
    tag_pct = _complete_pct(assets, ("tag",))
    cats.append({"key": "asset_data_readiness", "label": "Asset Data Readiness",
                 "grade": _grade(tag_pct, 90, 50) if assets else "na",
                 "headline": (f"{tag_pct}% tagged" if tag_pct is not None else "no asset register"),
                 "metrics": {"assets": len(assets), "tagged_pct": tag_pct}})

    # 8. Construction Data Readiness — product/manufacturer data + Digital Product Passport
    prod_pct = _complete_pct(assets, ("manufacturer", "model"))
    dpp_pct = _complete_pct(assets, ("gs1_id", "epd_reference", "manufacturer_url"))
    cats.append({"key": "construction_data_readiness", "label": "Construction Data Readiness",
                 "grade": _grade(prod_pct, 80, 40) if assets else "na",
                 "headline": (f"{prod_pct}% carry product data"
                              + (f", {dpp_pct}% DPP-complete" if dpp_pct else "")
                              if prod_pct is not None else "no asset register"),
                 "metrics": {"assets": len(assets), "product_data_pct": prod_pct, "dpp_pct": dpp_pct}})

    # 9. Handover Assurance — as-builts, O&M, completion certificate present + accepted
    def _has(key: str, states: tuple) -> tuple[int, int]:
        rs = me.list_records(db, key, pid, limit=10000)
        return len(rs), sum(1 for r in rs if r.get("workflow_state") in states)
    ab_n, _ = _has("as_built", ("closed",))
    om_n, _ = _has("om_manual", ("closed",))
    cc_n, cc_acc = _has("completion_certificate", ("issued", "accepted"))
    handover_ok = ab_n > 0 and om_n > 0 and cc_acc > 0
    cats.append({"key": "handover_assurance", "label": "Handover Assurance",
                 "grade": "good" if handover_ok else ("warn" if (ab_n or om_n or cc_n) else "na"),
                 "headline": ("handover package complete" if handover_ok
                              else "assemble as-builts, O&M, completion cert"),
                 "metrics": {"as_builts": ab_n, "om_manuals": om_n, "completion_certs": cc_n}})

    # 10. Digital Twin Readiness — asset↔system linkage + sensor/telemetry mapping (twin.py)
    meters = me.list_records(db, "meter", pid, limit=10000)
    linked = sum(1 for a in assets if (_d(a).get("system") or "").strip())
    sensored = sum(1 for a in assets if (_d(a).get("sensor_id") or "").strip())
    link_pct = _pct(linked, len(assets)) if assets else None
    sensor_pct = _pct(sensored, len(assets)) if assets else None
    tw_parts = [p for p in (link_pct, sensor_pct) if p is not None]
    twin_pct = round(sum(tw_parts) / len(tw_parts), 1) if tw_parts else None
    cats.append({"key": "digital_twin_readiness", "label": "Digital Twin Readiness",
                 "grade": _grade(twin_pct, 60, 20) if (assets and (linked or sensored or meters)) else "na",
                 "headline": (f"{twin_pct}% twin-ready ({linked} system-linked, {sensored} sensor-mapped)"
                              if twin_pct is not None else "no telemetry/asset links yet"),
                 "metrics": {"meters": len(meters), "system_linked_pct": link_pct,
                             "sensor_mapped_pct": sensor_pct, "twin_readiness_pct": twin_pct}})

    scored = [c for c in cats if c["grade"] != "na"]
    good = sum(1 for c in scored if c["grade"] == "good")
    return {
        "categories": cats,
        "summary": {"scored": len(scored), "good": good,
                    "warn": sum(1 for c in scored if c["grade"] == "warn"),
                    "poor": sum(1 for c in scored if c["grade"] == "poor"),
                    "na": sum(1 for c in cats if c["grade"] == "na"),
                    "health_pct": _pct(good, len(scored))},
        "model_scored": oq is not None,
        "note": "Ten information-management KPI categories graded from CDE, model quality and the "
                "issue/asset/closeout records. Categories with no inputs show 'n/a' rather than a guess.",
    }


def handover_acceptance(db, pid: str) -> dict[str, Any]:
    """Data-drop acceptance gate: the checklist an owner runs before accepting the information model —
    requirements issued, asset tags complete, as-builts + O&M + accepted completion certificate."""
    reqs = cde.requirements(db, pid)
    assets = me.list_records(db, "asset_register", pid, limit=100000)
    tag_pct = _complete_pct(assets, ("tag",)) or 0.0
    ab = me.list_records(db, "as_built", pid, limit=10000)
    om = me.list_records(db, "om_manual", pid, limit=10000)
    cc = me.list_records(db, "completion_certificate", pid, limit=10000)
    cc_accepted = sum(1 for r in cc if r.get("workflow_state") in ("issued", "accepted"))
    checks = [
        {"key": "requirements", "label": "Information requirements issued (AIR/EIR)",
         "ok": reqs["core_coverage"]["complete"]},
        {"key": "asset_tags", "label": "Assets tagged for CMMS (≥90%)", "ok": tag_pct >= 90},
        {"key": "as_built", "label": "As-built records delivered", "ok": len(ab) > 0},
        {"key": "om_manual", "label": "O&M manuals delivered", "ok": len(om) > 0},
        {"key": "completion_cert", "label": "Completion certificate accepted", "ok": cc_accepted > 0},
    ]
    accepted = all(c["ok"] for c in checks)
    return {"accepted": accepted, "checks": checks,
            "metrics": {"asset_tag_pct": round(tag_pct, 1), "as_builts": len(ab),
                        "om_manuals": len(om), "completion_certs_accepted": cc_accepted},
            "note": "Data-drop acceptance mirrors an owner's handover checklist against the AIR: "
                    "requirements, taggable asset data, as-builts, O&M and an accepted certificate."}
