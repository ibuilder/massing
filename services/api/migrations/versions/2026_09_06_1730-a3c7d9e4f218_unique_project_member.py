"""one membership row per (project, user) — revocation was silently failing

`rbac.grant` is a read-decide-insert on `(project_id, user)`, and `project_members` has carried only
two SEPARATE non-unique indexes — one per column, nothing spanning the pair — since the schema
baseline. Two concurrent grants for one person (an admin double-clicking "Add member", a SCIM sync
racing a manual add) therefore both read "not a member" and both INSERT, and nothing refuses the
second row.

The consequence is not cosmetic, and it is worse than the three tables `d5f2a81c6b47` and
`e7b3f4a9c218` fixed this morning:

  - `rbac.role_for` reads `.first()`, and `require_role` calls it on EVERY protected route — so with
    two rows the effective permission is whichever row the database happened to return.
  - `remove_member` deletes `.first()`, i.e. ONE row. The route returns 200, the person disappears
    from the member list, and they still have the project. **Revocation reported success and did not
    happen.**

The constraint is the half that makes the code fix work — `auth.get_or_create_by_key`'s savepoint has
nothing to catch until UNIQUE exists — so both ship together.

WHICH ROW SURVIVES IS A JUDGEMENT CALL, AND IT IS NOT THE SAME ONE THE SIBLING MIGRATIONS MADE.
`e7b3f4a9c218` keeps the earliest row so a dropdown's order does not move; here the rows are
PERMISSIONS, and the two failure directions are not symmetric. Keeping the least-privileged row can
demote the only admin of a project, which `remove_member`'s own "cannot remove the last project
admin" guard exists to prevent and which nothing in the app can undo from the inside. Keeping the
most-privileged row can leave someone with more access than intended — visible in the member list
and correctable with one click. So the survivor is the HIGHEST role, ties broken by the earliest
`created_at`. A duplicate almost always comes from one grant issued twice, in which case the roles
agree and the choice is moot; where they disagree, this fails toward a recoverable state.

`party_role` and `company` are carried forward from the rows being removed when the survivor's are
NULL, so a workflow party recorded against the losing row is not thrown away.

Revision ID: a3c7d9e4f218
Revises: e7b3f4a9c218
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a3c7d9e4f218"
down_revision: str | None = "e7b3f4a9c218"
branch_labels = None
depends_on = None

#: rbac.ROLE_ORDER, as SQL. Kept as a literal rather than imported: a migration must describe the
#: schema as it was at THIS revision, and importing application code would let a later edit to
#: ROLE_ORDER silently change what an old migration does on replay.
_ROLE_RANK = {"viewer": 0, "reviewer": 1, "editor": 2, "admin": 3}


def upgrade() -> None:
    conn = op.get_bind()
    # A writer can INSERT between the dedupe and the index build, and then CREATE UNIQUE INDEX fails
    # with the migration half-done. SHARE blocks writers and permits readers, so the app keeps
    # serving reads for the (brief) duration. Postgres only — SQLite has one writer by construction.
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("LOCK TABLE project_members IN SHARE MODE"))

    dupes = conn.execute(sa.text(
        "SELECT project_id, \"user\" FROM project_members "
        "GROUP BY project_id, \"user\" HAVING COUNT(*) > 1")).all()
    for pid, user in dupes:
        rows = conn.execute(sa.text(
            'SELECT id, role, party_role, company FROM project_members '
            'WHERE project_id = :p AND "user" = :u ORDER BY created_at ASC, id ASC'),
            {"p": pid, "u": user}).mappings().all()
        # Highest role wins; earliest created_at breaks a tie (the ORDER BY above makes `max` stable).
        keep = max(rows, key=lambda r: _ROLE_RANK.get(r["role"], -1))
        for col in ("party_role", "company"):
            if keep[col] is None:
                donor = next((r[col] for r in rows if r["id"] != keep["id"] and r[col] is not None),
                             None)
                if donor is not None:
                    conn.execute(
                        sa.text(f"UPDATE project_members SET {col} = :v WHERE id = :i"),  # noqa: S608
                        {"v": donor, "i": keep["id"]})
        drop = [r["id"] for r in rows if r["id"] != keep["id"]]
        if drop:
            conn.execute(sa.text("DELETE FROM project_members WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=drop, expanding=True)))

    op.create_index("uq_project_members_project_user", "project_members",
                    ["project_id", "user"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_project_members_project_user", table_name="project_members")
