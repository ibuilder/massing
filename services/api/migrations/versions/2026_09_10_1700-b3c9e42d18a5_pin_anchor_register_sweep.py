"""Sweep the register `anchor` columns the pin engine has only just started reading.

Two sweeps have run. `e4a7c2b81f60` nulled empty `{}` / `[]` / `[""]` pin values on `topics` (both
columns) and on eleven register names of which five existed (`element_guids` only). `f2b6d31a7c04`
extended the `element_guids` sweep to the thirty-two registers `pins.spatial_modules()` newly
reached. **Neither has ever touched a register's `anchor`,** because until PIN-ANCHOR no reader that
reported a total looked at one: `modules.project_pins` filtered on it but returns a bare list with no
count, so an empty `{}` there cost nothing.

`pins.resolve_pins` now selects register rows with `anchor IS NOT NULL OR element_guids IS NOT NULL`
-- the same predicate topics have always used, shared as `pins.pin_where`. That makes a stored `{}`
on any of the thirty-seven pinnable registers a *candidate* that fails the exact test in
`pins.pin_fields`, which is precisely the gap `pin_total`'s `~` exists to disclose. This closes it
for the newly-read column.

**And it sweeps `element_guids` again, on every table, because those columns were never SQL NULL.**
SQLAlchemy persists a Python `None` in a `JSON` column as the JSON scalar `null`, which is not SQL
NULL -- so `IS NOT NULL` matched every row that had ever been written, the SQL half of every pin
predicate narrowed nothing, and the two earlier sweeps were cleaning up behind a source that refilled
the same shape on the next write. `modules_registry` and `models.Topic` now declare
`JSON(none_as_null=True)` on these four columns, so from this change a `None` is stored as SQL NULL.
This migration is therefore the first of the three that is a backfill rather than a holding action,
and re-covering ground the others hold is the point rather than an oversight.

**The population is the thirty-seven registers `pins.spatial_modules()` returns today**, spelled out
rather than imported for the reason `e4a7c2b81f60` gives at length: a migration whose meaning changes
when a definition elsewhere changes is not a record of anything. It is the UNION of the two earlier
lists' real names, so it deliberately overlaps both -- `anchor` is a column neither swept, so there is
no double work, only one list that is easy to check against `spatial_modules()`.

`services/api/test_pin_empty.py` now derives coverage as **(register, column) pairs** rather than
register names. That distinction is what hid this: every one of these thirty-seven registers was
already recorded as "swept", so widening the engine to read a second COLUMN was invisible to the
check that exists to notice exactly that. **A coverage gate is bounded by the shape of the thing it
counts.**

Revision ID: b3c9e42d18a5
Revises: f2b6d31a7c04
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c9e42d18a5"
down_revision: str | None = "f2b6d31a7c04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Every register the product marks `pinnable`, as `pins.spatial_modules()` returns it today. The
#: two earlier sweeps between them cover this same set for `element_guids`; this covers it for
#: `anchor`, which neither did.
_SPATIAL = (
    "asi", "asset_register", "assumption", "bulletin", "climate_site_risk", "coordination_issue",
    "cor", "decision", "deficiency", "directive", "drainage_area", "eticket", "fault_finding",
    "fca_element", "field_verification", "flood_risk", "incident", "inspection", "issue",
    "mep_equipment", "meter", "ncr", "noc", "observation", "pco_request", "photo",
    "procurement_package", "progress_actual", "punchlist", "rfi", "safety_violation",
    "schedule_activity", "sketch", "spec_section", "submittal", "work_order", "zoning",
)

#: **Both columns, on every table, including ones an earlier sweep already covered.** `anchor` is
#: the column PIN-ANCHOR newly reads. `element_guids` is re-swept because the JSON-null defect below
#: means the earlier sweeps were running behind a source that kept refilling: every `None` written
#: since they ran went in as the JSON scalar `null`, which is not SQL NULL and which the exact test
#: rejects. The write path is fixed in the same change, so this is the first sweep that is actually
#: a backfill rather than a holding action.
#:
#: Named rather than inlined so `test_pin_empty.py` can derive the (table, column) pairs by RUNNING
#: `upgrade()` against a stubbed `_sweep`, instead of reading a list that says what the migration is
#: supposed to do.
_COLS = ("anchor", "element_guids")

#: The topic table. Not a register, and swept here for the same reason: `Topic.anchor` carried the
#: same JSON-null default.
_TOPICS = "topics"

#: How many ids one UPDATE carries -- see `f2b6d31a7c04`.
_BATCH = 500

#: `(table, id, column)` for every stored value that is not JSON at all. **Reported, never swept.**
SKIPPED: list[tuple[str, str, str]] = []


def _loads(v):
    """JSON columns come back decoded on some drivers and as text on others. Accept both."""
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return v


def _decode(v):
    """`(parsed_ok, value)` -- **a parse failure is not an empty value.** See `f2b6d31a7c04`.

    An anchor is a small fixed dict, so a truncated one carries less recoverable evidence than a
    truncated GUID list did. It is still the only record of where somebody placed that pin, and
    `downgrade()` is a documented no-op, so the rule is the same: leave it, name it.
    """
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
    """True when this element_guids value is non-NULL but holds no usable GUID.

    Unused by `upgrade()` -- this sweep only touches `anchor`. Kept because `test_pin_empty.py`
    drives every copy of the predicate through the same table of values, and a copy that is only
    half present is a copy that agrees by omission.
    """
    v = _loads(v)
    return not [g for g in (v or []) if g]


def _sweep(conn, table: str, cols: tuple[str, ...]) -> int:
    """NULL out every empty-but-not-null value in `cols`. Returns rows changed.

    SQL narrows to non-NULL candidates and Python decides, because `anchor` and `element_guids` are
    `JSON` rather than `JSONB` and PostgreSQL's `json` type has no equality operator.
    """
    insp = sa.inspect(conn)
    if not insp.has_table(table):
        return 0                      # a register whose module is not installed here
    have = {c["name"] for c in insp.get_columns(table)}
    cols = tuple(c for c in cols if c in have)
    if not cols:
        return 0
    sel = sa.text(f"SELECT id, {', '.join(cols)} FROM {table} "
                  f"WHERE {' OR '.join(f'{c} IS NOT NULL' for c in cols)}")
    todo: dict[tuple[str, ...], list] = {}
    changed = 0
    # **The options go on the STATEMENT, never on the connection** -- see `f2b6d31a7c04`: set on the
    # connection they are inherited by alembic's own `UPDATE alembic_version`, which Postgres then
    # rejects, and SQLite cannot see it because it has no server-side cursor.
    result = conn.execute(sel.execution_options(stream_results=True, yield_per=_BATCH))
    for row in result.mappings():
        empty = []
        for c in cols:
            v = row[c]
            if v is None:
                continue
            ok, decoded = _decode(v)
            if not ok:                      # not JSON at all -- evidence, not an empty value
                SKIPPED.append((table, str(row["id"]), c))
                continue
            if _is_empty_anchor(decoded) if c == "anchor" else _is_empty_guids(decoded):
                empty.append(c)
        if empty:
            todo.setdefault(tuple(empty), []).append(row["id"])

    # The cursor is fully drained before a single UPDATE runs: modifying a table while iterating a
    # SELECT over it is undefined behaviour on SQLite.
    for key, ids in todo.items():
        sets = ", ".join(f"{c} = NULL" for c in key)
        for i in range(0, len(ids), _BATCH):
            chunk = ids[i:i + _BATCH]
            names = [f"i{n}" for n in range(len(chunk))]
            binds = ", ".join(f":{n}" for n in names)
            res = conn.execute(sa.text(f"UPDATE {table} SET {sets} WHERE id IN ({binds})"),
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
            "b3c9e42d18a5: left %d unparseable anchor value(s) untouched (table, id, column): %s",
            len(SKIPPED), ", ".join(f"{t}/{i}/{c}" for t, i, c in SKIPPED[:20])
            + (" ..." if len(SKIPPED) > 20 else ""))


def downgrade() -> None:
    """Not reversible, and deliberately a no-op rather than a lie -- see `e4a7c2b81f60`.

    The rows this nulls held `{}`. Nothing distinguishes that from NULL under the exact test in
    `pins.pin_fields`, so there is no prior state to restore that differs in any behaviour.
    """
