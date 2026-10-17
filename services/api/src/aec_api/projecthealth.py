"""Project-health executive rollup — stitches the construction analytics engines (RFI, submittals,
T&M, quality, safety, field-log, closeout) into one executive summary: per-domain status
(green / amber / red), an overall health score (0-100), open-item totals, and a ranked list of
attention items. Pure read-side composition; no writes."""
from __future__ import annotations

from typing import Any

# status -> (score contribution, sort rank) — lower rank = more urgent
_STATUS_SCORE = {"green": 100, "amber": 60, "red": 20, "na": None}


def _status(red: bool, amber: bool) -> str:
    return "red" if red else ("amber" if amber else "green")


def submittal_status(s: dict[str, Any]) -> str:
    """The Submittals tile's colour.

    SUBMITTAL-RETURNED. Two corrections, either of which could leave this tile GREEN on a project
    in trouble, and both are about a count that was never taken.

    * A submittal the A/E sent back marked *"Revise & Resubmit"* used to count as CLOSED -- the
      shipped literal held `returned`, which the workflow's own two outgoing transitions say is not
      terminal -- so it was in neither `open_count` nor `overdue_count`. Measured: one such row six
      weeks past its required-on-site date gave *"0 open, 0 overdue"* and a green tile.
    * `overdue_count` can only count a submittal carrying a required-on-site date, so a backlog
      with none recorded reports zero overdue. *A count that cannot be taken is not a count of
      zero* -- hence the undated arm, which is amber on an open register where NOTHING is
      assessable rather than on any undated row, because a partly-dated log is ordinary.

    A function rather than two expressions inline because the FIRST version of this fix was two
    inline expressions, and the mutation that reverted them stayed green: the test asserted the keys
    appeared in the file, and they still did -- the headline below reads them too. *Reading a value
    and ruling on it are two different questions, and a substring cannot tell them apart.*
    """
    nothing_assessable = s["open_count"] > 0 and s["undated_count"] == s["submittal_count"]
    red = s["overdue_count"] > 5 or s["needs_resubmittal_count"] > 5
    amber = (s["overdue_count"] > 0 or s["needs_resubmittal_count"] > 0 or nothing_assessable)
    return _status(red, amber)


def submittal_headline(s: dict[str, Any]) -> str:
    """The tile's sentence. Never a bare `N open, M overdue` -- see `submittal_status`."""
    bits = [f"{s['open_count']} open", f"{s['overdue_count']} overdue"]
    if s["needs_resubmittal_count"]:
        bits.append(f"{s['needs_resubmittal_count']} awaiting resubmittal")
    if s["undated_count"]:
        bits.append(f"{s['undated_count']} with no required-on-site date, so not assessable for "
                    "lateness")
    return ", ".join(bits)


