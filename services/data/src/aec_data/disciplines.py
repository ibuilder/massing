"""Canonical low-level discipline data — the shared source of truth for the discipline colour palette
and the CSI MasterFormat division master. It lives in **aec_data** (the IFC/geometry engine) on purpose:
`aec_api` can import `aec_data`, but not the other way round, so anything both packages need has to sit
here. `aec_api.classification` imports these and builds its richer API surface (regional code maps, the
NCS discipline spine, `discipline_tree()`) on top. Pure data + pure helpers; no cross-package imports.
"""
from __future__ import annotations

# CSI MasterFormat division number -> title (the 2-digit prefix of a work-result code). One canonical
# table — previously duplicated in aec_api.classification.MF_DIVISIONS and aec_data.specmanual._DIVISIONS.
MF_DIVISIONS: dict[str, str] = {
    "00": "Procurement & Contracting Requirements", "01": "General Requirements",
    "02": "Existing Conditions", "03": "Concrete", "04": "Masonry", "05": "Metals",
    "06": "Wood, Plastics & Composites", "07": "Thermal & Moisture Protection", "08": "Openings",
    "09": "Finishes", "10": "Specialties", "11": "Equipment", "12": "Furnishings",
    "13": "Special Construction", "14": "Conveying Equipment", "21": "Fire Suppression",
    "22": "Plumbing", "23": "Heating, Ventilating & Air Conditioning (HVAC)",
    "25": "Integrated Automation", "26": "Electrical", "27": "Communications",
    "28": "Electronic Safety & Security", "31": "Earthwork", "32": "Exterior Improvements",
    "33": "Utilities",
}

# One canonical display colour per NCS discipline code (hex). The viewer's color-by-discipline mode, the
# plan/PDF poché, the model browser, and any legend all colour a discipline the same way. Chosen for
# perceptual separation + common coordination conventions (fire=red, plumbing=green, mechanical=amber,
# electrical=yellow, telecom=purple, structural=blue, civil=earth).
DISCIPLINE_COLORS: dict[str, str] = {
    "G": "#8A8F98", "C": "#A9744F", "L": "#5BA150", "S": "#2E5A88", "A": "#4B5563",
    "F": "#D64545", "P": "#2FA36B", "M": "#E07B2B", "E": "#EAC43A", "T": "#7C5CBF", "Q": "#C05CA0",
}
# Distinct sheet series that warrant their own swatch (Fire Alarm reads apart from Fire Protection red).
SERIES_COLORS: dict[str, str] = {"FA": "#E8663C", "FP": "#D64545"}


def discipline_color(code: str | None) -> str:
    """Canonical hex colour for a discipline code or distinct sheet series (FA/FP). Falls back to the
    General grey so an unknown/unmapped code still renders."""
    c = (code or "").strip().upper()
    return SERIES_COLORS.get(c) or DISCIPLINE_COLORS.get(c[:1] if c else "", "#8A8F98")


def division_of(section: str) -> str | None:
    """First two digits of a MasterFormat section number/code -> division code ('03 30 00' -> '03')."""
    digits = "".join(ch for ch in str(section or "") if ch.isdigit())
    return digits[:2] if len(digits) >= 2 else None
