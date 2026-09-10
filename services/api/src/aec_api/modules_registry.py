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

from .apppaths import bundle_dir, repo_root
from .db import Base


# `services/api/modules` in a checkout, `<bundle>/modules` in a frozen build, or whatever
# AEC_MODULES_DIR names. The bundled default is stated HERE rather than left to the desktop
# entry point to set: this module is imported by things that never go through it, and a
# default that only one caller installs is a default that is usually absent.
def _default_modules_dir() -> Path:
    bundle = bundle_dir()
    if bundle:
        return bundle / "modules"
    root = repo_root()
    if root:
        return root / "services" / "api" / "modules"
    # Neither a bundle nor a checkout (an installed package). `Path("modules")` would be the
    # obvious last resort and is the wrong one: it is CWD-relative, so what it names depends on
    # where the process happened to be started, and `load_registry` would find a different
    # catalog -- or somebody else's -- depending on the working directory. An absolute path
    # beside this package is deterministic; it not existing is the honest answer, and
    # AEC_MODULES_DIR is how such an install says where the catalog really is.
    return Path(__file__).resolve().parent / "modules"


MODULES_DIR = Path(os.environ.get("AEC_MODULES_DIR") or _default_modules_dir())

REGISTRY: dict[str, dict] = {}
TABLES: dict[str, Table] = {}
# reverse index of reference fields: target_module -> [(source_module, field_name, label)]
# lets a record show "what points at me" without scanning every module.
REVERSE_REFS: dict[str, list[tuple[str, str, str]]] = {}


def reference_fields(mod: dict) -> list[dict]:
    """Fields that point at another module's record (type == 'reference')."""
    return [f for f in mod.get("fields", []) if f.get("type") == "reference" and f.get("module")]


#: Suffixes a reference field carries over the free text it was added BESIDE.
#:
#: MOD-SWEEP's additive pattern never converts a text field; it adds a reference next to it, so a
#: register in use across the change holds both eras at once. Anything that answers a question about
#: "the party" therefore has to know the two fields are one concept.
#:
#: This lived only in `services/api/test_module_fields.py` until PAIR-FILTER, which is the point the
#: rule stopped being an assertion about the manifests and started deciding which ROWS a query
#: returns. A rule that shapes results is production code. The test now imports it from here, and
#: `apps/web/src/portal/register/fieldPairs.ts` mirrors it in TypeScript with a test that reads this
#: file and fails if the two lists disagree — three copies would drift, and a drift is silent: the
#: pair simply stops being detected.
REF_SUFFIXES = ("_company", "_loc", "_spec", "_system", "_contact", "_package", "_ref", "_id")


def text_half(name: str, by_name: dict[str, dict]) -> str | None:
    """The free-text field the reference `name` was added beside, or None if it stands alone.

    Two spellings, because the registers use both: `supplier` beside `supplier_company`, and
    `assignee_name` beside `assignee_contact`. The `_name` form was invisible to the first version of
    this rule, so it is spelled out rather than left to be rediscovered.
    """
    f = by_name.get(name)
    if not f or f.get("type") != "reference":
        return None
    for suf in REF_SUFFIXES:
        if not name.endswith(suf):
            continue
        stem = name[: -len(suf)]
        for cand in (stem, f"{stem}_name"):
            if by_name.get(cand, {}).get("type") in ("text", "textarea"):
                return cand
    return None


def reference_half(name: str, by_name: dict[str, dict]) -> str | None:
    """The reference field added beside the free-text field `name`, or None if nothing claims it.

    The inverse of `text_half`, and deliberately NOT derived by string-building a candidate name: a
    text field is half of a pair only if some reference claims it, so this asks the references.
    Building `name + "_company"` and testing for it would miss `assignee_name`/`assignee_contact`
    (whose stems differ) and would invent a pair for any text field that merely shares a prefix with
    a reference. `apps/web/src/portal/register/fieldPairs.ts` makes the same choice for the same
    reason.
    """
    f = by_name.get(name)
    if not f or f.get("type") not in ("text", "textarea"):
        return None
    for other, of in by_name.items():
        if of.get("type") == "reference" and text_half(other, by_name) == name:
            return other
    return None


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
        # R41-SCHEMA-STALE: the field shape `data` was written against, as "<epoch>:<signature>"
        # (module_schema.schema_stamp). Nullable because every row written before this shipped has
        # none, and a backfill would be a LIE — it would stamp historical rows with today's shape,
        # asserting they were validated against a schema that did not exist when they were written.
        # A null here means "unknown", which is the true answer; the payload checks in
        # module_schema.schema_status need no stamp and are what catches a rename on those rows.
        Column("schema_version", String, nullable=True),
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