def project_health(db, pid: str) -> dict[str, Any]:
    from . import closeout, dailylog, quality, rfi, safety, submittals, tm

    domains: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []

    def add(key, label, status, headline, open_count=0, overdue=0):
        domains.append({"key": key, "label": label, "status": status, "headline": headline,
                        "open_count": open_count, "overdue_count": overdue})
        if status in ("red", "amber"):
            attention.append({"domain": label, "status": status, "issue": headline})

    # --- RFIs ----------------------------------------------------------------
    r = rfi.rfi_register(db, pid)
    add("rfi", "RFIs", _status(r["overdue_count"] > 5, r["overdue_count"] > 0),
        f"{r['open_count']} open, {r['overdue_count']} overdue, {r['cost_impacted_count']} cost-impacting",
        r["open_count"], r["overdue_count"])

    # --- Submittals ----------------------------------------------------------
    s = submittals.submittal_register(db, pid)
    add("submittals", "Submittals", submittal_status(s), submittal_headline(s),
        s["open_count"], s["overdue_count"])

    # --- Quality (inspections + NCRs + deficiencies) -------------------------
    q = quality.quality_summary(db, pid)
    ins, ncr, df = q["inspections"], q["ncrs"], q["deficiencies"]
    q_red = (ins["pass_rate"] is not None and ins["pass_rate"] < 80) or ncr["overdue_count"] > 0
    q_amber = df["overdue_count"] > 0 or ncr["open_count"] > 0
    add("quality", "Quality", _status(q_red, q_amber),
        f"pass {ins['pass_rate'] if ins['pass_rate'] is not None else '—'}%, "
        f"{ncr['open_count']} open NCRs ({ncr['overdue_count']} overdue), {df['open_count']} open deficiencies",
        ncr["open_count"] + df["open_count"], ncr["overdue_count"] + df["overdue_count"])

    # --- Safety --------------------------------------------------------------
    sf = safety.safety_summary(db, pid)["incidents"]
    sf_red = sf["recordable_count"] > 0
    sf_amber = sf["incident_count"] > 0
    trir = sf["trir"]
    add("safety", "Safety", _status(sf_red, sf_amber),
        f"{sf['incident_count']} incidents, {sf['recordable_count']} recordable"
        + (f", TRIR {trir}" if trir is not None else ""),
        sf["open_count"], 0)

    # --- T&M cost exposure ---------------------------------------------------
    t = tm.tm_summary(db, pid)
    add("tm", "T&M exposure", _status(False, t["unbilled_total"] > 0),
        f"{t['ticket_count']} tickets, {_fmt_money(t['unbilled_total'])} unbilled of {_fmt_money(t['grand_total'])}",
        0, 0)

    # --- Field reporting coverage --------------------------------------------
    fl = dailylog.field_log_summary(db, pid)
    cov = fl["coverage_pct"]
    fl_red = cov is not None and cov < 70
    fl_amber = cov is not None and cov < 90
    add("field", "Field reporting", _status(fl_red, fl_amber) if cov is not None else "na",
        f"{fl['report_count']} daily reports, coverage {cov if cov is not None else '—'}%, "
        f"{fl['weather_lost_days']} weather lost-days", 0, 0)

    # --- Closeout / punchlist ------------------------------------------------
    co = closeout.closeout_summary(db, pid)
    pu = co["punchlist"]
    co_red = pu["overdue_count"] > 0
    co_amber = pu["open_count"] > 0 or co["warranties"]["expiring_soon"] > 0
    add("closeout", "Closeout", _status(co_red, co_amber) if pu["punch_count"] or co["warranties"]["warranty_count"] else "na",
        f"punch {pu['complete_pct'] if pu['complete_pct'] is not None else '—'}% complete "
        f"({pu['open_count']} open, {pu['overdue_count']} overdue), "
        f"{co['warranties']['expiring_soon']} warranties expiring",
        pu["open_count"], pu["overdue_count"])

    # --- Score ---------------------------------------------------------------
    # R26-ONE-HEALTH. These are two DIFFERENT aggregations of the same domains, and showing them side
    # by side without saying so is what makes the app look like it disagrees with itself: the score is
    # a MEAN ("most things are fine") while the band is WORST-OF ("one thing is blocking"). Six green
    # domains and one red reads as "88/100 · RED", which is correct twice over and confusing once.
    # Both are worth keeping — a PM needs the average and the blocker — so the fix is to name the
    # domain that governs the band, turning an apparent contradiction into an explanation.
    scored = [_STATUS_SCORE[d["status"]] for d in domains if _STATUS_SCORE[d["status"]] is not None]
    health_score = round(sum(scored) / len(scored)) if scored else None
    overall = "green"
    if any(d["status"] == "red" for d in domains):
        overall = "red"
    elif any(d["status"] == "amber" for d in domains):
        overall = "amber"
    governing = next((d for d in domains if d["status"] == overall), None) if overall != "green" else None
    rank = {"red": 0, "amber": 1}
    attention.sort(key=lambda a: rank.get(a["status"], 2))
    return {
        "health_score": health_score,
        "overall_status": overall,
        # what each number MEANS, so a caller never has to guess why 88/100 can read RED
        "score_basis": "mean of scored domains",
        "status_basis": "worst domain governs",
        "governing_domain": governing["label"] if governing else None,
        "governing_detail": governing["headline"] if governing else None,
        "open_items_total": sum(d["open_count"] for d in domains),
        "overdue_items_total": sum(d["overdue_count"] for d in domains),
        "domains": domains,
        "attention_items": attention,
    }


def _fmt_money(v: Any) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)
