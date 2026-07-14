"""Code-compliance assistant — "describe the project, get the applicable code sections with citations."

The report's build-first-design thesis is code/cost/constructibility rolled into design; AEC Foundry's
"Archie" productizes exactly this. Mirrors review.py: Claude when ANTHROPIC_API_KEY is set for a nuanced
answer, otherwise a deterministic rules table of the most-cited IBC provisions triggered by the project's
occupancy / area / stories. Offline path never invents a citation — it only surfaces sections whose
trigger the description actually matched. Not legal advice or a substitute for the AHJ; a design-stage
checklist that points you at the right sections early."""
from __future__ import annotations

import json
import logging
import math
import re
from typing import Any

from . import settings_store
from .ai import ai_enabled

_log = logging.getLogger("aec.codecheck")

# occupancy keyword -> (IBC group, label)
_OCCUPANCY = [
    (r"assembly|theater|auditorium|restaurant|church|gym|stadium|arena", "A", "Assembly"),
    (r"office|business|bank|clinic|professional", "B", "Business"),
    (r"school|classroom|education|daycare|kindergarten", "E", "Educational"),
    (r"factory|manufactur|industrial|assembly line|fabricat", "F", "Factory"),
    (r"hazard|flammable|combustible|explosive|chemical plant", "H", "High-hazard"),
    (r"hospital|nursing|assisted living|detention|jail|institutional", "I", "Institutional"),
    (r"retail|store|mercantile|shop|market|showroom", "M", "Mercantile"),
    (r"apartment|residential|dwelling|hotel|dormitory|condo|multifamily", "R", "Residential"),
    (r"warehouse|storage|parking garage", "S", "Storage"),
]


def _detect(text: str) -> dict[str, Any]:
    low = text.lower()
    occ = next(({"group": g, "label": lbl} for pat, g, lbl in _OCCUPANCY if re.search(pat, low)), None)
    area = None
    m = re.search(r"([\d,]+)\s*(?:sf|sq\.?\s*ft|square feet)", low)
    if m:
        area = int(m.group(1).replace(",", ""))
    stories = None
    m = re.search(r"(\d+)[\s-]*(?:stor(?:y|ies)|floors?)", low)
    if m:
        stories = int(m.group(1))
    occ_load = None
    m = re.search(r"(\d+)\s*(?:occupant|people|person|seat)", low)
    if m:
        occ_load = int(m.group(1))
    return {"occupancy": occ, "area_sf": area, "stories": stories, "occupant_load": occ_load}


# (trigger(feat)->bool, code, section, title, requirement)
_RULES: list[tuple[Any, str, str, str, str]] = [
    (lambda f: True, "IBC", "Ch. 3", "Occupancy classification",
     "Classify the use group (A/B/E/F/H/I/M/R/S/U); it drives nearly every other requirement."),
    (lambda f: True, "IBC", "Ch. 5 / Tables 504.3, 504.4, 506.2", "Height & area limits",
     "Allowable building height, number of stories, and area per floor depend on occupancy + "
     "construction type (and increase with an NFPA-13 sprinkler system)."),
    (lambda f: True, "IBC", "Ch. 10 §1004", "Occupant load",
     "Compute occupant load from the area and the §1004.5 load factors — it sizes egress."),
    (lambda f: True, "IBC", "Ch. 10 §1006", "Number of exits / access to exits",
     "Two exits are required where occupant load or common-path limits are exceeded (one is allowed "
     "only within §1006.2 limits)."),
    (lambda f: True, "IBC", "Ch. 10 §1005", "Egress width",
     "Egress width = occupant load × the §1005.3 factor (0.2 in/occupant stairs, 0.15 other) unless "
     "reduced for a sprinklered building."),
    (lambda f: True, "IBC / ADA", "Ch. 11 + A117.1", "Accessibility",
     "Accessible route, entrances, toilet rooms, and parking per IBC Ch. 11 and ICC A117.1 (and the ADA)."),
    (lambda f: (f.get("occupancy") or {}).get("group") == "A", "IBC", "§1010.1.10 / §1029",
     "Assembly egress (panic hardware, aisles)",
     "Assembly ≥50 occupants: panic/fire-exit hardware on egress doors and aisle/seating egress per §1029."),
    (lambda f: bool(f.get("area_sf") and f["area_sf"] >= 12000) or (f.get("occupancy") or {}).get("group") in ("A", "H"),
     "IBC", "§903.2", "Automatic sprinkler system",
     "An NFPA-13 automatic sprinkler system is commonly required by area/occupancy thresholds in §903.2 "
     "(and unlocks height/area increases)."),
    (lambda f: bool(f.get("stories") and f["stories"] >= 4), "IBC", "Ch. 7 + §3002 / §1009",
     "Fire-resistance, elevators & accessible means of egress",
     "Multi-story: rated construction/shafts (Ch. 7), at least one elevator, and accessible means of "
     "egress with areas of refuge (§1009)."),
    (lambda f: (f.get("occupancy") or {}).get("group") == "R", "IBC / IECC", "§420 + IECC",
     "Dwelling-unit separation & energy",
     "R occupancies: rated dwelling-unit/corridor separation (§420) and IECC envelope/energy compliance."),
    (lambda f: (f.get("occupancy") or {}).get("group") == "I", "IBC", "§407 / Ch. 4",
     "Institutional (defend-in-place)",
     "I-2 (hospitals/nursing): smoke compartments, defend-in-place egress, and special §407 provisions."),
]


