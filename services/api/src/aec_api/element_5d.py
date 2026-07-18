"""5D-BIND — element↔cost binding: every GlobalId carries its live cost (and carbon) row.

The 5D promise is that cost hangs off the *model*, not a spreadsheet: edit a wall, the price moves.
This binds each element to a priced row computed straight from the **live property index** — element
quantity (from its own Qto sets, per the rate's basis) × the class rate (`estimate.DEFAULT_RATES`,
the same representative table the conceptual estimate and the public cost-vintage use) — so a
GUID-stable edit → republish → reindex **reprices automatically**; nothing to resync.

Carbon rides the same binding: where the element's material matches (`carbon_compliance`), the row also
carries kgCO₂e — one GUID-keyed table serving cost heatmaps, carbon hotspots, and (later) generative
option scoring against cost + carbon + code in one pass.
"""
from __future__ import annotations

from typing import Any

from .carbon_compliance import _element_material_text, _element_quantity, _num
from .estimate import DEFAULT_RATES

_LEN_KEYS = ("Length", "NetLength", "GrossLength")


def _quantity_for_basis(el: dict, basis: str) -> float | None:
    """Element quantity in the rate's basis: volume/area via the carbon helpers' Qto scan, length via
    length keys, count = 1. None when the element carries no usable quantity for that basis."""
    if basis == "count":
        return 1.0
    if basis == "length":
        for props in (el.get("qtos") or {}).values():
            if isinstance(props, dict):
                for k in _LEN_KEYS:
                    q = _num(props.get(k))
                    if q is not None:
                        return q
        return None
    q = _element_quantity(el)                          # (qty, "m3"|"m2") — volume preferred
    if q is None:
        return None
    qty, unit = q
    if basis == "volume" and unit == "m3":
        return qty
    if basis == "area" and unit == "m2":
        return qty
    return None                                        # basis/quantity family mismatch → don't guess


def element_costs(idx: dict[str, dict]) -> dict[str, Any]:
    """The GUID-keyed 5D table over the live index. Honest coverage: an element prices only when its
    class has a rate AND its Qto family matches the rate's basis; carbon only when its material matches."""
    from .carbon import _match_factor

    rows: list[dict[str, Any]] = []
    by_class: dict[str, dict[str, float]] = {}
    by_storey: dict[str, float] = {}
    total_cost = carbon_total = 0.0
    priced = carbon_matched = 0
    for guid, el in idx.items():
        cls = el.get("ifc_class") or ""
        spec = DEFAULT_RATES.get(cls)
        if not spec:
            continue
        basis, rate = spec
        qty = _quantity_for_basis(el, basis)
        if qty is None:
            continue
        cost = round(qty * rate, 2)
        priced += 1
        total_cost += cost
        row: dict[str, Any] = {"guid": guid, "name": el.get("name"), "ifc_class": cls,
                               "storey": el.get("storey"), "basis": basis,
                               "quantity": round(qty, 3), "rate": rate, "cost": cost,
                               "carbon_kgco2e": None, "carbon_category": None}
        m = _match_factor(_element_material_text(el))
        if m:
            kw, factor, canon = m
            cq = _element_quantity(el)
            if cq and cq[1] == canon:
                kg = round(cq[0] * factor, 1)
                row["carbon_kgco2e"] = kg
                row["carbon_category"] = kw
                carbon_total += kg
                carbon_matched += 1
        rows.append(row)
        c = by_class.setdefault(cls, {"cost": 0.0, "count": 0})
        c["cost"] = round(c["cost"] + cost, 2)
        c["count"] += 1
        st = el.get("storey") or "(no storey)"
        by_storey[st] = round(by_storey.get(st, 0.0) + cost, 2)
    rows.sort(key=lambda r: -r["cost"])
    return {
        "element_count": len(idx), "priced": priced,
        "total_cost": round(total_cost, 2),
        "carbon_matched": carbon_matched, "total_carbon_kgco2e": round(carbon_total, 1),
        "by_class": dict(sorted(by_class.items(), key=lambda x: -x[1]["cost"])),
        "by_storey": dict(sorted(by_storey.items(), key=lambda x: -x[1])),
        "top_cost": rows[:10],
        "note": ("Live binding: quantity × class rate off the current property index — a GUID-stable "
                 "edit + republish reprices automatically. Rates are the representative table "
                 "(estimate.DEFAULT_RATES / the public cost vintage); pin a cost vintage or supply EPDs "
                 "to firm up either axis. Elements without a rate or a matching Qto family are excluded, "
                 "never guessed."),
    }
