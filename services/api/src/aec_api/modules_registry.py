"""GC portal module engine — the registry + table foundation, extracted from `modules.py`.

The shared base every other `modules.*` layer builds on: the `module.json` REGISTRY, the per-module
SQLAlchemy TABLES (`mod_<key>`), the reverse-reference index, the field-type selectors, and the table
factory `_table`. A leaf — it imports only `db.Base` + stdlib/sqlalchemy, nothing from `modules.py` — so
`modules.py` (and future `modules_*` splits) import it without a cycle. `modules.py` re-exports these names
so `modules.get_module` / `modules.TABLES` / `modules.load_registry` etc. keep working unchanged.

The REGISTRY / TABLES / REVERSE_REFS globals are mutated in place (never reassigned), so every importer
shares the one dict object and sees `load_registry()`'s population.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import JSON, Column, DateTime, Index, String, Table

from .db import Base

# repo layout: services/api/modules; the frozen desktop build sets AEC_MODULES_DIR to the
# bundled copy (PyInstaller _MEIPASS/modules) since __file__ no longer resolves there.
MODULES_DIR = Path(os.environ.get("AEC_MODULES_DIR") or (Path(__file__).resolve().parents[2] / "modules"))

REGISTRY: dict[str, dict] = {}
TABLES: dict[str, Table] = {}
# reverse index of reference fields: target_module -> [(source_module, field_name, label)]
# lets a record show "what points at me" without scanning every module.
REVERSE_REFS: dict[str, list[tuple[str, str, str]]] = {}


def reference_fields(mod: dict) -> list[dict]:
    """Fields that point at another module's record (type == 'reference')."""
    return [f for f in mod.get("fields", []) if f.get("type") == "reference" and f.get("module")]


def rollup_fields(mod: dict) -> list[dict]:
    """Computed fields that aggregate a numeric field across incoming related records.
    e.g. {"type":"rollup","source_module":"pco_request","source_field":"rough_cost","op":"sum"}"""
    return [f for f in mod.get("fields", []) if f.get("type") == "rollup"]


def input_fields(mod: dict) -> list[dict]:
    """Fields the user actually enters (excludes computed rollups)."""
    return [f for f in mod.get("fields", []) if f.get("type") != "rollup"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _table(key: str) -> Table:
    return Table(
        f"mod_{key}", Base.metadata,
        Column("id", String, primary_key=True),
        Column("project_id", String, index=True),
        Column("ref", String),
        Column("title", String),
        Column("workflow_state", String, index=True),
        Column("party_owner", String, nullable=True),
        Column("assignee", String, nullable=True),
        Column("created_by", String, nullable=True),
        Column("created_at", DateTime(timezone=True)),
        Column("modified_at", DateTime(timezone=True)),
        Column("anchor", JSON, nullable=True),         # {x,y,z} pin on the model
        Column("element_guids", JSON, nullable=True),  # referenced IFC GlobalIds
        Column("links", JSON, nullable=True),          # [{module,id,ref}] change-order chain
        Column("data", JSON),                          # module-defined fields
        # composite index for the hot path: "records in this project in this state" (dashboard
        # rollups, list filters) — more selective than the single-column indexes alone.
        Index(f"ix_mod_{key}_proj_state", "project_id", "workflow_state"),
        # every list_records does `WHERE project_id=? ORDER BY created_at LIMIT/OFFSET` — without this
        # that's a filesort of the whole project's rows on each page (brutal at 100k+ on Postgres).
        Index(f"ix_mod_{key}_proj_created", "project_id", "created_at"),
        # my-work / assignee queues filter `WHERE project_id=? AND assignee=?`.
        Index(f"ix_mod_{key}_proj_assignee", "project_id", "assignee"),
        extend_existing=True,
    )


def load_registry() -> None:
    """Load every modules/<key>/module.json and register its table. Idempotent."""
    if not MODULES_DIR.exists():
        return
    from . import module_schema
    folders = {p.parent.name for p in MODULES_DIR.glob("*/module.json")}
    for mj in sorted(MODULES_DIR.glob("*/module.json")):
        mod = json.loads(mj.read_text(encoding="utf-8"))
        key = mod["key"]
        # Advisory schema check at load: a malformed module logs a warning rather than crashing the
        # API (test_module_config fails the build on any issue). Same rules the config test enforces.
        problems = module_schema.validate_module(mod, known_modules=folders, folder=mj.parent.name)
        if problems:
            import logging
            logging.getLogger("aec_api.modules").warning(
                "module %r has %d config issue(s): %s", key, len(problems), "; ".join(problems))
        REGISTRY[key] = mod
        if key not in TABLES:
            TABLES[key] = _table(key)
    # build the reverse-reference index once everything is registered
    REVERSE_REFS.clear()
    for key, mod in REGISTRY.items():
        for f in reference_fields(mod):
            REVERSE_REFS.setdefault(f["module"], []).append(
                (key, f["name"], mod.get("name", key)))


def get_module(key: str) -> dict:
    mod = REGISTRY.get(key)
    if not mod:
        raise HTTPException(404, f"unknown module {key!r}")
    return mod
