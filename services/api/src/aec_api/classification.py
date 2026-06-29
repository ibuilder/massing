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
            f"          <Description><CompleteText><OutlineText><OutlTxt><TextOutlTxt><span>{text}</span></TextOutlTxt></OutlTxt></OutlineText></CompleteText></Description>\n"
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
