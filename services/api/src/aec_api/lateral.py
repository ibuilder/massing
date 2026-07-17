"""STRUCT-LATERAL · ASCE 7 lateral load analysis — wind + seismic base shear distributed to story forces.

The lateral complement to `loads.py` (gravity takedown) and `struct_solve.py` (member statics). It runs the
two hand analyses an engineer does before a lateral system is sized:

- **Seismic — Equivalent Lateral Force (ASCE 7-22 §12.8):** `Cs = SDS/(R/Ie)` (with the §12.8-3/4 upper
  bound and the §12.8-5 floor), base shear `V = Cs·W`, vertical distribution `Fx = Cvx·V` with
  `Cvx = wx·hx^k / Σ wi·hi^k` (k from the approximate period `Ta = Ct·hn^x`), story shears + overturning.
- **Wind — simplified directional MWFRS (ASCE 7-22 Ch. 26–27):** velocity pressure `qz = 0.00256·Kz·Kzt·
  Kd·Ke·V²` (Kz by the exposure power law), a net windward+leeward pressure `p = q·G·(Cpw − Cpl)`, story
  forces from `p × (width × tributary height)`, base shear + overturning.

Pure arithmetic — every coefficient is a fact from ASCE 7. Story weights/heights read off the model (weight
estimated from floor area × a dead-load psf). **PRELIMINARY — not a substitute for a licensed structural
engineer;** no torsion, no dynamic/modal analysis, no drift check, simplified wind only.

Units: forces kips, heights ft, weights kips, pressures psf, wind speed mph.
"""
from __future__ import annotations

import math
from typing import Any

# ASCE 7 exposure parameters for the Kz power law: (alpha, zg ft). C is the open-terrain default.
_EXPOSURE = {"B": (7.0, 1200.0), "C": (9.5, 900.0), "D": (11.5, 700.0)}
# approximate-period coefficients Ct, x by structural system (ASCE 7 §12.8.2.1 Table 12.8-2)
_CT_X = {
    "steel_moment": (0.028, 0.8), "concrete_moment": (0.016, 0.9),
    "steel_braced": (0.03, 0.75), "other": (0.02, 0.75),
}


def approx_period(hn_ft: float, system: str = "other") -> float:
    """ASCE 7 §12.8.2.1 approximate fundamental period Ta = Ct·hn^x."""
    ct, x = _CT_X.get(system, _CT_X["other"])
    return ct * (max(hn_ft, 1.0) ** x)


def _k_exponent(period_s: float) -> float:
    """ASCE 7 §12.8.3 distribution exponent k: 1 for T≤0.5s, 2 for T≥2.5s, linear between."""
    if period_s <= 0.5:
        return 1.0
    if period_s >= 2.5:
        return 2.0
    return 1.0 + (period_s - 0.5) / 2.0


