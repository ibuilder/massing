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
            "IfcFurniture": ("12 50 00", "Furniture (FF&E)"),
            "IfcFurnishingElement": ("12 00 00", "Furnishings (FF&E)"),
            "IfcSystemFurnitureElement": ("12 50 00", "Furniture (FF&E)"),
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

# The MasterFormat division master + the discipline colour palette are the shared low-level data — they
# live in aec_data.disciplines (reachable by both the geometry engine and this API layer) and are imported
# here so there is exactly one source. This module builds the richer discipline spine on top.
from aec_data.disciplines import (  # noqa: E402
    MF_DIVISIONS,
    discipline_color,
    division_of,
)

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

# DISCIPLINE_COLORS / SERIES_COLORS / discipline_color() are imported from aec_data.disciplines (above).

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


def discipline_of_division(div: str | None) -> str | None:
    return _DIV_TO_DISCIPLINE.get((div or "").strip().zfill(2)[:2]) if div else None


# IFC4.3 (ISO 16739-1:2024) infrastructure entities. These live in MasterFormat divisions 34
# (Transportation) / 35 (Waterway & Marine) that fall outside the Civil discipline's building
# divisions, so map them straight to Civil (C) rather than losing them to the default.
INFRA_IFC_CLASSES: frozenset[str] = frozenset({
    "IfcAlignment", "IfcRoad", "IfcRoadPart", "IfcRailway", "IfcRailwayPart", "IfcRail",
    "IfcBridge", "IfcBridgePart", "IfcMarineFacility", "IfcMarinePart", "IfcTunnel", "IfcTunnelPart",
    "IfcCourse", "IfcPavement", "IfcKerb", "IfcEarthworksCut", "IfcEarthworksFill",
    "IfcEarthworksElement", "IfcTrackElement", "IfcSign", "IfcSignal", "IfcBearing",
})


def is_infra_class(ifc_class: str | None) -> bool:
    """True for an IFC4.3 infrastructure entity (alignment / road / rail / bridge / marine / …)."""
    return (ifc_class or "").strip() in INFRA_IFC_CLASSES


# IFC classes whose discipline isn't cleanly derivable from the MasterFormat section map — mostly the
# MEP / fire / electrical / telecom distribution entities (which the estimate map doesn't enumerate).
# Pin them so color-by-discipline, the model browser, and property rollups classify every element.
_IFC_DISCIPLINE: dict[str, str] = {
    # fire protection (F)
    "IfcSprinkler": "F", "IfcFireSuppressionTerminal": "F",
    # fire alarm / life safety + electronic safety (fold to Electrical discipline; distinct FA sheet series)
    "IfcAlarm": "E", "IfcSensor": "E", "IfcActuator": "E",
    # telecommunications (T)
    "IfcCommunicationsAppliance": "T", "IfcAudioVisualAppliance": "T",
    # electrical distribution (E)
    "IfcTransformer": "E", "IfcElectricDistributionBoard": "E", "IfcElectricGenerator": "E",
    "IfcElectricMotor": "E", "IfcElectricAppliance": "E", "IfcProtectiveDevice": "E",
    "IfcSwitchingDevice": "E", "IfcOutlet": "E", "IfcLightFixture": "E", "IfcJunctionBox": "E",
    "IfcCableSegment": "E", "IfcCableCarrierSegment": "E", "IfcCableCarrierFitting": "E",
    "IfcCableFitting": "E",
    # plumbing (P)
    "IfcPump": "P", "IfcTank": "P", "IfcSanitaryTerminal": "P", "IfcWasteTerminal": "P",
    "IfcValve": "P", "IfcPipeFitting": "P", "IfcInterceptor": "P",
    # mechanical / HVAC (M)
    "IfcBoiler": "M", "IfcChiller": "M", "IfcCoolingTower": "M", "IfcFan": "M", "IfcCoil": "M",
    "IfcAirTerminal": "M", "IfcAirTerminalBox": "M", "IfcDuctFitting": "M", "IfcUnitaryEquipment": "M",
    "IfcAirToAirHeatRecovery": "M", "IfcDamper": "M", "IfcCompressor": "M", "IfcCondenser": "M",
    "IfcEvaporator": "M", "IfcHeatExchanger": "M", "IfcSpaceHeater": "M", "IfcHumidifier": "M",
    "IfcTubeBundle": "M", "IfcFlowMeter": "M",
    # structural reinforcement / assemblies (S) — swept solids the MasterFormat map doesn't list
    "IfcReinforcingBar": "S", "IfcReinforcingMesh": "S", "IfcTendon": "S", "IfcTendonAnchor": "S",
    "IfcReinforcingElement": "S",
    # conveying / vertical transport (Q)
    "IfcTransportElement": "Q",
    # architectural (A) — roof reads as an assembly, not through masonry default
    "IfcRoof": "A", "IfcRamp": "A", "IfcShadingDevice": "A",
}


