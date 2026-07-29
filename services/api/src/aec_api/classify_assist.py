"""R22-CLASSIFY-AI — cost/discipline classification for a model somebody else authored.

**The finding this is built around.** `classification.classify(ifc_class, system)` returns a
`(code, title)` tuple for any input. When the class is not in the system's map it returns the
system's **default bucket** — MasterFormat `01 00 00 General Requirements`, NRM1 `0 Facilitating
works` — and the return type cannot express the difference. A model we authored is full of classes
that *are* in the map, so this never shows. An imported model is full of `IfcBuildingElementProxy`,
and every one of those elements prices as General Requirements while the estimate reports a complete
takeoff. Nothing is missing, nothing errors, and the number is wrong.

That is the same shape as the `get_area` defect: a fault that only fires on a particular provenance
of model, so the everyday path never catches it. Here the provenance is *imported*, which is nearly
every real client model.

**So the first job is a coverage number that can be believed.** `coverage()` counts only what the
model actually **declares** — an `IfcRelAssociatesClassification` on the element. A code we derived
is a proposal, and proposals never inflate coverage. A 4% figure on a client model is the true
starting point of a cost exercise, and it is more useful than the 100% the current path implies.

**The second job is proposals with their evidence.** Four bases, ranked, and each says what kind of
claim it is:

* `declared` — the model asserts it. Not a proposal at all.
* `keyword` — the element's own name or type name determines the code ("CMU partition" → unit
  masonry). Specific to this element.
* `class_map` — the element's IFC class is in the system's published map. True of the class, and
  therefore identical for every element of that class in the model — including the ones it is wrong
  for. NRM1 maps `IfcWall` to *external walls*; an interior wall exported as plain `IfcWall` gets
  the external code, and nothing about the derivation knows that.
* `unmapped` — the class is not in the map. **This is the one the current code hides**, and it is
  reported as a gap rather than filled with the default bucket.

**Nothing is ever written by reading it.** `propose()` computes; `apply_plan()` turns an explicit
list of accepted GUIDs into `set_classification` recipe steps. A classification that appeared on
elements because somebody opened a report is indistinguishable, a week later, from one a quantity
surveyor decided.

**Uniclass and OmniClass are refused outright.** The standing rule in this codebase is that a
Uniclass code is never guessed; the tables here are the published IFC-class maps for MasterFormat,
DIN 276 and NRM 1, which is a different thing from inventing a Uniclass reference from a keyword. A
request to propose one is an error with that reason, not an empty result — an empty result reads as
"nothing to classify".
"""
from __future__ import annotations

import re
from typing import Any

from . import classification as cls

#: Bases, most to least authoritative. `unmapped` is not a basis for a code; it is the absence of one.
BASES = ("declared", "keyword", "class_map", "unmapped")

#: Systems this module will propose codes for — those with a published IFC-class map in
#: `classification.CLASSIFICATIONS`.
def systems() -> list[str]:
    return sorted(cls.CLASSIFICATIONS)


#: Systems this module refuses to propose for, and why. Kept as data so the refusal carries a reason
#: rather than being a missing branch.
REFUSED: dict[str, str] = {
    "uniclass": "a Uniclass code is never guessed in this codebase — the tables here are published "
                "IFC-class maps, which is not the same thing as inferring a Uniclass reference from "
                "an element name. Import a Uniclass mapping or set the codes explicitly.",
    "omniclass": "no published IFC-class map for OmniClass is carried here; proposing one would be "
                 "invention rather than derivation.",
}


class ClassifyError(ValueError):
    """The request cannot be answered honestly — an unknown or refused classification system."""


