"""Report builders — operations domain (extracted from reports.py, A2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..reports_core import Report
from ..reports_core import money as _money


def _esg(db: Session, pid: str, name: str) -> Report:
    """ESG / sustainability summary: metered energy (EUI), GHG Scope 1/2, water, certifications,
    and the POE actual-vs-design comparison — the asset-level sustainability scorecard."""
    from .. import energy as energy_mod
    from .. import esg as esg_mod
    s = esg_mod.summary(db, pid, gfa_sf=energy_mod.project_gfa_sf(db, pid))
    perf = s["performance"]
    r = Report("ESG / Sustainability Summary", name)
    r.kpi("Site energy (kBtu)", f"{perf['energy']['total_kbtu']:,.0f}")
    r.kpi("EUI (kBtu/sf/yr)", perf["energy"]["eui_kbtu_sf_yr"] if perf["energy"]["eui_kbtu_sf_yr"] is not None else "—")
    r.kpi("GHG Scope 1 (tCO2e)", perf["ghg"]["scope1_tco2e"])
    r.kpi("GHG Scope 2 (tCO2e)", perf["ghg"]["scope2_tco2e"])
    r.kpi("Water (gal)", f"{perf['water']['gallons']:,.0f}")
    r.kpi("Certification points (achieved / targeted)",
          f"{s['certifications']['points_achieved']:.0f} / {s['certifications']['points_targeted']:.0f}")
    ghg_rows = [
        ["Scope 1 — on-site fuel", f"{perf['ghg']['scope1_tco2e']:,} tCO2e"],
        ["Scope 2 — purchased energy", f"{perf['ghg']['scope2_tco2e']:,} tCO2e"],
        ["Total", f"{perf['ghg']['total_tco2e']:,} tCO2e"],
        ["Intensity", f"{perf['ghg']['intensity_kgco2e_sf']} kgCO2e/sf" if perf["ghg"]["intensity_kgco2e_sf"] is not None else "— (needs GFA)"],
        ["Grid factor", f"{perf['ghg']['grid_factor_kgco2e_kwh']} kgCO2e/kWh"],
    ]
    r.table("Operational GHG emissions", ["Metric", "Value"], ghg_rows)
    poe = s["poe"]["latest"]
    if poe:
        r.table("Post-occupancy evaluation (latest)", ["Metric", "Value"], [
            ["Evaluation", f"{poe['ref']} ({poe['level'] or '-'}) — {poe['state']}"],
            ["Occupant satisfaction (1-7)", poe["satisfaction_score"] if poe["satisfaction_score"] is not None else "—"],
            ["Design EUI", poe["design_eui"] if poe["design_eui"] is not None else "—"],
            ["Actual (metered) EUI", poe["actual_eui"] if poe["actual_eui"] is not None else "—"],
            ["Gap vs design", f"{poe['eui_gap_pct']:+}%" if poe["eui_gap_pct"] is not None else "—"],
        ])
    r.table("Data coverage", ["Metric", "Value"],
            [["Meter months", s["data_coverage"]["meter_months"]],
             ["POE evaluations (reported / total)", f"{s['poe']['reported']} / {s['poe']['count']}"]])
    return r


def _fca(db: Session, pid: str, name: str) -> Report:
    """Facility Condition Assessment: the FCI + band, the deferred/renewal split, and the condition
    backlog broken out by UNIFORMAT group and by worst element."""
    from .. import energy as energy_mod
    from .. import fca as fca_mod
    s = fca_mod.index(db, pid, gfa_sf=energy_mod.project_gfa_sf(db, pid))
    r = Report("Facility Condition Assessment (FCI)", name)
    r.kpi("Facility Condition Index", f"{s['fci_pct']}% ({s['band']})")
    r.kpi("Current replacement value", _money(s["crv"]))
    r.kpi("Deferred maintenance", _money(s["deferred_maintenance"]))
    r.kpi("Capital renewal due", _money(s["capital_renewal"]))
    r.kpi("Elements assessed", s["elements"])
    r.kpi("Open deficiencies", s["open_deficiencies"])
    if s["by_uniformat"]:
        r.table("Condition by UNIFORMAT group", ["Group", "Elements", "Deferred", "Renewal", "CRV", "FCI %"],
                [[u["group"], u["count"], _money(u["deferred"]), _money(u["renewal"]), _money(u["crv"]),
                  f"{u['fci_pct']}%" if u["fci_pct"] is not None else "—"] for u in s["by_uniformat"]])
    if s["worst_elements"]:
        r.table("Worst elements (by cost)", ["Ref", "Element", "Group", "Condition", "Cost"],
                [[w["ref"], w["element"], w["uniformat"], w["condition"], _money(w["cost"])]
                 for w in s["worst_elements"]])
    if s["recommended_by_year"]:
        r.chart("bar", "Recommended spend by year", [str(x["year"]) for x in s["recommended_by_year"]],
                [{"name": "Cost", "values": [x["cost"] for x in s["recommended_by_year"]]}])
    return r


def _resilience(db: Session, pid: str, name: str) -> Report:
    """Climate & water resilience: the flood Design Flood Elevation + at-risk assets, and the
    Rational-Method stormwater peak flow + detention."""
    from .. import resilience as rz
    fl = rz.flood_assessment(db, pid)
    sw = rz.stormwater(db, pid)
    wx = rz.weather(db, pid)
    cr = rz.climate_risk(db, pid, flood=fl, storm=sw, exposure=wx)   # reuse — don't recompute the scans
    r = Report("Climate & Water Resilience", name)
    r.kpi("Physical climate-risk rating", cr["rating"])
    r.kpi("Design Flood Elevation (ft)", fl["design_flood_elevation_ft"] if fl["design_flood_elevation_ft"] is not None else "—")
    r.kpi("In special flood hazard area", "Yes" if fl["in_special_flood_hazard_area"] else "No")
    r.kpi("Assets below DFE (flood-proof)", fl["at_risk_count"])
    r.kpi("Stormwater peak runoff (cfs)", sw["peak_runoff_cfs"])
    r.kpi("Detention volume (cf)", f"{sw['detention_volume_cf']:,.0f}")
    r.kpi("Weather-sensitive activities", wx["sensitive_count"])
    r.kpi("Weather-delay days logged", wx["weather_delay_days"])
    if fl["assets_at_risk"]:
        r.table("Assets below the Design Flood Elevation", ["Ref", "Asset", "Elev (ft)", "Below DFE by (ft)"],
                [[a["ref"], a["asset"], a["elevation_ft"], a["below_dfe_by_ft"]] for a in fl["assets_at_risk"]])
    if sw["by_surface"]:
        r.table("Stormwater by surface", ["Surface", "Area (sf)", "Peak (cfs)"],
                [[s["surface"], f"{s['area_sf']:,.0f}", s["peak_cfs"]] for s in sw["by_surface"]])
    if wx["site_risks"]:
        r.table("Site weather-risk register", ["Ref", "Hazard", "Season", "Severity", "Status"],
                [[x["ref"], x["hazard_type"], x["season"], x["severity"], x["state"]] for x in wx["site_risks"]])
    r.table("Physical climate-risk factors", ["Driver"], [[f] for f in cr["factors"]])
    return r
