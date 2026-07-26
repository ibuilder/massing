"""The **`.mass` project container** — one zip that is the whole project: geometry (published
Fragments tile + source IFC), every project-scoped database row, and attachment blobs. This is the
Save/Open unit, and the answer to "does the data come down with the model" is yes.

**Renamed from `.mmproj` in v2.** The old name read as *Microsoft Project* to people who had never
seen it, which is the opposite of what it is — this container has never held a byte of XML or any
proprietary format; it is a zip of JSON plus IFC. A file extension that misleads about what is inside
is a defect in its own right, so it became `.mass`. **Existing `.mmproj` files still open** — a rename
that orphans everything anyone already saved is not a rename, it is data loss.

**The container explains itself.** A `README.txt` is written *inside* the zip, in plain English, so
somebody who unzips this in ten years with none of our software can work out what they are holding.
The manifest carries a full **entry inventory** (every path, its role, its size) and — the part that
is easy to omit and dishonest to omit — an explicit **`excluded`** list naming what deliberately did
*not* travel. Users, the audit log, app settings and saved connections are machine- or
account-specific and are left behind on purpose; a container that silently drops them looks complete
and is not.

**A newer container is refused, never misread.** A `.mass` written by a future build may contain
structures this code would misinterpret, and half-importing a project is worse than declining it.

Importing always mints a FRESH project id and regenerates row primary keys (remapping the few
foreign-key links: topic_id and module record_id), so a container can be cloned into the same
database or moved to another machine without collisions."""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from . import storage
from .db import Base
from .models import Project

#: Format id written by this build. `.mass`, v2.
FORMAT = "massing.project"
VERSION = 2
EXTENSION = ".mass"

#: v1, written as `.mmproj`. Still READ so no saved file is orphaned; never written again.
LEGACY_FORMAT = "aec.mmproj"
LEGACY_EXTENSION = ".mmproj"

#: What every reader needs in order to make sense of the container without our code. Written into
#: the zip itself, because documentation that lives in a repository is documentation the person
#: holding the file does not have.
README = """This is a Massing project container (.mass) — a plain ZIP archive.

Everything inside is either JSON (UTF-8) or a standard AEC file format. There is no proprietary
encoding anywhere in this container, and you do not need Massing to read it.

  manifest.json      What this container is: format id, version, when it was written, an inventory
                     of every entry, and `excluded` — what was deliberately NOT included.
  README.txt         This file.
  project.json       The project itself: id, name, origin, and the name of its source IFC.
  data/<table>.json  One file per table. Each is a JSON array of row objects; keys are column names.
  geometry/          The source IFC (open with any IFC tool) and model.frag, a pre-converted
                     geometry tile used for fast viewing. The IFC is the source of truth; the .frag
                     is derived and can be regenerated from it.
  blobs/             File attachments, stored under their original storage keys.

Identity: building elements are referenced by IFC GlobalId throughout. Those ids are stable across
exports and across tools, so a row in data/ can always be tied back to an element in the IFC.

Not included, on purpose (see manifest `excluded`): user accounts, the audit log, application
settings and saved external connections. Those belong to a machine or an account, not to a project.
"""

# global / machine-specific tables never travel in a project bundle
_SKIP_TABLES = {"users", "audit_log", "app_settings", "connections", "alembic_version"}
# child tables whose foreign key into a "parent" row must be remapped on import
_TOPIC_FK = {"comments", "viewpoints", "attachments"}            # -> topics.id
_RECORD_FK = {"record_comments", "record_attachments", "record_activity"}  # -> mod_<module>.id

_IFC_DIR = Path(os.environ.get("IFC_DIR", "/app/ifc"))


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _project_tables():
    """Every metadata table carrying a project_id column — ORM tables and the dynamic mod_*
    module tables alike (they share Base.metadata once the module registry is loaded)."""
    return [t for t in Base.metadata.sorted_tables
            if "project_id" in t.c and t.name not in _SKIP_TABLES]


def _topic_child_tables():
    """Tables scoped to a project only via topic_id (BCF comments/viewpoints/attachments)."""
    return [t for t in Base.metadata.sorted_tables
            if "topic_id" in t.c and "project_id" not in t.c and t.name not in _SKIP_TABLES]


def _attachment_keys(db: Session, pid: str) -> list[str]:
    """Storage keys for every blob owned by the project (record + topic attachments)."""
    from .models import Attachment, RecordAttachment, Topic
    keys = [k for (k,) in db.query(RecordAttachment.storage_key)
            .filter(RecordAttachment.project_id == pid).all()]
    keys += [k for (k,) in db.query(Attachment.storage_key)
             .join(Topic, Attachment.topic_id == Topic.id)
             .filter(Topic.project_id == pid).all()]
    return [k for k in keys if k]


