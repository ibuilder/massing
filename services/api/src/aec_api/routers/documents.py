"""Document-control file manager (F2–F6): a role-based, standard-folder document store.

Reads need `viewer`; writes (upload / move / delete) need `editor`. The standard taxonomy is
role-organised — every folder has an owner role (PM owns the business, the Superintendent owns field
execution, the Architect/Engineer own the drawing set) — surfaced per node and filterable, so teams see
the folders they own. Uploads auto-name to the information standard and supersede prior revisions.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from .. import docmanager, filing, folder_template
from ..db import get_db
from ..models import Project
from ..rbac import require_role
from ..throttle import rate_limited

router = APIRouter()
_upload_throttle = rate_limited("doc_upload", 60)


def _project_or_404(pid: str, db):
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")


@router.get("/projects/{pid}/documents/template")
def documents_template(pid: str, _: str = Depends(require_role("viewer"))):
    """The standard folder taxonomy (static) — folders, owner roles, disciplines, required flags."""
    return {"nodes": folder_template.tree(), "roots": folder_template.roots(),
            "required": folder_template.required_paths(), "phases": folder_template.phases()}


@router.get("/projects/{pid}/documents/tree")
def documents_tree(pid: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The project's folder tree with per-folder file counts, required-doc gaps and owner roles."""
    _project_or_404(pid, db)
    return docmanager.tree(pid)


@router.get("/projects/{pid}/documents/folder")
def documents_folder(pid: str, path: str, superseded: bool = False,
                     db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Files in one folder (the file-manager's right pane). `superseded=true` shows old revisions."""
    _project_or_404(pid, db)
    if not folder_template.is_valid(path):
        raise HTTPException(400, f"'{path}' is not a standard folder")
    return docmanager.list_folder(pid, path, include_superseded=superseded)


@router.get("/projects/{pid}/documents/by-role")
def documents_by_role(pid: str, role: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Folders owned by a given role (PM / Superintendent / Architect / Engineer / QS) — the role-based
    view of the tree."""
    _project_or_404(pid, db)
    t = docmanager.tree(pid)
    owned = [n for n in t["nodes"] if (n.get("owner_role") or "").lower() == role.lower()]
    return {"role": role, "folders": owned, "count": len(owned)}


@router.post("/projects/{pid}/documents/upload", status_code=201)
async def documents_upload(pid: str, path: str = Form(...), file: UploadFile = File(...),
                           title: str | None = Form(None), discipline: str | None = Form(None),
                           doc_type: str | None = Form(None), cde_state: str | None = Form(None),
                           revision: str | None = Form(None),
                           db=Depends(get_db), actor: str = Depends(require_role("editor")),
                           __: None = Depends(_upload_throttle)):
    """Upload a document into a standard folder. Auto-named to the information standard; a new upload of
    the same document supersedes the prior revision (never overwritten — the old one is archived)."""
    _project_or_404(pid, db)
    from starlette.concurrency import run_in_threadpool

    from .. import storage
    try:
        # R39-UPLOAD-CAP-APP: stream rather than `await file.read()`. Documents are the largest
        # thing an ordinary user uploads here, and Starlette has already spooled this one to disk.
        # `docmanager.upload` is synchronous and does its own per-project locking, so the whole call
        # goes to the threadpool — iterating the chunks on the event loop would block every other
        # request for the duration of the write, which is the problem this is meant to remove.
        return await run_in_threadpool(
            lambda: docmanager.upload(pid, path, file.filename or "file", None, actor,
                                      chunks=storage.upload_chunks(file),
                                      title=title, discipline=discipline, doc_type=doc_type,
                                      cde_state=cde_state, revision=revision))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/projects/{pid}/documents/file-model", status_code=201)
def documents_file_model(pid: str, title: str = Form("Federated Model"),
                         discipline: str | None = Form(None), cde_state: str = Form("published"),
                         db=Depends(get_db), actor: str = Depends(require_role("editor")),
                         __: None = Depends(_upload_throttle)):
    """R32-MODEL-IN-TREE — file the project's current `source.ifc` into `12_Model/IFC` as a revision.

    Deliberately an explicit act rather than a hook on the storage write: `source.ifc` is rewritten by
    every edit recipe, so filing on save would mint a revision per keystroke and make the chain
    meaningless. Re-filing under the same `title` supersedes the prior revision, so the as-issued model
    stays recoverable and the current one is what the file manager shows.
    """
    _project_or_404(pid, db)
    try:
        return filing.file_model(pid, actor, title=title, discipline=discipline, cde_state=cde_state)
    except filing.NothingToFile as e:
        raise HTTPException(409, str(e))          # nothing to file is a state, not a bad request
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/projects/{pid}/documents/model-history")
def documents_model_history(pid: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Every filed revision of the model, newest first, **including superseded ones** — the point of
    filing the model is that the as-issued version stays recoverable."""
    _project_or_404(pid, db)
    revs = filing.filed_model_history(pid)
    return {"folder": filing.MODEL_FOLDER, "count": len(revs), "revisions": revs,
            "model_present": filing.has_model(pid)}


@router.post("/projects/{pid}/documents/{fid}/move")
def documents_move(pid: str, fid: str, path: str = Form(...),
                   db=Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Move a file to another standard folder."""
    _project_or_404(pid, db)
    try:
        return docmanager.move(pid, fid, path, actor)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "file not found")


@router.delete("/projects/{pid}/documents/{fid}")
def documents_delete(pid: str, fid: str, hard: bool = False,
                     db=Depends(get_db), _: str = Depends(require_role("editor"))):
    """Delete a file (soft by default — keeps the audit trail; `hard=true` removes the blob)."""
    _project_or_404(pid, db)
    if not docmanager.delete(pid, fid, hard=hard):
        raise HTTPException(404, "file not found")
    return {"deleted": fid, "hard": hard}


@router.get("/projects/{pid}/documents/{fid}/download")
def documents_download(pid: str, fid: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Download a file's bytes."""
    _project_or_404(pid, db)
    got = docmanager.get_file(pid, fid)
    if not got:
        raise HTTPException(404, "file not found")
    data, name, ctype = got
    return Response(data, media_type=ctype,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/projects/{pid}/documents/health")
def documents_health(pid: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Document-control health: naming compliance, required-folder coverage, revision control, CDE
    spread, orphans."""
    _project_or_404(pid, db)
    return docmanager.health(pid)


@router.get("/projects/{pid}/documents/phase-gaps")
def documents_phase_gaps(pid: str, phase: str, db=Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Required-document gaps for a design phase (AIA SD / DD / CD / CA / CLOSEOUT)."""
    _project_or_404(pid, db)
    return docmanager.phase_gaps(pid, phase)
