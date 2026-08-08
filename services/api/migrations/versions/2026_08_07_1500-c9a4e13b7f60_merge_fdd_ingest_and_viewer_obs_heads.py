"""merge the FDD-ingest and viewer-obs heads

Empty merge revision. It creates no tables and alters no columns; its only job is to give the graph a
single head again so `alembic upgrade head` resolves.

HOW THE FORK HAPPENED, because it is not anybody's mistake and it will happen again. Two PRs were
open at once, both branched from a main whose head was `f4b8d2e17c93`, and both added a migration
naming it as `down_revision`:

  * `b4c1f7d92e08` — mod_fault_finding (R41-FDD-INGEST, #246)
  * `b6d1c48f2a35` — viewer_load_timing (R39-VIEWER-OBS, #249)

Each PR was correct in isolation and each one's Alembic job passed, because **on either branch there
was exactly one head**. The fork exists only in the union, so no per-PR check could see it: the
property being violated is not a property of either change. `alembic upgrade head` on main then failed
with "Multiple head revisions are present", which is where it surfaced — after both had landed.

That is the general shape worth remembering: *a check that runs per-branch cannot catch a conflict
that only exists after the merge.* The defences that do work are (a) requiring a branch to be up to
date with main before merging, and (b) failing fast and legibly on main, which is what
`test_alembic_single_head.py` now does — it names the two heads and their common parent instead of
leaving a reader with alembic's message and eighteen files to diff.

MERGE RATHER THAN RE-POINTING. Re-pointing `b6d1c48f2a35` at `b4c1f7d92e08` would give a linear
history and was tempting, since both landed within the hour. It is rejected because a re-point is a
silent lie to any database that already ran the migration under its old parent — CI ran both, and
sibling sessions hold local databases at one head or the other. A merge node is correct for every
starting state, which a rewrite is not.

Revision ID: c9a4e13b7f60
Revises: b4c1f7d92e08, b6d1c48f2a35
Create Date: 2026-08-07 15:00:00.000000
"""
from __future__ import annotations

revision = "c9a4e13b7f60"
down_revision = ("b4c1f7d92e08", "b6d1c48f2a35")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do — the two branches touch disjoint tables (`mod_fault_finding`, `viewer_load`)."""


def downgrade() -> None:
    """Nothing to undo; downgrading past this point re-opens the two heads, which is the truth."""