# Framing/glazing parts (IfcMember/IfcPlate) default to Structural steel, but when they are aggregated
# under an architectural host — a curtain wall or a roof — they belong to that host's discipline
# (a mullion is façade, not frame). DISC-cw: context wins over the bare-class default.
_CW_PART_CLASSES = frozenset({"IfcMember", "IfcPlate"})
_ARCH_HOST_CLASSES = frozenset({"IfcCurtainWall", "IfcRoof"})


def discipline_of_ifc_class(ifc_class: str, host_class: str | None = None) -> str | None:
    """The NCS discipline for an IFC class. Explicit MEP/fire/telecom pins win; a framing/glazing part
    aggregated under a curtain wall or roof follows that host (Architectural); IFC4.3 infrastructure
    entities are Civil (C); everything else is derived through its MasterFormat section."""
    cl = (ifc_class or "").strip()
    host = (host_class or "").strip()
    if cl in _CW_PART_CLASSES and host in _ARCH_HOST_CLASSES:
        return "A"
    if cl in _IFC_DISCIPLINE:
        return _IFC_DISCIPLINE[cl]
    if is_infra_class(cl):
        return "C"
    code, _ = classify(cl, "masterformat")
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
    """Catalog for the UI + module selects: code, name, color, divisions (with titles), uniformat groups."""
    return [{**d, "color": discipline_color(d["code"]),
             "division_titles": {v: MF_DIVISIONS.get(v, v) for v in d["divisions"]}}
            for d in DISCIPLINES]


def discipline_tree() -> dict[str, Any]:
    """The single unified discipline spine for the whole app — one source of truth that the viewer
    (color-by-discipline), plan/PDF poché, sheet generator, model browser, and module selects all
    consume instead of each re-encoding their own list. For every NCS discipline it carries: display
    color, CSI MasterFormat divisions (+titles), UniFormat II groups (+titles), NCS sheet series, and
    the representative IFC classes that roll up to it (so a client can color/group by discipline with
    no local mapping table)."""
    by_disc: dict[str, list[str]] = {d["code"]: [] for d in DISCIPLINES}
    known = sorted(set(_IFC_DISCIPLINE) | set(CLASSIFICATIONS["masterformat"]["map"]) | INFRA_IFC_CLASSES)
    for cl in known:
        dc = discipline_of_ifc_class(cl)
        if dc in by_disc:
            by_disc[dc].append(cl)
    return {
        "disciplines": [
            {"code": d["code"], "name": d["name"], "color": discipline_color(d["code"]),
             "divisions": [{"code": v, "title": MF_DIVISIONS.get(v, v)} for v in d["divisions"]],
             "uniformat": [{"code": u, "title": UNIFORMAT.get(u, (u, []))[0]} for u in d["uniformat"]],
             "sheet_series": [d["code"], *[s for s in SHEET_SERIES if s[:1] == d["code"]]],
             "ifc_classes": by_disc.get(d["code"], [])}
            for d in DISCIPLINES
        ],
        "series": [{"code": k, "name": v, "color": discipline_color(k)} for k, v in SHEET_SERIES.items()],
        "ifc_class_discipline": {cl: discipline_of_ifc_class(cl) for cl in known},
        "colors": {d["code"]: discipline_color(d["code"]) for d in DISCIPLINES},
    }


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
