"""Extend the empty-pin-JSON sweep to the registers the pin engine now reads.

`e4a7c2b81f60` nulled empty `{}` / `[]` / `[""]` pin values so a capped `pin_total` would stop being
an upper bound. It swept `topics` plus **eleven** register names taken from `pins.SPATIAL_MODULES`,
of which **five existed**: the other six named no module at all.

`pins.spatial_modules()` now derives that population from the registry's own `pinnable` flag, which
is what `modules.project_pins` and `traceability` already used. That takes the pin engine from five
registers to thirty-seven -- and every register it newly reads may hold legacy empty values written
before PR #492 normalised the two write sites in `modules.py`. Unswept, those rows pass the SQL
candidate predicate, fail the exact test in `pins.pin_fields`, and put a `~` in front of a project's
pin total for no reason.

This sweeps the newly-reached registers with the same predicate. It is a second migration rather
than an edit to the first because the first already ran: a migration is a record of what happened,
and rewriting one changes history for the databases that applied it and nothing for the rest.

**The predicate and the sweep are copied, not imported**, for the reason `e4a7c2b81f60` gives at
length: a migration whose meaning changes when a definition elsewhere changes is not a record of
anything. `test_pin_empty.py` asserts every copy agrees with `pins.pin_fields` TODAY, over a table
of values, so no copy can drift silently while it still matters.

**The names are spelled out for the same reason.** `test_pin_empty.py` asserts the UNION of the two
`_SPATIAL` lists covers what the engine reads today, so a register that becomes pinnable later fails
the build until a third migration sweeps it.

Revision ID: f2b6d31a7c04
Revises: e4a7c2b81f60
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b6d31a7c04"
down_revision: str | None = "e4a7c2b81f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The registers `pins.spatial_modules()` reaches that `e4a7c2b81f60` did not sweep -- i.e. every
#: module carrying `"pinnable": true` minus the five real names that migration already covered
#: (`rfi`, `punchlist`, `observation`, `inspection`, `photo`).
_SPATIAL = (
    "asi", "asset_register", "assumption", "bulletin", "climate_site_risk", "coordination_issue",
    "cor", "decision", "deficiency", "directive", "drainage_area", "eticket", "fault_finding",
    "fca_element", "field_verification", "flood_risk", "incident", "issue", "mep_equipment",
    "meter", "ncr", "noc", "pco_request", "procurement_package", "progress_actual",
    "safety_violation", "schedule_activity", "sketch", "spec_section", "submittal", "work_order",
    "zoning",
)


#: How many ids one UPDATE carries. The candidate SELECT is streamed and only the ids that actually
#: need clearing are retained, so memory is O(legacy empty rows) rather than O(rows in the register;
#: this then bounds the bind parameters per statement. `stream_results` helps on Postgres; pysqlite
#: has no server-side cursor and buffers regardless, which is why holding ids rather than rows is the
#: part that does the work on every driver.
_BATCH = 500

#: `(table, id, column)` for every stored value that is not JSON at all. **Reported, never swept** —
#: see `_decode`. Module-level so `test_pin_empty.py` can assert on it rather than parse a log line.
SKIPPED: list[tuple[str, str, str]] = []


def _loads(v):
    """JSON columns come back decoded on some drivers and as text on others. Accept both.

    Kept byte-for-byte as `e4a7c2b81f60` has it, because `test_pin_empty.py` asserts the two copies
    agree over a table of values. `_sweep` no longer routes malformed text through it — see
    `_decode`, which is the difference.
    """
    if isinstance(v, (str, bytes)):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return None
    return v


def _decode(v):
    """`(parsed_ok, value)` — **a parse failure is not an empty value.**

    `_loads` collapses "malformed text" and "decoded to nothing" into the same `None`, and
    `_is_empty_guids(None)` is True, so a malformed stored value gets NULLed. Measured on a truncated
    list holding a well-formed GlobalId — `'["1WrzGm1SD2ev45B_OWQ39B", "2Ab'` — the row was cleared
    and the GUID went with it. `downgrade()` is a documented no-op, so it does not come back.

    Those bytes are the only surviving evidence of what the row meant, and a migration is the last
    place to discard evidence it cannot restore. So `_sweep` leaves the column alone and records the
    row in `SKIPPED` for a human to look at.

    **`e4a7c2b81f60` does NULL them, and it has already run**, so the two copies now differ here — in
    the safe direction, and deliberately. `test_pin_empty.py` asserts the difference so it cannot be
    mistaken for the drift that the copy-don't-import rule exists to catch.
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
    """True when this element_guids value is non-NULL but holds no usable GUID."""
    v = _loads(v)
    return not [g for g in (v or []) if g]


def _sweep(conn, table: str, cols: tuple[str, ...]) -> int:
    """NULL out every empty-but-not-null value in `cols`. Returns rows changed.

    SQL narrows to non-NULL candidates and Python decides, because `anchor` and `element_guids` are
    `JSON` rather than `JSONB` and PostgreSQL's `json` type has no equality operator -- `WHERE
    element_guids = '[]'` is a hard `UndefinedFunction`, not a portability wart.
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
    # ids to clear, keyed by the exact set of columns to clear on that row. Only ids are retained —
    # the values are examined and dropped — so this is bounded by the number of LEGACY EMPTY rows,
    # not by the size of the register. `e4a7c2b81f60` called `.all()` and issued one UPDATE per row.
    todo: dict[tuple[str, ...], list] = {}
    changed = 0
    result = conn.execution_options(stream_results=True, yield_per=_BATCH).execute(sel)
    for row in result.mappings():
        empty = []
        for c in cols:
            v = row[c]
            if v is None:
                continue
            ok, decoded = _decode(v)
            if not ok:                      # not JSON at all — evidence, not an empty value
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
            # **Count what the database actually changed, not what we intended to change.** Counting
            # during the scan made the return value independent of whether the UPDATEs ran: a
            # mutation that clipped the chunking loop to its first batch still reported every row as
            # swept. A migration that reports more than it did is the same shape as everything else
            # this branch is about.
            changed += res.rowcount if res.rowcount is not None and res.rowcount >= 0 else len(chunk)
    return changed


def upgrade() -> None:
    conn = op.get_bind()
    for key in _SPATIAL:
        _sweep(conn, f"mod_{key}", ("element_guids",))
    if SKIPPED:
        # Loud, and not fatal. These rows hold text that is not JSON; the migration cannot tell an
        # empty value from a corrupted one, so it leaves them exactly as they are and names them.
        logging.getLogger("alembic.runtime.migration").warning(
            "f2b6d31a7c04: left %d unparseable pin value(s) untouched (table, id, column): %s",
            len(SKIPPED), ", ".join(f"{t}/{i}/{c}" for t, i, c in SKIPPED[:20])
            + (" ..." if len(SKIPPED) > 20 else ""))


def downgrade() -> None:
    """Not reversible, and deliberately a no-op rather than a lie -- see `e4a7c2b81f60`.

    The rows this nulls held `{}` / `[]` / `[""]`. Nothing distinguishes those from NULL under the
    exact test, so there is no prior state to restore that differs in any behaviour.
    """
