"""A duplicate project_members row makes REVOKING ACCESS silently fail.

## The defect, and why it is the worst table this class has landed on

`rbac.grant` is a read-decide-insert on `(project_id, user)`, and `project_members` carried only two
SEPARATE non-unique indexes — one on each column — since the schema baseline. So two concurrent
grants for one person (an admin double-clicking "Add member", a SCIM sync racing a manual add) both
read "not a member" and both INSERT. Nothing refuses the second row.

Three consequences, and the third is the one that matters:

  1. `rbac.role_for` reads `.first()`. With two rows the effective role is whichever the database
     happened to return — and `require_role` calls this on EVERY protected route.
  2. `rbac.grant` updates `.first()` too, so changing someone's role may write to the row nobody
     reads.
  3. **`remove_member` deletes `.first()` — one row.** The route returns 200, the member disappears
     from the UI, and the person still has the project. Revocation reports success and does not
     happen.

(3) is why this is not merely another instance of the enum-dropdown bug. A duplicated dropdown entry
is visible and harmless; access that survives its own removal is neither.

## Why `test_seeding_sweep` did not catch it — a KNOWN blind spot, met in the wild

That gate reports a conditional branch that inserts a mapped model. `grant` is not written that way:

    existing = db.query(ProjectMember)...first()
    if existing:
        existing.role = role
        return existing          # <- early return
    m = ProjectMember(...)       # <- insert is at function scope, in no branch
    db.add(m)

The insert sits after an early `return`, at function scope. `test_seeding_sweep`'s own docstring
names exactly this — *"an insert guarded by an early `return`, or by `try/except` around the insert
rather than a branch"* — as what it still cannot see. **A named limit is still a limit**: writing the
blind spot down did not stop a live instance of the defect sitting inside it, on the authorisation
table, for the whole time the gate was reporting `0 unguarded`.

It was found from the READ side instead. `test_unique_read_guard` classifies `.first()` reads whose
filter no unique constraint covers, and `role_for` / `grant` / `remove_member` are three of them on
one table. *Two derivations from opposite directions, and only the second one reached this.*

## What is faked, and what is not

The same technique and the same reason as `test_natural_key_race`: SQLite serialises writers, so the
race itself cannot be run — a competing commit from a second connection deadlocks rather than races.
So the STATE a lost race leaves is reproduced, on a legacy table defined below with the pre-fix
schema, and the behaviour is then measured. The duplicate rows are real, the deletes are real, and
the `IntegrityError` in the post-fix case is the database's own.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_member_role_race.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_member_role_race.db")
for _p in ("src", "../data/src"):
    if _p not in sys.path:
        sys.path.insert(0, _p)
for _f in ("./_member_role_race.db", "./_member_role_race_legacy.db"):
    if os.path.exists(_f):
        os.remove(_f)

import sqlalchemy as sa                                              # noqa: E402, I001
from sqlalchemy.exc import IntegrityError                            # noqa: E402
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker  # noqa: E402

from aec_api import auth, rbac                                       # noqa: E402
from aec_api.db import SessionLocal, engine                          # noqa: E402
from aec_api.models import Base, Project, ProjectMember              # noqa: E402

Base.metadata.create_all(engine)

PID, USER = "p-race", "carla@example.com"
FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


# ── 1. the pre-fix schema, and what a lost race does to it ────────────────────────────────────────
class LegacyBase(DeclarativeBase):
    pass


class LegacyPM(LegacyBase):
    """`project_members` EXACTLY as it stood before this change: two separate non-unique indexes,
    nothing spanning the pair. Reproduced here so the severity claim above is measured, not asserted."""
    __tablename__ = "project_members"
    id: Mapped[str] = mapped_column(sa.String, primary_key=True)
    project_id: Mapped[str] = mapped_column(sa.String, index=True)
    user: Mapped[str] = mapped_column(sa.String, index=True)
    role: Mapped[str] = mapped_column(sa.String, default="viewer")
    party_role: Mapped[str | None] = mapped_column(sa.String, nullable=True)


legacy_engine = sa.create_engine("sqlite:///./_member_role_race_legacy.db")
LegacyBase.metadata.create_all(legacy_engine)
LegacySession = sessionmaker(bind=legacy_engine)

ldb = LegacySession()
try:
    ldb.add(LegacyPM(id="m1", project_id=PID, user=USER, role="viewer"))
    ldb.add(LegacyPM(id="m2", project_id=PID, user=USER, role="admin"))
    ldb.commit()
    both = ldb.query(LegacyPM).filter(LegacyPM.project_id == PID, LegacyPM.user == USER).all()
    check("the pre-fix schema ACCEPTS a second row for one (project, user)", len(both) == 2,
          f"{len(both)} rows — nothing refused the loser's INSERT")
    check("...and the two rows disagree about the person's role",
          {r.role for r in both} == {"viewer", "admin"},
          "role_for() reads .first(), so require_role's answer depends on row order")

    # THE ONE THAT MATTERS: remove_member deletes .first(), i.e. ONE row.
    victim = ldb.query(LegacyPM).filter(LegacyPM.project_id == PID, LegacyPM.user == USER).first()
    ldb.delete(victim)
    ldb.commit()
    left = ldb.query(LegacyPM).filter(LegacyPM.project_id == PID, LegacyPM.user == USER).all()
    check("REVOCATION SILENTLY FAILS — after remove_member the person is still a member",
          len(left) == 1,
          f"{len(left)} row survives; the route returned 200 and the member list no longer shows them")
finally:
    ldb.close()


# ── 2. the fixed schema refuses the second row ────────────────────────────────────────────────────
db = SessionLocal()
try:
    db.add(Project(id=PID, name="race"))
    db.commit()
    rbac.grant(db, PID, USER, "viewer")
    db.commit()

    # The unguarded shape, run against the fixed table: the loser's INSERT is now REFUSED, so the
    # duplicate cannot be written at all. This is the half the savepoint has nothing to catch without.
    raised = None
    try:
        db.add(ProjectMember(project_id=PID, user=USER, role="admin"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raised = exc
    check("the fixed schema REFUSES a second row for one (project, user)", raised is not None,
          "uq_project_members_project_user" if raised else "the duplicate was accepted")

    rows = db.query(ProjectMember).filter(
        ProjectMember.project_id == PID, ProjectMember.user == USER).all()
    check("exactly one membership row survives", len(rows) == 1, f"{len(rows)} row(s)")

    # ...and `grant` run twice is an UPDATE, not a second row — the behaviour callers rely on.
    rbac.grant(db, PID, USER, "editor", party_role="Consultant")
    db.commit()
    rows = db.query(ProjectMember).filter(
        ProjectMember.project_id == PID, ProjectMember.user == USER).all()
    check("re-granting updates the existing row rather than inserting",
          len(rows) == 1 and rows[0].role == "editor" and rows[0].party_role == "Consultant",
          [(r.role, r.party_role) for r in rows])
    check("role_for is now unambiguous", rbac.role_for(db, PID, USER) == "editor",
          rbac.role_for(db, PID, USER))

    # THE LOST RACE, folded: the loser's blind first read answers empty, its INSERT collides, and
    # `get_or_create_by_key` returns the WINNER's row instead of 500-ing on a legitimate request.
    m, created = auth.get_or_create_by_key(
        db, ProjectMember,
        (ProjectMember.project_id == PID, ProjectMember.user == USER),
        lambda: ProjectMember(project_id=PID, user=USER, role="admin"))
    check("a lost race folds into the winner's row instead of erroring",
          created is False and m.role == "editor", (created, m.role))
finally:
    db.close()

# ── 3. and `remove_member`'s single delete is now sufficient ──────────────────────────────────────
db = SessionLocal()
try:
    victim = db.query(ProjectMember).filter(
        ProjectMember.project_id == PID, ProjectMember.user == USER).first()
    db.delete(victim)
    db.commit()
    left = db.query(ProjectMember).filter(
        ProjectMember.project_id == PID, ProjectMember.user == USER).count()
    check("REVOCATION NOW HOLDS — one delete removes the membership", left == 0,
          f"{left} row(s) left; role_for -> {rbac.role_for(db, PID, USER)!r}")
finally:
    db.close()

for _f in ("./_member_role_race.db", "./_member_role_race_legacy.db"):
    if os.path.exists(_f):
        os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("\ntest_member_role_race OK - the pre-fix schema accepts the duplicate and revocation silently "
      "fails; the fixed schema refuses it, grant folds a lost race into the winner's row, and one "
      "delete is enough.")
