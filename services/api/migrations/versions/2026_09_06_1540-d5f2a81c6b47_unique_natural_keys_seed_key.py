"""unique natural keys on element_verifications + saved_views (SEED-KEY)

Two routes have always claimed a key their table did not have. `verification.set_status`'s
docstring says *"Upserts by (project, guid)"* and `SavedView`'s says *"Owned by project + module +
user + name"* — and both tables carry only NON-unique indexes on those columns. So the
read-decide-insert in each route has nothing refusing a second writer, and a lost race does not
fail: it **succeeds twice**.

That is worse than the primary-key seeding races the 2026-08-27 sweep fixed, not milder. There the
database refused the loser's INSERT, the caller saw one 500, and the retry worked because the
winner's row existed. Here the duplicate lands, and:

  - `element_verifications` is read with `scalar_one_or_none()`, which raises `MultipleResultsFound`
    the moment two rows match. Every LATER read of that element — status, photo upload, the
    coverage dashboard — takes the same path. A **permanent** 500 on one element, un-wedgeable
    without a manual DELETE.
  - `saved_views` is read with `.first()`, which raises nothing and silently returns one of the two.
    The user's saved report forks: they edit one and run the other.

The constraint is the half that makes the code fix work — `auth.get_or_create_by_key`'s savepoint
has nothing to catch until UNIQUE exists — so both ship together.

DEDUPE FIRST, because the deployments that need this migration most are exactly the ones already
holding a duplicate, and `CREATE UNIQUE INDEX` on those would fail. The survivor is the most
recently touched row; NULL columns on it are backfilled from the rows being removed, newest first,
so a photo uploaded against the losing row is not thrown away.

Revision ID: d5f2a81c6b47
Revises: c8a4e2f71b39
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d5f2a81c6b47"
down_revision: str | None = "c8a4e2f71b39"
branch_labels = None
depends_on = None

_EV_CARRY = ("note", "photo_key", "photo_phash", "ifc_class", "storey", "verified_by")


def _dupe_keys(conn, table: str, cols: tuple[str, ...]) -> list[tuple]:
    """The key tuples that appear more than once. Asked of the database rather than by reading the
    whole table, so a clean deployment does no work at all."""
    sel = ", ".join(cols)
    rows = conn.execute(sa.text(
        f"SELECT {sel} FROM {table} GROUP BY {sel} HAVING COUNT(*) > 1")).all()
    return [tuple(r) for r in rows]


def upgrade() -> None:
    conn = op.get_bind()

    # --- element_verifications: keep the newest by modified_at, carrying NULLs forward ------------
    for pid, guid in _dupe_keys(conn, "element_verifications", ("project_id", "guid")):
        rows = conn.execute(sa.text(
            "SELECT * FROM element_verifications WHERE project_id = :p AND guid = :g "
            "ORDER BY modified_at DESC, id DESC"), {"p": pid, "g": guid}).mappings().all()
        keep, drop = rows[0], rows[1:]
        fill = {c: keep[c] for c in _EV_CARRY if keep[c] is None}
        for r in drop:                       # newest first, so the freshest non-NULL wins
            for c in list(fill):
                if fill[c] is None and r[c] is not None:
                    fill[c] = r[c]
        fill = {c: v for c, v in fill.items() if v is not None}
        if fill:
            sets = ", ".join(f"{c} = :{c}" for c in fill)
            conn.execute(sa.text(f"UPDATE element_verifications SET {sets} WHERE id = :id"),
                         {**fill, "id": keep["id"]})
        conn.execute(sa.text("DELETE FROM element_verifications WHERE id IN :ids").bindparams(
            sa.bindparam("ids", value=[r["id"] for r in drop], expanding=True)))

    # --- saved_views: keep the newest by created_at ----------------------------------------------
    for pid, mod, user, name in _dupe_keys(
            conn, "saved_views", ("project_id", "module", '"user"', "name")):
        rows = conn.execute(sa.text(
            'SELECT id FROM saved_views WHERE project_id = :p AND module = :m AND "user" = :u '
            "AND name = :n ORDER BY created_at DESC, id DESC"),
            {"p": pid, "m": mod, "u": user, "n": name}).mappings().all()
        drop = [r["id"] for r in rows[1:]]
        if drop:
            conn.execute(sa.text("DELETE FROM saved_views WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=drop, expanding=True)))

    op.create_index("uq_element_verifications_project_guid", "element_verifications",
                    ["project_id", "guid"], unique=True)
    op.create_index("uq_saved_views_owner_name", "saved_views",
                    ["project_id", "module", "user", "name"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_saved_views_owner_name", table_name="saved_views")
    op.drop_index("uq_element_verifications_project_guid", table_name="element_verifications")
