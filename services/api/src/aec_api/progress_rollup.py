"""PROGRESS-ROLLUP (R17 Sprint E) — **% complete** rolled up from as-built element presence.

Given the design model's expected element set (each keyed by GlobalId, with its IFC class / discipline /
level, and optionally a cost) and the set of GUIDs verified **installed** (from field verification, a scan
match, or the verified-progress log), this computes percent-complete **by IFC class, by trade/discipline, by
level, and overall — by count *and* by value**. Count and value diverge exactly where it matters (lots of
cheap elements up vs. a few expensive ones outstanding), so both are reported.

Pure over the elements + installed GUIDs supplied; the installed set comes from whatever presence source the
caller has. Feeds the GC portal + earned value.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _discipline(el: dict) -> str:
    d = el.get("discipline") or el.get("trade")
    if d:
        return str(d)
    try:
        from . import classification
        return classification.discipline_name(classification.discipline_of_ifc_class(el.get("ifc_class") or "")) \
            or "General"
    except Exception:                                    # noqa: BLE001
        return "General"


def _bucket(rows: dict, key: str, installed: bool, value: float) -> None:
    b = rows.setdefault(key, {"expected": 0, "installed": 0, "value_total": 0.0, "value_installed": 0.0})
    b["expected"] += 1
    b["value_total"] += value
    if installed:
        b["installed"] += 1
        b["value_installed"] += value


def _finish(rows: dict, label: str) -> list[dict]:
    out = []
    for k, b in rows.items():
        out.append({
            label: k, "expected": b["expected"], "installed": b["installed"],
            "pct_complete": round(b["installed"] / b["expected"], 3) if b["expected"] else 0.0,
            "value_total": round(b["value_total"], 2),
            "pct_complete_value": round(b["value_installed"] / b["value_total"], 3) if b["value_total"] else None,
        })
    return sorted(out, key=lambda r: -r["expected"])


def rollup(elements: list[dict], installed_guids: list | set) -> dict[str, Any]:
    """Percent-complete by class / discipline / level / overall, by count and by value."""
    installed = {str(g) for g in (installed_guids or [])}
    by_class: dict[str, dict] = {}
    by_disc: dict[str, dict] = {}
    by_level: dict[str, dict] = {}
    n = done = 0
    v_total = v_done = 0.0
    for el in elements or []:
        if not isinstance(el, dict):
            continue
        guid = str(el.get("guid") or el.get("GlobalId") or "")
        is_in = guid in installed
        val = _num(el.get("value") or el.get("cost"))
        _bucket(by_class, el.get("ifc_class") or "Unclassified", is_in, val)
        _bucket(by_disc, _discipline(el), is_in, val)
        _bucket(by_level, str(el.get("storey") or el.get("level") or "—"), is_in, val)
        n += 1
        done += is_in
        v_total += val
        if is_in:
            v_done += val
    return {
        "element_count": n, "installed_count": done,
        "pct_complete": round(done / n, 3) if n else 0.0,
        "value_total": round(v_total, 2), "value_installed": round(v_done, 2),
        "pct_complete_value": round(v_done / v_total, 3) if v_total else None,
        "by_class": _finish(by_class, "ifc_class"),
        "by_discipline": _finish(by_disc, "discipline"),
        "by_level": _finish(by_level, "level"),
        "note": "Percent-complete from as-built element presence (installed GUIDs vs the design set), rolled "
                "up by IFC class · discipline · level, by count AND by value — the two diverge where cheap "
                "elements are up but expensive ones are outstanding. Feeds the GC portal + earned value.",
    }
