"""openBIM quality scoring — IDS rule-compliance %, LOIN per element, IFC export health, bSDD align.

buildingSMART's measurable openBIM signals: an IDS (Information Delivery Specification) states which
properties each element must carry, and a model is *scored* against it (pass/fail per rule → %); the
Level of Information Need (LOIN, the ISO 19650 successor to "LOD") measures geometric + alphanumeric +
documentation completeness per element; export health checks the IFC is well-formed (typed, not
proxy-dumped, georeferenced); bSDD alignment is the share of elements whose type/classification is
carried rather than left blank. Pure functions over the properties index (the {guid: element} map
properties.py builds) so they score any loaded model — and are testable without one."""
from __future__ import annotations

from typing import Any

# LOIN facets scored per element (geometry is implicit — the element is in the model).
LOIN_FACETS = ("geometry", "type", "classification", "properties", "quantities")


def _has(e: dict, pset: str, prop: str) -> bool:
    """Property present on an element, looked up in psets then qtos (pset::prop, case-sensitive)."""
    for holder in ("psets", "qtos"):
        d = (e.get(holder) or {}).get(pset)
        if isinstance(d, dict) and d.get(prop) not in (None, ""):
            return True
    return False


def _facets(e: dict) -> dict[str, bool]:
    return {
        "geometry": True,                                       # in the model → has geometry
        "type": bool(e.get("type_name")),
        "classification": bool(e.get("type_name") or e.get("classification")),
        "properties": isinstance(e.get("psets"), dict) and len(e["psets"]) > 0,
        "quantities": isinstance(e.get("qtos"), dict) and len(e["qtos"]) > 0,
    }


def loin(idx: dict[str, dict]) -> dict[str, Any]:
    """Level-of-Information-Need scoring: each element earns a 0–5 facet score; report the average,
    the % reaching a 'coordinated' bar (>=4 facets), and the distribution by score."""
    total = len(idx)
    dist = dict.fromkeys(range(len(LOIN_FACETS) + 1), 0)
    facet_present = dict.fromkeys(LOIN_FACETS, 0)
    coordinated = 0
    score_sum = 0
    for e in idx.values():
        fac = _facets(e)
        s = sum(1 for f in LOIN_FACETS if fac[f])
        dist[s] += 1
        score_sum += s
        if s >= 4:
            coordinated += 1
        for f in LOIN_FACETS:
            if fac[f]:
                facet_present[f] += 1
    return {
        "total": total, "max_score": len(LOIN_FACETS),
        "avg_score": round(score_sum / total, 2) if total else 0.0,
        "coordinated_pct": round(100 * coordinated / total, 1) if total else None,
        "distribution": dist,
        "facet_coverage_pct": {f: round(100 * facet_present[f] / total, 1) if total else None
                               for f in LOIN_FACETS},
        "note": "LOIN facets: geometry, type, classification, properties, quantities. 'Coordinated' "
                "= at least 4 of 5 present.",
    }


def ids_compliance(idx: dict[str, dict], specs: list[dict]) -> dict[str, Any]:
    """Score the model against an IDS: for each spec (an IFC class + required pset::property rules),
    every applicable element must carry every required property. Returns per-spec applicable/passing
    and an overall compliance %. `specs`: [{name, ifc_class, requirements:[{pset, property}]}]."""
    results = []
    tot_checks = tot_pass = 0
    for spec in specs:
        klass = spec.get("ifc_class")
        reqs = spec.get("requirements") or []
        ku = (klass or "").upper()                              # index uses IfcWall, IDS uses IFCWALL
        applicable = [e for e in idx.values() if (e.get("ifc_class") or "").upper() == ku]
        passing = 0
        for e in applicable:
            if all(_has(e, r.get("pset", ""), r.get("property", "")) for r in reqs):
                passing += 1
        n = len(applicable)
        tot_checks += n
        tot_pass += passing
        results.append({"name": spec.get("name") or klass, "ifc_class": klass,
                        "applicable": n, "passing": passing,
                        "pct": round(100 * passing / n, 1) if n else None})
    return {
        "specs": results, "applicable_total": tot_checks, "passing_total": tot_pass,
        "compliance_pct": round(100 * tot_pass / tot_checks, 1) if tot_checks else None,
        "note": "Compliance = applicable elements carrying every required property in their IDS spec.",
    }


