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
    # Bounded quantifiers ({1,n} not +/*) + a capped input keep these free-text scans linear — an
    # unbounded `\d+`/`[\d,]+`/`\s*` under re.search re-scans and is polynomial-ReDoS on a crafted string.
    low = (text or "")[:20_000].lower()
    occ = next(({"group": g, "label": lbl} for pat, g, lbl in _OCCUPANCY if re.search(pat, low)), None)
    area = None
    m = re.search(r"([\d,]{1,20})\s{0,4}(?:sf|sq\.?\s{0,4}ft|square feet)", low)
    if m:
        area = int(m.group(1).replace(",", ""))
    stories = None
    m = re.search(r"(\d{1,4})[\s-]{0,4}(?:stor(?:y|ies)|floors?)", low)
    if m:
        stories = int(m.group(1))
    occ_load = None
    m = re.search(r"(\d{1,7})\s{0,4}(?:occupant|people|person|seat)", low)
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


def code_ids(description: str, edition: str | None = None, title: str = "") -> dict[str, Any]:
    """CODE-5: emit the **machine-checkable subset** of the applicable code requirements as a buildingSMART
    **IDS 1.0** file — so the same jurisdiction-resolved rules validate an IFC in any IDS checker (extends
    the IDS→BCF pipeline). Composes the fired code rules (which requirements apply for this occupancy /
    size / edition) with the standard IFC common-property IDS specs. Facts of law (property requirements),
    never ICC prose; the AHJ makes the determination."""
    from . import ids_authoring
    rc = _rules_check(description)
    feat = rc["detected"]
    occ = (feat.get("occupancy") or {}).get("group")
    groups: list[str] = []
    for g in ((["walls", "doors", "slabs", "columns", "beams"]                 # fire-resistance-rated
               if (occ in ("R", "A", "H", "I") or (feat.get("stories") or 0) >= 4) else [])
              + ["spaces"]                                                       # occupant load / egress
              + ["walls", "windows"]):                                          # IECC envelope U-value
        if g not in groups:
            groups.append(g)
    specs = ids_authoring._specs_for(groups)
    ttl = title or ("Code data requirements" + (f" — {edition}" if edition else ""))
    xml = ids_authoring.build_ids(ttl, specs, purpose="Code-compliance data requirements (facts of law).")
    return {"edition": edition, "detected": feat, "topics": rc["topics"], "groups": groups,
            "spec_count": len(specs), "ids_xml": xml,
            "note": "The machine-checkable subset of the applicable code requirements as buildingSMART "
                    "IDS 1.0 — validate an IFC against it in any IDS checker. Property requirements (facts "
                    "of law), not code prose; the AHJ makes the final determination."}


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


# CODE-2: edition-scoped occupant-load-factor deltas (facts of law). The one well-established change in
# Table 1004.5 across current editions: Business areas moved from 100 gross (IBC 2012/2015) to 150 gross
# (IBC 2018 onward). Same regex label, edition-dependent factor. Everything else is stable across editions.
_OCC_FACTOR_BY_EDITION: dict[str, dict[int, int]] = {
    "Business": {2012: 100, 2015: 100, 2018: 150, 2021: 150, 2024: 150},
    "Business (assumed)": {2012: 100, 2015: 100, 2018: 150, 2021: 150, 2024: 150},
}


def _edition_factor(label: str, factor: int, edition: int | None) -> int:
    """Apply an edition-specific occupant-load factor when one differs from the default (else `factor`)."""
    if edition is None:
        return factor
    table = _OCC_FACTOR_BY_EDITION.get(label)
    return table.get(int(edition), factor) if table else factor


def _occ_factor(text: str, edition: int | None = None) -> tuple[str, int, str]:
    t = (text or "").lower()
    for rx, label, factor, basis in _OCC_FACTORS:
        if re.search(rx, t):
            return label, _edition_factor(label, factor, edition), basis
    label, factor, basis = _DEFAULT_FACTOR
    return label, _edition_factor(label, factor, edition), basis


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


def egress_analysis(elements: dict[str, dict], edition: int | None = None) -> dict[str, Any]:
    """Occupant load (IBC 1004) per space + building total, and egress capacity (IBC 1005) vs the
    provided egress-door width. `elements` is the property index {guid: element-dict}. `edition` (an IBC
    year) selects edition-scoped load factors (CODE-2) — e.g. the Business factor is 100 gross ≤2015 vs 150
    gross ≥2018; None keeps the current-edition default (150)."""
    spaces: list[dict] = []
    by_occ: dict[str, dict] = {}
    total_load, total_area = 0, 0.0
    for guid, e in elements.items():
        if e.get("ifc_class") != "IfcSpace":
            continue
        area = _space_area_ft2(e)
        label, factor, basis = _occ_factor(_space_occupancy(e), edition)
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
        "code_edition": int(edition) if edition else None,
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


