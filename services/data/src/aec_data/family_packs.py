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


#: SPDX expressions get written both ways in the wild: a single `license` string, or a `licenses`
#: **list** when content is dual-licensed. Reading only the singular form is why 57 packs that each
#: declared `"licenses": ["CC0-1.0"]` all reported as unlicensed — a shape mismatch presented as a
#: compliance problem. Multiple entries are joined with SPDX `OR`, which is what a list of
#: alternatives means; collapsing it to the first would silently drop terms a redistributor may rely on.
_LICENCE_KEYS = ("licence", "license", "licences", "licenses")


def _licence_value(val: Any) -> str | None:
    if isinstance(val, str) and val.strip():
        return val.strip()
    if isinstance(val, (list, tuple)):
        parts = [str(v).strip() for v in val if str(v).strip()]
        if parts:
            return " OR ".join(dict.fromkeys(parts))
    return None


def _licence_of(d: Any, *keys: str) -> str | None:
    """The licence `d` declares under any of `keys` (default: the four spellings above)."""
    if not isinstance(d, dict):
        return None
    for key in (keys or _LICENCE_KEYS):
        got = _licence_value(d.get(key))
        if got:
            return got
    return None


def _manifest(root: Path) -> tuple[dict[str, dict], dict[str, Any]]:
    """Per-file metadata from a sibling ``manifest.json``, plus the **library-level** metadata.

    Absent or malformed manifest → empty, never an error: the shelf must still list its files.

    Returning the library level matters. A licence is normally declared **once for the library**, not
    repeated on every pack — reading only the per-pack rows made all 57 packs report as `unlicensed`
    while the manifest had said `CC0-1.0` at the top the whole time. Absent and
    declared-somewhere-else are different, and only one of them is a problem.
    """
    path = root / "manifest.json"
    if not path.is_file():
        return {}, {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}, {}
    out: dict[str, dict] = {}
    for p in (raw.get("packs") or []):
        if isinstance(p, dict) and p.get("file"):
            out[str(p["file"])] = p
    lic = raw.get("licensing") if isinstance(raw.get("licensing"), dict) else {}
    library = {
        "licence": _licence_of(lic, "content", "content_licenses") or _licence_of(raw),
        "code_licence": _licence_of(lic, "code", "code_licenses"),
        "attribution": lic.get("attribution"),
        "licence_url": lic.get("url"),
        "notice_url": lic.get("notice"),
        "library": raw.get("library"),
        "version": raw.get("version"),
    }
    return out, {k: v for k, v in library.items() if v}


def _pack_entry(path: Path, meta: dict[str, Any], library: dict[str, Any] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": path.name, "size_bytes": path.stat().st_size}
    for key in ("discipline", "families", "types", "tiers", "version"):
        if key in meta:
            entry[key] = meta[key]
    own = _licence_of(meta)
    if own:
        entry["licence"] = own
        entry["licence_source"] = "pack"
    # a pack inherits the library's licence unless it states its own — that is what a library-level
    # declaration MEANS, and refusing to read it is how content that is licensed reads as if it isn't
    lib = library or {}
    if not entry.get("licence") and lib.get("licence"):
        entry["licence"] = lib["licence"]
        entry["licence_source"] = "library"     # stated, so nobody mistakes it for a per-pack claim
    for k in ("attribution", "licence_url", "notice_url"):
        if lib.get(k) and k not in entry:
            entry[k] = lib[k]
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
    meta, library = _manifest(root)
    packs = [_pack_entry(p, meta.get(p.name, {}), library) for p in sorted(root.glob("*.ifc"))]
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


# ── Batch-1 duplicate merge ─────────────────────────────────────────────────────────────────────
# The upstream review flagged six "overlapping" family keys from the plumbing batch. Reading the packs
# showed only ONE is a genuine duplicate — the rest are a *generic* tier and a *specific* tier, and
# merging those would invent information rather than remove it:
#
#   base `plumbing`:            bathtub · lavatory · shower · sink · toilet · urinal
#   `plumbing-fixtures`:        shower_receptor · sink_kitchen · sink_service · urinal_wall · wc_flush_valve
#
# `wc_flush_valve` is one *kind* of toilet — the fixtures pack carries no tank-type WC, so aliasing
# `toilet` onto it would assert a fixture type nobody specified. `shower_receptor` is a *part* of a
# shower. `sink_kitchen` is not what "sink" means. Those pairs are a legitimate two-tier catalog: you
# schedule the generic at concept and the specific at procurement.
#
# `pipe_copper_l` and `pipe_copper_type_l` ARE the same product under two names, in the same pack.
#
# The merge is done by ALIAS, not deletion. Deleting a key breaks every model that already placed one;
# aliasing keeps those references resolving while the shelf reports a single canonical family.
FAMILY_ALIASES: dict[str, str] = {
    # "Type L" is the ASTM B88 designation for the wall thickness, so it is the name that carries
    # information; the short form is the one that gets retired.
    "pipe_copper_l": "pipe_copper_type_l",
}

#: Generic families that a more specific one *narrows* but does NOT replace. Recorded so the duplicate
#: check stops flagging them and nobody merges them by mistake later.
FAMILY_TIERS: dict[str, tuple[str, ...]] = {
    "toilet": ("wc_flush_valve",),
    "sink": ("sink_kitchen", "sink_service"),
    "shower": ("shower_receptor",),
    "urinal": ("urinal_wall",),
}


def canonical_family(key: str) -> str:
    """The canonical key for a family, following the batch-1 merge.

    An unknown key returns unchanged — this resolves aliases, it does not validate existence.
    """
    return FAMILY_ALIASES.get(str(key or "").strip().lower(), str(key or "").strip().lower())


def is_narrowing(generic: str, specific: str) -> bool:
    """True when `specific` narrows `generic` — a two-tier pair, never a duplicate to merge."""
    return specific in FAMILY_TIERS.get(str(generic or "").strip().lower(), ())


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

    The digest goes into the audit trail so an import can later be tied to exact content — and so
    does the **licence**, taken from the pack's own row or inherited from the library declaration.
    The terms under which content entered a model are the part of provenance an operator is most
    likely to be asked about later, and reconstructing them after the fact means re-reading a
    manifest that may have moved on.
    """
    path = resolve(name)
    data = path.read_bytes()
    rows, library = _manifest(external_dir())
    meta = rows.get(path.name, {})
    licence = _licence_of(meta) or library.get("licence")
    return data, {"pack": path.name, "size_bytes": len(data),
                  "sha256": hashlib.sha256(data).hexdigest(),
                  "described": bool(meta),
                  "discipline": meta.get("discipline"),
                  "declared_types": meta.get("types"),
                  "licence": licence,
                  "code_licence": library.get("code_licence"),
                  "attribution": library.get("attribution")}
