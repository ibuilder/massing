"""Document manager (F2) — an elFinder-style file store over the standard folder taxonomy.

Bytes live in object storage (``{pid}/docs/<folder>/<name>``); a per-project sidecar index
(``{pid}/docs/_index.json``) holds the metadata — folder, discipline, revision, CDE state, owner role,
uploader, size, and the supersede chain — mirroring how the property index is stored. This keeps the
file manager independent of the module-CRUD engine while reusing the same storage backend (local / S3).

Discipline: **never overwrite an approved file.** A new upload of the same document (same title in the
same folder) supersedes the prior revision — the old one is archived (kept for audit), the new one gets
the next revision. Uploads are auto-named to the information standard (``Type_Discipline_Description_
Revision_Date``) and the name is validated (reported, not blocked) via `naming`.
"""
from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime
from typing import Any

from . import classification, folder_template, naming, pid_lock, storage

_INDEX = "{pid}/docs/_index.json"
_MAX_NAME = 120


def _locked(fn):
    """Serialize a load→mutate→save cycle per project (DOC-RACE): without this, two concurrent
    mutations (FastAPI threadpool) could interleave and silently lose the first writer's index entry
    or double-allocate `seq` ids. First positional arg must be `pid`."""
    import functools

    @functools.wraps(fn)
    def wrap(pid, *a, **k):
        with pid_lock.mutating(pid):
            return fn(pid, *a, **k)
    return wrap


def _key(pid: str) -> str:
    return _INDEX.format(pid=pid)


def _load(pid: str) -> dict[str, Any]:
    k = _key(pid)
    if storage.exists(k):
        try:
            return json.loads(storage.get(k))
        except (ValueError, OSError):
            pass
    return {"files": [], "seq": 0}


def _save(pid: str, idx: dict[str, Any]) -> None:
    storage.put(_key(pid), json.dumps(idx).encode("utf-8"))


