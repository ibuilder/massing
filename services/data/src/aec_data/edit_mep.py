"""REL-3 leaf: MEP authoring recipes — risers, runs, fittings, terminals, devices, systems, connections.

The mechanical/electrical/plumbing/fire recipe group split off `edit.py`: system assignment + predefined
types, sized risers/runs (round/rectangular), fittings with port counts, terminals, fire/FA/comms devices,
and the element-connection graph. Built entirely on the `edit_core` primitives (contexts, profiles, storey
lookup, GUID lookup) — never on another recipe. `edit.py` re-exports every name, so `edit.add_mep_run` /
`edit.connect_elements` importers (routers, RECIPES, nodegraph) are unchanged.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api

from .edit_core import _body_context, _first_storey, _rect_profile

_MEP_DISCIPLINE_PREDEF = {
    "hvac": "VENTILATION", "ventilation": "VENTILATION", "airconditioning": "AIRCONDITIONING",
    "exhaust": "EXHAUST", "heating": "HEATING", "refrigeration": "REFRIGERATION",
    "plumbing": "DOMESTICCOLDWATER", "domesticcoldwater": "DOMESTICCOLDWATER",
    "domestichotwater": "DOMESTICHOTWATER", "drainage": "DRAINAGE", "sewage": "SEWAGE",
    "watersupply": "WATERSUPPLY", "rainwater": "RAINWATER", "stormwater": "STORMWATER",
    "electrical": "ELECTRICAL", "lighting": "LIGHTING", "power": "ELECTRICAL", "earthing": "EARTHING",
    "fire": "FIREPROTECTION", "fireprotection": "FIREPROTECTION", "sprinkler": "FIREPROTECTION",
    "standpipe": "FIREPROTECTION", "firesuppression": "FIREPROTECTION",
    "communication": "COMMUNICATION", "comms": "COMMUNICATION", "data": "DATA", "signal": "SIGNAL",
}


def _resolve_system_predef(discipline: str | None) -> str | None:
    """Map a discipline word (e.g. 'fire') or a raw IfcDistributionSystemEnum value to a PredefinedType."""
    if not discipline:
        return None
    key = str(discipline).strip().lower()
    if key in _MEP_DISCIPLINE_PREDEF:
        return _MEP_DISCIPLINE_PREDEF[key]
    return str(discipline).strip().upper() or None   # allow a raw enum value to pass through


def _assign_to_system(model: ifcopenshell.file, element, name: str | None,
                      predefined_type: str | None = None) -> None:
    """Find-or-create a named IfcDistributionSystem, stamp its discipline PredefinedType (first author
    wins; retag via set_system_predefined), and assign the element to it. Best-effort — never aborts an
    authoring recipe on an older ifcopenshell or a schema without the enum."""
    try:
        name = name or "MEP"
        sysobj = next((s for s in model.by_type("IfcDistributionSystem") if s.Name == name), None) \
            or ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcDistributionSystem", name=name)
        pt = _resolve_system_predef(predefined_type)
        if pt and hasattr(sysobj, "PredefinedType") and not getattr(sysobj, "PredefinedType", None):
            try:
                sysobj.PredefinedType = pt
            except Exception:                             # noqa: BLE001 — enum invalid for this schema
                pass
        ifcopenshell.api.run("system.assign_system", model, products=[element], system=sysobj)
    except Exception:                                     # noqa: BLE001 — system assignment best-effort
        pass


def set_system_predefined(model: ifcopenshell.file, system: str, discipline: str) -> dict:
    """MEP-FP: (re)stamp a named IfcDistributionSystem's **discipline** via its PredefinedType — so an
    existing 'MEP' group can be typed as FIREPROTECTION / VENTILATION / ELECTRICAL / DOMESTICCOLDWATER…
    Returns {system, predefined_type}. Raises if the named system doesn't exist."""
    name = (system or "").strip()
    sysobj = next((s for s in model.by_type("IfcDistributionSystem") if (s.Name or "") == name), None)
    if sysobj is None:
        raise ValueError(f"no IfcDistributionSystem named {name!r}")
    pt = _resolve_system_predef(discipline)
    if not pt:
        raise ValueError("a discipline is required (e.g. 'fire', 'hvac', 'electrical', 'plumbing')")
    if hasattr(sysobj, "PredefinedType"):
        try:
            sysobj.PredefinedType = pt
        except Exception as e:                            # noqa: BLE001
            raise ValueError(f"{pt} is not a valid system type for this IFC schema") from e
    return {"system": name, "predefined_type": pt}


