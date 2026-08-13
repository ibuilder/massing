"""``massingcapture.probe`` -- reading what a capture file knows about itself.

Standard library only, and that is the point. Every module here extracts real metadata from a real
format without the library that format usually travels with:

=================  ===========================================================================
``e57``            the XML index: scan positions, poses, structured grids, embedded panoramas
``las``            the public header and VLRs: count, extent, scale, and the EPSG code
``ply``            the header, and the three different things a PLY can be
``mesh``           OBJ, glTF/GLB accessor bounds, STL
``bim``            IFC header, length unit, and the storey list -- floors, for free
``image``          JPEG/PNG/TIFF dimensions, EXIF GPS, GPano and DJI XMP
``media``          MP4/MOV duration and resolution, and the spherical-video markers
``splat``          .splat, .spz, .sog, .ksplat
``text``           PTX setup headers, PTS, XYZ
``structured``     3D Tiles tilesets, Earth Studio camera paths, pose arrays
=================  ===========================================================================

Two conventions hold across all of them:

- ``bounds`` is always ``[xmin, ymin, zmin, xmax, ymax, zmax]``, and ``bounds_sampled`` says whether
  the scan was exhaustive. A sampled extent is fine for a plausibility check and not fine for a
  claim of exactness, and the caller is entitled to know which they have.
- Nothing here converts anything. A probe reads; a job in ``massingcapture.pipeline`` converts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import bim, e57, image, las, media, mesh, plan, ply, splat, structured, text

#: ``asset_format`` to the callable that summarises it. The pipeline dispatches through this, so
#: adding a format means adding a probe module and one line here.
PROBES: dict[str, Any] = {
    "e57": e57.summarise,
    "las": las.summarise,
    "laz": las.summarise,
    "copc": las.summarise,
    "ply": ply.summarise,
    "pts": text.summarise_pts,
    "ptx": text.summarise_ptx,
    "xyz": text.summarise_xyz,
    "obj": mesh.summarise_obj,
    "stl": mesh.summarise_stl,
    "glb": lambda path: mesh.summarise_gltf(path, binary=True),
    "gltf": lambda path: mesh.summarise_gltf(path, binary=False),
    "ifc": bim.summarise,
    "frag": bim.summarise_fragments,
    "jpeg": image.summarise,
    "png": image.summarise,
    "tiff": image.summarise,
    "geotiff": image.summarise,
    "mp4": media.summarise,
    "mov": media.summarise,
    "insv": media.summarise,
    "splat": splat.summarise,
    "ksplat": splat.summarise,
    "spz": splat.summarise,
    "sog": splat.summarise,
    "pdf": plan.summarise_pdf,
    "dxf": plan.summarise_dxf,
    "dwg": plan.summarise_dwg,
    "json": structured.summarise,
    "tileset-json": structured.summarise,
}


def probe(path: str | Path, asset_format: str) -> dict[str, Any]:
    """Run the probe for a format. Never raises: a probe that fails reports why.

    A file that will not read is a fact about the project, not an exception that should abort an
    ingest of two hundred others. The failure lands in the asset's metadata where somebody can see
    it, and the asset is still recorded -- with no bounds, which is exactly the honest outcome.
    """
    reader = PROBES.get(asset_format)
    if reader is None:
        return {"probe": "none", "probe_note": f'No probe for format "{asset_format}".'}
    try:
        summary = reader(Path(path))
    except Exception as thrown:  # noqa: BLE001
        return {
            "probe": "failed",
            "probe_error": f"{type(thrown).__name__}: {thrown}",
        }
    summary.setdefault("probe", "ok")
    return summary


def supports(asset_format: str) -> bool:
    return asset_format in PROBES


__all__ = [
    "PROBES",
    "bim",
    "e57",
    "image",
    "las",
    "media",
    "mesh",
    "ply",
    "probe",
    "splat",
    "structured",
    "supports",
    "text",
]
