"""CX-1 (R14) — commissioning as a first-class loop over what already ships.

The `commissioning` module already carries phase-typed tests (Pre-Functional / Functional /
Integrated Systems / TAB / Retro-Cx) and `closeout.commissioning_rollup` reports pass rates. What
was missing is the FRONT of the loop and the cross-cut views:

  * ``seed_assets_from_model`` — equipment classes in the published model's property index become
    `asset_register` records (GUID-keyed, deduped), so the Cx registry starts from the model
    instead of manual entry.
  * ``seed_checklists``      — every systemed asset gets its phase-typed `commissioning` records
    (Pre-Functional + Functional by default), with **FPT expected values** pulled from the MEP
    equipment register (capacity / flow / size for the same system) stamped into the test data.
  * ``matrix``               — the system × phase completion grid (total / tested / accepted /
    pass / fail per cell) — the wall chart every Cx agent keeps.
  * ``dossier``              — the per-system turnover package: assets, tests by phase, expected
    values, and best-effort punch mentions.

Everything is deterministic reads/writes over the module engine — no model geometry needed
(the property index suffices), no new storage.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

# equipment classes worth an asset record (a subset of mep._MEP_CLASSES — segments/fittings are
# takeoff, not maintainable assets)
CX_ASSET_CLASSES = {
    "IfcAirTerminal": "Air terminal", "IfcAirTerminalBox": "Air terminal box", "IfcDamper": "Damper",
    "IfcFan": "Fan", "IfcValve": "Valve", "IfcPump": "Pump", "IfcTank": "Tank",
    "IfcSpaceHeater": "Space heater", "IfcBoiler": "Boiler", "IfcChiller": "Chiller",
    "IfcCoolingTower": "Cooling tower", "IfcUnitaryEquipment": "AHU / RTU", "IfcCoil": "Coil",
    "IfcLightFixture": "Light fixture", "IfcElectricAppliance": "Electrical appliance",
    "IfcElectricDistributionBoard": "Panel / board", "IfcSanitaryTerminal": "Plumbing fixture",
}
PHASES = ("Pre-Functional", "Functional", "Integrated Systems", "TAB", "Retro-Cx")
SEED_PHASES = ("Pre-Functional", "Functional")        # the two every asset gets on seed
MAX_SEED = 500                                        # per call — keep a huge model's seed bounded


def _system_of(entry: dict) -> str:
    """The element's system name: the MEP system if the index carries one, else its discipline."""
    sysname = entry.get("system") or (entry.get("psets", {}).get("Pset_SystemCommon", {}) or {}).get("Name")
    if sysname:
        return str(sysname)
    from . import classification
    return classification.discipline_name(
        classification.discipline_of_ifc_class(entry.get("ifc_class") or "", entry.get("host"))) or "General"


def seed_assets_from_model(db: Session, pid: str, idx: dict[str, dict] | None,
                           actor: str = "system") -> dict:
    """Equipment elements in the model index → asset_register records (GUID in data, deduped)."""
    if not idx:
        return {"model_scored": False, "created": 0, "skipped_existing": 0,
                "note": "No model loaded — seed needs a published model."}
    if "asset_register" not in me.TABLES:
        return {"model_scored": True, "created": 0, "skipped_existing": 0, "note": "no asset module"}
    have = {(r.get("data") or {}).get("guid")
            for r in me.list_records(db, "asset_register", pid, limit=100_000)}
    created = skipped = 0
    for guid, e in idx.items():
        cls = e.get("ifc_class") or ""
        if cls not in CX_ASSET_CLASSES:
            continue
        if guid in have:
            skipped += 1
            continue
        if created >= MAX_SEED:
            break
        me.create_record(db, "asset_register", pid, {"data": {
            "name": e.get("name") or f"{CX_ASSET_CLASSES[cls]} {guid[:6]}",
            "tag": e.get("name") or guid[:8], "location": e.get("storey") or "",
            "system": _system_of(e), "guid": guid, "ifc_class": cls}}, actor, None)
        created += 1
    return {"model_scored": True, "created": created, "skipped_existing": skipped,
            "capped": created >= MAX_SEED}


def _expected_for_system(db: Session, pid: str, system: str) -> dict[str, Any]:
    """FPT expected values for a system from the MEP equipment register (capacity/flow/size)."""
    from . import mep
    out: dict[str, Any] = {}
    for item in mep.schedule(db, pid)["items"]:
        if (item.get("system") or "").strip().lower() != system.strip().lower():
            continue
        for k in ("capacity", "flow"):
            if item.get(k):
                out[f"{item.get('tag') or item.get('type') or 'equip'}.{k}"] = item[k]
        if item.get("size"):
            out[f"{item.get('tag') or item.get('type') or 'equip'}.size"] = item["size"]
    return out