# MEP-FP: fire-protection equipment kind -> (IFC class, PredefinedType). Sprinkler heads, hose reels, the
# fire-department (siamese) connection, hydrants (all IfcFireSuppressionTerminal subtypes), and the fire
# pump (IfcPump). Authored onto the fire-protection distribution system.
_FIRE_EQUIPMENT = {
    "sprinkler": ("IfcFireSuppressionTerminal", "SPRINKLER"),
    "hose_reel": ("IfcFireSuppressionTerminal", "HOSEREEL"),
    "fdc":       ("IfcFireSuppressionTerminal", "BREECHINGINLET"),   # fire-department (siamese) connection
    "hydrant":   ("IfcFireSuppressionTerminal", "FIREHYDRANT"),
    "fire_pump": ("IfcPump", None),                                  # pump type enum has no "fire pump"
}


def _default_flow_unit(element) -> str:
    """The conventional design-flow unit for a segment's system: airflow for ducts (CFM), liquid flow for
    pipes (GPM), electrical current for cable (A). Used when a flow is given without an explicit unit."""
    cls = element.is_a()
    if "Duct" in cls:
        return "CFM"
    if "Cable" in cls:
        return "A"
    return "GPM"


def _set_mep_sizing(model: ifcopenshell.file, element, size: float, shape: str = "round",
                    length: float | None = None, flow: float | None = None,
                    flow_unit: str | None = None) -> None:
    """W10-4: record the **nominal size** (+ shape/length + optional design **flow rate**) on an MEP segment
    so schedules, QTO, and sizing pre-checks can read it directly instead of re-deriving from geometry. A
    pragmatic occurrence pset (`Pset_Massing_MEPSizing`) — nominal sizing normally lives on the IfcType/
    profile, which our on-the-fly segments don't carry."""
    props: dict[str, Any] = {"NominalSize_mm": round(float(size) * 1000.0, 1), "Shape": str(shape)}
    if length is not None:
        props["Length_m"] = round(float(length), 3)
    if flow is not None:
        props["FlowRate"] = round(float(flow), 3)
        props["FlowUnit"] = str(flow_unit) if flow_unit else _default_flow_unit(element)
    try:
        ps = ifcopenshell.api.run("pset.add_pset", model, product=element, name="Pset_Massing_MEPSizing")
        ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)
    except Exception:  # noqa: BLE001 — sizing metadata is best-effort, never blocks authoring
        pass


def add_riser(model: ifcopenshell.file, point=(0.0, 0.0), bottom_z: float = 0.0, top_z: float = 3.0,
              size: float = 0.1, ifc_class: str = "IfcPipeSegment", storey: str | None = None,
              system: str = "Fire Protection", discipline: str | None = "fire",
              flow: float | None = None, flow_unit: str | None = None) -> str:
    """A **vertical** MEP riser (fire standpipe · plumbing stack · vent) — an IfcPipeSegment swept along
    world +Z from `bottom_z` to `top_z` (metres) at an [E, N] point, with a port at each end, enrolled on
    the named distribution system. The vertical complement to the (horizontal) `add_mep_run`. GUID-stable."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    height = float(top_z) - float(bottom_z)
    if height <= 1e-9:
        raise ValueError("top_z must be above bottom_z (a riser needs a positive height)")
    seg = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name="Riser")
    m = np.eye(4)                                          # identity → local +Z is world +Z (vertical)
    m[0, 3], m[1, 3], m[2, 3] = float(point[0]), float(point[1]), float(bottom_z)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=seg, matrix=m)
    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(size) / 2.0 / scale)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=height)
    ifcopenshell.api.run("geometry.assign_representation", model, product=seg, representation=rep)
    st = _first_storey(model, storey)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[seg], relating_structure=st)
    try:
        ifcopenshell.api.run("system.add_port", model, element=seg)
        ifcopenshell.api.run("system.add_port", model, element=seg)
    except Exception:                                     # noqa: BLE001 — older ifcopenshell w/o system.add_port
        pass
    _assign_to_system(model, seg, system, discipline)
    _set_mep_sizing(model, seg, size, "round", height, flow, flow_unit)   # vertical riser length = height
    return seg.GlobalId


def add_fire_equipment(model: ifcopenshell.file, kind: str = "sprinkler", point=(0.0, 0.0),
                       storey: str | None = None, system: str = "Fire Protection") -> str:
    """MEP-FP: author a fire-protection device — sprinkler head / hose reel / fire-department (siamese)
    connection / hydrant / fire pump — as the right IFC class + PredefinedType, enrolled on the
    fire-protection distribution system (discipline=fire). Returns the new element's GUID."""
    k = (kind or "sprinkler").strip().lower()
    ifc_class, predef = _FIRE_EQUIPMENT.get(k, _FIRE_EQUIPMENT["sprinkler"])
    size = 0.4 if k == "fire_pump" else 0.15
    return add_mep_terminal(model, ifc_class, point, size, size, size, predef, storey, system, "fire")


