"""A seeding race on a NATURAL key is permanent where the primary-key races were transient.

## The defect

`get_or_create_by_pk` fixed the 2026-08-25 sweep's four sites, and every one of them was keyed by a
PRIMARY key. The sites keyed by a composite natural key were not converted, and — this is the part
worth keeping — they were not *mentioned* either. `cost_db.import_custom_vintage` had written down
what was missing (*"this wants `auth.get_or_create_by_pk`'s idiom with a query instead of a primary
key"*) and nothing acted on it, because a note in a comment is not a check. **A sweep is bounded by
the fix available to it**, and the leftovers do not announce themselves.

`services/api/test_seeding_sweep.py` is the check that would have. It derives the population instead
of listing it, and it found three: `verification.set_status`, `verification.upload_photo` and
`modules.save_view`.

## Why the natural-key version is WORSE, which is the thing this file exists to prove

When the key is a PRIMARY key the database refuses the loser's INSERT. That is one 500, on one
request, and the retry succeeds because the winner's row now exists — bad, and self-clearing.

When the key is only a non-unique index **nothing refuses anything**. The loser's row is written.
`element_verifications` is then read with `scalar_one_or_none()`, so *every later read of that
element* — set status, upload a photo, the coverage rollup — raises `MultipleResultsFound`. The
element is permanently unverifiable and no retry clears it; someone has to DELETE a row by hand.
`saved_views` reads with `.first()` and so raises nothing at all: the user's saved report silently
forks in two, and they edit one and run the other.

So the fix is two halves that do not work apart. `auth.get_or_create_by_key` supplies the savepoint;
migration `d5f2a81c6b47` supplies the UNIQUE constraints **the savepoint has nothing to catch
without**. `legacy` below is the schema as it stood before that migration, and it is in this file
precisely so the severity claim is measured rather than asserted.

## What is faked, and what is not

The same technique as `test_sso_provision_race`, for the same reason it settled on it: SQLite
serialises writers, so the concurrency cannot be reproduced — committing a competing row from a
second connection while this session's transaction is open deadlocks rather than races. So the
*state* a lost race leaves is reproduced instead. Exactly one thing is faked: the loser's first
lookup answers empty, as it would have if it ran before the winner committed. The INSERT that
follows is real, the constraint it collides with is really there, and the `IntegrityError` is the
database's own.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_natural_key_race.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_natural_key_race.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_natural_key_race")

for _f in ("./_natural_key_race.db", "./_natural_key_race_legacy.db"):
    if os.path.exists(_f):
        os.remove(_f)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.exc import IntegrityError, MultipleResultsFound  # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker  # noqa: E402

from aec_api import auth  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import AuditLog, Base, ElementVerification, SavedView  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []
PID, GUID = "P-race", "2O2Fr$t4X7Zf8NOew3FLKU"


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail!r}" if detail else ""))
    if not ok:
        FAILED.append(name)


def _where(pid: str = PID, guid: str = GUID):
    return (ElementVerification.project_id == pid, ElementVerification.guid == guid)


def _competitor(status: str) -> None:
    """Another writer wins the seeding race, in its own committed transaction."""
    other = SessionLocal()
    try:
        other.add(ElementVerification(project_id=PID, guid=GUID, status=status,
                                      verified_by="winner"))
        other.commit()
    finally:
        other.close()


def _blind_first_read(db):
    """Make this session's FIRST read for the racing key answer empty — the one thing faked. The
    INSERT that follows is real, and so is the constraint it hits."""
    real = db.execute
    seen = {"n": 0}

    def execute(statement, *a, **kw):
        res = real(statement, *a, **kw)
        if seen["n"] == 0 and "element_verifications" in str(statement):
            seen["n"] = 1
            return _Empty()
        return res

    class _Empty:
        def scalars(self):
            return self

        def first(self):
            return None

        def scalar_one_or_none(self):
            return None

    db.execute = execute


# --------------------------------------------------------------------------------------------
print("\nthe fix: the loser folds into the winner's row")
db = SessionLocal()
try:
    _competitor("verified")
    # A row the caller has every right to keep — this stands in for the audit entry a route stages
    # before its commit. If the IntegrityError reached the outer transaction it would be lost.
    db.add(AuditLog(action="verification.set_status", actor="loser", method="PATCH",
                    path=f"/projects/{PID}/verification/{GUID}"))
    _blind_first_read(db)

    row, created = auth.get_or_create_by_key(
        db, ElementVerification, _where(),
        lambda: ElementVerification(project_id=PID, guid=GUID, status="installed",
                                    verified_by="loser"))
    check("losing the race does not raise", True)
    check("the caller is handed the WINNER's row, not its own unsaved object",
          row.verified_by == "winner" and created is False, (row.verified_by, created))
    db.commit()

    n = db.scalar(sa.select(sa.func.count()).select_from(ElementVerification)
                  .where(ElementVerification.project_id == PID))
    check("exactly one row exists for the element", n == 1, n)
    staged = db.scalar(sa.select(sa.func.count()).select_from(AuditLog)
                       .where(AuditLog.actor == "loser"))
    check("the loser's other staged row survived the refusal (session still usable)", staged == 1,
          staged)

    # The read the route does on EVERY later request. It is the assertion that matters most: this
    # is the call that raised forever once a duplicate existed.
    try:
        again = db.execute(sa.select(ElementVerification).where(*_where())).scalar_one_or_none()
        check("the route's own later read still resolves to one row", again is not None)
    except MultipleResultsFound as e:                       # pragma: no cover - the bug, if back
        check("the route's own later read still resolves to one row", False, e)
finally:
    db.close()

# --------------------------------------------------------------------------------------------
print("\nmutation A — the same race against the UNGUARDED code, constraint in place")
db = SessionLocal()
try:
    _blind_first_read(db)
    try:
        v = db.execute(sa.select(ElementVerification).where(*_where())).scalar_one_or_none()
        if v is None:
            db.add(ElementVerification(project_id=PID, guid=GUID, status="installed"))
        db.commit()
        check("the unguarded read-decide-insert raises IntegrityError (so the test can fail)",
              False, "it committed — the mutation did not reproduce the race")
    except IntegrityError:
        db.rollback()
        check("the unguarded read-decide-insert raises IntegrityError (so the test can fail)", True)
finally:
    db.close()

# --------------------------------------------------------------------------------------------
print("\nmutation B — the SAME unguarded code against the schema BEFORE d5f2a81c6b47")
# element_verifications as it was: three plain indexes, no unique constraint. This is the half of
# the fix that is easy to mistake for decoration, so it is measured here rather than argued.


class LegacyBase(DeclarativeBase):
    pass


class LegacyEV(LegacyBase):
    __tablename__ = "element_verifications"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(sa.String, index=True)
    guid: Mapped[str] = mapped_column(sa.String, index=True)
    status: Mapped[str] = mapped_column(sa.String, default="installed")


legacy_engine = sa.create_engine("sqlite:///./_natural_key_race_legacy.db")
LegacyBase.metadata.create_all(legacy_engine)
LegacySession = sessionmaker(bind=legacy_engine)

ldb = LegacySession()
try:
    ldb.add(LegacyEV(project_id=PID, guid=GUID, status="verified"))    # the winner
    ldb.commit()
    ldb.add(LegacyEV(project_id=PID, guid=GUID, status="installed"))   # the loser, unrefused
    ldb.commit()
    n = ldb.scalar(sa.select(sa.func.count()).select_from(LegacyEV))
    check("without the constraint the loser's row is ACCEPTED — the race does not fail, it "
          "succeeds twice", n == 2, n)
    try:
        ldb.execute(sa.select(LegacyEV).where(
            LegacyEV.project_id == PID, LegacyEV.guid == GUID)).scalar_one_or_none()
        check("...and the route's own read then raises MultipleResultsFound on every later "
              "request, permanently", False, "it returned a row")
    except MultipleResultsFound:
        check("...and the route's own read then raises MultipleResultsFound on every later "
              "request, permanently", True)
finally:
    ldb.close()

# --------------------------------------------------------------------------------------------
print("\nsaved views — the same race, and the failure mode that raises nothing at all")
db = SessionLocal()
try:
    other = SessionLocal()
    other.add(SavedView(project_id=PID, module="rfis", user="ana", name="Open, mine",
                        config={"filters": {"status": "open"}}, scope="private"))
    other.commit()
    other.close()

    real = db.execute
    seen = {"n": 0}

    def execute(statement, *a, **kw):                        # noqa: ANN001 - local shim
        if seen["n"] == 0 and "saved_views" in str(statement):
            seen["n"] = 1

            class _E:
                def scalars(self):
                    return self

                def first(self):
                    return None
            return _E()
        return real(statement, *a, **kw)

    db.execute = execute
    v, created = auth.get_or_create_by_key(
        db, SavedView,
        (SavedView.project_id == PID, SavedView.module == "rfis",
         SavedView.user == "ana", SavedView.name == "Open, mine"),
        lambda: SavedView(project_id=PID, module="rfis", user="ana", name="Open, mine",
                          config={}, scope="private"))
    db.commit()
    db.execute = real
    n = db.scalar(sa.select(sa.func.count()).select_from(SavedView)
                  .where(SavedView.project_id == PID))
    check("the view is not forked: one row, and the loser edits the row the reader will run",
          n == 1 and created is False, (n, created))
finally:
    db.close()

# --------------------------------------------------------------------------------------------
print("\ncustom enum options — the third instance, and the one the FIRST gate could not see")
# Found by relaxing test_seeding_sweep's own predicate: it required the model's name to appear in a
# lookup call in the same function, and `add_enum_option` reads through `list_enum_options(db, pid)`.
# So a gate reporting "0 unguarded" was not looking at this site at all. The gate no longer asks
# whether a function read the model first; see its docstring.
db = SessionLocal()
try:
    from aec_api.models import EnumOption

    other = SessionLocal()
    other.add(EnumOption(project_id=PID, module="rfis", field="discipline", value="Facade",
                         created_by="winner"))
    other.commit()
    other.close()

    real = db.execute
    seen = {"n": 0}

    def execute(statement, *a, **kw):                        # noqa: ANN001 - local shim
        if seen["n"] == 0 and "enum_options" in str(statement):
            seen["n"] = 1

            class _E:
                def scalars(self):
                    return self

                def first(self):
                    return None
            return _E()
        return real(statement, *a, **kw)

    db.execute = execute
    row, created = auth.get_or_create_by_key(
        db, EnumOption,
        (EnumOption.project_id == PID, EnumOption.module == "rfis",
         EnumOption.field == "discipline", EnumOption.value == "Facade"),
        lambda: EnumOption(project_id=PID, module="rfis", field="discipline", value="Facade",
                           created_by="loser"))
    db.commit()
    db.execute = real
    n = db.scalar(sa.select(sa.func.count()).select_from(EnumOption)
                  .where(EnumOption.project_id == PID))
    check("the option is stored once, so it cannot appear twice in the dropdown "
          "(list_enum_options APPENDS — it does not de-duplicate)", n == 1 and created is False,
          (n, created))
finally:
    db.close()

print()
if FAILED:
    print(f"NATURAL KEY RACE FAILED - {len(FAILED)}: {FAILED}")
    sys.exit(1)
print(
    "NATURAL KEY RACE OK - losing a seeding race on a composite natural key folds into the "
    "winner's row instead of writing a second one, the caller's other staged rows survive, and the "
    "route's own later read still resolves. Both halves are measured: without the savepoint the "
    "IntegrityError escapes, and without the UNIQUE constraint there is no IntegrityError at all — "
    "the duplicate lands and `scalar_one_or_none` raises on every later read of that element, which "
    "is why this class is permanent where the primary-key races were transient."
)
