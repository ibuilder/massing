"""Report Center — detailed, exportable construction reports (PDF + Excel).

A small catalog of best-practice reports (executive health, cost, EVM/S-curve, operational logs,
contracts & signatures) built from the existing engines (px.py, project_budget.py, the modules
records) into a neutral structure, then rendered to PDF (reportlab) or Excel (openpyxl via exports).

This module is the thin dispatch layer: the REPORTS catalog, the key→builder registry, and build().
The ~50 per-domain builder functions live in the report_builders/ package (A2 decomposition); the
Report model + formatting live in reports_core; PDF/Excel rendering in reports_render. All three are
re-exported here so existing callers keep using `reports.Report` / `reports.build` / `reports.to_pdf`.
"""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from .models import Project

# Per-domain builders (report_builders/{finance,construction,precon,bim,operations}.py).
from .report_builders import (
    _action_tracker,
    _appraisal,
    _assumptions_register,
    _bep,
    _bim_kpi,
    _cap_table,
    _closeout,
    _co_log,
    _contractor,
    _contracts,
    _cost,
    _decision_log,
    _design_options,
    _design_standards,
    _document_control,
    _envelope,
    _esg,
    _estimate_continuity,
    _evm,
    _executive,
    _fca,
    _field_log,
    _financials,
    _lease_management,
    _listing_factsheet,
    _lod,
    _market_intelligence,
    _marketing_flyer,
    _mep,
    _naming,
    _precon_alignment,
    _productivity,
    _project_health,
    _quality,
    _rent_roll,
    _resilience,
    _resource_loading,
    _rfi_register,
    _risk,
    _safety,
    _site_feasibility,
    _spec_submittal_log,
    _stakeholder_analysis,
    _submittal_register,
    _tm_log,
    _wip,
)

# Shared "generic log table" builder — also used directly by build() for the _LOGS reports.
from .report_builders._common import _log
from .reports_core import Report
from .reports_render import to_pdf, to_sheets  # noqa: F401  (re-exported for the router)

__all__ = ["catalog", "build", "to_pdf", "to_sheets", "Report"]

# id -> (name, group)
REPORTS: dict[str, tuple[str, str]] = {
    "executive": ("Executive Summary", "Health"),
    "risk": ("Risk Digest", "Health"),
    "cost": ("Cost Report", "Cost"),
    "evm": ("Earned Value Management", "Cost"),
    "wip": ("Work-in-Progress Schedule", "Cost"),
    "contractor_financials": ("Contractor Financial Statements", "Finance"),
    "change_orders": ("Change Order Log", "Logs"),
    "rfi": ("RFI Log", "Logs"),
    "submittals": ("Submittal Log", "Logs"),
    "daily": ("Daily Report Log", "Logs"),
    "safety": ("Safety / Incident Log", "Logs"),
    "contracts": ("Contracts & Signatures", "Contracts"),
    "financials": ("Financial Statements", "Finance"),
    "appraisal": ("Valuation (Tri-Approach Appraisal)", "Finance"),
    "market_intelligence": ("Market Intelligence & Escalation", "Finance"),
    "listing_factsheet": ("Listing Fact Sheet", "Disposition"),
    "marketing_flyer": ("Marketing Flyer", "Disposition"),
    "rent_roll": ("Rent Roll", "Operations"),
    "lease_management": ("Lease Management (renewals / escalations / CAM)", "Operations"),
    "cap_table": ("Investor Cap Table", "Capital"),
    "tm_log": ("T&M / eTicket Log", "Cost"),
    "submittal_register": ("Submittal Register", "Logs"),
    "quality": ("Quality Dashboard", "Quality"),
    "rfi_register": ("RFI Register", "Logs"),
    "field_log": ("Field-Log Rollup", "Field"),
    "safety_dashboard": ("Safety Dashboard (OSHA)", "Safety"),
    "closeout": ("Closeout Dashboard", "Closeout"),
    "project_health": ("Project Health (Executive)", "Executive"),
    "co_log": ("Change-Order Log", "Cost"),
    "action_tracker": ("Meeting Action-Item Tracker", "Logs"),
    "estimate_continuity": ("Estimate Continuity (Preconstruction)", "Preconstruction"),
    "decision_log": ("Decision Log", "Preconstruction"),
    "assumptions_register": ("Assumptions & Clarifications", "Preconstruction"),
    "precon_alignment": ("Preconstruction Alignment", "Preconstruction"),
    "stakeholder_analysis": ("Stakeholder Analysis (power/interest)", "Project Controls"),
    "spec_submittal_log": ("Spec-Driven Submittal Log", "Preconstruction"),
    "site_feasibility": ("Site Feasibility / Zoning Envelope", "Preconstruction"),
    "esg": ("ESG / Sustainability Summary", "Operations"),
    "fca": ("Facility Condition Assessment (FCI)", "Operations"),
    "resilience": ("Climate & Water Resilience (flood + stormwater)", "Operations"),
    "bim_kpi": ("BIM KPI Scorecard (ISO 19650)", "Quality"),
    "bep": ("BIM Execution Plan (BEP, ISO 19650)", "Quality"),
    "lod": ("LOD Matrix & Coverage", "Quality"),
    "naming": ("Naming Convention Compliance", "Quality"),
    "document_control": ("Document Control Health", "Quality"),
    "design_options": ("Design Options Comparison", "Design"),
    "design_standards": ("Design Standards Compliance", "Design"),
    "mep": ("MEP Equipment Schedule", "Engineering"),
    "resource_loading": ("Resource-Loaded Schedule", "Schedule"),
    "envelope": ("Envelope Code Compliance (IECC)", "Engineering"),
    "productivity": ("Field Labor Productivity", "Field"),
}