def seismic_elf(weights_kip: list[float], heights_ft: list[float], *, sds: float, sd1: float,
                r: float = 8.0, ie: float = 1.0, tl: float = 8.0, system: str = "other",
                period_s: float | None = None) -> dict[str, Any]:
    """ASCE 7-22 §12.8 Equivalent Lateral Force. `weights_kip`/`heights_ft` are per story (ground→up).
    Returns Cs, period, base shear, and per-story force / shear / overturning."""
    n = min(len(weights_kip), len(heights_ft))
    weights = [float(weights_kip[i]) for i in range(n)]
    heights = [float(heights_ft[i]) for i in range(n)]
    w_total = sum(weights)
    hn = max(heights) if heights else 0.0
    t = float(period_s) if period_s else approx_period(hn, system)

    rie = r / ie
    cs = sds / rie
    cs_max = (sd1 / (t * rie)) if t <= tl else (sd1 * tl / (t * t * rie))
    cs = min(cs, cs_max)
    cs = max(cs, max(0.044 * sds * ie, 0.01))     # §12.8-5 floor
    v_base = cs * w_total

    k = _k_exponent(t)
    denom = sum(w * (h ** k) for w, h in zip(weights, heights)) or 1.0
    stories = []
    for i in range(n):
        cvx = weights[i] * (heights[i] ** k) / denom
        fx = cvx * v_base
        stories.append({"level": i + 1, "height_ft": round(heights[i], 2),
                        "weight_kip": round(weights[i], 1), "cvx": round(cvx, 4),
                        "force_kip": round(fx, 2)})
    # story shear = sum of forces at & above; overturning at base = Σ Fx·hx
    for i in range(n):
        stories[i]["shear_kip"] = round(sum(s["force_kip"] for s in stories[i:]), 2)
    overturning = round(sum(s["force_kip"] * s["height_ft"] for s in stories), 1)
    return {
        "method": "ASCE 7-22 §12.8 Equivalent Lateral Force",
        "inputs": {"SDS": sds, "SD1": sd1, "R": r, "Ie": ie, "TL": tl, "system": system},
        "period_s": round(t, 3), "k": round(k, 3), "Cs": round(cs, 4),
        "seismic_weight_kip": round(w_total, 1), "base_shear_kip": round(v_base, 2),
        "overturning_kipft": overturning, "stories": stories,
    }


def _kz(height_ft: float, exposure: str = "C") -> float:
    """ASCE 7 velocity-pressure exposure coefficient Kz via the power law (min z = 15 ft)."""
    alpha, zg = _EXPOSURE.get(exposure.upper(), _EXPOSURE["C"])
    z = max(height_ft, 15.0)
    return 2.01 * (z / zg) ** (2.0 / alpha)


def wind_mwfrs(heights_ft: list[float], *, speed_mph: float = 115.0, width_ft: float = 100.0,
               exposure: str = "C", kd: float = 0.85, kzt: float = 1.0, ke: float = 1.0,
               g: float = 0.85, cp_windward: float = 0.8, cp_leeward: float = 0.5) -> dict[str, Any]:
    """Simplified directional MWFRS wind (ASCE 7 Ch. 26–27). Story forces from the net windward+leeward
    pressure over each story's tributary strip (`width_ft` × tributary height). Returns base shear +
    per-story force/shear + overturning."""
    n = len(heights_ft)
    heights = [float(h) for h in heights_ft]
    hn = max(heights) if heights else 0.0
    qh = 0.00256 * _kz(hn, exposure) * kzt * kd * ke * speed_mph * speed_mph   # leeward uses q at roof ht
    p_leeward = qh * g * cp_leeward
    stories = []
    for i in range(n):
        lo = heights[i - 1] if i > 0 else 0.0
        hi = heights[i]
        trib = (hi - lo) / 2.0 + ((heights[i + 1] - hi) / 2.0 if i + 1 < n else 0.0)
        qz = 0.00256 * _kz(hi, exposure) * kzt * kd * ke * speed_mph * speed_mph
        p_windward = qz * g * cp_windward
        p_net = p_windward + p_leeward                          # psf (leeward acts suction, same direction)
        force = p_net * width_ft * trib / 1000.0                # kips
        stories.append({"level": i + 1, "height_ft": round(hi, 2), "trib_ft": round(trib, 2),
                        "pressure_psf": round(p_net, 2), "force_kip": round(force, 2)})
    for i in range(n):
        stories[i]["shear_kip"] = round(sum(s["force_kip"] for s in stories[i:]), 2)
    v_base = round(sum(s["force_kip"] for s in stories), 2)
    overturning = round(sum(s["force_kip"] * s["height_ft"] for s in stories), 1)
    return {
        "method": "ASCE 7-22 simplified directional MWFRS",
        "inputs": {"speed_mph": speed_mph, "exposure": exposure.upper(), "width_ft": width_ft,
                   "Kd": kd, "G": g, "Cp_windward": cp_windward, "Cp_leeward": cp_leeward},
        "qh_psf": round(qh, 2), "base_shear_kip": v_base, "overturning_kipft": overturning,
        "stories": stories,
    }


