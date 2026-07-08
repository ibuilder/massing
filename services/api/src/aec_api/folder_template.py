"""Standard project folder taxonomy (F1) — the role-based document-control tree.

A construction/AEC project runs on a consistent, standard folder structure: every job, every office, the
same tree, so anyone can find anything and required documents are never missing. This encodes that
standard (the widely-used QS/engineer "01_Contract Documents … 11_Final Account" structure) as data:
each folder node carries an **owner role** (who is accountable — PM owns the *business* of the project,
the Superintendent owns *execution*, the Architect/Engineer own *design*), an optional **discipline**
(NCS), a default **CDE state** (ISO 19650 WIP/Shared/Published), and a **required** flag used to score
document-control completeness. The document manager (`docmanager.py`) provisions this tree per project,
files uploads into it, and flags gaps.

Owner-role rationale (PM vs Superintendent split): the business of the project — contracts, payments,
variations, procurement, correspondence — is the PM's; field execution — site instructions, inspections,
NCRs, daily reports, progress photos — is the Superintendent's; the drawing set is the design team's.
"""
from __future__ import annotations

from typing import Any

# Owner roles used across the tree. These map loosely onto the app's personas
# (architect/engineer -> Design; PM/Superintendent/QS -> Construction).
PM = "PM"                 # owns the business of the project
SUPER = "Superintendent"  # owns field execution
ARCH = "Architect"
ENGR = "Engineer"
QS = "QS"                 # quantity surveyor / cost

# CDE states (ISO 19650) reused as the default suitability of a folder's contents.
WIP, SHARED, PUBLISHED = "wip", "shared", "published"


def _n(path: str, owner: str, *, discipline: str | None = None, cde: str = SHARED,
       required: bool = False) -> dict[str, Any]:
    label = path.split("/")[-1]
    return {"path": path, "label": label, "depth": path.count("/"), "owner_role": owner,
            "discipline": discipline, "cde_default": cde, "required": required}


# The standard tree, in display order (numeric prefixes keep folders ordered on any filesystem).
STANDARD_TREE: list[dict[str, Any]] = [
    _n("01_Contract Documents", PM, cde=PUBLISHED, required=True),
    _n("01_Contract Documents/Contract Agreement", PM, cde=PUBLISHED, required=True),
    _n("01_Contract Documents/BOQ", QS, cde=PUBLISHED),
    _n("01_Contract Documents/Tender Documents", PM),
    _n("01_Contract Documents/Specifications", ARCH, cde=PUBLISHED, required=True),
    _n("01_Contract Documents/Conditions of Contract", PM, cde=PUBLISHED),

    _n("02_Drawings", ARCH, cde=PUBLISHED, required=True),
    _n("02_Drawings/Architectural", ARCH, discipline="Architectural", cde=PUBLISHED, required=True),
    _n("02_Drawings/Structural", ENGR, discipline="Structural", cde=PUBLISHED),
    _n("02_Drawings/MEP", ENGR, discipline="MEP", cde=PUBLISHED),
    _n("02_Drawings/Fit-Out", ARCH, discipline="Architectural"),
    _n("02_Drawings/As-Built Drawings", SUPER, cde=PUBLISHED),

    _n("03_Correspondence", PM),
    _n("03_Correspondence/Client", PM),
    _n("03_Correspondence/Consultant", PM),
    _n("03_Correspondence/Main Contractor", PM),
    _n("03_Correspondence/Supplier", PM),
    _n("03_Correspondence/Internal", PM),

    _n("04_Payment Applications", PM, required=True),
    _n("04_Payment Applications/Applications", QS, required=True),
    _n("04_Payment Applications/Payment Certificates", PM, cde=PUBLISHED),

    _n("05_Variations", PM),
    _n("05_Variations/Submitted", QS),
    _n("05_Variations/Approved", PM, cde=PUBLISHED),
    _n("05_Variations/Rejected", PM),

    _n("06_Quantity Take-Off", QS, cde=WIP),
    _n("06_Quantity Take-Off/Excel", QS, cde=WIP),
    _n("06_Quantity Take-Off/Marked Drawings", QS, cde=WIP),
    _n("06_Quantity Take-Off/Measurements", QS, cde=WIP),

    _n("07_Procurement", PM),
    _n("07_Procurement/RFQs", PM),
    _n("07_Procurement/Quotations", PM),
    _n("07_Procurement/Purchase Orders", PM, cde=PUBLISHED),
    _n("07_Procurement/Material Approval", ENGR),

    _n("08_Site Documents", SUPER),
    _n("08_Site Documents/Site Instructions", SUPER),
    _n("08_Site Documents/Inspection Requests", SUPER),
    _n("08_Site Documents/NCR", SUPER),
    _n("08_Site Documents/RFI", SUPER),
    _n("08_Site Documents/Daily Reports", SUPER, required=True),

    _n("09_Meetings", PM),
    _n("09_Meetings/MOM", PM),
    _n("09_Meetings/Progress Meetings", PM),

    _n("10_Photos", SUPER),
    _n("10_Photos/Before", SUPER),
    _n("10_Photos/During", SUPER),
    _n("10_Photos/Completion", SUPER),

    _n("11_Final Account", PM, cde=PUBLISHED),
    _n("11_Final Account/Final BOQ", QS, cde=PUBLISHED),
    _n("11_Final Account/Final Variations", QS, cde=PUBLISHED),
    _n("11_Final Account/Close-Out", PM, cde=PUBLISHED, required=True),
]

