"""Regional classification standards + GAEB DA XML (X83) export — OpenConstructionERP parity.

We estimate in IFC classes / US CSI divisions; international tenders want their own classification
(DIN 276 in DACH, NRM 1 in the UK, CSI MasterFormat in the US/CA) and DACH procurement runs on GAEB
DA XML. This maps an estimate's IFC-class line items to a chosen system and exports a GAEB X83
(Leistungsverzeichnis / Bill of Quantities). Compact built-in code tables — directional, editable.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from xml.sax.saxutils import escape

# ifc_class -> (code, title) per system, plus a default for anything unmapped.
CLASSIFICATIONS: dict[str, dict[str, Any]] = {
    "masterformat": {
        "name": "CSI MasterFormat (US/CA)",
        "default": ("01 00 00", "General Requirements"),
        "map": {
            "IfcWall": ("04 20 00", "Unit Masonry"),
            "IfcWallStandardCase": ("09 20 00", "Plaster & Gypsum Board"),
            "IfcColumn": ("03 30 00", "Cast-in-Place Concrete"),
            "IfcBeam": ("05 12 00", "Structural Steel Framing"),
            "IfcMember": ("05 12 00", "Structural Steel Framing"),
            "IfcPlate": ("05 12 00", "Structural Steel Framing"),
            "IfcSlab": ("03 30 00", "Cast-in-Place Concrete"),
            "IfcFooting": ("03 30 00", "Cast-in-Place Concrete"),
            "IfcStair": ("03 30 00", "Cast-in-Place Concrete"),
            "IfcRoof": ("07 50 00", "Membrane Roofing"),
            "IfcDoor": ("08 10 00", "Doors & Frames"),
            "IfcWindow": ("08 50 00", "Windows"),
            "IfcCurtainWall": ("08 44 00", "Curtain Wall Assemblies"),
            "IfcCovering": ("09 20 00", "Plaster & Gypsum Board"),
            "IfcRailing": ("05 50 00", "Metal Fabrications"),
            "IfcPipeSegment": ("22 10 00", "Plumbing Piping"),
            "IfcDuctSegment": ("23 30 00", "HVAC Air Distribution"),
            "IfcFlowTerminal": ("23 37 00", "Air Outlets & Inlets"),
        },
    },
    "din276": {
        "name": "DIN 276 (DACH)",
        "default": ("300", "Bauwerk – Baukonstruktionen"),
        "map": {
            "IfcWall": ("331", "Tragende Außenwände"),
            "IfcWallStandardCase": ("341", "Tragende Innenwände"),
            "IfcColumn": ("359", "Stützen"),
            "IfcBeam": ("352", "Decken, Balken"),
            "IfcMember": ("352", "Decken, Balken"),
            "IfcSlab": ("351", "Deckenkonstruktionen"),
            "IfcFooting": ("322", "Flachgründungen"),
            "IfcStair": ("353", "Treppen, Rampen"),
            "IfcRoof": ("361", "Dachkonstruktionen"),
            "IfcDoor": ("334", "Außentüren und -fenster"),
            "IfcWindow": ("334", "Außentüren und -fenster"),
            "IfcCurtainWall": ("337", "Elementierte Außenwände"),
            "IfcCovering": ("345", "Innenwandbekleidungen"),
            "IfcPipeSegment": ("411", "Abwasser-, Wasseranlagen"),
            "IfcDuctSegment": ("430", "Lufttechnische Anlagen"),
            "IfcFlowTerminal": ("430", "Lufttechnische Anlagen"),
        },
    },
    "nrm1": {
        "name": "RICS NRM 1 (UK)",
        "default": ("0", "Facilitating works"),
        "map": {
            "IfcColumn": ("2.1", "Frame"),
            "IfcBeam": ("2.1", "Frame"),
            "IfcMember": ("2.1", "Frame"),
            "IfcSlab": ("2.3", "Upper floors"),
            "IfcFooting": ("1.1", "Substructure"),
            "IfcRoof": ("2.4", "Roof"),
            "IfcStair": ("2.5", "Stairs & ramps"),
            "IfcWall": ("2.6", "External walls"),
            "IfcWallStandardCase": ("2.7", "Internal walls & partitions"),
            "IfcCurtainWall": ("2.6", "External walls"),
            "IfcWindow": ("2.6", "External walls"),
            "IfcDoor": ("2.8", "Internal doors"),
            "IfcCovering": ("3.1", "Wall finishes"),
            "IfcPipeSegment": ("5.4", "Water installations"),
            "IfcDuctSegment": ("5.6", "Air conditioning / ventilation"),
            "IfcFlowTerminal": ("5.6", "Air conditioning / ventilation"),
        },
    },
}


def classify(ifc_class: str, system: str) -> tuple[str, str]:
    """(code, title) for an IFC class in a classification system (default bucket if unmapped)."""
    sysdef = CLASSIFICATIONS.get(system) or CLASSIFICATIONS["masterformat"]
    return sysdef["map"].get(ifc_class, sysdef["default"])


def systems() -> list[dict[str, Any]]:
    """Catalog for the UI picker."""
    return [{"id": k, "name": v["name"]} for k, v in CLASSIFICATIONS.items()]


# --- The Discipline Spine: NCS disciplines + MasterFormat divisions + Uniformat crosswalk ----------
# Two shared vocabularies thread the whole delivery chain together — model → sheets → specs → bid
# packages → budget: the National CAD Standard **discipline designator** and the CSI **MasterFormat
# division**. `classify()` above already derives a MasterFormat section per IFC class; these tables add
# the division master, the discipline vocabulary (with each discipline's default divisions), and the
# Uniformat II ↔ MasterFormat crosswalk that migrates a concept budget into the procurement budget.

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

# NCS discipline designator -> canonical name + its default MasterFormat divisions + Uniformat groups.
# Ordered per the National CAD Standard sheet sequence (general/site/structure → arch → systems).
DISCIPLINES: list[dict[str, Any]] = [
    {"code": "G", "name": "General", "divisions": ["00", "01"], "uniformat": ["Z"]},
    {"code": "C", "name": "Civil", "divisions": ["02", "31", "32", "33"], "uniformat": ["G"]},
    {"code": "L", "name": "Landscape", "divisions": ["32"], "uniformat": ["G"]},
    {"code": "S", "name": "Structural", "divisions": ["03", "04", "05"], "uniformat": ["A", "B10"]},
    {"code": "A", "name": "Architectural", "divisions": ["06", "07", "08", "09", "10", "12"],
     "uniformat": ["B20", "B30", "C"]},
    {"code": "F", "name": "Fire Protection", "divisions": ["21"], "uniformat": ["D40"]},
    {"code": "P", "name": "Plumbing", "divisions": ["22"], "uniformat": ["D20"]},
    {"code": "M", "name": "Mechanical", "divisions": ["23", "25"], "uniformat": ["D30"]},
    {"code": "E", "name": "Electrical", "divisions": ["26", "28"], "uniformat": ["D50"]},
    {"code": "T", "name": "Telecommunications", "divisions": ["27"], "uniformat": ["D50"]},
    {"code": "Q", "name": "Equipment", "divisions": ["11", "14"], "uniformat": ["D10", "E"]},
]

# Uniformat II element -> (title, typical MasterFormat divisions) — the concept↔procurement crosswalk.
UNIFORMAT: dict[str, tuple[str, list[str]]] = {
    "A": ("Substructure", ["03", "31"]), "B10": ("Superstructure", ["03", "05"]),
    "B20": ("Exterior Enclosure", ["04", "07", "08"]), "B30": ("Roofing", ["07"]),
    "C": ("Interiors", ["06", "09", "10"]), "D10": ("Conveying", ["14"]),
    "D20": ("Plumbing", ["22"]), "D30": ("HVAC", ["23"]), "D40": ("Fire Protection", ["21"]),
    "D50": ("Electrical", ["26", "27", "28"]), "E": ("Equipment & Furnishings", ["11", "12"]),
    "G": ("Building Sitework", ["31", "32", "33"]), "Z": ("General", ["00", "01"]),
}

_CODE_TO_NAME = {d["code"]: d["name"] for d in DISCIPLINES}
_DIV_TO_DISCIPLINE = {div: d["code"] for d in DISCIPLINES for div in d["divisions"]}
_NAME_TO_DISCIPLINE = {d["name"].lower(): d for d in DISCIPLINES}
_CODE_SET = {d["code"] for d in DISCIPLINES}
# normalize the legacy free-text enums (e.g. rfi's "MEP"/"Geotechnical"/"Low Voltage") to NCS codes.
_ALIASES = {"mep": "M", "geotechnical": "C", "geotech": "C", "low voltage": "T", "lv": "T",
            "arch": "A", "struct": "S", "structure": "S", "elec": "E", "mech": "M", "plumb": "P",
            "hvac": "M", "fire": "F", "civil/site": "C", "site": "C"}


def division_of(section: str) -> str | None:
    """First two digits of a MasterFormat section number/code -> division code (e.g. '03 30 00' -> '03')."""
    digits = "".join(ch for ch in str(section or "") if ch.isdigit())
    return digits[:2] if len(digits) >= 2 else None


def discipline_of_division(div: str | None) -> str | None:
    return _DIV_TO_DISCIPLINE.get((div or "").strip().zfill(2)[:2]) if div else None


def discipline_of_ifc_class(ifc_class: str) -> str | None:
    """The NCS discipline for an IFC class, derived through its MasterFormat section."""
    code, _ = classify(ifc_class, "masterformat")
    return discipline_of_division(division_of(code))


def discipline_name(code: str | None) -> str | None:
    """The canonical discipline name for an NCS code (e.g. 'S' -> 'Structural')."""
    return _CODE_TO_NAME.get((code or "").strip().upper()) if code else None


# NCS level-2 designators that name a *distinct* sheet series with its own numbering (not just a
# refinement that folds to the level-1 discipline). Fire Alarm (FA) and Fire Protection (FP) are the
# common ones on a building set — FA is documented separately from the electrical (E) series.
SHEET_SERIES: dict[str, str] = {"FA": "Fire Alarm", "FP": "Fire Protection"}


def sheet_series(prefix: str | None) -> str | None:
    """Discipline name for a drawing-sheet designator, honouring distinct 2-letter series (FA/FP)
    before folding a longer designator to its level-1 discipline. 'FA' -> 'Fire Alarm',
    'M' -> 'Mechanical', 'AD' -> 'Architectural'."""
    p = (prefix or "").strip().upper()
    if not p:
        return None
    return SHEET_SERIES.get(p) or discipline_name(p[:1])


def discipline_code(name_or_code: str | None) -> str | None:
    """Normalize a free-text discipline name/code (incl. legacy aliases) to a canonical NCS code."""
    v = (name_or_code or "").strip()
    if not v:
        return None
    if v.upper() in _CODE_SET:
        return v.upper()
    low = v.lower()
    if low in _NAME_TO_DISCIPLINE:
        return _NAME_TO_DISCIPLINE[low]["code"]
    return _ALIASES.get(low)


def disciplines() -> list[dict[str, Any]]:
    """Catalog for the UI + module selects: code, name, divisions (with titles), uniformat groups."""
    return [{**d, "division_titles": {v: MF_DIVISIONS.get(v, v) for v in d["divisions"]}}
            for d in DISCIPLINES]


def discipline_names() -> list[str]:
    """The canonical discipline names, in NCS sheet order — the option list for module selects."""
    return [d["name"] for d in DISCIPLINES]


def masterformat_divisions() -> list[dict[str, Any]]:
    """Division master: code, title, and the discipline each division rolls up to."""
    return [{"code": k, "title": v, "discipline": _DIV_TO_DISCIPLINE.get(k)}
            for k, v in MF_DIVISIONS.items()]


def uniformat_crosswalk() -> list[dict[str, Any]]:
    """Uniformat II elements with the MasterFormat divisions they map to (concept→procurement)."""
    return [{"code": k, "title": t, "masterformat_divisions": divs} for k, (t, divs) in UNIFORMAT.items()]


# --- GAEB DA XML 3.2, category 83 (Leistungsverzeichnis / BoQ) ----------------
_GAEB_UNIT = {"m²": "m2", "m³": "m3", "m": "m", "ea": "St", "count": "St", "EA": "St"}


def _gaeb_unit(u: str) -> str:
    return _GAEB_UNIT.get(u, u or "St")


def gaeb_x83(project_name: str, lines: list[dict[str, Any]], system: str = "din276") -> str:
    """Render priced estimate lines as a GAEB DA XML 3.2 award (DP=83) Bill of Quantities.
    Each line → an <Item> with quantity, unit, classification-coded short text and unit price."""
    items: list[str] = []
    for i, ln in enumerate(lines, 1):
        code, title = classify(ln.get("ifc_class", ""), system)
        qty = float(ln.get("quantity") or ln.get("count") or 0)
        up = float(ln.get("rate") or 0)
        cls = ln.get("ifc_class", "").replace("Ifc", "")
        text = escape(f"{code} {title} — {cls}")
        items.append(
            f'        <Item RNoPart="{i*10:04d}">\n'
            f"          <Qty>{qty:.3f}</Qty>\n"
            f"          <QU>{escape(_gaeb_unit(ln.get('unit', 'St')))}</QU>\n"
            f"          <Description><CompleteText><OutlineText><OutlTxt><TextOutlTxt>"
            f"<span>{text}</span></TextOutlTxt></OutlTxt></OutlineText></CompleteText></Description>\n"
            f"          <UP>{up:.2f}</UP>\n"
            f"        </Item>"
        )
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA86/3.2">\n'
        f"  <GAEBInfo><Version>3.2</Version><VersDate>{date.today().isoformat()}</VersDate><ProgSystem>Massing</ProgSystem></GAEBInfo>\n"
        f"  <PrjInfo><NamePrj>{escape(project_name)}</NamePrj></PrjInfo>\n"
        "  <Award>\n    <DP>83</DP>\n    <BoQ>\n      <BoQInfo><Name>Estimate</Name></BoQInfo>\n      <BoQBody>\n        <Itemlist>\n"
        f"{body}\n"
        "        </Itemlist>\n      </BoQBody>\n    </BoQ>\n  </Award>\n</GAEB>\n"
    )
