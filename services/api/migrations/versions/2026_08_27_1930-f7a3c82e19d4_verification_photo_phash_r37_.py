"""element_verifications.photo_phash — R37-TESTED-UNWIRED (`photo_cv.duplicate_of` gets a caller)

`duplicate_of` exists for one abuse: a single photo uploaded against thirty elements to clear a
checklist. It was built, tested, and called by nothing — `routers/verification.py` ran `photo_quality`
and `compare_photos` on upload and never this. Detecting it needs a fingerprint of every OTHER photo
in the project, and re-reading every stored photo from object storage on each upload would make the
check cost O(photos) per upload; a stored hash makes it one indexed query.

Nullable with no server_default, and that is the point: NULL means "not hashed" — a row written before
this column, or a photo no codec here could decode (iPhone HEIC needs `pillow-heif`, which is not a
dependency) — and it must stay distinguishable from "hashed, and unlike everything else". A default
would turn "we never looked" into a hash that matches nothing, and the route reports how many photos it
actually compared against precisely so a clean result cannot be read as a complete one.

Existing rows are NOT backfilled. Backfilling means decoding every stored verification photo, which is
a long job against object storage inside a migration — the wrong place for it. They become comparable
the next time each element's photo is uploaded.

`String`, not `BigInteger`: the dHash is an UNSIGNED 64-bit value and would overflow a signed BIGINT on
Postgres for half its range.

Revision ID: f7a3c82e19d4
Revises: e5f2a91c73d8
Create Date: 2026-08-27 19:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a3c82e19d4"
down_revision = "e5f2a91c73d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("element_verifications", sa.Column("photo_phash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("element_verifications", "photo_phash")
