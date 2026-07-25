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
from pathlib import Path
from typing import Any

# a pack file is content, not a project model: keep a ceiling so a mis-dropped 2 GB file can't be
# pulled into a source IFC by a single request
MAX_PACK_BYTES = 64 * 1024 * 1024


def library_dir() -> Path:
    from .build_family_library import LIBRARY_DIR
    return Path(LIBRARY_DIR)


def external_dir() -> Path:
    return library_dir() / "external"


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