# Fire Alarm / life-safety devices — a discipline distinct from fire *protection* (documented on its own
# FA sheet series). Detectors are IfcSensor; manual/notification devices + the control panel are IfcAlarm.
_FA_DEVICE = {
    "smoke_detector": ("IfcSensor", "SMOKESENSOR"),
    "heat_detector":  ("IfcSensor", "HEATSENSOR"),
    "duct_detector":  ("IfcSensor", "SMOKESENSOR"),
    "pull_station":   ("IfcAlarm", "MANUALPULLBOX"),
    "horn_strobe":    ("IfcAlarm", "SIREN"),
    "strobe":         ("IfcAlarm", "LIGHT"),
    "bell":           ("IfcAlarm", "BELL"),
    "facp":           ("IfcAlarm", "BREAKGLASSBUTTON"),   # Fire Alarm Control Panel (no dedicated enum)
}


def add_fa_device(model: ifcopenshell.file, kind: str = "smoke_detector", point=(0.0, 0.0),
                  storey: str | None = None, system: str = "Fire Alarm") -> str:
    """Author a **fire-alarm / life-safety** device — smoke/heat/duct detector (IfcSensor), manual pull
    station / horn-strobe / strobe / bell / FACP (IfcAlarm) — enrolled on a named Fire-Alarm system.
    Fire alarm is its own discipline (FA sheet series), separate from fire *protection* (sprinklers).
    Returns the new element's GUID."""
    k = (kind or "smoke_detector").strip().lower()
    ifc_class, predef = _FA_DEVICE.get(k, _FA_DEVICE["smoke_detector"])
    size = 0.5 if k == "facp" else 0.15
    return add_mep_terminal(model, ifc_class, point, size, size, size, predef, storey, system, "electrical")


# Telecommunications / low-voltage / data devices (discipline T). MDF/IDF racks + WAPs are comms
# appliances; data jacks are outlets.
_COMMS_DEVICE = {
    "mdf":         ("IfcCommunicationsAppliance", "NETWORKHUB"),   # main distribution frame / head-end rack
    "idf":         ("IfcCommunicationsAppliance", "NETWORKHUB"),   # intermediate distribution frame / floor rack
    "rack":        ("IfcCommunicationsAppliance", "NETWORKAPPLIANCE"),
    "switch":      ("IfcCommunicationsAppliance", "SWITCH"),
    "wap":         ("IfcCommunicationsAppliance", "ANTENNA"),      # wireless access point
    "data_outlet": ("IfcOutlet", "DATAOUTLET"),
}


def add_comms_device(model: ifcopenshell.file, kind: str = "idf", point=(0.0, 0.0),
                     storey: str | None = None, system: str = "Telecommunications") -> str:
    """Author a **telecom / low-voltage** device — MDF/IDF rack, network switch, wireless access point
    (IfcCommunicationsAppliance) or data outlet (IfcOutlet) — enrolled on a named Telecommunications
    system (discipline T). Returns the new element's GUID."""
    k = (kind or "idf").strip().lower()
    ifc_class, predef = _COMMS_DEVICE.get(k, _COMMS_DEVICE["idf"])
    size = 0.9 if k in ("mdf", "idf", "rack") else 0.15
    return add_mep_terminal(model, ifc_class, point, size, size, size, predef, storey, system, "communication")


