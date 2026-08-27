"""Pre-v0.3.1106 storey markups can be moved onto their storey's GlobalId.

v0.3.1106 keyed storey plan markups on the storey's GlobalId instead of its NAME, because a rename
orphaned every pin on the level. The old key is still READ, so nothing already saved disappeared —
but a markup left under it **still orphans on rename**. That residual limitation was recorded at the
time rather than hidden, and this is the backfill that clears it.

It is a route and not an alembic migration for a reason that is not a preference: rekeying needs a
`name → GlobalId` map, and only the project's source IFC holds one. A migration has the database and
not the model.

## What it refuses to guess, and why each refusal matters

* **`dry_run` defaults to TRUE.** The mapping depends on a model that may have been re-uploaded since
  the markups were made, so the caller sees exactly what would move before anything does.
* **An ambiguous name is skipped**, not resolved. Two storeys called "Level 1" — one per building, or
  a duplicated level — mean the name does not identify a GlobalId. Picking either is the same guess in
  the other direction, and it is the guess this whole change exists to stop making.
* **An unmatched name is skipped.** Either the storey is gone, or the key is *already* a GUID — which
  is what makes a second run a no-op instead of a corruption.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_markup_rekey.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_markup_rekey.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_markup_rekey")
for _f in ("./_markup_rekey.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, DrawingMarkup  # noqa: E402
from aec_api.routers.drawings import rekey_storey_markups  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


PID = "P-rekey"

#: Two storeys with distinct names and one DUPLICATED name, so both the mappable and the ambiguous
#: case are exercised by the same fixture. Patched in rather than baked into an IFC, because what is
#: under test is the rekeying rule and not `storey_elevations`.
STOREYS = [
    {"name": "Level 1", "elevation": 0.0, "guid": "GUID_L1"},
    {"name": "Level 2", "elevation": 3.5, "guid": "GUID_L2"},
    {"name": "Twin", "elevation": 7.0, "guid": "GUID_TWIN_A"},
    {"name": "Twin", "elevation": 10.5, "guid": "GUID_TWIN_B"},
    # A storey with NO name. It can never be matched by name — but a markup already keyed on its
    # GlobalId is correctly keyed, and must not be reported as "storey no longer exists".
    {"name": None, "elevation": 14.0, "guid": "GUID_NONAME"},
]


class _FakeDrawings:
    @staticmethod
    def storey_elevations(_model):
        return STOREYS


def run(db, dry_run: bool):
    """Call the route with the model lookup stubbed — the IFC is not what is under test."""
    import aec_data.drawings as real_dw
    import aec_data.ifc_loader as real_loader
    from aec_api import deps

    orig_open, orig_src = real_loader.open_model, deps.source_ifc_path
    orig_storeys = real_dw.storey_elevations
    real_loader.open_model = lambda *_a, **_k: object()
    deps.source_ifc_path = lambda *_a, **_k: "unused.ifc"
    real_dw.storey_elevations = _FakeDrawings.storey_elevations
    # The route resolves `_source_ifc` from its own module namespace, so patch that binding too.
    import aec_api.routers.drawings as route_mod
    orig_route_src = route_mod._source_ifc
    route_mod._source_ifc = lambda *_a, **_k: "unused.ifc"
    try:
        return rekey_storey_markups(PID, dry_run=dry_run, db=db, actor="tester")
    finally:
        real_loader.open_model, deps.source_ifc_path = orig_open, orig_src
        real_dw.storey_elevations = orig_storeys
        route_mod._source_ifc = orig_route_src


def seed(db):
    db.query(DrawingMarkup).filter(DrawingMarkup.project_id == PID).delete()
    rows = [
        DrawingMarkup(project_id=PID, sheet_id="plan:Level 1", note="old name key"),
        DrawingMarkup(project_id=PID, sheet_id="plan:Level 1#pdf", note="old takeoff key"),
        DrawingMarkup(project_id=PID, sheet_id="plan:GUID_L2", note="already a guid key"),
        DrawingMarkup(project_id=PID, sheet_id="plan:Twin", note="ambiguous name"),
        DrawingMarkup(project_id=PID, sheet_id="plan:Demolished", note="storey is gone"),
        DrawingMarkup(project_id=PID, sheet_id="elev:north", note="not a storey plan at all"),
        DrawingMarkup(project_id=PID, sheet_id="plan:GUID_NONAME", note="guid of a nameless storey"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


db = SessionLocal()
try:
    seed(db)

    # ---- dry run: reports, writes nothing ----------------------------------------------------------
    out = run(db, dry_run=True)
    check("the dry run is the default posture and says so", out["dry_run"] is True)
    check("it would move the two name-keyed markups", out["moved"] == 2, f"moved={out['moved']}")
    check("...and it wrote NOTHING", db.query(DrawingMarkup).filter(
        DrawingMarkup.sheet_id == "plan:Level 1").count() == 1)

    check("an ambiguous storey name is reported, not resolved", out["ambiguous_names"] == ["Twin"],
          f"{out['ambiguous_names']}")
    check("a name with no storey behind it is reported too", out["unmatched_names"] == ["Demolished"],
          f"{out['unmatched_names']}")
    # A key that is already a GlobalId is the DESIRED end state. Reporting it beside genuinely
    # unmappable names would make a clean second run read as a partial failure.
    check("...and a key already on a GlobalId is reported separately, not as a problem",
          sorted(out["already_keyed_by_guid"]) == ["GUID_L2", "GUID_NONAME"],
          f"{out['already_keyed_by_guid']}")
    # Review finding: `known_guids` was derived from the name index, which skips nameless storeys —
    # so a markup correctly keyed on one was reported as unmappable. The two sets answer different
    # questions and only one of them may skip a storey.
    check("a nameless storey's GlobalId still counts as already-keyed",
          "GUID_NONAME" in out["already_keyed_by_guid"]
          and "GUID_NONAME" not in out["unmatched_names"], f"{out['unmatched_names']}")

    # ---- apply -------------------------------------------------------------------------------------
    out = run(db, dry_run=False)
    check("applying moves exactly what the dry run predicted", out["moved"] == 2,
          f"moved={out['moved']}")
    keys = {r.note: r.sheet_id for r in db.query(DrawingMarkup).filter(
        DrawingMarkup.project_id == PID).all()}
    check("the name key became the storey's GlobalId", keys["old name key"] == "plan:GUID_L1",
          keys["old name key"])
    check("...and the #pdf takeoff key moved with it, suffix intact",
          keys["old takeoff key"] == "plan:GUID_L1#pdf", keys["old takeoff key"])

    # The three that must NOT move, each for a different reason.
    check("an ambiguous markup is left exactly where it was", keys["ambiguous name"] == "plan:Twin",
          keys["ambiguous name"])
    check("an unmatched markup is left alone", keys["storey is gone"] == "plan:Demolished",
          keys["storey is gone"])
    check("a non-plan sheet is never touched", keys["not a storey plan at all"] == "elev:north",
          keys["not a storey plan at all"])
    check("a key that was ALREADY a guid is unchanged", keys["already a guid key"] == "plan:GUID_L2",
          keys["already a guid key"])

    # ---- the audit trail actually persists ----------------------------------------------------------
    # Review finding, 2026-08-26: `audit.record` only `db.add`s the row, and this route committed
    # BEFORE recording — so the rekey landed and the AuditLog row was discarded when the session
    # closed. A destructive operation with no trail, and nothing failed to say so.
    from aec_api.models import AuditLog  # noqa: PLC0415
    trail = db.query(AuditLog).filter(AuditLog.action == "drawings.markups.rekey_storeys").all()
    check("the rekey leaves an audit row that SURVIVES the commit", len(trail) == 1,
          f"{len(trail)} audit rows — record-then-commit, not commit-then-record")
    check("...naming what moved", bool(trail) and trail[0].detail.get("moved") == 2,
          str(trail[0].detail if trail else None))

    # ---- a capped preview says it capped -------------------------------------------------------------
    check("the preview reports whether it was truncated", out["changes_truncated"] is False
          and out["changes_shown"] == 2,
          f"truncated={out['changes_truncated']} shown={out['changes_shown']}")

    # ---- idempotence: the second run is the real test of "already a guid" ---------------------------
    again = run(db, dry_run=False)
    check("running it twice moves nothing the second time", again["moved"] == 0,
          f"moved={again['moved']} — a non-idempotent backfill is one nobody can safely re-run")
    keys2 = {r.note: r.sheet_id for r in db.query(DrawingMarkup).filter(
        DrawingMarkup.project_id == PID).all()}
    check("...and every key is where the first run left it", keys2 == keys)
finally:
    db.close()

if os.path.exists("./_markup_rekey.db"):
    os.remove("./_markup_rekey.db")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("MARKUP REKEY OK - pre-v0.3.1106 storey markups move onto their storey's GlobalId, the #pdf "
      "takeoff suffix travelling with them. A duplicated storey name is reported rather than "
      "resolved, a vanished storey is left alone, non-plan sheets are untouched, and a second run "
      "moves nothing.")