# --- export -------------------------------------------------------------------
def export_bundle(db: Session, pid: str) -> bytes:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "no such project")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps({
            "id": p.id, "name": p.name, "origin": p.origin,
            "source_ifc": Path(p.source_ifc).name if p.source_ifc else None}))
        counts: dict[str, int] = {}
        for t in _project_tables():
            rows = [dict(r._mapping) for r in db.execute(t.select().where(t.c.project_id == pid))]
            if rows:
                z.writestr(f"data/{t.name}.json", json.dumps(rows, default=_json_default))
                counts[t.name] = len(rows)
        # BCF topic children (comments/viewpoints/attachments) are scoped via topic_id
        from .models import Topic
        topic_ids = [tid for (tid,) in db.query(Topic.id).filter(Topic.project_id == pid).all()]
        if topic_ids:
            for t in _topic_child_tables():
                rows = [dict(r._mapping) for r in db.execute(t.select().where(t.c.topic_id.in_(topic_ids)))]
                if rows:
                    z.writestr(f"data/{t.name}.json", json.dumps(rows, default=_json_default))
                    counts[t.name] = len(rows)
        has_frag = storage.exists(f"{pid}/model.frag")
        if has_frag:
            z.writestr("geometry/model.frag", storage.get(f"{pid}/model.frag"))
        if p.source_ifc and Path(p.source_ifc).exists():
            z.writestr(f"geometry/{Path(p.source_ifc).name}", Path(p.source_ifc).read_bytes())
        for key in _attachment_keys(db, pid):
            if storage.exists(key):
                z.writestr(f"blobs/{key}", storage.get(key))
        # The container documents itself. Documentation that lives in a repository is documentation
        # the person holding the file does not have.
        z.writestr("README.txt", README)
        # A full inventory, so a reader can check what it received against what was meant to be sent
        # rather than inferring completeness from the absence of an error.
        entries = sorted(({"path": zi.filename, "bytes": zi.file_size} for zi in z.infolist()),
                         key=lambda e: str(e["path"]))
        z.writestr("manifest.json", json.dumps({
            "format": FORMAT, "version": VERSION, "extension": EXTENSION,
            "exported_at": _now_iso(),
            "project": {"id": pid, "name": p.name}, "tables": counts,
            "has_frag": has_frag,
            "entries": entries,
            # STATED, not silent. These tables are machine- or account-specific and are left behind
            # deliberately; a container that drops them without saying so looks complete and is not.
            "excluded": {
                "tables": sorted(_SKIP_TABLES),
                "why": "machine- or account-specific: user accounts, the audit log, application "
                       "settings and saved external connections belong to an installation, not to "
                       "a project, and importing them would overwrite the destination's own.",
            },
            "reads": [f"{FORMAT} v{VERSION}", f"{LEGACY_FORMAT} v1 ({LEGACY_EXTENSION})"],
        }, indent=2))
    return buf.getvalue()


# --- import -------------------------------------------------------------------
def _coerce_datetimes(t, row: dict) -> dict:
    """Parse ISO strings back into datetimes for DateTime columns (Postgres core insert needs it)."""
    for col in t.c:
        if isinstance(col.type, DateTime) and isinstance(row.get(col.name), str):
            try:
                row[col.name] = datetime.fromisoformat(row[col.name].replace("Z", "+00:00"))
            except ValueError:
                row[col.name] = None
    return row