# IBC occupancy-label → group letter (Ch. 3), for the code-analysis summary. Matched as ordered
# substrings, NOT exact keys — the labels `_occ_factor` emits carry parentheticals and synonyms
# ("Assembly (unconcentrated)", "Educational (classroom)", "Industrial", "Business (assumed)"), so an
# exact dict silently drops most of them to "". First substring hit wins (order matters where a label
# could match two keys). Accessory/utility spaces have no standalone group → left unresolved ("").
_OCC_GROUP_MATCH: list[tuple[str, str]] = [
    ("assembly", "A"), ("kitchen", "B"), ("business", "B"), ("educational", "E"),
    ("institutional", "I"), ("mercantile", "M"), ("residential", "R"),
    ("parking", "S"), ("storage", "S"), ("industrial", "F"), ("factory", "F"),
    ("high-hazard", "H"),
]


def _occ_group(label: str) -> str:
    t = (label or "").lower()
    return next((g for key, g in _OCC_GROUP_MATCH if key in t), "")


def code_analysis(model, occupancy_group: str = "", construction_type: str = "",
                  sprinklered: bool = False, jurisdiction: str = "") -> dict[str, Any]:
    """Assemble the **IBC code-analysis summary** a permit set carries on its G-series code sheet —
    occupancy classification, construction type, gross area + stories, the **computed occupant load +
    egress** (reused from the egress analysis), and the governing code sections for allowable area/height
    and fire-resistance. `occupancy_group`/`construction_type` are project inputs (else inferred/defaulted);
    `jurisdiction` (US state code) resolves the adopted IBC **edition** so citations name it (CODE-1/3).
    A pre-check assist that cites sections; NOT a certified review — verify allowable area against the
    actual Table 506.2 with the AHJ."""
    # CODE-1/2/3: resolve the jurisdiction's adopted IBC edition first, so the occupant-load computation
    # uses that edition's load factors and the summary names it.
    from aec_data import codes  # type: ignore
    ctx = codes.resolve(jurisdiction)
    ibc_ed = ctx["primary"].get("IBC")

    eg = egress_from_model(model, ibc_ed)
    by_occ = eg.get("by_occupancy") or []
    primary = by_occ[0]["occupancy"] if by_occ else ""
    group = (occupancy_group or _occ_group(primary)).upper()
    ctype = construction_type or "II-B (verify with AHJ)"
    stories = len(model.by_type("IfcBuildingStorey"))
    gross_ft2 = eg["building"]["area_ft2"]
    ibc_label = f"IBC {ibc_ed}" if ibc_ed else "IBC"

    return {
        "code_context": {"jurisdiction": ctx["jurisdiction"], "ibc_edition": ibc_ed,
                         "resolved": ctx["resolved"], "as_of": ctx["as_of"], "verify": ctx["verify"]},
        "occupancy": {"group": group or "—", "primary": primary or "—",
                      "mix": [o["occupancy"] for o in by_occ]},
        "construction_type": ctype, "sprinklered": bool(sprinklered),
        "building": {"gross_area_ft2": gross_ft2, "stories": stories,
                     "occupant_load": eg["building"]["occupant_load"]},
        "occupant_load_by_occupancy": by_occ,
        "egress": eg["egress"], "doors": eg["doors"],
        "allowable": {
            "note": "Compare gross area/height/stories against the allowable for this occupancy + "
                    "construction type. Base allowable area (Table 506.2) increases for frontage "
                    "(§506.3) and an NFPA-13 sprinkler system (§506.2/§504).",
            "sections": ["IBC Table 506.2 (allowable area)", "IBC §504 (height & stories)",
                         "IBC §506.3 (frontage increase)", "IBC Table 601/602 (element fire ratings)"],
            "sprinkler_increase": "eligible" if sprinklered else "not applied",
        },
        "citations": eg["citations"] + [f"{ibc_label} Ch. 3 (occupancy)",
                                        f"{ibc_label} Ch. 6 / Table 601 (construction type)",
                                        f"{ibc_label} Table 506.2 (allowable area)",
                                        f"{ibc_label} §504 (height/stories)"],
        "disclaimer": eg["disclaimer"] + (f" Code context: {ibc_label}"
                                          + (f" ({ctx['jurisdiction']} adoption, as-of {ctx['as_of']})"
                                             if ctx["resolved"] else " (national baseline — set a jurisdiction)")
                                          + f". {ctx['verify']}"),
    }


def _fire_rating(el, ue) -> str | None:
    """A fire-resistance rating from the standard psets (Pset_*Common.FireRating), if any."""
    for pset in (f"Pset_{el.is_a()[3:]}Common", "Pset_WallCommon", "Pset_SlabCommon"):
        p = ue.get_pset(el, pset) or {}
        fr = p.get("FireRating")
        if fr and str(fr).strip() not in ("", "0"):
            return str(fr)
    return None


