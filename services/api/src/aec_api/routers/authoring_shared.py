"""Shared helpers for the authoring router family (REL-3 leaf split of `authoring.py`)."""
from __future__ import annotations

import contextlib
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import storage
from ..models import Project


@contextlib.contextmanager
def staged_ifc(final: Path):
    """Yield a unique staging path and REMOVE it if it is never promoted.

    Every producer can fail between writing the staged bytes and promoting them — a bad upload, a
    generator raising, a 502 from the RVT bridge. Without this the staged file survives, referenced
    by nothing and named so it is easy not to notice. This repository has already run a disk out
    mid-suite once (R41-TEST-RESIDUE, 1.42 GB of orphaned per-test storage), and the lesson there
    was that residue is cheap to create and expensive to find.

    `publish_source_ifc` renames the staged file away, so on the success path there is nothing left
    to remove and the `missing_ok` unlink is a no-op. One context manager rather than `try/finally`
    at each producer, for the same reason the promotion itself is one helper.
    """
    path = staged_ifc_path(final)
    try:
        yield path
    finally:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)


def staged_ifc_path(final: Path) -> Path:
    """A UNIQUE sibling path to write a new model into before it is published.

    Unique per call, which is the whole point. `storage.stream_to_path` already writes
    `<dest>.part` and renames, and that is enough to stop a reader seeing a half-written file —
    but the name is derived from the DESTINATION, so two concurrent uploads to one project share
    it and interleave their bytes into a single `.part` before either renames. *A staging name
    that is a function of the destination is not staging, it is a second shared path.*
    """
    return final.with_name(f".staged-{uuid.uuid4().hex}-{final.name}")


def publish_source_ifc(db: Session, p: Project, pid: str, staged: Path, final: Path) -> str:
    """Promote a fully-written STAGED model to the project's published `source.ifc`, under the lock.

    **The bytes are what readers open, and the pointer is not the only thing that has to be
    serialised.** `bake_layers` and `/edit` take the project lock and then open `p.source_ifc`; a
    producer that wrote the fixed `source.ifc` path outside the lock let them open a file mid-write.
    Locking the assignment alone moved the race rather than closing it — the same correction PR #552
    forced on `under_pid_lock`, one layer down: *a lock proves something about the interval it spans,
    and here the interval has to contain the bytes as well as the pointer.*

    So every producer writes to a unique staged path and promotion happens HERE — rename, storage
    publish, pointer, commit, all inside one critical section. `os.replace` is atomic within a
    filesystem, so a reader holding the lock sees either the old complete file or the new one.

    **The sequence is three steps and only the first undoes itself, so the previous file is kept
    aside and restored if a later step raises.** *Atomic at each step is not atomic across the
    sequence* — without that, a failing `put_stream` or `commit` left the published local path
    holding the new bytes while nothing else had been published.

    What this does NOT make atomic, stated rather than implied: if `put_stream` SUCCEEDS and the
    commit then fails, object storage is left holding the newer bytes while the local file and the
    row are rolled back. Storage is the durable copy rather than what readers open, and the next
    successful publish overwrites it — but it is a real window, and closing it properly means
    publishing immutable versioned artifacts and moving the pointer last, which is a design change
    rather than a guard. Tracked, not silently accepted.

    One helper rather than the same critical section written out at each producer, for the reason
    `connections._lock_key` is one: copies drift, and the drift is invisible until two of them
    interleave. Callers in `async def` routes must run this through `run_in_threadpool` — it blocks
    on a Postgres advisory lock, and taking that on the event loop is the v0.3.703 SSE failure.
    """
    from .. import pid_lock
    with pid_lock.mutating(pid):
        db.refresh(p)
        # ROLLBACK. `os.replace` is atomic, but the publication is three steps and only the first is
        # undone for free. If `put_stream` or `commit` raises after the rename, the published local
        # file -- the one `bake_layers` and the converter open by path -- is already the NEW bytes
        # while the rest of the publication did not happen. So the previous file is kept aside and
        # put back on any failure. *Atomic at each step is not atomic across the sequence.*
        backup = final.with_name(f".rollback-{uuid.uuid4().hex}-{final.name}") if final.exists() else None
        if backup is not None:
            os.replace(final, backup)
        try:
            os.replace(staged, final)                # atomic within the filesystem
            storage.put_stream(f"{storage.safe_seg(pid)}/source.ifc", storage.file_chunks(final))
            p.source_ifc = str(final)
            db.commit()
        except BaseException:
            if backup is not None and backup.exists():
                os.replace(backup, final)            # readers get the previous model back, intact
            raise
        finally:
            if backup is not None:
                with contextlib.suppress(OSError):
                    backup.unlink(missing_ok=True)
    return str(final)


def project_with_source(db: Session, pid: str) -> Project:
    """The project row, 404 when missing, 409 when it has no readable source IFC — the precondition
    every model-derived authoring endpoint shares."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return p


def safe_filename(name: str, fallback: str = "sheet") -> str:
    """Whitelist a download filename segment so a crafted `number` can't break out of the
    Content-Disposition quoting (defence-in-depth; the value is self-reflected only)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", name or "")[:80]
    return cleaned or fallback
