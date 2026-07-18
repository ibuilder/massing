"""TZ-UTC: one clock for due-date / aging math.

Stored dates are ISO (effectively UTC); comparing them against the server's *local* wall-clock made
"overdue" / "days open" drift by a day near midnight and change with the host timezone. Every
overdue/aging computation uses these helpers so the whole platform ages records on the same clock
(matching `benchmarking.py`, which already did this)."""
from __future__ import annotations

from datetime import date, datetime, timezone


def utc_now() -> datetime:
    """Timezone-aware now in UTC."""
    return datetime.now(timezone.utc)


def utc_today() -> date:
    """Today's date on the UTC clock (use for all due/aging comparisons)."""
    return datetime.now(timezone.utc).date()
