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


# ── engineering depth: pressure loss · per-conductor tray fill · space thermal loads ───────────────

_DUCT_FRICTION_MAX = 0.10   # in. w.g. per 100 ft — the classic equal-friction design target
_PIPE_FRICTION_MAX = 4.0    # ft head per 100 ft — typical hydronic ceiling (noise/erosion economics)
_HAZEN_C = 140.0            # Hazen-Williams roughness coefficient, copper / new steel
_M_PER_FT = 0.3048
_NEC_FILL_IN2_PER_IN = 7.0 / 6.0   # NEC Table 392.22(A) col 1: 7 in² allowable per 6 in tray width


def _equiv_round_in(size_mm: float, shape: str) -> float:
    """Equivalent round diameter (inches). A rectangular run carries one nominal dimension in our
    model (treated square), via the standard De = 1.30·(a·b)^0.625/(a+b)^0.25."""
    side_in = float(size_mm) / _MM_PER_IN
    if str(shape).lower().startswith("rect"):
        return 1.30 * (side_in * side_in) ** 0.625 / (2.0 * side_in) ** 0.25
    return side_in


def pressure_loss(model, *, duct_friction_max: float = _DUCT_FRICTION_MAX,
                  pipe_friction_max: float = _PIPE_FRICTION_MAX,
                  hazen_c: float = _HAZEN_C) -> dict[str, Any]:
    """Friction (pressure) loss per authored duct/pipe run + per-system balancing view. Ducts use the
    round-galvanized empirical friction equation (Δp in.w.g./100 ft = 0.109136·CFM^1.9/De^5.02); pipes
    use Hazen-Williams (ft/100 ft = 0.2083·(100/C)^1.852·GPM^1.852/d^4.8655). Each run's friction RATE
    is checked against the design budget; per system the losses are series-summed (no branch topology
    yet — an upper bound) and the **index run** (largest loss) is named, which is what a balancing
    engineer hunts first. Needs size + flow + length on the sizing pset."""
    runs: list[dict] = []
    for classes, kind in ((_DUCT_CLASSES, "duct"), (_PIPE_CLASSES, "pipe")):
        for cls in classes:
            for el in model.by_type(cls):
                if el.is_a("IfcElementType"):
                    continue
                ps = _pset(el)
                size, flow, length = ps.get("NominalSize_mm"), ps.get("FlowRate"), ps.get("Length_m")
                if not size or not flow or not length:
                    continue
                len_ft = float(length) / _M_PER_FT
                if kind == "duct":
                    de = _equiv_round_in(float(size), ps.get("Shape") or "round")
                    rate = 0.109136 * float(flow) ** 1.9 / de ** 5.02 if de > 0 else 0.0
                    budget, unit = duct_friction_max, "in_wg_per_100ft"
                else:
                    d_in = float(size) / _MM_PER_IN
                    rate = (0.2083 * (100.0 / hazen_c) ** 1.852 * float(flow) ** 1.852
                            / d_in ** 4.8655) if d_in > 0 else 0.0
                    budget, unit = pipe_friction_max, "ft_per_100ft"
                loss = rate * len_ft / 100.0
                runs.append({"guid": el.GlobalId, "class": el.is_a(), "kind": kind,
                             "system": _system_name(el), "size_mm": round(float(size), 1),
                             "flow": float(flow), "length_ft": round(len_ft, 1),
                             "friction_rate": round(rate, 4), "rate_unit": unit,
                             "loss": round(loss, 4), "budget_rate": budget,
                             "status": "pass" if rate <= budget else "fail"})

    systems: list[dict] = []
    for sysname in sorted({r["system"] or "(unassigned)" for r in runs}):
        rs = [r for r in runs if (r["system"] or "(unassigned)") == sysname]
        index = max(rs, key=lambda r: r["loss"])
        systems.append({"system": sysname, "kind": rs[0]["kind"], "runs": len(rs),
                        "total_length_ft": round(sum(r["length_ft"] for r in rs), 1),
                        "total_loss": round(sum(r["loss"] for r in rs), 3),
                        "loss_unit": "in_wg" if rs[0]["kind"] == "duct" else "ft_head",
                        "index_run": {"guid": index["guid"], "loss": index["loss"],
                                      "friction_rate": index["friction_rate"]},
                        "all_within_budget": all(r["status"] == "pass" for r in rs)})
    runs.sort(key=lambda r: (0 if r["status"] == "fail" else 1, -r["loss"]))
    return {
        "checked": len(runs), "failed": sum(1 for r in runs if r["status"] == "fail"),
        "budgets": {"duct_in_wg_per_100ft": float(duct_friction_max),
                    "pipe_ft_per_100ft": float(pipe_friction_max), "hazen_c": float(hazen_c)},
        "runs": runs, "systems": systems,
        "disclaimer": "PRELIMINARY friction-loss screen — empirical round-duct + Hazen-Williams rates "
                      "over the authored sizes; system totals are a series sum (no branch topology, no "
                      "fittings, no diversity). NOT a hydraulic design; final balancing by a licensed PE.",
    }