def _rules_check(text: str) -> dict[str, Any]:
    feat = _detect(text)
    topics = []
    for trig, code, section, title, req in _RULES:
        try:
            if trig(feat):
                topics.append({"code": code, "section": section, "title": title, "requirement": req})
        except Exception:                                    # noqa: BLE001 — a bad trigger never breaks the check
            continue
    return {"detected": feat, "topics": topics, "source": "rules",
            "message": ("Matched the built-in IBC checklist from your description. Set an Anthropic API "
                        "key in Settings for a fuller, reasoned answer. Always confirm with the AHJ.")}


_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["code", "section", "title", "requirement"],
        "properties": {"code": {"type": "string"}, "section": {"type": "string"},
                       "title": {"type": "string"}, "requirement": {"type": "string"}}}}}}

_SYSTEM = (
    "You are a code consultant for US building projects. From the project description (and any model "
    "context), list the applicable building-code provisions the design team must address — primarily the "
    "IBC, plus ADA/A117.1, IECC, IFC, and IMC/IPC where relevant. For each, give the code, the section "
    "number, a short title, and the requirement in one sentence. Cite real section numbers; if unsure of "
    "an exact number, name the chapter. Note that final authority is the AHJ. Do not invent provisions.")


def check(description: str, context: str | None = None) -> dict[str, Any]:
    desc = (description or "").strip()
    if not desc:
        return {"topics": [], "source": "empty",
                "message": "Describe the project — occupancy/use, area, stories — to get applicable codes."}
    if ai_enabled():
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"), timeout=60.0, max_retries=1)
            user = desc if not context else f"{desc}\n\nModel context:\n{context[:4000]}"
            resp = client.messages.create(
                model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=3072,
                system=_SYSTEM, messages=[{"role": "user", "content": user[:12000]}],
                output_config={"format": {"type": "json_schema", "schema": _SCHEMA}, "effort": "medium"})
            out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(out)
            data["detected"] = _detect(desc)
            data["source"] = "claude"
            return data
        except Exception as e:                               # noqa: BLE001
            _log.warning("AI code check failed (%s) — using rules", e)
    return _rules_check(desc)


# --- Computed occupancy-load + egress-capacity analysis (Wave 9 · W9-2) ------------------------------
# A COMPUTED pre-check over the model's IfcSpaces/IfcDoors — the depth layer above the presence-only
# /elements/code-check. Encodes IBC *thresholds* (which are facts), never ICC prose. NOT a certified
# review or a substitute for the AHJ; travel-distance / performance-based egress are out of scope.
_M2_TO_FT2 = 10.7639
_M_TO_IN = 39.3701
_MIN_EGRESS_DOOR_M = 0.813   # 32 in clear width (IBC 1010.1.1)

# IBC Table 1004.5 — maximum floor-area allowance per occupant (ft²/occupant) + basis (net vs gross).
_OCC_FACTORS = [   # (keyword regex, label, ft²/occupant, basis)
    (r"assembly.*concentrat|chairs? only|theater|auditorium|arena|stadium", "Assembly (concentrated)", 7, "net"),
    (r"assembly|dining|restaurant|conference|lobby|gym|exhibit|worship|church", "Assembly (unconcentrated)", 15, "net"),
    (r"kitchen", "Commercial kitchen", 200, "gross"),
    (r"classroom|education|school|daycare|kindergarten", "Educational (classroom)", 20, "net"),
    (r"office|business|clinic|bank|professional|admin", "Business", 150, "gross"),
    (r"mercantile|retail|store|sales|shop", "Mercantile", 60, "gross"),
    (r"resid|dwelling|apartment|hotel|dorm|sleeping|bedroom|guest", "Residential", 200, "gross"),
    (r"warehouse|storage|stock", "Storage", 500, "gross"),
    (r"industrial|factory|manufactur", "Industrial", 100, "gross"),
    (r"institution|hospital|nursing|patient|ward", "Institutional", 240, "gross"),
    (r"parking|garage", "Parking", 200, "gross"),
    (r"mechanical|electrical|equipment|utility|riser|shaft|closet|corridor|circulation", "Accessory", 300, "gross"),
]
_DEFAULT_FACTOR = ("Business (assumed)", 150, "gross")


def _occ_factor(text: str) -> tuple[str, int, str]:
    t = (text or "").lower()
    for rx, label, factor, basis in _OCC_FACTORS:
        if re.search(rx, t):
            return label, factor, basis
    return _DEFAULT_FACTOR


def _space_area_ft2(e: dict) -> float | None:
    qtos = e.get("qtos") or {}
    q = qtos.get("Qto_SpaceBaseQuantities") or {}
    for key in ("NetFloorArea", "GrossFloorArea"):
        v = q.get(key)
        if isinstance(v, (int, float)):
            return float(v) * _M2_TO_FT2
    return None