def import_bundle(db: Session, data: bytes, *, new_name: str | None = None) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, f"not a valid project container ({EXTENSION} is a ZIP archive)")
    names = set(z.namelist())
    if "manifest.json" not in names:
        raise HTTPException(400, "not a project container — manifest.json is missing")
    man = json.loads(z.read("manifest.json"))
    fmt = man.get("format")
    # BOTH formats are read. `.mmproj` was this container's name through v1; renaming it to `.mass`
    # must not orphan a single file anybody already saved, so v1 stays readable forever. Only the
    # current format is ever written.
    if fmt not in (FORMAT, LEGACY_FORMAT):
        raise HTTPException(400, f"unsupported container format {fmt!r} — expected {FORMAT!r} "
                                 f"or {LEGACY_FORMAT!r}")
    # A container from a FUTURE build is refused, not half-read. It may hold structures this code
    # would silently misinterpret, and a partially-imported project is worse than a declined one:
    # the user believes they have their data.
    try:
        ver = int(man.get("version") or 1)
    except (TypeError, ValueError):
        raise HTTPException(400, f"container version is not a number: {man.get('version')!r}") from None
    if fmt == FORMAT and ver > VERSION:
        raise HTTPException(400,
                            f"this container was written by a newer build (format version {ver}; "
                            f"this build reads up to {VERSION}). Refusing rather than importing it "
                            "partially — update Massing and try again.")
    proj = json.loads(z.read("project.json"))

    new_pid = uuid.uuid4().hex
    # source IFC -> a fresh local path under IFC_DIR
    src_path = None
    ifc_name = proj.get("source_ifc")
    if ifc_name and f"geometry/{ifc_name}" in names:
        _IFC_DIR.mkdir(parents=True, exist_ok=True)
        dest = _IFC_DIR / f"{new_pid}_{ifc_name}"
        dest.write_bytes(z.read(f"geometry/{ifc_name}"))
        src_path = str(dest)
    db.add(Project(id=new_pid, name=new_name or proj.get("name") or "Imported project",
                   origin=proj.get("origin"), source_ifc=src_path))
    db.flush()                                   # project row must exist before FK children (Postgres)
    if "geometry/model.frag" in names:
        storage.put(f"{new_pid}/model.frag", z.read("geometry/model.frag"))

    tables = {t.name: t for t in Base.metadata.sorted_tables}
    table_rows = {n[5:-5]: json.loads(z.read(n)) for n in names
                  if n.startswith("data/") and n.endswith(".json")}

    # 1) regenerate primary keys; remember maps for the FK links we need to repair
    topic_map: dict[str, str] = {}
    record_map: dict[tuple[str, str], str] = {}   # (module, old_id) -> new_id
    for name, rows in table_rows.items():
        for r in rows:
            old = r.get("id")
            if old is not None:
                new = uuid.uuid4().hex
                r["id"] = new
                if name == "topics":
                    topic_map[old] = new
                elif name.startswith("mod_"):
                    record_map[(name[4:], old)] = new
            if "project_id" in (tables.get(name).c if name in tables else []):
                r["project_id"] = new_pid

    # 2) repair foreign keys + re-key attachment blobs, then insert
    def reput_blob(r):
        old_key = r.get("storage_key")
        if old_key and f"blobs/{old_key}" in names:
            new_key = f"{new_pid}/{old_key.split('/', 1)[-1]}"
            storage.put(new_key, z.read(f"blobs/{old_key}"))
            r["storage_key"] = new_key

    # insert order: parents (topics, mod_*) before children, project already added
    ordered = (["topics"]
               + [n for n in table_rows if n.startswith("mod_")]
               + [n for n in table_rows if n not in {"topics"} and not n.startswith("mod_")])
    for name in ordered:
        rows = table_rows.get(name)
        t = tables.get(name)
        if not rows or t is None:
            continue
        for r in rows:
            if name in _TOPIC_FK and r.get("topic_id") in topic_map:
                r["topic_id"] = topic_map[r["topic_id"]]
            if name in _RECORD_FK:
                r["record_id"] = record_map.get((r.get("module"), r.get("record_id")), r.get("record_id"))
            if name in {"record_attachments", "attachments"}:
                reput_blob(r)
            _coerce_datetimes(t, r)
            db.execute(t.insert().values({k: v for k, v in r.items() if k in t.c}))
    db.commit()
    return new_pid


# --- delete -------------------------------------------------------------------
def delete_project(db: Session, pid: str) -> dict:
    """Remove a project and everything it owns — project-scoped rows (ORM + mod_* tables), BCF
    topic children, the published Fragments tile, and attachment blobs. Mirrors export_bundle's
    surface so nothing is orphaned."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "no such project")
    # storage blobs first (best-effort) — attachments, then the WHOLE {pid}/ prefix (model.frag,
    # source-IFC copies, props.json, publish_status.json, …) so no orphan blobs survive the delete
    for key in _attachment_keys(db, pid):
        try:
            if storage.exists(key):
                storage.delete(key)
        except Exception:                        # noqa: BLE001 — a missing blob mustn't block delete
            pass
    try:
        storage.delete_prefix(pid)
    except Exception:                            # noqa: BLE001 — best-effort cleanup
        pass
    deleted: dict[str, int] = {}
    # BCF topic children (no project_id) before the topics they hang off
    from .models import Topic
    topic_ids = [tid for (tid,) in db.query(Topic.id).filter(Topic.project_id == pid).all()]
    if topic_ids:
        for t in _topic_child_tables():
            n = db.execute(t.delete().where(t.c.topic_id.in_(topic_ids))).rowcount or 0
            if n:
                deleted[t.name] = n
    for t in _project_tables():
        n = db.execute(t.delete().where(t.c.project_id == pid)).rowcount or 0
        if n:
            deleted[t.name] = n
    db.delete(p)                                 # cascades topics (relationship delete-orphan)
    db.commit()
    return {"deleted": True, "id": pid, "rows": deleted}
