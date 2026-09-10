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
    for key in _SPATIAL:
        _sweep(conn, f"mod_{key}", ("element_guids",))


def downgrade() -> None:
    """Not reversible, and deliberately a no-op rather than a lie -- see `e4a7c2b81f60`.

    The rows this nulls held `{}` / `[]` / `[""]`. Nothing distinguishes those from NULL under the
    exact test, so there is no prior state to restore that differs in any behaviour.
    """