def seed_checklists(db: Session, pid: str, actor: str = "system") -> dict:
    """Phase-typed commissioning records for every systemed asset that lacks them — Pre-Functional +
    Functional per asset, with the system's MEP expected values stamped into the Functional test."""
    if "commissioning" not in me.TABLES or "asset_register" not in me.TABLES:
        return {"created": 0, "note": "commissioning/asset modules unavailable"}
    assets = me.list_records(db, "asset_register", pid, limit=100_000)
    cx = me.list_records(db, "commissioning", pid, limit=100_000)
    have = {((c.get("data") or {}).get("asset"), (c.get("data") or {}).get("test_type")) for c in cx}
    expected_cache: dict[str, dict] = {}
    created = 0
    for a in assets:
        d = a.get("data") or {}
        system = (d.get("system") or "").strip()
        if not system:
            continue
        for phase in SEED_PHASES:
            if (a["id"], phase) in have:
                continue
            if created >= MAX_SEED:
                return {"created": created, "capped": True}
            data = {"system": system, "asset": a["id"], "test_type": phase,
                    "status": "not started"}
            if phase == "Functional":
                exp = expected_cache.setdefault(system, _expected_for_system(db, pid, system))
                if exp:
                    data["deficiencies"] = "Expected (FPT): " + "; ".join(
                        f"{k}={v}" for k, v in sorted(exp.items())[:12])
            me.create_record(db, "commissioning", pid, {"data": data}, actor, None)
            created += 1
    return {"created": created, "capped": False}


def matrix(db: Session, pid: str) -> dict:
    """The system × phase wall chart: per cell total / tested / accepted / pass / fail."""
    cx = me.list_records(db, "commissioning", pid, limit=100_000) if "commissioning" in me.TABLES else []
    assets = me.list_records(db, "asset_register", pid, limit=100_000) if "asset_register" in me.TABLES else []
    asset_by_system: dict[str, int] = {}
    for a in assets:
        s = ((a.get("data") or {}).get("system") or "").strip()
        if s:
            asset_by_system[s] = asset_by_system.get(s, 0) + 1
    grid: dict[str, dict[str, dict]] = {}
    for c in cx:
        d = c.get("data") or {}
        system = (d.get("system") or "(unassigned)").strip() or "(unassigned)"
        phase = d.get("test_type") or "Pre-Functional"
        cell = grid.setdefault(system, {}).setdefault(phase, {
            "total": 0, "tested": 0, "accepted": 0, "pass": 0, "fail": 0})
        cell["total"] += 1
        st = c.get("workflow_state") or "open"
        if st in ("tested", "accepted"):
            cell["tested"] += 1
        if st == "accepted":
            cell["accepted"] += 1
        res = (d.get("result") or "").strip()
        if res == "Pass":
            cell["pass"] += 1
        elif res == "Fail":
            cell["fail"] += 1
    rows = []
    for system in sorted(set(grid) | set(asset_by_system)):
        phases = {p: grid.get(system, {}).get(p) for p in PHASES}
        total = sum(c["total"] for c in grid.get(system, {}).values())
        accepted = sum(c["accepted"] for c in grid.get(system, {}).values())
        rows.append({"system": system, "assets": asset_by_system.get(system, 0),
                     "tests": total, "accepted": accepted,
                     "complete_pct": round(100 * accepted / total, 1) if total else 0.0,
                     "phases": phases})
    return {"systems": rows, "phases": list(PHASES), "system_count": len(rows),
            "note": "system × phase completion — cells carry total/tested/accepted/pass/fail."}


def dossier(db: Session, pid: str, system: str) -> dict:
    """The per-system turnover package: assets, tests by phase, FPT expected values, punch mentions."""
    want = system.strip().lower()
    assets = [a for a in (me.list_records(db, "asset_register", pid, limit=100_000)
                          if "asset_register" in me.TABLES else [])
              if ((a.get("data") or {}).get("system") or "").strip().lower() == want]
    cx = [c for c in (me.list_records(db, "commissioning", pid, limit=100_000)
                      if "commissioning" in me.TABLES else [])
          if ((c.get("data") or {}).get("system") or "").strip().lower() == want]
    by_phase: dict[str, list] = {}
    for c in cx:
        d = c.get("data") or {}
        by_phase.setdefault(d.get("test_type") or "Pre-Functional", []).append({
            "ref": c.get("ref"), "asset": d.get("asset"), "state": c.get("workflow_state"),
            "result": d.get("result"), "date": d.get("date"), "cx_agent": d.get("cx_agent"),
            "deficiencies": (d.get("deficiencies") or "")[:400]})
    # best-effort punch mentions (punchlist has no system field — substring match, labelled as such)
    punch = [p for p in (me.list_records(db, "punchlist", pid, limit=100_000)
                         if "punchlist" in me.TABLES else [])
             if want and want in f"{(p.get('data') or {}).get('description', '')} "
                                 f"{(p.get('data') or {}).get('location', '')}".lower()]
    accepted = sum(1 for c in cx if c.get("workflow_state") == "accepted")
    return {"system": system, "asset_count": len(assets),
            "assets": [{"ref": a.get("ref"), "name": (a.get("data") or {}).get("name"),
                        "tag": (a.get("data") or {}).get("tag"),
                        "location": (a.get("data") or {}).get("location"),
                        "guid": (a.get("data") or {}).get("guid")} for a in assets[:500]],
            "tests": {p: by_phase.get(p, []) for p in PHASES if by_phase.get(p)},
            "test_count": len(cx), "accepted": accepted,
            "complete_pct": round(100 * accepted / len(cx), 1) if cx else 0.0,
            "expected_values": _expected_for_system(db, pid, system),
            "open_punch_mentions": len([p for p in punch if p.get("workflow_state") != "verified"]),
            "note": "Punch mentions are a substring match on description/location (the punchlist "
                    "module has no system field)."}