def _safe(name: str) -> str:
    """A filesystem-safe leaf name (no separators / traversal), length-bounded."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or "file").replace("\\", "/").split("/")[-1])
    return base.strip("-. ")[:_MAX_NAME] or "file"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", str(text or "").title()) or "Document"


def _next_rev(prev: str | None) -> str:
    """Increment a revision token: P01->P02, 00->01, C1->C2; default first rev P01."""
    if not prev:
        return "P01"
    m = re.match(r"^([A-Za-z]*)(\d+)$", prev.strip())
    if not m:
        return "P01"
    alpha, num = m.group(1), m.group(2)
    return f"{alpha}{int(num) + 1:0{len(num)}d}"


def _standard_name(doc_type: str, discipline: str | None, title: str, rev: str, when: datetime) -> str:
    """Build a ``Type_Discipline_Description_Revision_Date`` filename per the information standard."""
    dtype = re.sub(r"[^A-Za-z0-9]+", "", (doc_type or "DOC"))[:8].upper() or "DOC"
    disc = classification.discipline_code(discipline or "") or "G"
    return f"{dtype}_{disc}_{_slug(title)}_{rev}_{when.strftime('%Y-%m-%d')}"


def _active(idx: dict[str, Any]) -> list[dict]:
    return [f for f in idx["files"] if not f.get("superseded") and not f.get("deleted")]


# --- tree + listing -------------------------------------------------------------------------------
def tree(pid: str) -> dict[str, Any]:
    """The standard taxonomy annotated with per-folder active-file counts, required-doc gaps and owner
    role. Counts roll up to parent folders so the tree shows totals at every level."""
    idx = _load(pid)
    active = _active(idx)                       # compute once, not per folder node
    counts: dict[str, int] = {}
    direct: dict[str, int] = {}
    for f in active:
        p = f["folder"]
        direct[p] = direct.get(p, 0) + 1
        # count against the folder and every ancestor
        parts = p.split("/")
        for i in range(len(parts)):
            anc = "/".join(parts[: i + 1])
            counts[anc] = counts.get(anc, 0) + 1
    nodes = []
    for n in folder_template.tree():
        nodes.append({**n, "count": counts.get(n["path"], 0), "direct_count": direct.get(n["path"], 0),
                      "gap": bool(n["required"] and counts.get(n["path"], 0) == 0)})
    return {"project": pid, "nodes": nodes, "total_files": len(active),
            "required_gaps": [n["path"] for n in nodes if n["gap"]]}


def list_folder(pid: str, folder: str, include_superseded: bool = False) -> dict[str, Any]:
    """Files filed directly in `folder` (elFinder's right pane). Superseded revisions hidden by default."""
    idx = _load(pid)
    rows = [f for f in idx["files"] if f["folder"] == folder and not f.get("deleted")
            and (include_superseded or not f.get("superseded"))]
    rows.sort(key=lambda f: (f.get("title", ""), f.get("revision", "")))
    node = folder_template.node(folder)
    return {"folder": folder, "owner_role": node["owner_role"] if node else None,
            "valid_folder": folder_template.is_valid(folder), "files": rows, "count": len(rows)}


def get_file(pid: str, fid: str) -> tuple[bytes, str, str] | None:
    """(bytes, download-name, content-type) for a file id, or None if missing."""
    idx = _load(pid)
    f = next((x for x in idx["files"] if x["id"] == fid and not x.get("deleted")), None)
    if not f or not storage.exists(f["key"]):
        return None
    ctype = mimetypes.guess_type(f["name"])[0] or "application/octet-stream"
    return storage.get(f["key"]), f["name"], ctype


# --- upload (with auto-naming + revision supersede) -----------------------------------------------
@_locked
def upload(pid: str, folder: str, filename: str, data: bytes, actor: str, *, title: str | None = None,
           discipline: str | None = None, doc_type: str | None = None, cde_state: str | None = None,
           revision: str | None = None, when: datetime | None = None) -> dict[str, Any]:
    """File an uploaded document into `folder`. Auto-names to the standard, supersedes any prior revision
    of the same document, and returns the new entry + the naming-validation result."""
    if not folder_template.is_valid(folder):
        raise ValueError(f"'{folder}' is not a standard folder — file into the standard taxonomy")
    node = folder_template.node(folder)
    when = when or datetime.now()
    title = (title or filename.rsplit(".", 1)[0] or "Document").strip()
    discipline = discipline or node.get("discipline") or "General"
    doc_type = doc_type or "DOC"
    cde_state = cde_state or node.get("cde_default") or "shared"

    idx = _load(pid)
    # supersede a prior active revision of the same document (same title, same folder)
    prior = next((f for f in _active(idx) if f["folder"] == folder
                  and f.get("title", "").lower() == title.lower()), None)
    rev = revision or (_next_rev(prior.get("revision")) if prior else "P01")

    ext = ("." + filename.rsplit(".", 1)[1]) if "." in filename else ""
    stored = _safe(_standard_name(doc_type, discipline, title, rev, when) + ext)
    key = f"{pid}/docs/{folder}/{stored}"
    storage.put(key, data)

    if prior:
        prior["superseded"] = True
        prior["cde_state"] = "archived"
        prior["status"] = "Superseded"

    idx["seq"] = int(idx.get("seq", 0)) + 1
    entry = {
        "id": f"f{idx['seq']}", "folder": folder, "name": stored, "orig_name": filename,
        "title": title, "discipline": discipline, "doc_type": doc_type, "revision": rev,
        "cde_state": cde_state, "status": "Issued" if cde_state == "published" else "Draft",
        "owner_role": node.get("owner_role"), "size": len(data), "key": key,
        "uploaded_by": actor, "uploaded_at": when.isoformat(timespec="seconds"),
        "supersedes": prior["id"] if prior else None,
    }
    if prior:
        prior["superseded_by"] = entry["id"]
    idx["files"].append(entry)
    _save(pid, idx)
    return {"entry": entry, "naming": naming.validate_container_name(stored),
            "superseded": prior["id"] if prior else None}


@_locked
def move(pid: str, fid: str, new_folder: str, actor: str) -> dict[str, Any]:
    """Move a file to another standard folder (rewrites the storage key; index updated)."""
    if not folder_template.is_valid(new_folder):
        raise ValueError(f"'{new_folder}' is not a standard folder")
    idx = _load(pid)
    f = next((x for x in idx["files"] if x["id"] == fid and not x.get("deleted")), None)
    if not f:
        raise KeyError(fid)
    old_key = f["key"]
    new_key = f"{pid}/docs/{new_folder}/{f['name']}"
    if storage.exists(old_key):
        storage.put(new_key, storage.get(old_key))
        storage.delete(old_key)
    f["folder"], f["key"] = new_folder, new_key
    node = folder_template.node(new_folder)
    f["owner_role"] = node.get("owner_role") if node else f.get("owner_role")
    _save(pid, idx)
    return f


@_locked
def delete(pid: str, fid: str, hard: bool = False) -> bool:
    """Soft-delete (default) or hard-delete a file. Soft keeps the audit trail; hard removes the blob."""
    idx = _load(pid)
    f = next((x for x in idx["files"] if x["id"] == fid), None)
    if not f:
        return False
    if hard:
        if storage.exists(f["key"]):
            storage.delete(f["key"])
        idx["files"] = [x for x in idx["files"] if x["id"] != fid]
    else:
        f["deleted"] = True
    _save(pid, idx)
    return True


# --- F5: document-control health + F6: phase gaps -------------------------------------------------
def health(pid: str) -> dict[str, Any]:
    """Document-control health: naming compliance, required-folder coverage, revision control, CDE
    spread, orphaned (non-standard-folder) files."""
    idx = _load(pid)
    active = _active(idx)
    total = len(active)
    named_ok = sum(1 for f in active if naming.validate_container_name(f["name"])["valid"])
    with_rev = sum(1 for f in active if (f.get("revision") or "").strip())
    orphans = [f["id"] for f in active if not folder_template.is_valid(f["folder"])]
    req = folder_template.required_paths()
    covered = [p for p in req if any(f["folder"] == p for f in active)]
    by_state: dict[str, int] = {}
    for f in active:
        by_state[f.get("cde_state", "?")] = by_state.get(f.get("cde_state", "?"), 0) + 1

    def _pct(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    return {
        "total_files": total, "by_cde_state": by_state,
        "naming_compliance_pct": _pct(named_ok, total),
        "revision_control_pct": _pct(with_rev, total),
        "required_coverage_pct": _pct(len(covered), len(req)),
        "required_missing": [p for p in req if p not in covered],
        "orphans": orphans,
        "superseded_kept": sum(1 for f in idx["files"] if f.get("superseded")),
        "note": "Health of the document set: names against the standard, coverage of required folders, "
                "revision control, and CDE-state spread. Superseded revisions are retained for audit.",
    }


def phase_gaps(pid: str, phase: str) -> dict[str, Any]:
    """For a design phase (AIA SD/DD/CD/CA/CLOSEOUT), which required documents are present vs missing."""
    idx = _load(pid)
    active = _active(idx)
    items = []
    for chk in folder_template.phase_checklist(phase):
        present = any(f["folder"] == chk["folder"] for f in active)
        items.append({**chk, "present": present})
    missing = [i for i in items if not i["present"]]
    return {"phase": phase.upper(), "items": items, "missing": len(missing),
            "complete": not missing}
