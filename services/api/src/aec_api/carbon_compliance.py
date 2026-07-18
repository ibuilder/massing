"""CARBON-EC3 — compliance-grade embodied carbon: per-element A1–A3, Buy Clean limits, LEED inventory.

LEED v5 makes an embodied-carbon inventory **mandatory** for projects registering after July 1 2026, and
Buy Clean programs (federal GSA + CA/CO/NY) set procurement GWP limits per material category. This layer
upgrades the keyword estimator in `carbon.py` from "manual quantity lines" to the **model itself**:

  · **per-element A1–A3** — material category matched from each element's name / type / material psets
    (the `carbon.FACTORS` keyword table), quantity read from the element's own Qto sets (volume → m³,
    else area → m²), carbon keyed by **GlobalId** so hotspots click through to the 3D model;
  · **Buy Clean check** — the achieved factor per category vs representative published GWP limits
    (defaults an operator can tighten per jurisdiction); generic default factors that exceed a limit are
    flagged as "needs a product EPD", which is exactly the procurement action Buy Clean forces;
  · **LEED-style A1–A3 inventory** — category rows (quantity · factor · source · kgCO₂e · share),
    intensity per floor area, coverage (how much of the model the inventory actually explains), and the
    hotspot list.

Offline and deterministic: factors are the built-in representative table (each row says so) until a
deployment supplies its own EPD values; a live EPD-database lookup is a config-gated follow-up.
"""
from __future__ import annotations

from typing import Any

from .carbon import FACTORS, _match_factor

# Representative Buy Clean GWP limits per material category (kgCO2e per canonical unit) — public
# program values rounded; a deployment tightens these per its jurisdiction. "limit" is the max allowed.
BUY_CLEAN_LIMITS: dict[str, dict[str, Any]] = {
    "concrete": {"limit": 361.0, "unit": "m3", "program": "GSA ready-mix (typ. mix, representative)"},
    "structural steel": {"limit": 1.22, "unit": "kg", "program": "Buy Clean structural sections (representative)"},
    "steel": {"limit": 1.22, "unit": "kg", "program": "Buy Clean structural sections (representative)"},
    "rebar": {"limit": 0.98, "unit": "kg", "program": "Buy Clean rebar (representative)"},
    "glass": {"limit": 48.0, "unit": "m2", "program": "Buy Clean flat glass (representative)"},
    "insulation": {"limit": 6.0, "unit": "m2", "program": "Buy Clean insulation (representative)"},
    "aluminum": {"limit": 8.6, "unit": "kg", "program": "Buy Clean extrusions (representative)"},
}

_VOL_KEYS = ("NetVolume", "GrossVolume", "Volume")
_AREA_KEYS = ("NetSideArea", "NetArea", "GrossArea", "Area", "GrossSideArea")


