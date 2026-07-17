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



# --- egress / occupancy-load analysis lives in codecheck_egress.py; re-exported here as a façade so
# `codecheck.approvability` / `.code_analysis` / `.egress_from_model` / `.egress_analysis` keep working ---
from .codecheck_egress import (  # noqa: E402
    approvability,
    code_analysis,
    egress_analysis,
    egress_from_model,
)

__all__ = ["approvability", "check", "code_analysis", "code_ids", "egress_analysis",
           "egress_from_model"]