# Keyword refinements, per system. Each rule is (pattern, applies-to-classes, code, title).
# These exist because the class alone genuinely does not determine the code, and the element's own
# name does: a wall is masonry or gypsum, and "IfcWall" says nothing about which. `applies_to` is an
# empty tuple when the rule stands on the keyword alone.
#
# Deliberately small. Every rule here is one where the keyword IS the answer; a longer list of
# plausible-sounding rules would raise the proposal rate and lower the proportion a reviewer accepts,
# which is the wrong trade for a surface whose whole purpose is that a human confirms each line.
_KEYWORDS: dict[str, list[tuple[str, tuple[str, ...], str, str]]] = {
    "masterformat": [
        (r"\bcmu\b|concrete masonry|\bmasonry\b|\bbrick\b", ("IfcWall", "IfcWallStandardCase"),
         "04 20 00", "Unit Masonry"),
        (r"\bgyp\b|gypsum|drywall|\bstud\b|partition", ("IfcWall", "IfcWallStandardCase"),
         "09 20 00", "Plaster & Gypsum Board"),
        (r"cast[- ]?in[- ]?place|\bcip\b|\bconcrete\b", ("IfcWall", "IfcWallStandardCase", "IfcColumn",
                                                         "IfcSlab", "IfcBeam"),
         "03 30 00", "Cast-in-Place Concrete"),
        (r"\bsteel\b|\bhss\b|\bw\d+x\d+", ("IfcColumn", "IfcBeam", "IfcMember", "IfcPlate"),
         "05 12 00", "Structural Steel Framing"),
        (r"acoustic(al)? (ceiling|tile)|\bact\b|suspended ceiling", (),
         "09 50 00", "Ceilings"),
        (r"\bcarpet\b|resilient floor|\bvct\b|\blvt\b", (),
         "09 60 00", "Flooring"),
    ],
    "nrm1": [
        (r"\bexternal\b|\bexterior\b|\bfacade\b|\bfaçade\b", ("IfcWall", "IfcWallStandardCase"),
         "2.6", "External walls"),
        (r"\binternal\b|\binterior\b|partition", ("IfcWall", "IfcWallStandardCase"),
         "2.7", "Internal walls & partitions"),
        (r"\bexternal\b|\bexterior\b", ("IfcDoor",), "2.6", "External walls"),
    ],
    "din276": [
        (r"\baußen\b|\baussen\b|\bexternal\b|\bexterior\b", ("IfcWall", "IfcWallStandardCase"),
         "331", "Tragende Außenwände"),
        (r"\binnen\b|\binternal\b|\binterior\b|partition", ("IfcWall", "IfcWallStandardCase"),
         "341", "Tragende Innenwände"),
    ],
}


def _system(system: str) -> str:
    key = (system or "").strip().lower()
    if key in REFUSED:
        raise ClassifyError(f"{system!r}: {REFUSED[key]}")
    if key not in cls.CLASSIFICATIONS:
        raise ClassifyError(f"unknown classification system {system!r}; "
                            f"known: {', '.join(systems())}")
    return key