def tray_fill(model) -> dict[str, Any]:
    """Per-conductor NEC 392.22 tray fill — computed from the actual cables, not a supplied ratio.
    For each cable tray, the cables enrolled on the *same distribution system* contribute their
    cross-section (π/4·d² from the authored nominal diameter); the allowable fill area follows NEC
    Table 392.22(A) column 1 (ladder/ventilated tray, multiconductor < 4/0): 7 in² per 6 in of tray
    width. A supplied `FillRatio` still wins when no cables are authored (back-compat)."""
    cables_by_system: dict[str, list[dict]] = {}
    for el in model.by_type("IfcCableSegment"):
        if el.is_a("IfcElementType"):
            continue
        ps = _pset(el)
        d_in = float(ps.get("NominalSize_mm") or 0.0) / _MM_PER_IN
        if d_in <= 0:
            continue
        sysname = _system_name(el) or "(unassigned)"
        cables_by_system.setdefault(sysname, []).append(
            {"guid": el.GlobalId, "diameter_in": round(d_in, 3),
             "area_in2": round(math.pi / 4.0 * d_in * d_in, 3)})

    trays: list[dict] = []
    for cls in _TRAY_CLASSES:
        for el in model.by_type(cls):
            if el.is_a("IfcElementType"):
                continue
            ps = _pset(el)
            width_in = float(ps.get("NominalSize_mm") or 0.0) / _MM_PER_IN
            if width_in <= 0:
                continue
            sysname = _system_name(el) or "(unassigned)"
            cables = cables_by_system.get(sysname, [])
            allowable = _NEC_FILL_IN2_PER_IN * width_in
            base = {"guid": el.GlobalId, "system": sysname, "width_in": round(width_in, 1),
                    "allowable_fill_in2": round(allowable, 2),
                    "citation": "NEC 392.22(A), Table 392.22(A) col 1 (ladder/ventilated, <4/0)"}
            if cables:
                used = sum(c["area_in2"] for c in cables)
                ratio = used / allowable if allowable > 0 else 0.0
                trays.append({**base, "conductors": len(cables), "used_fill_in2": round(used, 2),
                              "fill_ratio": round(ratio, 3),
                              "status": "pass" if ratio <= 1.0 else "fail",
                              "cables": cables[:20]})
            elif ps.get("FillRatio") is not None:
                r = float(ps["FillRatio"])
                trays.append({**base, "conductors": 0, "fill_ratio": round(r, 3),
                              "status": "pass" if r <= _TRAY_MAX_FILL else "fail",
                              "note": "supplied fill ratio (no cables authored on this system)"})
            else:
                trays.append({**base, "conductors": 0, "fill_ratio": None, "status": "info",
                              "note": "no cables authored on this tray's system — author IfcCableSegment "
                                      "runs (add_wire) with a nominal diameter to compute the fill"})
    trays.sort(key=lambda t: {"fail": 0, "info": 1, "pass": 2}[t["status"]])
    return {
        "checked": len(trays), "failed": sum(1 for t in trays if t["status"] == "fail"),
        "trays": trays,
        "disclaimer": "Per-conductor NEC 392.22 fill screen from the authored cable diameters — assumes "
                      "ladder/ventilated tray and multiconductor cables < 4/0 (Table 392.22(A) col 1). "
                      "Verify the actual tray type/table row; final design by a licensed PE.",
    }


