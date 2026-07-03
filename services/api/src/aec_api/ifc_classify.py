"""IFC classification assist — suggest the right IfcClass for mis-/under-classified elements.

Authoring tools export a lot of `IfcBuildingElementProxy` (generic) or leave elements loosely typed;
that quietly breaks QTO, embodied-carbon, and IDS compliance downstream (a proxy gets no quantities or
carbon factor). Qonic productizes a neural-net version of this; here it's a transparent rules classifier
over the element name/type we already extract — every suggestion carries the reason it fired, so a human
approves before anything is rewritten. Improves the accuracy of the data feeding carbon.py / QTO."""
from __future__ import annotations

import re

# name/type keyword -> canonical IfcClass. Order matters (first match wins); more specific first.
_RULES: list[tuple[str, str]] = [
    (r"curtain\s*wall|storefront", "IfcCurtainWall"),
    (r"\bwall\b|partition", "IfcWall"),
    (r"\bdoor\b|overhead door|roll[- ]?up", "IfcDoor"),
    (r"\bwindow\b|glazing|fenestration", "IfcWindow"),
    (r"\bslab\b|floor plate|deck\b|topping", "IfcSlab"),
    (r"\broof\b", "IfcRoof"),
    (r"\bcolumn\b|\bpost\b|pilaster", "IfcColumn"),
    (r"\bbeam\b|girder|joist|lintel", "IfcBeam"),
    (r"\bstair\b|stringer", "IfcStair"),
    (r"\bramp\b", "IfcRamp"),
    (r"\brailing\b|guardrail|handrail|balustrade", "IfcRailing"),
    (r"\bfooting\b|foundation|pile cap|grade beam", "IfcFooting"),
    (r"\bpile\b|caisson", "IfcPile"),
    (r"\bduct\b|diffuser|\bvav\b|air handler|\bahu\b", "IfcDuctSegment"),
    (r"\bpipe\b|plumbing|sanitary|storm line", "IfcPipeSegment"),
    (r"\bconduit\b|cable tray|busway", "IfcCableCarrierSegment"),
    (r"\bfixture\b|luminaire|light fitting", "IfcLightFixture"),
    (r"\bfurnitur|casework|millwork|cabinet", "IfcFurniture"),
    (r"\bcovering\b|ceiling|finish\b|cladding", "IfcCovering"),
    (r"\bspace\b|\broom\b|zone\b", "IfcSpace"),
]

# classes considered "unclassified/generic" — prime candidates for reclassification.
_GENERIC = {"IfcBuildingElementProxy", "IfcElementAssembly", "IfcProduct", "IfcElement", "", None}


def _suggest_class(text: str) -> tuple[str, str] | None:
    low = (text or "").lower()
    for pat, cls in _RULES:
        if re.search(pat, low):
            return cls, pat
    return None


def classify(elements: list[dict]) -> dict:
    """elements: [{guid?, name, ifc_class, type?}] -> reclassification suggestions.

    Suggests when: (a) the element is generic/proxy and its name implies a class, or (b) its name
    strongly implies a class that differs from its current one. Only name-supported suggestions."""
    suggestions = []
    by_target: dict[str, int] = {}
    generic = 0
    for e in elements:
        cur = e.get("ifc_class") or e.get("class") or ""
        name = e.get("name") or e.get("type") or ""
        is_generic = cur in _GENERIC
        if is_generic:
            generic += 1
        m = _suggest_class(name)
        if not m:
            continue
        target, reason = m
        if target == cur:
            continue                                     # already correct
        # only propose a *change* of a real class when the name signal is strong (whole-word class term)
        if not is_generic:
            base = target.replace("Ifc", "").lower()
            if not re.search(rf"\b{base}\b", name.lower()):
                continue
        confidence = "high" if is_generic else "medium"
        suggestions.append({"guid": e.get("guid"), "name": name, "current_class": cur or "(none)",
                            "suggested_class": target, "confidence": confidence,
                            "reason": f"name matches /{reason}/"})
        by_target[target] = by_target.get(target, 0) + 1
    suggestions.sort(key=lambda s: (s["confidence"] != "high", s["suggested_class"]))
    return {"suggestions": suggestions, "count": len(suggestions),
            "generic_elements": generic, "by_target_class": dict(sorted(by_target.items(), key=lambda x: -x[1])),
            "message": (None if suggestions else "No name-supported reclassifications found — the model "
                        "looks well-classified, or names don't carry element-type hints.")}
