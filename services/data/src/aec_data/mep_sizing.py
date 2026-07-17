"""MEP-SIZE · engineering size checks over already-authored MEP runs.

W10-4 writes a design size + flow onto each MEP segment (`Pset_Massing_MEPSizing`: NominalSize_mm, Shape,
Length_m, FlowRate, FlowUnit). This module turns that from *modeled* into *engineered*: it computes the
flow velocity in each duct / pipe from size + design flow and checks it against accepted limits, exactly
the pass/fail pre-check a mechanical engineer runs before locking a size —

    duct (air, CFM):   V = Q / A          → ASHRAE low-velocity commercial limit (~2500 fpm main supply)
    pipe (water, GPM): V = 0.408·Q / d²    → erosion/noise limit (~8 ft/s for copper/steel)
    cable tray:        NEC 392 fill ≤ 50%  → reported as info unless a fill ratio is supplied

Pure physics (the velocity relations + limit values are facts, no license issue); reads the sizing pset
off the model, no geometry kernel. **Preliminary — not a substitute for a licensed MEP engineer's design.**

Units: sizes in mm on the pset (→ inches here), duct flow CFM, pipe flow GPM, velocities fpm / ft·s⁻¹.
"""
from __future__ import annotations

import math
from typing import Any

_MM_PER_IN = 25.4
_DUCT_MAX_FPM = 2500.0     # ASHRAE recommended max air velocity, commercial main supply (low-velocity)
_PIPE_MAX_FPS = 8.0        # general max water velocity to limit erosion + noise (copper / steel)
_TRAY_MAX_FILL = 0.50      # NEC 392.22 cable-tray fill for a ladder/ventilated tray

_DUCT_CLASSES = ("IfcDuctSegment", "IfcDuctFitting")
_PIPE_CLASSES = ("IfcPipeSegment", "IfcPipeFitting")
_TRAY_CLASSES = ("IfcCableCarrierSegment", "IfcCableCarrierFitting")


def _pset(el) -> dict:
    try:
        import ifcopenshell.util.element as _ue
        return _ue.get_psets(el).get("Pset_Massing_MEPSizing", {}) or {}
    except Exception:  # noqa: BLE001 — an element with no readable psets simply isn't size-checked
        return {}


def _system_name(el) -> str | None:
    """The distribution system this element is enrolled on (via IfcRelAssignsToGroup), for the report."""
    for rel in getattr(el, "HasAssignments", None) or []:
        if rel.is_a("IfcRelAssignsToGroup"):
            grp = getattr(rel, "RelatingGroup", None)
            if grp is not None and grp.is_a("IfcDistributionSystem"):
                return getattr(grp, "Name", None) or getattr(grp, "LongName", None)
    return None


def _duct_area_ft2(size_mm: float, shape: str) -> float:
    """Cross-sectional area (ft²) from the nominal size. Round → circle of that diameter; a rectangular
    run carries a single nominal dimension in our model, so it is treated as square (documented)."""
    side_in = size_mm / _MM_PER_IN
    if str(shape).lower().startswith("rect"):
        return (side_in / 12.0) ** 2
    d_ft = side_in / 12.0
    return math.pi / 4.0 * d_ft * d_ft