def catalog() -> list[dict[str, str]]:
    return [{"id": k, "name": n, "group": g} for k, (n, g) in REPORTS.items()]


# report key → builder. Data-driven dispatch (was a ~90-line if/elif ladder): adding a report is now
# one registry line, and `catalog()`/`build()` can't drift out of sync with each other.
_BUILDERS: dict[str, Callable[[Session, str, str], Report]] = {
    "bep": _bep, "design_options": _design_options, "design_standards": _design_standards,
    "mep": _mep, "resource_loading": _resource_loading, "envelope": _envelope,
    "productivity": _productivity, "lod": _lod, "document_control": _document_control,
    "market_intelligence": _market_intelligence, "naming": _naming, "appraisal": _appraisal,
    "rent_roll": _rent_roll, "lease_management": _lease_management, "cap_table": _cap_table,
    "tm_log": _tm_log, "submittal_register": _submittal_register, "quality": _quality,
    "rfi_register": _rfi_register, "field_log": _field_log, "safety_dashboard": _safety,
    "closeout": _closeout, "project_health": _project_health, "co_log": _co_log,
    "action_tracker": _action_tracker, "estimate_continuity": _estimate_continuity,
    "decision_log": _decision_log, "assumptions_register": _assumptions_register,
    "precon_alignment": _precon_alignment, "stakeholder_analysis": _stakeholder_analysis,
    "spec_submittal_log": _spec_submittal_log,
    "site_feasibility": _site_feasibility, "esg": _esg, "fca": _fca, "resilience": _resilience,
    "bim_kpi": _bim_kpi, "listing_factsheet": _listing_factsheet, "marketing_flyer": _marketing_flyer,
    "executive": _executive, "risk": _risk, "cost": _cost, "evm": _evm, "wip": _wip,
    "contractor_financials": _contractor, "contracts": _contracts, "financials": _financials,
}

# module-record "log" reports share one builder (_log) parameterized by (module, title, columns).
_LOGS: dict[str, tuple[str, str, list[tuple[str, str]]]] = {
    "change_orders": ("cor", "Change Order Log", [("subject", "Subject"), ("amount", "Amount"), ("reason", "Reason")]),
    "rfi": ("rfi", "RFI Log", [("subject", "Subject"), ("discipline", "Discipline"), ("cost_impact", "Cost impact")]),
    "submittals": ("submittal", "Submittal Log", [("title", "Title"), ("spec_section", "Spec"), ("type", "Type")]),
    "daily": ("daily_report", "Daily Report Log", [("report_date", "Date"), ("weather", "Weather")]),
    "safety": ("incident", "Safety / Incident Log", [("subject", "Subject"), ("classification", "Class"), ("severity", "Severity")]),
}


def build(db: Session, pid: str, report: str) -> Report:
    p = db.get(Project, pid)
    name = (p.name if p else pid)
    if report in _BUILDERS:
        return _BUILDERS[report](db, pid, name)
    if report in _LOGS:
        key, title, cols = _LOGS[report]
        return _log(db, pid, name, key, title, cols)
    raise ValueError(f"unknown report {report!r}")
