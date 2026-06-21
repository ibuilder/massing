"""File-conversion endpoint for proprietary formats.

Honest by design: .rvt/.dwg/.nwc are closed Autodesk formats with NO open-source reader, so
they cannot be converted to IFC offline. The only paths are the paid Autodesk APS cloud
(RVT→IFC, behind a feature flag + per-translation cost) or the commercial ODA SDK. This
endpoint routes RVT through the APS bridge when configured and returns a clear, actionable
error otherwise — it never fakes a conversion. IFC, .frag (and glTF/OBJ/STL, future) load
fully offline via the normal Open flow."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

router = APIRouter()

_CONVERTER = Path(__file__).resolve().parents[4] / "services" / "converter" / "src" / "cli.mjs"


def _aps_configured() -> bool:
    return bool(os.environ.get("APS_CLIENT_ID") and os.environ.get("APS_CLIENT_SECRET"))


@router.post("/convert")
async def convert(file: UploadFile = File(...)):
    """Convert an uploaded proprietary model to Fragments. RVT via APS (paid) when configured;
    DWG/NWC require the paid APS/ODA bridge. Returns .frag bytes on success."""
    ext = (file.filename or "").lower().rsplit(".", 1)[-1]
    if ext == "rvt":
        if not _aps_configured():
            raise HTTPException(503, "Revit (.rvt) import needs the Autodesk APS bridge "
                                     "(paid, per-translation cost). Set APS_CLIENT_ID and "
                                     "APS_CLIENT_SECRET and retry — there is no open-source RVT reader.")
        # APS configured: RVT → IFC (Model Derivative) → .frag via the Node converter (cli --rvt).
        with tempfile.TemporaryDirectory() as td:
            rvt = Path(td) / (file.filename or "model.rvt")
            frag = Path(td) / "out.frag"
            rvt.write_bytes(await file.read())
            try:
                subprocess.run(["node", str(_CONVERTER), "--rvt", str(rvt), str(frag)],
                               check=True, capture_output=True, timeout=1800)
            except subprocess.CalledProcessError as e:
                raise HTTPException(502, f"APS RVT→IFC translation failed: {(e.stderr or b'').decode()[:300]}")
            except FileNotFoundError:
                raise HTTPException(500, "Node is required for the RVT converter but isn't installed on the server.")
            if not frag.exists():
                raise HTTPException(502, "APS translation produced no fragments output.")
            return Response(frag.read_bytes(), media_type="application/octet-stream",
                            headers={"Content-Disposition": 'attachment; filename="model.frag"'})
    if ext in ("dwg", "nwc"):
        raise HTTPException(501, f".{ext} is a closed Autodesk format with no open-source "
                                 f"converter. It requires the paid Autodesk APS / ODA SDK bridge. "
                                 f"IFC and .frag load offline; glTF/OBJ/STL import is on the roadmap.")
    raise HTTPException(415, f"unsupported format .{ext or '?'}")