def _has_assembly_ref(el) -> bool:
    """Whether a rated element carries a tested-assembly reference — a classification (UL/GA/etc.) or an
    attached document (the assembly listing / detail). The reviewer signal that a rating is substantiated."""
    for rel in (getattr(el, "HasAssociations", None) or []):
        if rel.is_a() in ("IfcRelAssociatesClassification", "IfcRelAssociatesDocument"):
            return True
    return False


def approvability(model) -> dict[str, Any]:
    """D8 — a **plan-reviewer pre-flight checklist** over the model: is it permit-ready? Each check reports
    pass/fail with counts + the governing citation. Reuses the computed egress; scans rated assemblies for
    a substantiating reference. A pre-check assist that mirrors what a reviewer looks for first — NOT a
    certified review or a guarantee of approval."""
    import ifcopenshell.util.element as ue

    checks: list[dict[str, Any]] = []
    eg = egress_from_model(model)

    # 1. egress capacity (IBC 1005)
    adeq = eg["egress"]["adequate"]
    checks.append({"check": "Egress capacity", "citation": "IBC 1005.3",
                   "status": "na" if adeq is None else ("pass" if adeq else "fail"),
                   "detail": (f"{eg['egress']['provided_width_in']} in provided vs "
                              f"{eg['egress']['required_width_in']} in required for "
                              f"{eg['building']['occupant_load']} occupants")
                   if adeq is not None else "no occupiable spaces with area — add IfcSpaces"})

    # 2. egress door clear width (IBC 1010.1.1 / A117.1 404)
    below = eg["doors"]["below_min_32in"]
    checks.append({"check": "Egress door clear width (≥32 in)", "citation": "IBC 1010.1.1 / A117.1 404",
                   "status": "na" if eg["doors"]["checked"] == 0 else ("pass" if below == 0 else "fail"),
                   "detail": f"{below} of {eg['doors']['checked']} door(s) below the 32 in minimum"})

    # 3. two exits where required (IBC 1006.2)
    needs2 = [s for s in eg["spaces"] if s.get("needs_2_exits")]
    checks.append({"check": "Two exits where occupant load > 49", "citation": "IBC 1006.2",
                   "status": "info" if needs2 else "pass",
                   "detail": (f"{len(needs2)} space(s) exceed 49 occupants — verify each has 2 exits/exit "
                              "accesses (exit count isn't modeled)") if needs2 else "no space exceeds 49 occupants"})

    # 4. occupancy classification present (spaces carry an occupancy → the code analysis is valid)
    spaces = model.by_type("IfcSpace")
    # a real occupancy classification lives in Pset_SpaceOccupancyRequirements.OccupancyType — NOT the
    # space's free-text LongName (which our own add_spaces always sets to "Room NN"), so LongName would
    # green-light every auto-authored space.
    classified = [s for s in spaces
                  if str((ue.get_pset(s, "Pset_SpaceOccupancyRequirements") or {}).get("OccupancyType") or "").strip()]
    checks.append({"check": "Occupancy classification on spaces", "citation": "IBC Ch. 3",
                   "status": "na" if not spaces else ("pass" if len(classified) == len(spaces) else "fail"),
                   "detail": f"{len(classified)} of {len(spaces)} space(s) carry an occupancy type "
                             "(Pset_SpaceOccupancyRequirements.OccupancyType)"})

    # 5. fire-rated assemblies substantiated (a rated wall/slab carries a UL/GA/detail reference)
    rated, undocumented = [], []
    for el in (*model.by_type("IfcWall"), *model.by_type("IfcSlab")):
        if el.is_a("IfcElementType"):
            continue
        if _fire_rating(el, ue):
            rated.append(el)
            if not _has_assembly_ref(el):
                undocumented.append(el.GlobalId)
    checks.append({"check": "Fire-rated assemblies substantiated (UL/GA or detail)", "citation": "IBC Table 721 / 703.2",
                   "status": "na" if not rated else ("pass" if not undocumented else "fail"),
                   "detail": (f"{len(rated) - len(undocumented)} of {len(rated)} rated assembly(ies) carry a "
                              "tested-assembly reference (classification or attached detail)")
                   if rated else "no fire-rated walls/slabs found (set FireRating to track)",
                   "guids": undocumented[:20]})

    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    gating = sum(1 for c in checks if c["status"] in ("pass", "fail"))
    return {
        "checks": checks,
        "summary": {"passed": passed, "failed": failed, "gating": gating,
                    "ready": failed == 0, "score_pct": round(100 * passed / gating) if gating else None},
        "disclaimer": "Plan-reviewer pre-flight computed from the IFC — mirrors first-pass review checks but "
                      "is NOT a certified review or a guarantee of permit approval. Confirm with the AHJ.",
    }


def egress_from_model(model, edition: int | None = None) -> dict[str, Any]:
    """Extract IfcSpace + IfcDoor (with their psets/qtos) straight from the source IFC and run the
    egress analysis. Spaces are read from the model — the property index holds only *physical*
    elements, so IfcSpace (a spatial element) isn't in it. `edition` selects edition-scoped load factors."""
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
    return egress_analysis(idx, edition)