def _check_element(el, duct_max_fpm: float, pipe_max_fps: float) -> dict | None:
    """One size check for a single MEP element, or None if it carries no design size to check."""
    ps = _pset(el)
    size = ps.get("NominalSize_mm")
    if not size:
        return None
    cls = el.is_a()
    shape = ps.get("Shape") or "round"
    flow = ps.get("FlowRate")
    unit = str(ps.get("FlowUnit") or "").upper()
    base = {"guid": el.GlobalId, "class": cls, "system": _system_name(el),
            "size_mm": round(float(size), 1), "shape": shape,
            "flow": float(flow) if flow is not None else None, "flow_unit": unit or None}

    if cls in _DUCT_CLASSES or unit == "CFM":
        if not flow:
            return {**base, "parameter": "air velocity", "value": None, "limit_fpm": duct_max_fpm,
                    "status": "info", "note": "no design flow on the run — size check skipped"}
        area = _duct_area_ft2(float(size), shape)
        v = float(flow) / area if area > 0 else 0.0
        ok = v <= duct_max_fpm
        return {**base, "parameter": "air velocity", "value_fpm": round(v, 0), "limit_fpm": duct_max_fpm,
                "status": "pass" if ok else "fail",
                "note": f"{round(v)} fpm vs {int(duct_max_fpm)} fpm limit"
                        + ("" if ok else " — undersized / noisy; increase the duct")}
    if cls in _PIPE_CLASSES or unit == "GPM":
        if not flow:
            return {**base, "parameter": "water velocity", "value": None, "limit_fps": pipe_max_fps,
                    "status": "info", "note": "no design flow on the run — size check skipped"}
        d_in = float(size) / _MM_PER_IN
        v = 0.408 * float(flow) / (d_in * d_in) if d_in > 0 else 0.0
        ok = v <= pipe_max_fps
        return {**base, "parameter": "water velocity", "value_fps": round(v, 2), "limit_fps": pipe_max_fps,
                "status": "pass" if ok else "fail",
                "note": f"{round(v, 2)} ft/s vs {pipe_max_fps} ft/s limit"
                        + ("" if ok else " — erosion/noise risk; increase the pipe")}
    if cls in _TRAY_CLASSES:
        fill = ps.get("FillRatio")
        if fill is None:
            return {**base, "parameter": "cable-tray fill", "value": None, "limit": _TRAY_MAX_FILL,
                    "status": "info", "note": "provide a conductor fill ratio to check NEC 392.22 (≤ 50%)"}
        ok = float(fill) <= _TRAY_MAX_FILL
        return {**base, "parameter": "cable-tray fill", "value": round(float(fill), 3), "limit": _TRAY_MAX_FILL,
                "status": "pass" if ok else "fail",
                "note": f"{round(float(fill) * 100)}% vs 50% NEC 392.22 limit"}
    return None


def sizing_check(model, *, duct_max_fpm: float = _DUCT_MAX_FPM,
                 pipe_max_fps: float = _PIPE_MAX_FPS) -> dict[str, Any]:
    """Velocity / fill size checks over every authored MEP segment carrying a design size + flow. Returns
    per-element checks + a pass/fail/info summary, in the same shape as the code checks. Read-only."""
    checks: list[dict] = []
    for classes in (_DUCT_CLASSES, _PIPE_CLASSES, _TRAY_CLASSES):
        for cls in classes:
            for el in model.by_type(cls):
                if el.is_a("IfcElementType"):
                    continue
                r = _check_element(el, float(duct_max_fpm), float(pipe_max_fps))
                if r is not None:
                    checks.append(r)

    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    info = sum(1 for c in checks if c["status"] == "info")
    checks.sort(key=lambda c: {"fail": 0, "info": 1, "pass": 2}[c["status"]])
    return {
        "checked": len(checks), "passed": passed, "failed": failed, "info": info,
        "all_pass": failed == 0 and (passed + failed) > 0,
        "limits": {"duct_max_fpm": float(duct_max_fpm), "pipe_max_fps": float(pipe_max_fps),
                   "tray_max_fill": _TRAY_MAX_FILL},
        "checks": checks,
        "disclaimer": "PRELIMINARY MEP size check for early coordination — flow velocity from the authored "
                      "nominal size + design flow against accepted velocity/fill limits (ASHRAE low-velocity "
                      "air, erosion-limit water, NEC 392 tray fill). NOT a full hydraulic/thermal design "
                      "(no pressure-loss balancing, no diversity, no acoustics). All final MEP sizing must be "
                      "performed and stamped by a licensed professional engineer.",
    }
