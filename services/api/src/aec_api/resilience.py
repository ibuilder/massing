"""Climate & water resilience — treat rainfall and flooding as quantifiable design parameters.

Two deterministic engines for the design phase:

- **Flood risk** (ASCE 24 / FEMA): from the FEMA flood zone, Base Flood Elevation (BFE) and Flood
  Design Class, derive the **Design Flood Elevation** (DFE = BFE + freeboard) and flag any building
  asset installed below it — the flood-proof-MEP check (elevate equipment above the flood plane).
- **Stormwater** (Rational Method): peak runoff **Q = C·i·A** per catchment (runoff coefficient ×
  rainfall intensity × area) plus a first-order detention volume, so drainage is sized against a real
  design storm rather than guessed.

No external calls, no AI — the inputs (zone, BFE, rainfall intensity from an IDF curve) are entered or
imported; the maths are standard. References: ASCE 24-24 (flood-resistant design, 2024 IBC), the
Rational Method (Q=CiA)."""
from __future__ import annotations

from typing import Any

from . import modules as me

# FEMA Special Flood Hazard Areas (the 1%-annual-chance floodplain) — a zone code starting with A or V.
_SFHA_PREFIXES = ("A", "V")
# ASCE 24 minimum freeboard above the BFE by Flood Design Class when none is entered (ft).
_DEFAULT_FREEBOARD = {"1": 1.0, "2": 1.0, "3": 2.0, "4": 2.0}
# Typical Rational-Method runoff coefficients by surface when none is entered.
_C_BY_SURFACE = {
    "Roof": 0.90, "Pavement - asphalt / concrete": 0.90, "Gravel / compacted": 0.55,
    "Lawn / landscaped": 0.25, "Undeveloped / meadow": 0.20,
}
_ACRE_SF = 43560.0

