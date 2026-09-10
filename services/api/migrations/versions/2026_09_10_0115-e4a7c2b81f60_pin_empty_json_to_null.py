"""Normalise empty pin JSON to NULL, so a capped pin total stops being an upper bound.

`pins._topic_pin_where` selects pin CANDIDATES in SQL with `anchor IS NOT NULL OR element_guids IS
NOT NULL`, and `pins.pin_fields` then applies the exact test in Python. A stored `{}`, `[]` or `[""]`
is **non-NULL**, so it passes the SQL half and fails the exact half. That gap is the entire reason
`resolve_pins` reports `total_counts_candidates` and the printed plan sheet prints `~` before the
project total.

Two write sites in `modules.py` could persist those values; both were normalised to `or None` in
PR #492, so **no new rows carry them**. This sweeps the rows written before that.

**The other nine write sites were read and cannot produce this** (derived, not assumed): every
`anchor` writer stores either `None` or a fully-populated `{x,y,z}` — `codecheck._anchor` returns a
dict or `None`, never `{}` — and the remaining `element_guids` writers either end in `or None` or
build a list literal from IFC GlobalIds.

**Why the decision runs in Python rather than in the WHERE clause.** `anchor` and `element_guids` are
`JSON`, not `JSONB`. PostgreSQL's `json` type has **no equality operator**, so `WHERE anchor = '{}'`
is not a subtle portability wart, it is a hard `UndefinedFunction` error. Casting to text would work
but compares a serialisation (`{}` vs `{ }`) rather than a value. SQL narrows to non-NULL candidates;
Python decides.

The predicate below is a deliberate SELF-CONTAINED copy of `pins.pin_fields` rather than an import.
A migration is a point-in-time operation and must keep meaning what it meant when it ran, even after
the app's definition moves. `services/api/test_pin_empty.py` asserts the two agree TODAY, so the
copy cannot drift silently while it still matters.

Revision ID: e4a7c2b81f60
Revises: c9f4a8b2e731
"""
from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4a7c2b81f60"
down_revision: str | None = "c9f4a8b2e731"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The eleven spatial registers, as `pins.SPATIAL_MODULES` had them when this migration was written.
#: Spelled out rather than imported for the same reason the predicate is: a migration that changes
#: meaning when a tuple elsewhere changes is not a record of what happened.
_SPATIAL = ("rfi", "punchlist", "observation", "clash", "inspection", "snag", "defect",
            "safety_observation", "quality_issue", "field_report", "photo")


def _loads(v):
    """JSON columns come back decoded on some drivers and as text on others. Accept both."""
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return v


def _is_empty_anchor(v) -> bool:
    """True when this anchor value is non-NULL but the exact test would reject it."""
    v = _loads(v)
    return not (isinstance(v, dict) and v)


def _is_empty_guids(v) -> bool:
    """True when this element_guids value is non-NULL but holds no usable GUID."""
    v = _loads(v)
    return not [g for g in (v or []) if g]


def _sweep(conn, table: str, cols: tuple[str, ...]) -> int:
    """NULL out every empty-but-not-null value in `cols`. Returns rows changed."""
    insp = sa.inspect(conn)
    if not insp.has_table(table):
        return 0                      # a register whose module is not installed here
    have = {c["name"] for c in insp.get_columns(table)}
    cols = tuple(c for c in cols if c in have)
    if not cols:
        return 0
    sel = sa.text(f"SELECT id, {', '.join(cols)} FROM {table} "
                  f"WHERE {' OR '.join(f'{c} IS NOT NULL' for c in cols)}")
    changed = 0
    for row in conn.execute(sel).mappings().all():
        empty = [c for c in cols
                 if row[c] is not None
                 and (_is_empty_anchor(row[c]) if c == "anchor" else _is_empty_guids(row[c]))]
        if not empty:
            continue
        conn.execute(sa.text(f"UPDATE {table} SET {', '.join(f'{c} = NULL' for c in empty)} "
                             f"WHERE id = :i"), {"i": row["id"]})
        changed += 1
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    _sweep(conn, "topics", ("anchor", "element_guids"))
    for key in _SPATIAL:
        _sweep(conn, f"mod_{key}", ("element_guids",))


def downgrade() -> None:
    """Not reversible, and deliberately a no-op rather than a lie.

    The rows this nulls held `{}` / `[]` / `[""]`, which carry no information the exact test can use
    — there is nothing to restore them *to* that differs from NULL in any behaviour. Writing an
    `UPDATE ... SET anchor = '{}'` here would invent rows that were never distinguishable, and would
    re-introduce the very upper-bound this removes.
    """
