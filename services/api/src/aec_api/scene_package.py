"""Scene packages — the model's semantic half as a portable document, geometry by reference.

WHAT THIS IS
    A scene package is a small JSON manifest plus binary payloads named from it. The manifest carries
    GlobalId-keyed nodes, their property sets, typed relationships and **precomputed indexes** (by IFC
    class, by level); the geometry stays out of it, referenced by id and fetched only when something
    is actually going to draw it. The format is defined by `@massingifc/engine-bridge` and implemented
    twice — TypeScript and the vendored `massingifc_scene` here — with a conformance suite upstream
    that checks the two agree, including whether an absent value is *omitted* or written as `null`.

WHY IT IS WORTH SERVING
    Three things this codebase already believes, made portable:

    1. **Identity is the GlobalId.** Every node is addressed by it, so an answer from a package is
       already in the identity markup, cost and coordination key on. This is the project's first
       non-negotiable, and the format shares it rather than needing a translation layer.
    2. **Geometry and metadata stay separate.** `.frag` is carried as a payload BY REFERENCE, with its
       own content hash — the manifest is small and cacheable even when the geometry is not. Notably
       the format carries Fragments rather than re-encoding to glTF, for the reason this repo would
       give: re-encoding means decoding geometry the engine decodes better and discarding the
       per-element addressing Fragments already has.
    3. **The server does the work once.** The class and level indexes are computed here, at conversion
       time, instead of by every consumer on every load.

    The consumer that benefits most is not our own web client — it already receives class and storey
    per element from `/elements`, which is why this module claims no load-time win there and none is
    asserted below. It is everything that is NOT our web client: an engine importer, a Blender addon,
    a CI check, a native viewer. Those exist today only as "parse the IFC yourself", which is the one
    thing this platform tells people not to do.

WHAT IT DOES NOT DO
    It does not replace `/elements`, it does not stream geometry per element, and it does not make the
    first paint faster. `.frag` is still one blob per project. Saying so here because a new endpoint
    that *sounds* like a performance feature is exactly the kind of claim that gets repeated without
    anyone measuring it.

DETERMINISM
    `generated_at` is derived from the source IFC's own modification time, never from `now()`. A
    manifest that changes on every request cannot be cached, cannot be diffed between two builds, and
    makes a content hash meaningless — and the format's whole change-detection story rests on the hash
    being stable when the model has not moved.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

#: Products IFC declares but that hang outside the spatial hierarchy are NOT silently dropped — the
#: converter reports them and we carry the report into the response. A package that quietly contains
#: fewer elements than the model reads as a complete answer, which is the failure direction that
#: matters: a visible gap gets chased, a silent one gets cited.
MAX_REPORTED_WARNINGS = 20


def _stamp(path: str) -> str:
    """A deterministic `generated_at` for this source file.

    The source IFC's mtime, in UTC. Two conversions of an unchanged model produce byte-identical
    manifests, so the content hash means what the format says it means.
    """
    ts = Path(path).stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _convert(db: Session, pid: str, *, geometry: bytes | None):
    from massingifc_ifc import convert_ifc  # type: ignore

    from .deps import source_ifc_path

    src = source_ifc_path(db, pid)   # 409 if the project has no accessible source IFC
    warnings: list[str] = []
    pkg, payloads = convert_ifc(
        src,
        model_id=pid,
        generated_at=_stamp(src),
        geometry=geometry,
        on_warning=warnings.append,
    )
    return pkg, payloads, warnings


def _geometry(pid: str) -> bytes | None:
    """The project's converted `.frag`, if the pipeline has produced one yet."""
    from . import storage

    key = f"{pid}/model.frag"
    return storage.get(key) if storage.exists(key) else None


def manifest(db: Session, pid: str) -> dict[str, Any]:
    """The manifest alone — nodes, properties, relationships and indexes, no geometry bytes.

    Geometry is omitted rather than referenced-but-absent. A payload entry naming bytes this response
    does not carry would be a promise the caller cannot keep, and the format treats that as an error
    on write for the same reason.
    """
    pkg, _, warnings = _convert(db, pid, geometry=None)
    data = pkg.to_json()
    data["_warnings"] = warnings[:MAX_REPORTED_WARNINGS]
    data["_warning_count"] = len(warnings)
    data["_geometry"] = "omitted — request the package for geometry, or GET the model .frag"
    return data


def package(db: Session, pid: str) -> tuple[bytes, dict[str, Any]]:
    """The full package as a zip: `scene.json` plus the `.frag` payload it names.

    Returns `(zip_bytes, report)`. The report is metadata about the conversion — element count and any
    products the converter could not reach — kept beside the archive rather than inside it, so the
    archive stays exactly what a consumer expects to open.
    """
    from massingifc_scene import MemoryArchive, write_scene_package  # type: ignore

    frag = _geometry(pid)
    pkg, payloads, warnings = _convert(db, pid, geometry=frag)

    # Build in memory, then zip. `ZipArchive` takes a filesystem path, and the container runs with a
    # read-only source tree — writing a scratch archive next to the code is how that rule gets broken.
    archive = MemoryArchive()
    write_scene_package(archive, pkg, payloads)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in archive.entries():
            zf.writestr(name, archive.read(name) or b"")

    report = {
        "nodes": len(pkg.nodes),
        "payloads": len(pkg.payloads),
        "geometry_bytes": len(frag) if frag else 0,
        "geometry_present": frag is not None,
        "warnings": warnings[:MAX_REPORTED_WARNINGS],
        "warning_count": len(warnings),
    }
    return buf.getvalue(), report
