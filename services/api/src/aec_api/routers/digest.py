"""R23-DIGEST — deterministic model digest + change detection (project-scoped).

Its own router rather than a section of `analysis.py`: that module is clash detection and IDS
validation, and a model digest is neither. Keeping it separate also means this feature does not
edit a file other work is actively changing.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import source_ifc_path as _source_ifc
from ..rbac import require_role

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


# --- R23-DIGEST — model change detection ---------------------------------------------------------
# There is no version table behind `source_ifc`: a project has one current model, and publishing
# overwrites it. So the diff is **stateless** — the caller keeps the digest it got last time and
# posts it back as the baseline. That is deliberate rather than a shortcut: a digest pruned at
# `storey` is a few kilobytes, the client already has somewhere to put it (a CI artifact, a
# document record, an email attachment), and storing baselines here would mean a migration and a
# retention policy for data whose whole purpose is to be compared once.

@router.get("/projects/{pid}/digest")
def project_digest(
    pid: str,
    scale: str | None = Query(None, pattern="^(project|storey|class|element)$"),
    geometry: bool = False,
    summary: bool = False,
    db: Session = Depends(get_db),
    _sec: str = Depends(require_role("viewer")),
):
    """A deterministic, Merkle-hashed digest of the project's source IFC.

    `scale` prunes the tree (`storey` is the useful default for a stored baseline — kilobytes, and it
    still carries the hashes that prove what the full digest would have said). `geometry=true` meshes
    elements with no base quantities: slow, and it changes what the numbers mean, so a digest taken
    that way can only be diffed against another taken the same way — the refusal is enforced in
    `diff`, not left to the caller to remember.

    `summary=true` returns the one-screen form: project hash, element count, per-storey hashes."""
    from aec_data import model_digest  # type: ignore

    ifc = _source_ifc(db, pid)
    try:
        d = model_digest.digest(ifc, geometry=geometry, prune_at=scale)
    except model_digest.DigestError as e:
        raise HTTPException(422, str(e)) from e
    return model_digest.summary(d) if summary else d


@router.post("/projects/{pid}/digest/diff")
def project_digest_diff(
    pid: str,
    baseline: dict = Body(..., description="a digest previously returned by GET /projects/{pid}/digest"),
    geometry: bool = False,
    db: Session = Depends(get_db),
    _sec: str = Depends(require_role("viewer")),
):
    """Diff the project's **current** source IFC against a baseline digest.

    Returns `compatible: false` with a reason when the two were not produced the same way, rather
    than reporting a configuration change as a change to the building.

    The current digest inherits the baseline's `scale`, so the common case — post back exactly what
    you were given — is compatible by construction. It does **not** inherit the baseline's
    measurement mode. Mirroring that too would be more convenient and is the wrong trade twice over:
    it lets a field in caller-supplied JSON decide whether this request meshes every element in the
    model (minutes of CPU the caller never asked for), and it disarms the one guard that keeps a
    measurement change from being reported as a change to the building. A geometry-measured baseline
    therefore needs an explicit `?geometry=true`, and the refusal says exactly why.
    """
    from aec_data import model_digest  # type: ignore

    if not isinstance(baseline, dict) or "digest_version" not in baseline:
        raise HTTPException(422, "baseline must be a digest object from GET /projects/{pid}/digest")
    mode = baseline.get("mode") or {}
    scale = mode.get("pruned_at")
    if scale is not None and scale not in model_digest.SCALES:
        raise HTTPException(422, f"baseline mode.pruned_at is not a digest scale: {scale!r}")
    ifc = _source_ifc(db, pid)
    try:
        current = model_digest.digest(ifc, geometry=geometry, prune_at=scale)
    except model_digest.DigestError as e:
        raise HTTPException(422, str(e)) from e
    return {"current": model_digest.summary(current), "diff": model_digest.diff(baseline, current)}
