"""FILL-MATRIX (R17 Sprint F) — a category × property **fill-rate pivot** over the property index that
pinpoints *which* pset field is systematically blank, and hands back the blank GUIDs so the gap flows
straight into a bulk edit (the analytics → selection → bulk-write loop).

For each IFC class it takes the union of Pset::Prop keys seen on its elements and reports, per property, how
many carry a non-empty value (`fill_rate`) and the **GUIDs that are blank** — the exact selection a
`query_dsl` scope + edit recipe fills in one pass. `worst_gaps` surfaces the biggest partially-filled fields
(present on some, missing on many) — the highest-leverage fixes.

Pure over the index we already hold; no model load.
"""
from __future__ import annotations

from typing import Any

_MISSING = (None, "", [], {})


def matrix(idx: dict[str, dict] | None, min_count: int = 1, sample: int = 50) -> dict[str, Any]:
    """Per-class property fill rates + the blank GUIDs per property + the worst partially-filled fields."""
    idx = idx or {}
    # pass 1: per class, collect the key universe + each member's filled-key set
    classes: dict[str, dict] = {}
    for guid, e in idx.items():
        if not isinstance(e, dict):
            continue
        cls = e.get("ifc_class") or "Unclassified"
        c = classes.setdefault(cls, {"keys": set(), "members": []})
        filled = set()
        for pset, grp in (e.get("psets") or {}).items():
            if not isinstance(grp, dict):
                continue
            for prop, val in grp.items():
                key = (pset, prop)
                c["keys"].add(key)
                if val not in _MISSING:
                    filled.add(key)
        c["members"].append((guid, filled))

    class_rows = []
    worst: list[dict] = []
    for cls, c in classes.items():
        count = len(c["members"])
        if count < min_count:
            continue
        props = []
        for pset, prop in sorted(c["keys"]):
            key = (pset, prop)
            blank_guids = [g for g, f in c["members"] if key not in f]
            filled_n = count - len(blank_guids)
            rate = round(filled_n / count, 3) if count else 0.0
            row = {"pset": pset, "prop": prop, "filled": filled_n, "blank": len(blank_guids),
                   "fill_rate": rate, "blank_guids": blank_guids[:sample],
                   "selector": f"class={cls} & {pset}.{prop}"}
            props.append(row)
            if 0.0 < rate < 1.0:                         # partially filled = a real, fixable gap
                worst.append({"ifc_class": cls, "pset": pset, "prop": prop, "blank": len(blank_guids),
                              "fill_rate": rate, "blank_guids": blank_guids[:sample]})
        props.sort(key=lambda r: (r["fill_rate"], -r["blank"]))   # most-blank first
        class_rows.append({"ifc_class": cls, "count": count, "property_count": len(props), "properties": props})

    class_rows.sort(key=lambda r: -r["count"])
    worst.sort(key=lambda w: -w["blank"])
    return {
        "element_count": sum(len(c["members"]) for c in classes.values()),
        "class_count": len(class_rows),
        "classes": class_rows,
        "worst_gaps": worst[:25],
        "note": "Category × property fill-rate pivot over the property index. Each property carries the GUIDs "
                "that are blank — feed them + a value to a bulk edit (the analytics → selection → bulk-write "
                "loop). worst_gaps = the biggest partially-filled fields (present on some, missing on many).",
    }