_BY_PATH = {n["path"]: n for n in STANDARD_TREE}
_VALID_PATHS = set(_BY_PATH)


def tree() -> list[dict[str, Any]]:
    """The full standard taxonomy (flat, ordered; each node has depth for indenting)."""
    return [dict(n) for n in STANDARD_TREE]


def node(path: str) -> dict[str, Any] | None:
    n = _BY_PATH.get(path)
    return dict(n) if n else None


def is_valid(path: str) -> bool:
    return path in _VALID_PATHS


def owner_of(path: str) -> str | None:
    n = _BY_PATH.get(path)
    return n["owner_role"] if n else None


def required_paths() -> list[str]:
    return [n["path"] for n in STANDARD_TREE if n["required"]]


def roots() -> list[dict[str, Any]]:
    return [dict(n) for n in STANDARD_TREE if n["depth"] == 0]


# --- F6: required-document checklists by design phase (AIA) ---------------------------------------
# What each phase should have on file, expressed as (folder, description). Powers the "gaps" view so an
# architect/PM sees, e.g., that the CD milestone is missing structural drawings.
REQUIRED_BY_PHASE: dict[str, list[tuple[str, str]]] = {
    "SD": [
        ("02_Drawings/Architectural", "Schematic architectural drawings"),
        ("01_Contract Documents/Specifications", "Outline specifications"),
    ],
    "DD": [
        ("02_Drawings/Architectural", "Design-development architectural set"),
        ("02_Drawings/Structural", "Structural design drawings"),
        ("02_Drawings/MEP", "MEP design drawings"),
    ],
    "CD": [
        ("02_Drawings/Architectural", "Construction-document architectural set"),
        ("02_Drawings/Structural", "Structural construction documents"),
        ("02_Drawings/MEP", "MEP construction documents"),
        ("01_Contract Documents/Specifications", "Project manual / specifications"),
        ("01_Contract Documents/BOQ", "Bill of quantities"),
    ],
    "CA": [
        ("08_Site Documents/RFI", "RFI log"),
        ("08_Site Documents/Inspection Requests", "Inspection records"),
        ("05_Variations/Approved", "Approved change orders"),
        ("04_Payment Applications/Applications", "Payment applications"),
    ],
    "CLOSEOUT": [
        ("02_Drawings/As-Built Drawings", "As-built record drawings"),
        ("11_Final Account/Close-Out", "Close-out documentation"),
        ("11_Final Account/Final BOQ", "Final account"),
    ],
}


def phase_checklist(phase: str) -> list[dict[str, str]]:
    """The required-document checklist for a design phase (AIA SD/DD/CD/CA/CLOSEOUT)."""
    return [{"folder": f, "description": d} for f, d in REQUIRED_BY_PHASE.get(phase.upper(), [])]


def phases() -> list[str]:
    return list(REQUIRED_BY_PHASE)
