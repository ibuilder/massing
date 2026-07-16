"""A4 — scene digest: a compact, LLM-friendly summary of what's in the model, so an AI authoring/QA step
can ground itself (and a human gets a one-glance overview). Composes the shipped summaries — element counts
by class, storeys, spaces, MEP systems + disciplines, phasing, LOD, and model hygiene — into a small dict
plus a one-paragraph `prose` string suitable for an LLM system prompt.
"""
from __future__ import annotations

from typing import Any


def digest(model) -> dict[str, Any]:
    """Summarise the model into a compact dict + `prose`. Cheap and read-only; degrades gracefully if any
    sub-summary is unavailable (e.g. an IFC2x3 model without distribution systems)."""
    by_class: dict[str, int] = {}
    for el in model.by_type("IfcElement"):
        by_class[el.is_a()] = by_class.get(el.is_a(), 0) + 1
    total = sum(by_class.values())
    storeys = [s.Name or "?" for s in sorted(model.by_type("IfcBuildingStorey"),
                                             key=lambda s: float(getattr(s, "Elevation", 0) or 0))]
    spaces = len(model.by_type("IfcSpace"))

    try:
        from aec_data import mep
        mep_s = mep.mep_summary(model)
    except Exception:                                  # noqa: BLE001
        mep_s = {"total_systems": 0, "by_discipline": {}, "has_fire_protection": False}
    try:
        from aec_data.edit import phase_summary
        phase_s = phase_summary(model)["counts"]
    except Exception:                                  # noqa: BLE001
        phase_s = {}
    try:
        from aec_data import representations as reps
        lod_s = reps.lod_summary(model)["counts"]
    except Exception:                                  # noqa: BLE001
        lod_s = {}
    try:
        from . import model_qa as mq
        qa = mq.model_qa(model)
        hygiene = {"issues": qa.get("total_issues"), "clean": qa.get("clean")}
    except Exception:                                  # noqa: BLE001
        hygiene = {"issues": None, "clean": None}

    top = sorted(by_class.items(), key=lambda kv: -kv[1])[:6]
    top_str = ", ".join(f"{n} {c[3:].lower()}" for c, n in top) or "no elements"
    disc = ", ".join(f"{d} ({v.get('systems', 0)})" for d, v in (mep_s.get("by_discipline") or {}).items())
    phased = {k: v for k, v in (phase_s or {}).items() if v and k != "UNSET"}
    prose = (
        f"{total} elements ({top_str}) across {len(storeys)} storey(s)"
        + (f", {spaces} space(s)" if spaces else "")
        + (f". MEP: {mep_s.get('total_systems', 0)} system(s) — {disc}" if disc else "")
        + (f". Phasing: {phased}" if phased else "")
        + (f". {hygiene['issues']} model-hygiene issue(s)" if hygiene.get("issues") else
           (". Model is hygiene-clean" if hygiene.get("clean") else ""))
        + "."
    )
    return {
        "totals": {"elements": total, "storeys": len(storeys), "spaces": spaces},
        "by_class": dict(sorted(by_class.items(), key=lambda kv: -kv[1])),
        "storeys": storeys,
        "mep": {"systems": mep_s.get("total_systems", 0), "by_discipline": mep_s.get("by_discipline", {}),
                "has_fire_protection": mep_s.get("has_fire_protection", False)},
        "phasing": phase_s, "lod": lod_s, "hygiene": hygiene,
        "prose": prose,
    }