def _space_occupancy(e: dict) -> str:
    p = (e.get("psets") or {}).get("Pset_SpaceOccupancyRequirements") or {}
    return str(p.get("OccupancyType") or e.get("name") or e.get("long_name") or "")


def _door_width_m(e: dict) -> float | None:
    # authored doors store their clear width in the OverallWidth ATTRIBUTE (not a pset); prefer it,
    # then fall back to the (less common) quantity/pset widths.
    ow = e.get("overall_width")
    if isinstance(ow, (int, float)) and ow > 0:
        return float(ow)
    for container, grp, key in (("qtos", "Qto_DoorBaseQuantities", "Width"),
                                ("psets", "Pset_DoorCommon", "Width")):
        v = ((e.get(container) or {}).get(grp) or {}).get(key)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def egress_analysis(elements: dict[str, dict]) -> dict[str, Any]:
    """Occupant load (IBC 1004) per space + building total, and egress capacity (IBC 1005) vs the
    provided egress-door width. `elements` is the property index {guid: element-dict}."""
    spaces: list[dict] = []
    by_occ: dict[str, dict] = {}
    total_load, total_area = 0, 0.0
    for guid, e in elements.items():
        if e.get("ifc_class") != "IfcSpace":
            continue
        area = _space_area_ft2(e)
        label, factor, basis = _occ_factor(_space_occupancy(e))
        if area is None:
            spaces.append({"guid": guid, "name": e.get("name"), "occupancy": label,
                           "area_ft2": None, "load": None, "note": "no floor-area quantity"})
            continue
        load = math.ceil(area / factor - 1e-6)   # round up genuine fractions, not float-dust
        total_load += load
        total_area += area
        agg = by_occ.setdefault(label, {"occupancy": label, "factor": factor, "basis": basis,
                                        "spaces": 0, "area_ft2": 0.0, "load": 0})
        agg["spaces"] += 1
        agg["area_ft2"] = round(agg["area_ft2"] + area, 1)
        agg["load"] += load
        spaces.append({"guid": guid, "name": e.get("name"), "occupancy": label, "factor": factor,
                       "basis": basis, "area_ft2": round(area, 1), "load": load,
                       "needs_2_exits": load > 49})
    # egress capacity: required egress width = occupant load × 0.15 in/occ (IBC 1005.3.2, doors/level)
    req_in = round(total_load * 0.15, 1)
    doors = below_min = 0
    provided_in = 0.0
    min_fail: list[str] = []
    for guid, e in elements.items():
        if e.get("ifc_class") != "IfcDoor":
            continue
        w = _door_width_m(e)
        if w is None:
            continue
        doors += 1
        if w + 1e-6 < _MIN_EGRESS_DOOR_M:
            below_min += 1
            min_fail.append(guid)
        else:
            provided_in += w * _M_TO_IN   # egress-capable doors contribute capacity
    return {
        "building": {"occupant_load": total_load, "area_ft2": round(total_area, 1),
                     "spaces": sum(1 for s in spaces if s["load"] is not None),
                     "spaces_missing_area": sum(1 for s in spaces if s["load"] is None)},
        "egress": {"required_width_in": req_in, "provided_width_in": round(provided_in, 1),
                   "adequate": (round(provided_in, 1) >= req_in) if total_load else None,
                   "factor_in_per_occ": 0.15, "code": "IBC 1005.3"},
        "doors": {"checked": doors, "below_min_32in": below_min, "fail_guids": min_fail,
                  "min_clear_m": _MIN_EGRESS_DOOR_M, "code": "IBC 1010.1.1"},
        "by_occupancy": sorted(by_occ.values(), key=lambda x: -x["load"]),
        "spaces": spaces,
        "citations": ["IBC 1004.5 (occupant-load factors)", "IBC 1005.3 (egress width per occupant)",
                      "IBC 1006.2 (two exits when load > 49)", "IBC 1010.1.1 (32 in min clear door)"],
        "disclaimer": "Pre-check / design assist computed from the IFC — not a certified code review or "
                      "a substitute for the authority having jurisdiction. Travel-distance and "
                      "performance-based egress are out of scope.",
    }


def egress_from_model(model) -> dict[str, Any]:
    """Extract IfcSpace + IfcDoor (with their psets/qtos) straight from the source IFC and run the
    egress analysis. Spaces are read from the model — the property index holds only *physical*
    elements, so IfcSpace (a spatial element) isn't in it."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)                # OverallWidth is in file units → metres
    idx: dict[str, dict] = {}
    for cls in ("IfcSpace", "IfcDoor"):
        for el in model.by_type(cls):
            ow = getattr(el, "OverallWidth", None) if cls == "IfcDoor" else None
            idx[el.GlobalId] = {
                "ifc_class": cls,
                "name": getattr(el, "Name", None),
                "long_name": getattr(el, "LongName", None),
                "overall_width": float(ow) * scale if isinstance(ow, (int, float)) else None,
                "psets": ue.get_psets(el, psets_only=True),
                "qtos": ue.get_psets(el, qtos_only=True),
            }
    return egress_analysis(idx)