def read_declared(model: Any) -> dict[str, list[dict[str, Any]]]:
    """`{guid: [{system, code, title}]}` from each element's `IfcRelAssociatesClassification`.

    Walks `ReferencedSource` up to the owning `IfcClassification`, because a reference may point at
    another reference (a facet of a code) rather than straight at the source — reading only one level
    reports the system as None for every correctly-authored hierarchical code.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for rel in (model.by_type("IfcRelAssociatesClassification") or []):
        ref = getattr(rel, "RelatingClassification", None)
        if ref is None:
            continue
        src = getattr(ref, "ReferencedSource", None)
        seen = 0
        while src is not None and getattr(src, "is_a", None) and src.is_a("IfcClassificationReference"):
            src = getattr(src, "ReferencedSource", None)
            seen += 1
            if seen > 16:                    # a malformed self-referencing chain must not hang a scan
                src = None
                break
        entry = {"system": getattr(src, "Name", None) if src is not None else None,
                 "code": getattr(ref, "Identification", None),
                 "title": getattr(ref, "Name", None)}
        for obj in (getattr(rel, "RelatedObjects", None) or []):
            guid = getattr(obj, "GlobalId", None)
            if guid:
                out.setdefault(guid, []).append(dict(entry))
    return out


#: The names a model authored elsewhere actually writes into `IfcClassification.Name`. An explicit
#: list rather than fuzzy matching: the first version of this matched substrings in both directions,
#: which meant the display name "CSI MasterFormat (US/CA)" contributed the fragment "us" and a model
#: declaring "AusSpec" matched MasterFormat. A wrong system match is worse than no match — it reports
#: an element as classified under a standard it was never classified under.
_ALIASES: dict[str, frozenset[str]] = {
    "masterformat": frozenset({"masterformat", "master format", "csi masterformat",
                               "csi master format", "csi masterformat (us/ca)", "csi"}),
    "din276": frozenset({"din276", "din 276", "din-276", "din 276 (dach)"}),
    "nrm1": frozenset({"nrm1", "nrm 1", "nrm-1", "rics nrm 1", "rics nrm1", "rics nrm 1 (uk)"}),
}


def _norm(s: Any) -> str:
    """Lowercase, collapse internal whitespace, strip. Nothing else — no substring games."""
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _declared_for(entries: list[dict[str, Any]] | None, system: str) -> dict[str, Any] | None:
    """The declared code for `system`, matched on the classification source's name.

    Exact match against a known alias, after normalising case and whitespace. An entry whose source
    name we do not recognise is deliberately NOT counted as this system: it may be a different
    standard, and counting it would inflate the coverage figure with codes that are not comparable.
    """
    if not entries:
        return None
    label = _norm(cls.CLASSIFICATIONS[system]["name"])
    wanted = set(_ALIASES.get(system, frozenset())) | {system, _norm(system), label}
    for e in entries:
        if not e.get("code"):
            continue                        # a reference with no Identification classifies nothing
        if _norm(e.get("system")) in wanted:
            return e
    return None


def _keyword_hit(text: str, ifc_class: str, system: str) -> tuple[str, str, str] | None:
    low = (text or "").lower()
    for pattern, applies, code, title in _KEYWORDS.get(system, []):
        if applies and ifc_class not in applies:
            continue
        if re.search(pattern, low):
            return code, title, pattern
    return None


def propose(elements: list[dict[str, Any]], system: str,
            declared: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """One row per element: what it is classified as, or what it could be and on what evidence.

    `elements` are index records — `{guid, ifc_class, name, type_name}`. `declared` is the output of
    `read_declared`; without it every element is treated as undeclared, which is honest for a caller
    that only has the property index (the index does not carry classification associations) but makes
    the coverage figure a lower bound. That is stated in the result rather than left to be inferred.
    """
    key = _system(system)
    sysdef = cls.CLASSIFICATIONS[key]
    cmap = sysdef["map"]
    rows: list[dict[str, Any]] = []

    for e in elements:
        guid = e.get("guid")
        ifc_class = e.get("ifc_class") or e.get("class") or ""
        name = e.get("name") or ""
        type_name = e.get("type_name") or e.get("type") or ""
        row: dict[str, Any] = {"guid": guid, "ifc_class": ifc_class or None,
                               "name": name or None, "type_name": type_name or None}

        found = _declared_for((declared or {}).get(guid or ""), key)
        if found:
            rows.append({**row, "basis": "declared", "code": found["code"],
                         "title": found.get("title"), "confidence": None,
                         "evidence": "the model carries this classification on the element"})
            continue

        hit = _keyword_hit(f"{name} {type_name}", ifc_class, key)
        if hit:
            code, title, pattern = hit
            rows.append({**row, "basis": "keyword", "code": code, "title": title,
                         "confidence": "medium",
                         "evidence": f"the element's own name/type matches /{pattern}/"})
            continue

        if ifc_class in cmap:
            code, title = cmap[ifc_class]
            rows.append({**row, "basis": "class_map", "code": code, "title": title,
                         "confidence": "low",
                         "evidence": f"{key} maps {ifc_class} to this code — true of the CLASS, so "
                                     f"every {ifc_class} in the model gets it, including the ones it "
                                     f"is wrong for"})
            continue

        rows.append({**row, "basis": "unmapped", "code": None, "title": None, "confidence": None,
                     "evidence": (f"{key} has no entry for {ifc_class or '(no class)'}. "
                                  f"`classification.classify` would return the default bucket "
                                  f"{sysdef['default'][0]} {sysdef['default'][1]!r} here, which is "
                                  "not a classification of this element")
                     if ifc_class else "the element carries no IFC class"})

    rows.sort(key=lambda r: (BASES.index(r["basis"]), r["ifc_class"] or "", r["name"] or ""))
    return {
        "system": key, "system_name": sysdef["name"],
        "default_bucket": {"code": sysdef["default"][0], "title": sysdef["default"][1]},
        "rows": rows,
        "declared_supplied": declared is not None,
        **coverage(rows, key),
    }


def coverage(rows: list[dict[str, Any]], system: str) -> dict[str, Any]:
    """The headline number, and what it is made of.

    `classified_pct` counts **declared only**. A derived code is a proposal; letting proposals count
    would make the figure describe how good our guessing is rather than how classified the model is,
    and the whole reason to look at it is to decide whether a cost exercise can start.
    """
    total = len(rows)
    by_basis: dict[str, int] = dict.fromkeys(BASES, 0)
    for r in rows:
        by_basis[r["basis"]] = by_basis.get(r["basis"], 0) + 1
    declared = by_basis["declared"]
    proposable = by_basis["keyword"] + by_basis["class_map"]
    unmapped = by_basis["unmapped"]

    if not total:
        headline = "no elements to classify"
    elif declared == total:
        headline = "fully classified in the model"
    else:
        headline = (f"{round(100 * declared / total, 1)}% of {total} element(s) carry a "
                    f"{system} code in the model")
    return {
        "total": total,
        "declared": declared,
        "classified_pct": round(100 * declared / total, 1) if total else None,
        "proposable": proposable,
        "unmapped": unmapped,
        "by_basis": by_basis,
        "headline": headline,
        "counts_only_declared": (
            "classified_pct counts only codes the MODEL declares. Derived codes are proposals and do "
            "not raise it — a coverage figure that included our own guesses would measure the "
            "guessing, not the model"),
        "unmapped_warning": (
            f"{unmapped} element(s) have no entry in the {system} class map. An estimate built "
            f"without classifying them prices them in the default bucket and reports a complete "
            f"takeoff") if unmapped else None,
    }


def apply_plan(rows: list[dict[str, Any]], accept: list[str], system: str,
               *, edition: str | None = None) -> dict[str, Any]:
    """`set_classification` recipe steps for an explicit list of accepted GUIDs.

    Accepting is a separate, deliberate act — nothing here is applied as a side effect of computing
    a proposal. Anything asked for that cannot be applied is returned in `skipped` **with a reason**
    rather than dropped: a plan that silently covers 40 of the 60 elements somebody ticked is worse
    than one that refuses, because the 20 look done.
    """
    key = _system(system)
    wanted = list(dict.fromkeys(accept or []))          # dedupe, keep the caller's order
    by_guid = {r["guid"]: r for r in rows if r.get("guid")}
    steps: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for guid in wanted:
        row = by_guid.get(guid)
        if row is None:
            skipped.append({"guid": guid, "reason": "not in the proposal set"})
            continue
        if row["basis"] == "declared":
            skipped.append({"guid": guid, "reason": "already declared in the model; applying would "
                                                    "add a second reference for the same system"})
            continue
        if not row.get("code"):
            skipped.append({"guid": guid, "reason": row.get("evidence") or "no code to apply"})
            continue
        params = {"guid": guid, "system": cls.CLASSIFICATIONS[key]["name"],
                  "code": row["code"], "name": row.get("title")}
        if edition:
            params["edition"] = edition
        steps.append({"recipe": "set_classification", "params": params})

    return {
        "system": key, "steps": steps, "count": len(steps),
        "skipped": skipped,
        "note": "apply with POST /projects/{pid}/edit/batch, or one step at a time via POST "
                "/projects/{pid}/edit — the steps are ordinary GUID-stable edit recipes",
    }
