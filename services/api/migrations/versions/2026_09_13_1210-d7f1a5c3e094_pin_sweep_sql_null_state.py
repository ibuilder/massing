"""Re-sweep the pin columns, asking SQL whether the value is NULL instead of asking Python.

`b3c9e42d18a5` swept `anchor` and `element_guids` on `topics` and thirty-seven registers, and **on
PostgreSQL it skipped exactly the rows it was written to convert.** Its `_sweep` selects the
candidates with `anchor IS NOT NULL OR element_guids IS NOT NULL` and then decides per column in
Python, beginning `if v is None: continue`.

A `json` column holding the JSON scalar `null` is **not SQL NULL** -- and psycopg decodes it, so the
driver hands back Python `None`, indistinguishable at that point from a column that really was SQL
NULL. The row passes the SELECT and is then skipped by the first line of the loop. Measured against
PostgreSQL 16 on a three-row table before any of this was written:

    row  sqlnull    anchor IS NULL=True   driver returned None   -> correctly skipped
    row  jsonnull   anchor IS NULL=False  driver returned None   -> SKIPPED, and it should not be
    row  empty      anchor IS NULL=False  driver returned {}     -> swept

`_sweep` reported `changed=1` and `SKIPPED` was empty, so the run looked clean and said nothing about
the row it had walked past. Those JSON-null rows are precisely the legacy the sweep exists for:
every `None` written to these columns before `b3c9e42d18a5` added `JSON(none_as_null=True)` went in
that way, they satisfy `pins.pin_where`, they fail the exact test in `pins.pin_fields`, and so they
inflate `total_counts_candidates` and put the `~` on the plan sheet's project total.

**SQLite hid it, and not by accident.** There a JSON column is TEXT, the scalar arrives as the four
characters `null`, and `_loads` turns it into `None` *after* the `v is None` guard has already let it
through -- so the conversion happens and every local test passes. This is the same
`null`-is-not-`NULL` distinction `b3c9e42d18a5` was itself about, reappearing one layer up in its own
reader. *A migration that fixes a representation problem has to be careful not to inherit it.*

**Why a new revision rather than a fix to `b3c9e42d18a5`.** That migration has run. Editing it would
change nothing on any database that has it stamped -- which is every database the defect affects --
while making the file disagree with what was actually executed there. The three sweeps before this
one each re-covered ground their predecessors held for the same reason; re-covering it is the point.

**What changed in the mechanism: one SELECT per COLUMN, narrowed to that column.** The predicate
copies below are unchanged from `b3c9e42d18a5`. The reader is not: where the old statement asked for
a row that had *either* column non-NULL and then tried to recover per-column null-state from the
decoded value, each column is now selected under its own `WHERE <col> IS NOT NULL`. Everything that
comes back is therefore non-NULL *in SQL*, so a Python `None` can only be the JSON scalar `null`, and
it is empty rather than absent. The null-state question is answered by the database, which is the
only party that can tell the two apart. A per-column null-flag alias beside the value would work too
and was rejected: it needs an alias that provably collides with no real column, and an extra name to
get wrong is worse than an extra SELECT.

Revision ID: d7f1a5c3e094
Revises: b3c9e42d18a5
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f1a5c3e094"
down_revision: str | None = "b3c9e42d18a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The same thirty-seven registers `b3c9e42d18a5` names, spelled out for the reason
#: `e4a7c2b81f60` gives at length: a migration whose meaning changes when a definition elsewhere
#: changes is not a record of anything. `test_pin_empty.py` asserts this list still covers every
#: register `pins.spatial_modules()` returns, so a register added later is a failing gate rather
#: than a silently unswept table.
_SPATIAL = (
    "asi", "asset_register", "assumption", "bulletin", "climate_site_risk", "coordination_issue",
    "cor", "decision", "deficiency", "directive", "drainage_area", "eticket", "fault_finding",
    "fca_element", "field_verification", "flood_risk", "incident", "inspection", "issue",
    "mep_equipment", "meter", "ncr", "noc", "observation", "pco_request", "photo",
    "procurement_package", "progress_actual", "punchlist", "rfi", "safety_violation",
    "schedule_activity", "sketch", "spec_section", "submittal", "work_order", "zoning",
)

#: Both pin columns, on every table. Named rather than inlined so `test_pin_empty.py` can derive the
#: (table, column) pairs by RUNNING `upgrade()` against a stubbed `_sweep`.
_COLS = ("anchor", "element_guids")

#: The topic table -- not a register, same two columns, same defect.
_TOPICS = "topics"

#: How many ids one UPDATE carries -- see `f2b6d31a7c04`.
_BATCH = 500

#: `(table, id, column)` for every stored value this sweep cannot judge. **Reported, never swept.**
SKIPPED: list[tuple[str, str, str]] = []

#: What a decoded value must BE for its column. See `b3c9e42d18a5`.
_SHAPE = {"anchor": dict, "element_guids": list}


def _wrong_shape(col: str, decoded) -> bool:
    """Is this decoded value the wrong TYPE for its column?

    Carried unchanged from `b3c9e42d18a5`, where it exists because `_is_empty_guids` raised
    `TypeError` on a stored scalar and aborted the whole `alembic upgrade`, and `_is_empty_anchor`
    silently NULLed a wrong-shaped anchor.

    `None` is still not wrong-shaped, but it no longer means what it meant there. Under the
    per-column SELECT in `_sweep`, every value reaching this function is non-NULL *in SQL*, so a
    decoded `None` is the JSON scalar `null` -- empty, and swept by the predicates below. It is
    still not evidence, so it must still not be reported as such.
    """
    return decoded is not None and not isinstance(decoded, _SHAPE[col])


def _loads(v):
    """JSON columns come back decoded on some drivers and as text on others. Accept both."""
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return v


def _decode(v):
    """`(parsed_ok, value)` -- **a parse failure is not an empty value.** See `f2b6d31a7c04`."""
    if isinstance(v, (str, bytes)):
        try:
            return True, json.loads(v)
        except (ValueError, TypeError):
            return False, None
    return True, v


def _is_empty_anchor(v) -> bool:
    """True when this anchor value is non-NULL but the exact test would reject it."""
    v = _loads(v)
    return not (isinstance(v, dict) and v)


def _is_empty_guids(v) -> bool:
    """True when this element_guids value is non-NULL but holds no usable GUID."""
    v = _loads(v)
    return not [g for g in (v or []) if g]


def _sweep(conn, table: str, cols: tuple[str, ...]) -> int:
    """NULL out every empty-but-not-null value in `cols`. Returns rows changed.

    **One SELECT per column, each narrowed to that column being non-NULL.** That is the whole fix:
    everything a given pass returns is non-NULL in SQL, so a Python `None` in it is the JSON scalar
    `null` rather than an absent value, and the two are not otherwise distinguishable once a driver
    has decoded the column. `b3c9e42d18a5` selected the union of both columns and asked Python, which
    on PostgreSQL skipped every legacy row.

    SQL narrows and Python decides, because these are `JSON` rather than `JSONB` and PostgreSQL's
    `json` type has no equality operator.
    """
    insp = sa.inspect(conn)
    if not insp.has_table(table):
        return 0                      # a register whose module is not installed here
    have = {c["name"] for c in insp.get_columns(table)}
    changed = 0
    for col in (c for c in cols if c in have):
        empty_ids: list = []
        sel = sa.text(f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL")
        # **The options go on the STATEMENT, never on the connection** -- see `f2b6d31a7c04`: set on
        # the connection they are inherited by alembic's own `UPDATE alembic_version`, which Postgres
        # then rejects, and SQLite cannot see it because it has no server-side cursor.
        result = conn.execute(sel.execution_options(stream_results=True, yield_per=_BATCH))
        for row in result.mappings():
            ok, decoded = _decode(row[col])
            if not ok or _wrong_shape(col, decoded):
                # Not JSON at all, or JSON of a shape this column never holds. Evidence either way.
                SKIPPED.append((table, str(row["id"]), col))
                continue
            if _is_empty_anchor(decoded) if col == "anchor" else _is_empty_guids(decoded):
                empty_ids.append(row["id"])

        # The cursor is fully drained before a single UPDATE runs: modifying a table while iterating
        # a SELECT over it is undefined behaviour on SQLite.
        for i in range(0, len(empty_ids), _BATCH):
            chunk = empty_ids[i:i + _BATCH]
            names = [f"i{n}" for n in range(len(chunk))]
            binds = ", ".join(f":{n}" for n in names)
            res = conn.execute(sa.text(f"UPDATE {table} SET {col} = NULL WHERE id IN ({binds})"),
                               dict(zip(names, chunk)))
            # Count what the database changed, not what we intended to change.
            changed += res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(chunk)
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    _sweep(conn, _TOPICS, _COLS)
    for key in _SPATIAL:
        _sweep(conn, f"mod_{key}", _COLS)
    if SKIPPED:
        logging.getLogger("alembic.runtime.migration").warning(
            "d7f1a5c3e094: left %d uninterpretable pin value(s) untouched -- unparseable text or the wrong JSON shape for the column (table, id, column): %s",
            len(SKIPPED), ", ".join(f"{t}/{i}/{c}" for t, i, c in SKIPPED[:20])
            + (" ..." if len(SKIPPED) > 20 else ""))


def downgrade() -> None:
    """Not reversible, and deliberately a no-op rather than a lie -- see `e4a7c2b81f60`.

    The rows this nulls held `{}`, `[]`, `[""]` or the JSON scalar `null`. Nothing distinguishes any
    of those from NULL under the exact test in `pins.pin_fields`, so there is no prior state to
    restore that differs in any behaviour.
    """
