"""External family-pack shelf — the `services/data/families/external/` directory as a first-class,
server-side importable library rather than a bare file listing.

The platform already had both halves of a content story and no bridge between them:
`GET /families/library` *listed* the external directory (filename + size), and
`POST /projects/{pid}/families/import` imported an IFC the caller **uploaded**. So a pack sitting on
the server could be seen but not used — an operator had to download it and upload it back to import
content the server was already holding.

This module is the bridge. It reads an optional sibling ``manifest.json`` (the shape the
`massing-families` generator publishes) so a shelf of forty discipline packs is navigable — how many
families and types, which discipline, what licence — instead of forty opaque filenames, and it
resolves a pack *name* to a path safely.

Pure over the filesystem; the router adapter owns auth, versioning and audit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# a pack file is content, not a project model: keep a ceiling so a mis-dropped 2 GB file can't be
# pulled into a source IFC by a single request
MAX_PACK_BYTES = 64 * 1024 * 1024


def library_dir() -> Path:
    from .build_family_library import LIBRARY_DIR
    return Path(LIBRARY_DIR)


def external_dir() -> Path:
    """The shelf directory. ``AEC_FAMILY_SHELF`` relocates it.

    The override exists so a test can exercise the shelf without writing into the shipped content
    directory. Two tests that both mutate the real `families/external/` race under the parallel
    runner — one sees the other's half-written manifest — and the failure looks like a bug in the
    reader rather than what it is: shared mutable state in the source tree.
    """
    override = os.environ.get("AEC_FAMILY_SHELF")
    return Path(override) if override else library_dir() / "external"


def _manifest(root: Path) -> dict[str, dict]:
    """Per-file metadata from a sibling ``manifest.json``, keyed by filename. Absent or malformed
    manifest → empty, never an error: the shelf must still list its files."""
    path = root / "manifest.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    out: dict[str, dict] = {}
    for p in (raw.get("packs") or []):
        if isinstance(p, dict) and p.get("file"):
            out[str(p["file"])] = p
    return out


def _pack_entry(path: Path, meta: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": path.name, "size_bytes": path.stat().st_size}
    for key in ("discipline", "families", "types", "tiers", "licence", "license", "version"):
        if key in meta:
            entry[key if key != "license" else "licence"] = meta[key]
    entry["described"] = bool(meta)          # a pack with no manifest row is listed, but says so
    return entry


def list_packs() -> dict[str, Any]:
    """Every `.ifc` on the external shelf, enriched from ``manifest.json`` when one is present.

    ``described`` is false for a pack the manifest does not cover — an undescribed pack is still
    importable, but nothing is claimed about its contents.
    """
    root = external_dir()
    if not root.is_dir():
        return {"packs": [], "count": 0, "totals": {}, "manifest": False}
    meta = _manifest(root)
    packs = [_pack_entry(p, meta.get(p.name, {})) for p in sorted(root.glob("*.ifc"))]
    totals = {
        "packs": len(packs),
        "families": sum(int(p.get("families") or 0) for p in packs),
        "types": sum(int(p.get("types") or 0) for p in packs),
        "size_bytes": sum(int(p["size_bytes"]) for p in packs),
        "undescribed": sum(1 for p in packs if not p["described"]),
        # Content you redistribute needs a licence you can point at. A pack whose manifest declares
        # none is counted here rather than shown blank: absent is not the same as permissive, and a
        # reader scanning a shelf will not notice an empty column.
        "unlicensed": sum(1 for p in packs if not p.get("licence")),
    }
    return {"packs": packs, "count": len(packs), "totals": totals, "manifest": bool(meta)}


def resolve(name: str) -> Path:
    """Resolve a pack *name* to a path on the external shelf.

    Name-only, never a path: anything carrying a separator, a parent reference, a drive or UNC
    prefix, or a non-`.ifc` suffix is refused outright.

    The returned path is then **selected out of the directory's own listing** rather than built by
    joining the caller's string onto the root. That inverts the trust: the path is one the server
    enumerated, and the caller's input only ever gets compared against it, so no amount of clever
    encoding can steer the result outside the shelf — and a symlink cannot walk out either, because
    the final containment check still runs on the resolved target.
    """
    raw = (name or "").strip()
    if not raw or raw != Path(raw).name or raw.startswith("."):
        raise ValueError(f"pack must be a plain file name on the shelf, got {name!r}")
    if not raw.lower().endswith(".ifc"):
        raise ValueError(f"pack must be an .ifc file, got {name!r}")
    root = external_dir()
    if not root.is_dir():
        raise ValueError(f"no such pack {raw!r} — the external shelf does not exist")
    path = next((p for p in root.glob("*.ifc") if p.name == raw and p.is_file()), None)
    if path is None:
        raise ValueError(f"no such pack {raw!r} on the external shelf")
    if root.resolve() not in path.resolve().parents:       # a symlink pointing off the shelf
        raise ValueError(f"pack {raw!r} resolves outside the external shelf")
    size = path.stat().st_size
    if size > MAX_PACK_BYTES:
        raise ValueError(f"pack {raw!r} is {size} bytes, over the {MAX_PACK_BYTES}-byte ceiling")
    return path


# ── typology coverage ────────────────────────────────────────────────────────────────────────────
# What it takes to model a building of each kind, expressed as the IFC *type* classes the shelf must
# be able to place. Deliberately class-level, not family-level: a shelf that has some IfcPumpType is
# provably able to place a pump, whereas asserting on family keys would only prove that one catalog
# happened to name something "fire_pump". The requirement is what IFC can express, not what we named.
#
# BASE is every building — structure, envelope, openings, circulation, and the four regulated MEP
# systems no occupiable building is permitted without. The per-typology entries are the systems that
# distinguish that building type and whose absence makes the model unbuildable rather than sparse.
BASE_SYSTEMS: dict[str, tuple[str, ...]] = {
    "structure": ("IfcColumnType", "IfcBeamType", "IfcSlabType", "IfcFootingType"),
    "envelope": ("IfcWallType", "IfcCurtainWallType", "IfcRoofType", "IfcCoveringType"),
    "openings": ("IfcDoorType", "IfcWindowType"),
    "circulation": ("IfcStairType", "IfcStairFlightType", "IfcRailingType", "IfcRampType"),
    "hvac": ("IfcAirTerminalType", "IfcDuctSegmentType", "IfcDuctFittingType", "IfcDamperType"),
    "plumbing": ("IfcSanitaryTerminalType", "IfcPipeSegmentType", "IfcValveType"),
    "electrical": ("IfcElectricDistributionBoardType", "IfcLightFixtureType", "IfcCableCarrierSegmentType",
                   "IfcOutletType", "IfcSwitchingDeviceType"),
    "fire_protection": ("IfcFireSuppressionTerminalType", "IfcAlarmType", "IfcSensorType"),
    "site": ("IfcSlabType", "IfcRailingType", "IfcDistributionChamberElementType"),
}

TYPOLOGY_SYSTEMS: dict[str, dict[str, tuple[str, ...]]] = {
    "residential": {"unit_fitout": ("IfcFurnitureType", "IfcElectricApplianceType"),
                    "vertical_transport": ("IfcTransportElementType",)},
    "commercial": {"workplace_fitout": ("IfcFurnitureType", "IfcSystemFurnitureElementType"),
                   "vertical_transport": ("IfcTransportElementType",),
                   "central_plant": ("IfcChillerType", "IfcBoilerType", "IfcPumpType")},
    "hotel": {"guestroom_fitout": ("IfcFurnitureType", "IfcElectricApplianceType"),
              "vertical_transport": ("IfcTransportElementType",),
              "back_of_house": ("IfcElectricApplianceType", "IfcUnitaryEquipmentType")},
    "hospital": {"clinical_fitout": ("IfcMedicalDeviceType", "IfcFurnitureType"),
                 "vertical_transport": ("IfcTransportElementType",),
                 "air_isolation": ("IfcDamperType", "IfcFilterType", "IfcHumidifierType"),
                 "central_plant": ("IfcChillerType", "IfcBoilerType", "IfcPumpType"),
                 "standby_power": ("IfcElectricGeneratorType", "IfcSwitchingDeviceType")},
    "industrial": {"material_handling": ("IfcTransportElementType",),
                   "process_services": ("IfcCompressorType", "IfcTankType"),
                   "storage": ("IfcFurnitureType",)},
    "airport": {"passenger_processing": ("IfcFurnitureType", "IfcAudioVisualApplianceType"),
                "baggage_handling": ("IfcTransportElementType",),
                "long_span_structure": ("IfcMemberType", "IfcPlateType")},
}

_CLASS_RE = re.compile(rb"=\s{0,4}(IFC[A-Z0-9]{2,60}TYPE)\s{0,4}\(")
_CLASS_CACHE: dict[tuple[str, int, int], frozenset[str]] = {}
_CANON = {c.upper(): c for group in (BASE_SYSTEMS, *TYPOLOGY_SYSTEMS.values())
          for classes in group.values() for c in classes}


def _pack_classes(path: Path) -> frozenset[str]:
    """The set of IFC type classes a pack instantiates, read straight off the STEP text.

    A text scan rather than a parse: the question is only *which classes appear*, and parsing 56
    packs to answer it would cost seconds per call for no extra truth. Cached on (path, size, mtime)
    so a shelf that hasn't changed is scanned once.
    """
    st = path.stat()
    key = (str(path), st.st_size, int(st.st_mtime))
    hit = _CLASS_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        raw = path.read_bytes()
    except OSError:
        return frozenset()
    # STEP writes class names upper-case; fold to the schema's CamelCase spelling so the requirement
    # tables above can be written the way the schema does. An entity we never ask for keeps its raw
    # upper-case name — it is still counted, just never matched.
    found = frozenset(_CANON.get(m.group(1).decode("ascii"), m.group(1).decode("ascii"))
                      for m in _CLASS_RE.finditer(raw))
    _CLASS_CACHE[key] = found
    return found


def shelf_classes() -> frozenset[str]:
    """Every IFC type class the installed external shelf can place."""
    root = external_dir()
    if not root.is_dir():
        return frozenset()
    out: set[str] = set()
    for p in sorted(root.glob("*.ifc")):
        out |= _pack_classes(p)
    return frozenset(out)


def coverage(typology: str | None = None) -> dict[str, Any]:
    """Can the installed shelf model this kind of building?

    Reports per system: what it requires, what the shelf actually has, and what is missing — so an
    incomplete shelf names the gap instead of failing at placement time. ``satisfied`` means *every*
    required class for that system is present, because a system half-covered is a system whose
    drawings won't issue: an HVAC package with terminals and no duct is not 50% of an HVAC package.
    """
    keys = sorted(TYPOLOGY_SYSTEMS) if typology is None else [typology]
    unknown = [k for k in keys if k not in TYPOLOGY_SYSTEMS]
    if unknown:
        raise ValueError(f"unknown typology {unknown[0]!r} — known: {sorted(TYPOLOGY_SYSTEMS)}")
    have = shelf_classes()
    out: list[dict[str, Any]] = []
    for key in keys:
        systems = []
        for name, required in ((*BASE_SYSTEMS.items(), *TYPOLOGY_SYSTEMS[key].items())):
            missing = sorted(set(required) - have)
            systems.append({"system": name, "required": list(required),
                            "present": sorted(set(required) & have),
                            "missing": missing, "satisfied": not missing})
        done = [s for s in systems if s["satisfied"]]
        out.append({"typology": key, "systems": systems,
                    "satisfied_systems": len(done), "total_systems": len(systems),
                    "satisfied_pct": round(100.0 * len(done) / len(systems), 1),
                    "buildable": len(done) == len(systems),
                    "missing_systems": [s["system"] for s in systems if not s["satisfied"]]})
    return {"typologies": out, "shelf_classes": len(have),
            "buildable": [r["typology"] for r in out if r["buildable"]],
            "not_buildable": [r["typology"] for r in out if not r["buildable"]]}


def read(name: str) -> tuple[bytes, dict[str, Any]]:
    """Pack bytes + a provenance record (name, size, sha256, and its manifest row if described).
    The digest goes into the audit trail so an import can later be tied to exact content."""
    path = resolve(name)
    data = path.read_bytes()
    meta = _manifest(external_dir()).get(path.name, {})
    return data, {"pack": path.name, "size_bytes": len(data),
                  "sha256": hashlib.sha256(data).hexdigest(),
                  "described": bool(meta),
                  "discipline": meta.get("discipline"),
                  "declared_types": meta.get("types")}