def add_mep_run(model: ifcopenshell.file, ifc_class: str, start, end, shape: str = "round",
                size: float = 0.3, storey: str | None = None, system: str = "MEP",
                discipline: str | None = None, flow: float | None = None,
                flow_unit: str | None = None) -> str:
    """A straight MEP segment (IfcDuctSegment / IfcPipeSegment / IfcCableCarrierSegment /
    IfcCableSegment) swept along start→end: a round (size=diameter) or rectangular (tray) section.
    Adds two connection ports and assigns it to a named IfcDistributionSystem."""
    import math

    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    sx, sy, ex, ey = float(start[0]), float(start[1]), float(end[0]), float(end[1])
    length = math.hypot(ex - sx, ey - sy)
    if length < 1e-9:
        raise ValueError("start and end points must differ")
    dx, dy = (ex - sx) / length, (ey - sy) / length
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    seg = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class,
                               name=ifc_class.replace("Ifc", "").replace("Segment", ""))
    matrix = np.array([[-dy, 0, dx, sx], [dx, 0, dy, sy], [0, 1, 0, elev], [0, 0, 0, 1]], dtype=float)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=seg, matrix=matrix)
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    if shape == "rect":                                            # profile dims in file units (÷ scale)
        profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                                      XDim=float(size) / scale, YDim=float(size) * 0.4 / scale)
    else:
        profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos,
                                      Radius=float(size) / 2.0 / scale)
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=length)
    ifcopenshell.api.run("geometry.assign_representation", model, product=seg, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[seg], relating_structure=st)
    try:                                              # ports — a bare segment is flagged invalid
        ifcopenshell.api.run("system.add_port", model, element=seg)
        ifcopenshell.api.run("system.add_port", model, element=seg)
    except Exception:                                 # noqa: BLE001 — older ifcopenshell w/o system.add_port
        pass
    _assign_to_system(model, seg, system, discipline)
    _set_mep_sizing(model, seg, size, shape, length, flow, flow_unit)
    return seg.GlobalId


# fitting PredefinedType → number of connection ports (IfcDuct/PipeFittingTypeEnum: JUNCTION = tee/cross)
_MEP_FITTING_PORTS = {"BEND": 2, "TRANSITION": 2, "CONNECTOR": 2, "OBSTRUCTION": 2,
                      "JUNCTION": 3, "ENTRY": 1, "EXIT": 1}


