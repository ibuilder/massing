"""WALL-ASSEMBLY thermal (R17 Sprint F) — **R/U-values computed from the layers themselves**.

The model already carries genuine layered assemblies (``IfcMaterialLayerSet`` via `material_layers.py` /
`assign_material_set`), and the envelope code-check demands a U-value — but nothing bridged the two. This
does: each layer's R = thickness ÷ conductivity (a standard k-value catalog keyed by material category,
overridable per material), summed with the standard interior/exterior surface films → the assembly
**U-value**, per layer and per assembly, plus a **per-layer material takeoff** (thickness × element area)
when the model carries side-area quantities.

Deterministic; the catalog values are representative design k-values (ASHRAE-style), clearly overridable —
an honest analytical number for the COMcheck-style pre-check, not a certified hot-box test.
"""
from __future__ import annotations

from typing import Any

# representative design conductivities k (W/m·K) by material category (material_layers.py categories)
_K_BY_CATEGORY = {
    "masonry": 0.77, "concrete": 1.80, "insulation": 0.030, "gypsum": 0.16, "air": None,  # air = fixed R
    "finish": 0.17, "screed": 1.40, "roofing": 0.17, "membrane": 0.17, "wood": 0.13,
    "steel": 45.0, "glass": 1.0, "stone": 2.3,
}
_R_AIR_CAVITY = 0.17     # unventilated vertical air cavity (m²K/W)
_R_FILMS = 0.17          # interior (0.13) + exterior (0.04) surface films


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def layer_r(thickness_m: float, category: str | None, k: float | None = None) -> float:
    """One layer's R (m²K/W): thickness ÷ k, an air cavity at its fixed R, unknown category conservatively 0."""
    if k:
        return thickness_m / k
    cat_k = _K_BY_CATEGORY.get((category or "").strip().lower(), 0.0)
    if cat_k is None:                          # air cavity: R is fixed, not thickness-proportional
        return _R_AIR_CAVITY
    return thickness_m / cat_k if cat_k else 0.0


def analyze(layers: list[dict]) -> dict[str, Any]:
    """R/U for one assembly. layers = [{name?, material?, category, thickness_m, k?}] in order."""
    rows = []
    r_total = _R_FILMS
    thickness = 0.0
    for ly in layers or []:
        t = _num(ly.get("thickness_m") or ly.get("thickness"))
        r = layer_r(t, ly.get("category"), _num(ly.get("k")) or None)
        rows.append({"name": ly.get("name") or ly.get("material") or ly.get("category") or "layer",
                     "category": ly.get("category"), "thickness_m": round(t, 4), "r_value": round(r, 3)})
        r_total += r
        thickness += t
    u = round(1.0 / r_total, 3) if r_total > 0 else None
    return {"layers": rows, "thickness_m": round(thickness, 3),
            "r_value": round(r_total, 3), "r_value_imperial": round(r_total * 5.678, 1),
            "u_value": u, "surface_films_r": _R_FILMS,
            "note": "R = Σ(thickness ÷ k) per layer + standard surface films (0.17); U = 1/R. Design "
                    "k-values by category (air cavity at its fixed R) — an analytical pre-check number, "
                    "overridable per layer with an explicit k."}


def _side_area(el, ue) -> float:
    """The element's face area from its base quantities (wall NetSideArea / slab-roof NetArea)."""
    try:
        qtos = ue.get_psets(el, qtos_only=True) or {}
    except Exception:                          # noqa: BLE001
        return 0.0
    for grp in qtos.values():
        if not isinstance(grp, dict):
            continue
        for key in ("NetSideArea", "GrossSideArea", "NetArea", "GrossArea"):
            v = _num(grp.get(key))
            if v > 0:
                return v
    return 0.0


def from_model(model) -> dict[str, Any]:
    """Every distinct IfcMaterialLayerSet in the model → its computed R/U + the elements using it + a
    per-layer material takeoff (layer thickness × Σ element face area, when quantities exist)."""
    try:
        import ifcopenshell.util.element as ue
    except Exception:                          # noqa: BLE001
        ue = None

    # layer-set → elements using it (via IfcMaterialLayerSetUsage or direct)
    sets: dict[int, dict] = {}
    for el in list(model.by_type("IfcWall")) + list(model.by_type("IfcSlab")) + list(model.by_type("IfcRoof")):
        try:
            mat = ue.get_material(el) if ue else None
        except Exception:                      # noqa: BLE001
            mat = None
        if mat is not None and mat.is_a("IfcMaterialLayerSetUsage"):
            mat = mat.ForLayerSet
        if mat is None or not mat.is_a("IfcMaterialLayerSet"):
            continue
        s = sets.setdefault(mat.id(), {"set": mat, "guids": [], "area": 0.0})
        s["guids"].append(el.GlobalId)
        s["area"] += _side_area(el, ue) if ue else 0.0

    assemblies = []
    for s in sets.values():
        ls = s["set"]
        layers = []
        for ly in (ls.MaterialLayers or []):
            m = getattr(ly, "Material", None)
            layers.append({"name": getattr(ly, "Name", None),
                           "material": getattr(m, "Name", None) if m is not None else None,
                           "category": getattr(m, "Category", None) if m is not None else None,
                           "thickness_m": _num(getattr(ly, "LayerThickness", 0))})
        th = analyze(layers)
        area = round(s["area"], 1)
        takeoff = [{"material": ly["material"] or ly["name"], "thickness_m": ly["thickness_m"],
                    "volume_m3": round(ly["thickness_m"] * area, 2) if area else None}
                   for ly in layers]
        assemblies.append({"name": getattr(ls, "LayerSetName", None) or getattr(ls, "Name", None),
                           "element_count": len(s["guids"]), "guids": s["guids"][:50],
                           "face_area_m2": area or None, **th, "takeoff": takeoff})

    assemblies.sort(key=lambda a: -a["element_count"])
    return {"assembly_count": len(assemblies), "assemblies": assemblies,
            "note": "Each distinct IfcMaterialLayerSet with its computed R/U (from the layers), the elements "
                    "using it, and a per-layer material takeoff (thickness × face area from the base "
                    "quantities). The bridge from the authored assemblies to the envelope code-check."}
