"""unique (project_id, version) on model_versions — the version number is COMPUTED, so two publishes collide

`versions.snapshot()` allocates `version = last.version + 1` after reading the maximum, over an index
on `project_id` alone. Two publishes to one project — two uploads, or a retried convert — both read
7 and both insert 8. Nothing refused it.

## Why this one is worse than the diff being wrong

`versions.review` reads `(project_id, version).first()` and sets `review_status` on whatever comes
back, so approving "version 8" approves one of the two rows and leaves its twin a draft. The rule the
review gate exists to enforce is *issue drawings only from approved versions*.

And `turnover.py` stamps `record_model_version` — a bare integer — into the `data` of a signed
substantial-completion certificate. With two rows carrying that number, **which snapshot the
certificate attests to is decided by `.first()`**, which is to say by nothing.

## The dedupe RENUMBERS, and it does NOT re-sequence

That signed integer is also why the obvious repair is wrong. Re-sequencing a project's versions by
`created_at` would make the numbers match the chronology exactly — and would silently change what an
already-signed certificate points at. A migration must not move the target of a signature.

So every number that exists today stays on the row that has it. Only the LATER members of a duplicate
set move, to `max + 1`, `max + 2`, … in `created_at` order. Existing references keep resolving, and
they resolve to the earliest row — the one that held the number when it was first issued, which is
the only row a reference written at that time could have meant.

**The honest cost, stated rather than hidden:** a renumbered row's new number sits after versions
created later than it, so for that project the numbering no longer matches chronology. `created_at`
still does, and the alternative was invalidating a signature. A `note` is appended to each moved row
saying where it came from, so the history explains itself instead of looking like a gap.

Revision ID: c9f4a8b2e731
Revises: b6e1c4d09a37
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c9f4a8b2e731"
down_revision: str | None = "b6e1c4d09a37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Writers held off across the renumber and the index build, for the reason d5f2a81c6b47 records:
    # a live publish can take the very number just vacated, and the index build then fails and aborts
    # the deploy. SHARE is what CREATE INDEX takes anyway. Postgres only — SQLite has no LOCK TABLE
    # and serialises writers for the whole transaction regardless.
    if conn.dialect.name == "postgresql":
        conn.execute(sa.text("LOCK TABLE model_versions IN SHARE MODE"))

    projects = [r[0] for r in conn.execute(sa.text(
        "SELECT project_id FROM model_versions "
        "GROUP BY project_id, version HAVING COUNT(*) > 1")).all()]
    for pid in dict.fromkeys(projects):                     # de-duplicated, order preserved
        top = conn.execute(sa.text(
            "SELECT MAX(version) FROM model_versions WHERE project_id = :p"), {"p": pid}).scalar() or 0
        dupes = conn.execute(sa.text(
            "SELECT version FROM model_versions WHERE project_id = :p "
            "GROUP BY version HAVING COUNT(*) > 1 ORDER BY version"), {"p": pid}).all()
        for (version,) in dupes:
            rows = conn.execute(sa.text(
                "SELECT id FROM model_versions WHERE project_id = :p AND version = :v "
                "ORDER BY created_at ASC, id ASC"), {"p": pid, "v": version}).mappings().all()
            for row in rows[1:]:                            # rows[0] keeps the number it was issued
                top += 1
                conn.execute(sa.text(
                    "UPDATE model_versions SET version = :new, "
                    # The note is how a reader of the history later understands why version 12 holds
                    # a snapshot older than version 9. Concatenated rather than replaced so an
                    # existing "+3/-1" element summary is not thrown away.
                    "note = COALESCE(note, '') || :suffix WHERE id = :i"),
                    {"new": top, "i": row["id"],
                     "suffix": f" [renumbered from {version}: duplicate number, c9f4a8b2e731]"})

    op.create_index("uq_model_versions_project_version", "model_versions",
                    ["project_id", "version"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_model_versions_project_version", table_name="model_versions")