def export_health(idx: dict[str, dict]) -> dict[str, Any]:
    """IFC export-health signals: proxy/untyped share (IfcBuildingElementProxy or missing class),
    typing coverage, and property/quantity coverage — a pass/warn/fail per check."""
    total = len(idx)
    proxy = sum(1 for e in idx.values()
                if (e.get("ifc_class") or "") in ("", "IfcBuildingElementProxy"))
    typed = sum(1 for e in idx.values() if e.get("type_name"))
    with_pset = sum(1 for e in idx.values() if isinstance(e.get("psets"), dict) and e["psets"])

    def _grade(pct: float | None, good: float, warn: float) -> str:
        if pct is None:
            return "n/a"
        return "pass" if pct >= good else ("warn" if pct >= warn else "fail")

    proxy_pct = round(100 * proxy / total, 1) if total else 0.0
    typed_pct = round(100 * typed / total, 1) if total else None
    pset_pct = round(100 * with_pset / total, 1) if total else None
    checks = [
        {"key": "non_proxy", "label": "Elements properly typed (not proxy)",
         "pct": round(100 - proxy_pct, 1), "grade": _grade(round(100 - proxy_pct, 1), 95, 80)},
        {"key": "type_coverage", "label": "Elements carry a Type", "pct": typed_pct,
         "grade": _grade(typed_pct, 90, 60)},
        {"key": "property_coverage", "label": "Elements carry property sets", "pct": pset_pct,
         "grade": _grade(pset_pct, 90, 60)},
    ]
    worst = ("fail" if any(c["grade"] == "fail" for c in checks)
             else "warn" if any(c["grade"] == "warn" for c in checks) else "pass")
    return {"total": total, "proxy_count": proxy, "checks": checks, "overall": worst,
            "note": "Export health flags proxy/untyped dumps and thin property coverage — the usual "
                    "authoring-tool export defects that break QTO, carbon and IDS downstream."}


def bsdd_alignment(idx: dict[str, dict]) -> dict[str, Any]:
    """bSDD alignment: two tiers, honestly separated.
      * `classified` — elements carrying any type/classification (the field a bSDD ref populates);
      * `bsdd_linked` — the subset whose classification is a real **buildingSMART Data Dictionary
        URI** (identifier.buildingsmart.org/...), i.e. genuine linked-data alignment, not a bare code.
    Also lists the distinct bSDD dictionaries actually referenced, so a reviewer sees *which*
    dictionaries the model aligns to (Uniclass, IFC, an EIR-mandated one, …)."""
    from . import bsdd
    total = len(idx)
    classified = bsdd_linked = 0
    dictionaries: dict[str, int] = {}
    for e in idx.values():
        cls = e.get("classification")
        if e.get("type_name") or cls:
            classified += 1
        if bsdd.is_bsdd_uri(cls):
            bsdd_linked += 1
            duri = bsdd.parse_uri(cls).get("dictionary_uri") or "?"
            dictionaries[duri] = dictionaries.get(duri, 0) + 1
    return {"total": total, "classified": classified, "bsdd_linked": bsdd_linked,
            "alignment_pct": round(100 * classified / total, 1) if total else None,
            "bsdd_linked_pct": round(100 * bsdd_linked / total, 1) if total else None,
            "dictionaries": [{"dictionary_uri": k, "count": v}
                             for k, v in sorted(dictionaries.items(), key=lambda kv: -kv[1])],
            "note": "`classified` = has any type/classification; `bsdd_linked` = classification is a "
                    "buildingSMART Data Dictionary URI (true linked-data alignment)."}


def summary(idx: dict[str, dict], specs: list[dict] | None = None) -> dict[str, Any]:
    """Everything openBIM-quality in one call for the standards panel + the KPI scorecard (C3)."""
    out = {"loin": loin(idx), "export_health": export_health(idx), "bsdd": bsdd_alignment(idx)}
    if specs:
        out["ids"] = ids_compliance(idx, specs)
    return out