def _num(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _element_quantity(el: dict) -> tuple[float, str] | None:
    """Best quantity for carbon: volume (m³) preferred, else area (m²), from the element's Qto sets."""
    qtos = el.get("qtos") or {}
    for keys, unit in ((_VOL_KEYS, "m3"), (_AREA_KEYS, "m2")):
        for props in qtos.values():
            if not isinstance(props, dict):
                continue
            for k in keys:
                q = _num(props.get(k))
                if q is not None:
                    return q, unit
    return None


def _element_material_text(el: dict) -> str:
    """The text a material keyword can match: name + type + any material-ish pset values."""
    bits = [str(el.get("name") or ""), str(el.get("type_name") or "")]
    for props in (el.get("psets") or {}).values():
        if isinstance(props, dict):
            for k, v in props.items():
                if "material" in str(k).lower() and isinstance(v, str):
                    bits.append(v)
    return " ".join(bits)


def element_carbon(idx: dict[str, dict], gfa_m2: float | None = None) -> dict[str, Any]:
    """Per-element A1–A3 over the loaded model index. Honest about coverage: an element only counts
    when BOTH a material keyword matched and its Qto family matches the factor's unit — everything
    else is reported, never guessed."""
    rows: list[dict[str, Any]] = []
    by_cat: dict[str, dict[str, float]] = {}
    by_storey: dict[str, float] = {}
    total = 0.0
    considered = matched = 0
    for guid, el in idx.items():
        q = _element_quantity(el)
        if q is None:
            continue
        considered += 1
        qty, unit = q
        m = _match_factor(_element_material_text(el))
        if not m:
            continue
        kw, factor, canon = m
        if canon != unit:                      # factor family ≠ quantity family → skip, don't guess
            continue
        matched += 1
        kg = round(qty * factor, 1)
        total += kg
        rows.append({"guid": guid, "name": el.get("name"), "ifc_class": el.get("ifc_class"),
                     "storey": el.get("storey"), "category": kw, "quantity": round(qty, 3),
                     "unit": unit, "factor": factor, "kgco2e": kg})
        c = by_cat.setdefault(kw, {"kgco2e": 0.0, "quantity": 0.0})
        c["kgco2e"] = round(c["kgco2e"] + kg, 1)
        c["quantity"] = round(c["quantity"] + qty, 3)
        st = el.get("storey") or "(no storey)"
        by_storey[st] = round(by_storey.get(st, 0.0) + kg, 1)
    rows.sort(key=lambda r: -r["kgco2e"])
    total = round(total, 1)
    out: dict[str, Any] = {
        "total_kgco2e": total, "total_tco2e": round(total / 1000.0, 2),
        "element_count": len(idx), "with_quantity": considered, "carbon_matched": matched,
        "coverage_pct": round(matched / considered * 100, 1) if considered else 0.0,
        "by_category": {k: {**v, "unit": FACTORS[k][1]} for k, v in
                        sorted(by_cat.items(), key=lambda x: -x[1]["kgco2e"])},
        "by_storey": dict(sorted(by_storey.items(), key=lambda x: -x[1])),
        "hotspots": rows[:10],
        "note": ("A1–A3 cradle-to-gate from model quantities × representative default factors — replace "
                 "factors with product EPDs for a compliance submission. Unmatched elements are excluded, "
                 "never guessed (see coverage_pct)."),
    }
    if gfa_m2 and gfa_m2 > 0 and total:
        out["intensity_kgco2e_m2"] = round(total / gfa_m2, 1)
        out["gfa_m2"] = round(gfa_m2, 1)
    return out


def buy_clean_check(result: dict[str, Any]) -> dict[str, Any]:
    """Compare each category's achieved factor against the Buy Clean limit. With default factors the
    'achieved' value IS the default — a fail therefore means 'this category needs a product EPD to
    demonstrate compliance', which is the procurement action the program forces."""
    rows = []
    passes = fails = 0
    for cat, agg in (result.get("by_category") or {}).items():
        lim = BUY_CLEAN_LIMITS.get(cat)
        if not lim:
            continue
        factor = FACTORS[cat][0]
        ok = factor <= lim["limit"]
        passes += ok
        fails += (not ok)
        rows.append({"category": cat, "achieved_factor": factor, "limit": lim["limit"],
                     "unit": lim["unit"], "program": lim["program"], "pass": ok,
                     "headroom_pct": round((lim["limit"] - factor) / lim["limit"] * 100, 1),
                     "kgco2e": agg.get("kgco2e"),
                     "action": None if ok else "obtain a product EPD below the limit (default factor exceeds it)"})
    rows.sort(key=lambda r: (r["pass"], -(r["kgco2e"] or 0)))
    return {"rows": rows, "categories_checked": len(rows), "passing": passes, "failing": fails,
            "note": "Representative program limits — tighten per your jurisdiction. Achieved = the "
                    "factor in use (default until a product EPD replaces it)."}


def leed_inventory(result: dict[str, Any], project_name: str | None = None) -> dict[str, Any]:
    """The LEED-v5-style A1–A3 inventory: category rows with quantity, factor, source and share —
    the mandatory reporting artifact, generated straight off the model."""
    total = result.get("total_kgco2e") or 0.0
    items = []
    for cat, agg in (result.get("by_category") or {}).items():
        items.append({
            "category": cat, "quantity": agg.get("quantity"), "unit": agg.get("unit"),
            "factor_kgco2e_per_unit": FACTORS[cat][0],
            "factor_source": "built-in representative average — replace with product EPD",
            "kgco2e": agg.get("kgco2e"),
            "share_pct": round((agg.get("kgco2e") or 0.0) / total * 100, 1) if total else 0.0,
        })
    return {
        "scope": "A1–A3 (cradle-to-gate), structure + enclosure as modeled",
        "project": project_name,
        "total_kgco2e": total, "total_tco2e": result.get("total_tco2e"),
        "intensity_kgco2e_m2": result.get("intensity_kgco2e_m2"),
        "coverage_pct": result.get("coverage_pct"),
        "items": items, "hotspots": result.get("hotspots"),
        "disclosure": ("Inventory computed from model quantities (per-element, GlobalId-keyed) with "
                       "representative default factors; not a verified EPD-backed LCA until factors are "
                       "replaced with product EPDs. Coverage below 100% means unmatched elements are "
                       "excluded from the total."),
    }