_DISCLAIMER = ("PRELIMINARY lateral analysis for early coordination — ASCE 7 Equivalent Lateral Force "
               "(seismic) + simplified directional MWFRS (wind), distributed to story forces. NOT a full "
               "lateral design: no torsion / accidental eccentricity, no modal/response-spectrum analysis, "
               "no drift or P-delta check, no soil-structure interaction. All lateral system design must be "
               "performed and stamped by a licensed professional engineer.")


def lateral_from_model(model, *, dead_psf: float = 90.0, area_sf: float | None = None,
                       seismic: dict | None = None, wind: dict | None = None) -> dict[str, Any]:
    """Read story elevations off the model and run both analyses. Seismic weight per story is estimated as
    floor area × `dead_psf` (a superimposed-dead + structure allowance); pass `area_sf` or it is taken from
    the plan bounding box. `seismic`/`wind` override the code parameters."""
    sts = []
    for st in model.by_type("IfcBuildingStorey"):
        elev = getattr(st, "Elevation", None)
        sts.append({"name": getattr(st, "Name", None) or "Level", "elev_m": float(elev) if elev is not None else None})
    # keep stories with a real elevation, ordered ground→up; drop a basement/foundation datum below 0 if it is the only <=0
    sts = [s for s in sts if s["elev_m"] is not None]
    sts.sort(key=lambda s: s["elev_m"])
    sts = [s for s in sts if s["elev_m"] >= 0]            # above-grade stories carry the lateral mass
    if area_sf is None:
        area_sf = _plan_area_sf(model)
    heights_ft = [s["elev_m"] * 3.28084 for s in sts]
    # a story with 0 ft height (grade) carries weight but no ELF arm — keep it; ELF handles h=0 (Fx=0)
    story_weight = (float(area_sf) * dead_psf) / 1000.0 if area_sf else 0.0   # kips per story
    weights = [story_weight for _ in sts]

    seismic = seismic or {}
    wind = wind or {}
    width_ft = wind.get("width_ft") or (math.sqrt(float(area_sf)) if area_sf else 100.0)
    result = {
        "story_count": len(sts), "area_sf": round(float(area_sf), 1) if area_sf else None,
        "dead_psf": dead_psf, "story_weight_kip": round(story_weight, 1),
        "seismic": seismic_elf(weights, heights_ft,
                               sds=float(seismic.get("sds", 1.0)), sd1=float(seismic.get("sd1", 0.6)),
                               r=float(seismic.get("r", 8.0)), ie=float(seismic.get("ie", 1.0)),
                               tl=float(seismic.get("tl", 8.0)), system=str(seismic.get("system", "other"))),
        "wind": wind_mwfrs(heights_ft, speed_mph=float(wind.get("speed_mph", 115.0)),
                           width_ft=float(width_ft), exposure=str(wind.get("exposure", "C"))),
        "disclaimer": _DISCLAIMER,
    }
    sv = result["seismic"]["base_shear_kip"]
    wv = result["wind"]["base_shear_kip"]
    result["governing"] = {"system": "seismic" if sv >= wv else "wind",
                           "base_shear_kip": max(sv, wv)}
    return result


def _plan_area_sf(model) -> float | None:
    """Rough plan footprint area (ft²) from the slab/space bounding box — a story-weight estimate input."""
    try:
        import ifcopenshell.util.placement as _pl
        import numpy as np
        xs, ys = [], []
        for cls in ("IfcSlab", "IfcSpace"):
            for el in model.by_type(cls):
                pl = getattr(el, "ObjectPlacement", None)
                if pl is None:
                    continue
                m = np.array(_pl.get_local_placement(pl), dtype=float)
                xs.append(m[0, 3]); ys.append(m[1, 3])
        if len(xs) >= 2:
            area_m2 = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if area_m2 > 1.0:
                return area_m2 * 10.7639
    except Exception:  # noqa: BLE001 — area is a best-effort input; caller can override
        pass
    return None
