"""openBIM standards & version registry — one source of truth for which open standards this platform
speaks and, per standard, which versions it can **read** and **write**.

The point is *pluggability*: version-specific behaviour lives behind a registry, and the capability
matrix is **derived from the real engines** (BCF versions from `bcf_io`, IFC schemas from
`model_capabilities`) rather than hand-copied — so it can't drift, and adding a future version
(IFC5, BCF 3.x, IDS 2.0) is a registry entry + an adapter, not scattered `if version ==` edits.

`capabilities()` powers `GET /openbim/capabilities` and the compliance surface. Each standard entry:
  { key, name, role, read:[...], write:[...], current, default_write?, api?, notes }
"""
from __future__ import annotations

from typing import Any

# Live version lists pulled from the engines that actually implement them (no duplicated constants).
from . import bcf_io
from . import model_capabilities as _mc

# IFC5 / IFCX is a JSON data read+write path (no geometry yet — that waits on web-ifc/Fragments
# upstream); it's reported separately from the STEP schemas so a caller knows read != full support.
# The write side emits the element/property layer as ifcJSON / IFCX from the model index (ifc5_writer).
_IFC_JSON_READ = ["IFC5"]
_IFC_JSON_WRITE = ["IFC5"]

# Which openBIM standards are pluggable here. Version lists that a live engine owns are filled in
# by _resolve() below from that engine, so this table stays declarative + drift-free.
_REGISTRY: dict[str, dict[str, Any]] = {
    "ifc": {
        "name": "Industry Foundation Classes",
        "role": "model source of truth",
        "read": None,          # <- from model_capabilities.SUPPORTED_SCHEMAS (+ IFC5 JSON)
        "write": ["IFC4", "IFC4X3"],
        "current": "IFC4X3",   # IFC4.3 = ISO 16739-1:2024
        "notes": "IFC is the source of truth; geometry is pre-converted to Fragments for the web viewer. "
                 "IFC4X3 is ISO 16739-1:2024 (infrastructure/alignment). IFC5/IFCX is a JSON "
                 "data read+write path (ifcJSON / IFCX element+property export; geometry waits upstream).",
    },
    "bcf": {
        "name": "BIM Collaboration Format",
        "role": "issue / coordination exchange",
        "read": None,          # <- from bcf_io.SUPPORTED_VERSIONS
        "write": None,         # <- from bcf_io.SUPPORTED_VERSIONS
        "current": "3.0",
        "default_write": bcf_io._BCF_VERSION,
        "notes": "Import auto-detects the version; export takes ?version=2.1|3.0. 3.0 nests "
                 "comments/viewpoints under <Topic> and groups <Labels><Label>.",
    },
    "ids": {
        "name": "Information Delivery Specification",
        "role": "requirements authoring + model validation",
        "read": ["1.0"],
        "write": ["1.0"],
        "current": "1.0",      # IDS 1.0 — official buildingSMART standard since 2024-06
        "notes": "Author IDS 1.0 (ifctester, 100% compliant), validate a model against it, and export "
                 "the non-conformances as a BCF punch list.",
    },
    "bsdd": {
        "name": "buildingSMART Data Dictionary",
        "role": "classification / property dictionary",
        "api": ["v1"],
        "current": "v1",
        "notes": "Class search + canonical URI / property-set resolution against api.bsdd.buildingsmart.org.",
    },
    "cobie": {
        "name": "COBie",
        "role": "facility handover export",
        "write": ["2.4"],
        "current": "2.4",
        "notes": "Model- + closeout-derived Facility/Floor/Space/Type/Component/Attribute worksheets.",
    },
    "cde": {
        "name": "ISO 19650 CDE",
        "role": "common data environment / information management",
        "read": ["ISO 19650"],
        "write": ["ISO 19650"],
        "current": "ISO 19650",
        "notes": "Information containers with S0-S4/A/B suitability + WIP/Shared/Published/Archived states.",
    },
}


def _resolve(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Fill the engine-owned version lists from live code so the matrix reflects what's actually built."""
    out = {"key": key, **{k: v for k, v in entry.items() if v is not None}}
    if key == "ifc":
        out["read"] = list(_mc.SUPPORTED_SCHEMAS) + _IFC_JSON_READ
        out["write"] = list(entry.get("write") or []) + _IFC_JSON_WRITE
    elif key == "bcf":
        out["read"] = list(bcf_io.SUPPORTED_VERSIONS)
        out["write"] = list(bcf_io.SUPPORTED_VERSIONS)
    return out


def standards() -> list[dict[str, Any]]:
    """The resolved per-standard capability entries."""
    return [_resolve(k, v) for k, v in _REGISTRY.items()]


def capabilities() -> dict[str, Any]:
    """Full openBIM capability matrix + a flat read/write index for quick lookups."""
    items = standards()
    return {
        "standards": items,
        # a compact index: standard -> {read, write} version lists (for a caller that just wants "can we?")
        "index": {i["key"]: {"read": i.get("read", []), "write": i.get("write", i.get("api", []))}
                  for i in items},
        "summary": {
            "standards": len(items),
            "ifc_read_schemas": next(i["read"] for i in items if i["key"] == "ifc"),
            "bcf_versions": next(i["read"] for i in items if i["key"] == "bcf"),
        },
    }


def supports(standard: str, version: str, mode: str = "read") -> bool:
    """Does this platform `read` (default) or `write` a given standard version? Powers guards/tests."""
    entry = _REGISTRY.get(standard)
    if not entry:
        return False
    versions = _resolve(standard, entry).get(mode) or []
    return version in versions