def add_mep_fitting(model: ifcopenshell.file, ifc_class: str, point, size: float = 0.3,
                    predefined: str = "BEND", storey: str | None = None, system: str = "MEP",
                    discipline: str | None = None) -> str:
    """A MEP **fitting** (IfcDuctFitting / IfcPipeFitting / IfcCableCarrierFitting) at an XY point — an
    elbow (BEND), tee/cross (JUNCTION), or size change (TRANSITION) that joins runs. A sized box body,
    the right number of connection **ports** for the fitting type, and assignment to the named
    IfcDistributionSystem. The LOD 350/400 detailing that turns loose segments into a real system."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    fit = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class,
                               name=ifc_class.replace("Ifc", "").replace("Fitting", " fitting").strip())
    pd = (predefined or "BEND").upper()
    if hasattr(fit, "PredefinedType"):
        try:
            fit.PredefinedType = pd
        except Exception:                             # noqa: BLE001 — invalid enum for the schema
            pd = "BEND"
    m = np.eye(4)
    m[0, 3], m[1, 3], m[2, 3] = float(point[0]), float(point[1]), elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=fit, matrix=m)
    s = max(0.05, float(size))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=_rect_profile(model, s, s), depth=s)
    ifcopenshell.api.run("geometry.assign_representation", model, product=fit, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[fit], relating_structure=st)
    for _ in range(_MEP_FITTING_PORTS.get(pd, 2)):
        try:
            ifcopenshell.api.run("system.add_port", model, element=fit)
        except Exception:                             # noqa: BLE001 — older ifcopenshell w/o system.add_port
            pass
    _assign_to_system(model, fit, system, discipline)
    return fit.GlobalId


def add_mep_terminal(model: ifcopenshell.file, ifc_class: str, point, width: float = 0.4,
                     depth: float = 0.4, height: float = 0.4, predefined: str | None = None,
                     storey: str | None = None, system: str | None = None,
                     discipline: str | None = None) -> str:
    """Point MEP equipment (electrical panel, outlet, light, air terminal, sanitary/waste terminal,
    fire-suppression sprinkler head, fire alarm, sensor, comms appliance) as a sized box of `ifc_class`
    at an XY point. Pass `system` to add a port and enrol it in a named IfcDistributionSystem (with an
    optional `discipline` — e.g. 'fire' for a sprinkler head on a fire-protection system)."""
    import ifcopenshell.util.unit as uunit
    import numpy as np

    scale = uunit.calculate_unit_scale(model)
    body = _body_context(model)
    st = _first_storey(model, storey)
    elev = (float(getattr(st, "Elevation", 0) or 0) if st else 0.0) * scale
    el = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class,
                              name=ifc_class.replace("Ifc", ""))
    if predefined:
        try:
            el.PredefinedType = predefined
        except Exception:                             # noqa: BLE001 — enum not in this schema
            pass
    matrix = np.eye(4)
    matrix[0, 3] = float(point[0]); matrix[1, 3] = float(point[1]); matrix[2, 3] = elev
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=matrix)
    profile = _rect_profile(model, float(width), float(depth))
    rep = ifcopenshell.api.run("geometry.add_profile_representation", model, context=body,
                               profile=profile, depth=float(height))
    ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
    if st:
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=st)
    if system:                                        # enrol the terminal in a distribution system (+ a port)
        try:
            ifcopenshell.api.run("system.add_port", model, element=el)
        except Exception:                             # noqa: BLE001 — older ifcopenshell w/o system.add_port
            pass
        _assign_to_system(model, el, system, discipline)
    return el.GlobalId


def connect_mep(model: ifcopenshell.file, guid_a: str, guid_b: str) -> dict:
    """W10-4: connect two MEP elements **port-to-port** (`IfcRelConnectsPorts`) — the logical-network edge
    that turns a pile of segments/fittings into a connected distribution system. Uses the first free
    (unconnected) port on each element. GUID-stable; raises if either has no free port."""
    from . import mep

    a = _mep_element(model, guid_a)
    b = _mep_element(model, guid_b)
    pa = next((p for p in mep._ports(a) if not mep._port_connected(p)), None)
    pb = next((p for p in mep._ports(b) if not mep._port_connected(p)), None)
    if pa is None:
        raise ValueError(f"{a.is_a()} {guid_a} has no free connection port")
    if pb is None:
        raise ValueError(f"{b.is_a()} {guid_b} has no free connection port")
    try:
        ifcopenshell.api.run("system.connect_port", model, port1=pa, port2=pb)
    except Exception as e:  # noqa: BLE001 — older ifcopenshell shape
        raise ValueError(f"could not connect ports: {e}") from e
    return {"connected": [guid_a, guid_b]}


def _mep_element(model: ifcopenshell.file, guid: str):
    """Resolve an MEP element by GUID (distribution elements are IfcElement subtypes, but be lenient)."""
    el = model.by_guid(guid)
    if el is None:
        raise ValueError(f"element {guid} not found")
    return el


def connect_elements(model: ifcopenshell.file, guid_a: str, guid_b: str, description: str | None = None) -> dict:
    """B5: record a physical **connection** between two building elements (`IfcRelConnectsElements`) — the
    LOD-350 coordination primitive (a beam framing into a column, a brace to a gusset plate, a hanger to a
    slab). Distinct from the MEP port link (`connect_mep`). GUID-stable + idempotent per ordered pair;
    raises if either element is missing or they're the same. Returns {connected, created}."""
    def _by_guid(g):
        try:
            return model.by_guid(g)
        except (RuntimeError, Exception):          # noqa: BLE001 — malformed/absent GUID → treat as missing
            return None

    a = _by_guid(guid_a)
    b = _by_guid(guid_b)
    if a is None or b is None:
        raise ValueError("both elements must exist")
    if a.id() == b.id():
        raise ValueError("cannot connect an element to itself")
    for rel in model.by_type("IfcRelConnectsElements"):
        if rel.RelatingElement == a and rel.RelatedElement == b:
            return {"connected": [guid_a, guid_b], "created": False}
    rel = model.create_entity("IfcRelConnectsElements", GlobalId=ifcopenshell.guid.new(),
                              RelatingElement=a, RelatedElement=b)
    if description:
        rel.Description = str(description)
    return {"connected": [guid_a, guid_b], "created": True}


def element_connections(model: ifcopenshell.file) -> dict:
    """B5: the element-to-element **connection graph** (`IfcRelConnectsElements`) — the connected pairs
    (each with class + optional description) and the per-element connection degree. The coordination
    read-back over `connect_elements`."""
    try:
        rels = model.by_type("IfcRelConnectsElements")
    except RuntimeError:
        rels = []
    pairs: list[dict] = []
    degree: dict[str, int] = {}
    for rel in rels:
        a = getattr(rel, "RelatingElement", None)
        b = getattr(rel, "RelatedElement", None)
        if a is None or b is None:
            continue
        pairs.append({"a": a.GlobalId, "a_class": a.is_a(), "b": b.GlobalId, "b_class": b.is_a(),
                      "description": getattr(rel, "Description", None)})
        for g in (a.GlobalId, b.GlobalId):
            degree[g] = degree.get(g, 0) + 1
    return {"count": len(pairs), "connections": pairs[:200],
            "elements_connected": len(degree),
            "max_degree": max(degree.values()) if degree else 0}


# --- architectural finishes: coverings (ceiling/tile/cladding) + railings (P3) ----------------