# daily_report weather_impact codes that cost schedule time, and the fraction of a day each burns.
_DELAY_DAYS = {"Minor Delay": 0.25, "Half-Day Lost": 0.5, "Full-Day Lost": 1.0, "Stoppage": 1.0}
# how each site-weather-risk severity scores toward the physical-risk rollup.
_SEVERITY_SCORE = {"Low": 1, "Moderate": 2, "High": 3}


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _num(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _fdc(v) -> str:
    return (str(v).strip()[:1] or "2") if v else "2"     # Flood Design Class digit, default 2


def flood_assessment(db, pid: str) -> dict[str, Any]:
    """Design Flood Elevation + the flood-proof-MEP check over the `flood_risk` assessment and the
    asset register's installed elevations."""
    rows = me.list_records(db, "flood_risk", pid, limit=10000)
    assessments = []
    dfe_max = None
    in_sfha = False
    for r in rows:
        d = _d(r)
        zone = d.get("flood_zone") or ""
        bfe = _num(d.get("bfe_ft"))
        fdc = _fdc(d.get("flood_design_class"))
        freeboard = _num(d.get("freeboard_ft"))
        if freeboard is None:
            freeboard = _DEFAULT_FREEBOARD.get(fdc, 1.0)
        dfe = (bfe + freeboard) if bfe is not None else None
        zone_in_sfha = zone[:1] in _SFHA_PREFIXES
        in_sfha = in_sfha or zone_in_sfha
        if dfe is not None and (dfe_max is None or dfe > dfe_max):
            dfe_max = dfe
        assessments.append({"ref": r.get("ref"), "name": d.get("name") or r.get("ref"),
                            "flood_zone": zone, "in_sfha": zone_in_sfha, "bfe_ft": bfe,
                            "flood_design_class": fdc, "freeboard_ft": freeboard,
                            "dfe_ft": round(dfe, 2) if dfe is not None else None,
                            "state": r.get("workflow_state")})

    # flood-proof MEP: any asset with an installed elevation below the (max) DFE is at risk
    at_risk = []
    checked = 0
    if dfe_max is not None:
        for a in me.list_records(db, "asset_register", pid, limit=100000):
            elev = _num(_d(a).get("elevation_ft"))
            if elev is None:
                continue
            checked += 1
            if elev < dfe_max:
                at_risk.append({"ref": a.get("ref"), "asset": _d(a).get("name") or a.get("ref"),
                                "elevation_ft": elev, "below_dfe_by_ft": round(dfe_max - elev, 2)})
    at_risk.sort(key=lambda x: -x["below_dfe_by_ft"])
    return {
        "assessments": assessments, "count": len(assessments),
        "in_special_flood_hazard_area": in_sfha,
        "design_flood_elevation_ft": round(dfe_max, 2) if dfe_max is not None else None,
        "assets_checked": checked, "assets_at_risk": at_risk, "at_risk_count": len(at_risk),
        "compliant": (checked > 0 and not at_risk) or (dfe_max is not None and checked == 0 and not in_sfha),
        "note": "Design Flood Elevation = Base Flood Elevation + freeboard (ASCE 24 minimum by Flood "
                "Design Class when not entered). Assets installed below the DFE are flagged to be "
                "elevated or flood-proofed. Enter installed elevations on Asset Register items.",
    }


def stormwater(db, pid: str) -> dict[str, Any]:
    """Rational-Method peak runoff (Q = C·i·A) and a first-order detention volume over the catchment
    (`drainage_area`) records."""
    rows = me.list_records(db, "drainage_area", pid, limit=10000)
    total_area_sf = total_ca = peak_q = detention_cf = 0.0
    by_surface: dict[str, dict] = {}
    catchments = []
    for r in rows:
        d = _d(r)
        area_sf = _num(d.get("area_sf")) or 0.0
        if area_sf <= 0:
            continue
        surface = d.get("surface_type") or "(unspecified)"
        c = _num(d.get("runoff_coefficient"))
        if c is None:
            c = _C_BY_SURFACE.get(surface, 0.5)
        i = _num(d.get("rainfall_intensity_in_hr")) or 0.0
        depth = _num(d.get("rainfall_depth_in")) or 0.0
        area_ac = area_sf / _ACRE_SF
        q = c * i * area_ac                               # Q (cfs) = C · i(in/hr) · A(acres)
        vol = c * (depth / 12.0) * area_sf                # detention volume (cf) ≈ C · depth · area
        total_area_sf += area_sf
        total_ca += c * area_ac
        peak_q += q
        detention_cf += vol
        s = by_surface.setdefault(surface, {"surface": surface, "area_sf": 0.0, "peak_cfs": 0.0})
        s["area_sf"] += area_sf
        s["peak_cfs"] += q
        catchments.append({"ref": r.get("ref"), "name": d.get("name") or r.get("ref"), "surface": surface,
                           "area_sf": round(area_sf), "c": round(c, 2), "i_in_hr": i,
                           "return_period_years": d.get("return_period_years"), "peak_cfs": round(q, 2)})
    total_area_ac = total_area_sf / _ACRE_SF
    for s in by_surface.values():
        s["area_sf"] = round(s["area_sf"])
        s["peak_cfs"] = round(s["peak_cfs"], 2)
    return {
        "catchments": sorted(catchments, key=lambda x: -x["peak_cfs"]), "count": len(catchments),
        "total_area_acres": round(total_area_ac, 3),
        "composite_runoff_coefficient": round(total_ca / total_area_ac, 2) if total_area_ac > 0 else None,
        "peak_runoff_cfs": round(peak_q, 2),
        "detention_volume_cf": round(detention_cf, 0),
        "detention_volume_gal": round(detention_cf * 7.48052, 0),
        "by_surface": sorted(by_surface.values(), key=lambda x: -x["peak_cfs"]),
        "note": "Rational Method: Q = C·i·A (runoff coefficient × rainfall intensity in/hr × area in "
                "acres). Detention volume ≈ C × storm depth × area. Enter rainfall intensity/depth from "
                "the local IDF curve for the chosen return period.",
    }


def weather(db, pid: str) -> dict[str, Any]:
    """Weather-sequenced construction: which schedule activities are weather-sensitive, the standing
    site-weather-risk register, and the weather-delay days already logged in daily reports — so the
    plan can sequence exposed work out of the wet/freeze season and controls are tracked."""
    # weather-sensitive schedule activities
    sensitive = []
    by_sensitivity: dict[str, int] = {}
    for r in me.list_records(db, "schedule_activity", pid, limit=100000):
        d = _d(r)
        s = (d.get("weather_sensitivity") or "").strip()
        if not s or s == "None":
            continue
        by_sensitivity[s] = by_sensitivity.get(s, 0) + 1
        sensitive.append({"ref": r.get("ref"), "name": d.get("name") or r.get("ref"),
                          "trade": d.get("trade"), "sensitivity": s,
                          "start": d.get("start"), "finish": d.get("finish"),
                          "percent": _num(d.get("percent")) or 0})

    # standing site-weather-risk register
    site_risks = []
    by_season: dict[str, int] = {}
    by_hazard: dict[str, int] = {}
    high_open = 0
    risk_score = 0
    for r in me.list_records(db, "climate_site_risk", pid, limit=100000):
        d = _d(r)
        state = r.get("workflow_state")
        sev = d.get("severity") or "Moderate"
        season = d.get("season") or "(unspecified)"
        hazard = d.get("hazard_type") or "(unspecified)"
        by_season[season] = by_season.get(season, 0) + 1
        by_hazard[hazard] = by_hazard.get(hazard, 0) + 1
        open_ = state != "closed"
        if open_:
            risk_score += _SEVERITY_SCORE.get(sev, 2)
            if sev == "High":
                high_open += 1
        site_risks.append({"ref": r.get("ref"), "name": d.get("name") or r.get("ref"),
                           "hazard_type": hazard, "season": season, "severity": sev,
                           "location": d.get("location"), "activity_ref": d.get("activity_ref"),
                           "open": open_, "state": state})
    site_risks.sort(key=lambda x: (-_SEVERITY_SCORE.get(x["severity"], 0), not x["open"]))

    # weather-delay days already logged in daily reports
    delay_days = 0.0
    delay_reports = []
    for r in me.list_records(db, "daily_report", pid, limit=100000):
        d = _d(r)
        impact = d.get("weather_impact")
        frac = _DELAY_DAYS.get(impact)
        if not frac:
            continue
        delay_days += frac
        delay_reports.append({"ref": r.get("ref"), "date": d.get("report_date"),
                              "weather": d.get("weather"), "impact": impact, "days": frac})
    delay_reports.sort(key=lambda x: (x.get("date") or ""), reverse=True)

    return {
        "weather_sensitive_activities": sensitive, "sensitive_count": len(sensitive),
        "by_sensitivity": by_sensitivity,
        "site_risks": site_risks, "site_risk_count": len(site_risks),
        "open_risk_count": sum(1 for x in site_risks if x["open"]), "high_severity_open": high_open,
        "by_season": by_season, "by_hazard": by_hazard, "risk_score": risk_score,
        "weather_delay_days": round(delay_days, 2), "delay_report_count": len(delay_reports),
        "delay_reports": delay_reports[:50],
        "note": "Flag weather-sensitive activities so exposed work is sequenced out of the wet/freeze "
                "season; log site-weather hazards with controls; weather-delay days roll up from the "
                "daily reports' weather-impact field.",
    }


def _rating(score: int) -> str:
    return "Severe" if score >= 6 else "High" if score >= 4 else "Moderate" if score >= 2 else "Low"


def climate_risk(db, pid: str) -> dict[str, Any]:
    """Physical climate-risk rollup for ESG — folds flood exposure, stormwater load, the site-weather
    register and logged weather delays into a single scored rating with the driving factors."""
    flood = flood_assessment(db, pid)
    storm = stormwater(db, pid)
    wx = weather(db, pid)

    factors = []
    score = 0
    if flood.get("in_special_flood_hazard_area"):
        score += 2
        factors.append("Site in a FEMA Special Flood Hazard Area (1%-annual-chance floodplain).")
    if flood.get("at_risk_count"):
        score += 2
        factors.append(f"{flood['at_risk_count']} asset(s) installed below the Design Flood Elevation.")
    if wx.get("high_severity_open"):
        score += 2
        factors.append(f"{wx['high_severity_open']} high-severity site-weather hazard(s) open.")
    elif wx.get("open_risk_count"):
        score += 1
        factors.append(f"{wx['open_risk_count']} open site-weather hazard(s).")
    if (wx.get("weather_delay_days") or 0) >= 5:
        score += 1
        factors.append(f"{wx['weather_delay_days']} weather-delay day(s) logged to date.")
    if not factors:
        factors.append("No flood-plain exposure, at-risk assets or open weather hazards recorded.")

    return {
        "rating": _rating(score), "score": score,
        "in_special_flood_hazard_area": flood.get("in_special_flood_hazard_area"),
        "design_flood_elevation_ft": flood.get("design_flood_elevation_ft"),
        "assets_at_risk": flood.get("at_risk_count"),
        "peak_runoff_cfs": storm.get("peak_runoff_cfs"),
        "open_site_risks": wx.get("open_risk_count"), "high_severity_open": wx.get("high_severity_open"),
        "weather_delay_days": wx.get("weather_delay_days"),
        "factors": factors,
        "note": "Physical climate-risk rating rolls up flood-plain exposure, at-risk assets, open "
                "site-weather hazards and logged weather-delay days. Feeds the ESG summary.",
    }