# space-type keyword → (sf per person, lighting W/sf, equipment W/sf) — typical design densities
_SPACE_LOADS: list[tuple[tuple[str, ...], str, tuple[float, float, float]]] = [
    (("conference", "meeting"), "conference", (15.0, 1.0, 0.5)),
    (("class", "training"), "classroom", (20.0, 0.9, 0.8)),
    (("retail", "shop", "store"), "retail", (60.0, 1.4, 0.5)),
    (("corridor", "lobby", "stair", "circulation"), "circulation", (100.0, 0.7, 0.1)),
    (("mech", "electrical", "storage", "janitor", "utility"), "back-of-house", (500.0, 0.6, 0.2)),
    (("apartment", "residential", "bedroom", "unit"), "residential", (200.0, 0.6, 0.5)),
    (("office", "work", "open plan"), "office", (150.0, 0.9, 1.0)),
]
_DEFAULT_SPACE_LOAD = ("general", (150.0, 1.0, 0.8))
_BTUH_PER_PERSON = 450.0    # sensible + latent, light office activity
_W_TO_BTUH = 3.412


def thermal_loads(model, *, envelope_btuh_sf: float = 12.0,
                  block_sf_per_ton: float = 350.0) -> dict[str, Any]:
    """Space-by-space cooling-load screen (W/sf method): per IfcSpace, people (by design density) +
    lighting + equipment W/sf by space type (from the space name) + a flat envelope allowance, summed
    to tons and compared to the single-number block estimate. The step between 'GFA ÷ 350' and a real
    load calc — shows WHERE the load lives so the block number can be believed or challenged."""
    import ifcopenshell.util.element as ue

    spaces: list[dict] = []
    skipped = 0
    for el in model.by_type("IfcSpace"):
        qtos = ue.get_psets(el, qtos_only=True)
        area_m2 = None
        for q in qtos.values():
            area_m2 = q.get("NetFloorArea") or q.get("GrossFloorArea") or area_m2
        if not area_m2:
            skipped += 1
            continue
        area_sf = float(area_m2) * 10.7639
        name = " ".join(filter(None, [getattr(el, "Name", None) or "",
                                      getattr(el, "LongName", None) or ""])).lower()
        label, (sf_pp, light_w, equip_w) = _DEFAULT_SPACE_LOAD
        for keys, lab, vals in _SPACE_LOADS:
            if any(k in name for k in keys):
                label, (sf_pp, light_w, equip_w) = lab, vals
                break
        people = max(1, round(area_sf / sf_pp)) if area_sf > 0 else 0
        internal = people * _BTUH_PER_PERSON + area_sf * (light_w + equip_w) * _W_TO_BTUH
        envelope = area_sf * float(envelope_btuh_sf)
        total = internal + envelope
        spaces.append({"guid": el.GlobalId, "name": getattr(el, "Name", None),
                       "long_name": getattr(el, "LongName", None), "type": label,
                       "area_sf": round(area_sf, 0), "people": people,
                       "internal_btuh": round(internal, 0), "envelope_btuh": round(envelope, 0),
                       "total_btuh": round(total, 0), "tons": round(total / 12000.0, 2)})

    spaces.sort(key=lambda s: -s["total_btuh"])
    total_btuh = sum(s["total_btuh"] for s in spaces)
    total_sf = sum(s["area_sf"] for s in spaces)
    tons = total_btuh / 12000.0
    block_tons = total_sf / float(block_sf_per_ton) if total_sf else 0.0
    return {
        "spaces": spaces, "skipped_no_area": skipped,
        "total_area_sf": round(total_sf, 0), "total_btuh": round(total_btuh, 0),
        "tons": round(tons, 1), "sf_per_ton": round(total_sf / tons, 0) if tons else None,
        "block_tons": round(block_tons, 1),
        "delta_vs_block_pct": round(100.0 * (tons - block_tons) / block_tons, 1) if block_tons else None,
        "assumptions": {"envelope_btuh_sf": float(envelope_btuh_sf),
                        "btuh_per_person": _BTUH_PER_PERSON,
                        "block_sf_per_ton": float(block_sf_per_ton),
                        "space_types": {lab: {"sf_per_person": v[0], "lighting_w_sf": v[1],
                                              "equipment_w_sf": v[2]}
                                        for _, lab, v in _SPACE_LOADS}},
        "disclaimer": "Space-by-space W/sf cooling-load SCREEN (people + lighting + equipment densities "
                      "by space type + a flat envelope allowance) — NOT an ASHRAE heat-balance load calc "
                      "(no orientation, glazing, schedules, or psychrometrics). Design loads by a "
                      "licensed mechanical engineer.",
    }
