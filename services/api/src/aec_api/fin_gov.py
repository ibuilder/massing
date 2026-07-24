"""FIN-GOV — financial governance: scenario review workflow + locked reporting periods.

Two deterministic controls a finance platform needs before breadth (R19):

1. **Scenario review states** — draft → in_review → approved → published on the persisted
   pro-forma `Scenario` (the MODEL-PUBLISH pattern reapplied): `submit`/`approve`/`publish` move
   forward, `reject` and `reopen` return to draft with a note; approved/published scenarios are
   immutable (clone a revision). Who/when/why ride the row; every action is audit-logged by the
   router.

2. **Locked reporting periods** — a per-project lock date (stored as a small storage blob, no
   migration): finance-module records whose accounting date falls in a **closed month**
   (year-month ≤ the lock's year-month) refuse create/update/delete with a 409. Adjustments go
   into open periods, the way accountants expect. Enforced in the modules ENGINE so every path
   (routers, imports, internal flows) hits the same gate.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from . import storage


def _read_json(key: str) -> dict | None:
    try:
        return json.loads(storage.get(key).decode("utf-8"))
    except Exception:                                        # noqa: BLE001 — absent/corrupt blob = none
        return None

# --- scenario review workflow ---------------------------------------------------------------------

REVIEW_ACTIONS: dict[str, tuple[str, str]] = {
    "submit": ("draft", "in_review"),
    "approve": ("in_review", "approved"),
    "reject": ("in_review", "draft"),
    "publish": ("approved", "published"),
    "reopen": ("approved", "draft"),      # pre-publish walk-back; published is terminal (clone)
}

# states whose assumptions may no longer change in place
IMMUTABLE_STATES = ("approved", "published")


def review_scenario(scenario, action: str, actor: str, note: str = "") -> dict[str, Any]:
    """Apply a review action to a Scenario row (mutates the row; caller commits).
    Raises KeyError for an unknown action, ValueError for an illegal transition."""
    if action not in REVIEW_ACTIONS:
        raise KeyError(f"unknown review action {action!r} — one of {sorted(REVIEW_ACTIONS)}")
    was, to = REVIEW_ACTIONS[action]
    cur = getattr(scenario, "review_status", None) or "draft"
    if cur != was:
        raise ValueError(f"cannot {action} from {cur!r} (requires {was!r})")
    scenario.review_status = to
    scenario.reviewed_by = actor
    scenario.reviewed_at = datetime.now(timezone.utc)
    scenario.review_note = (note or "")[:500]
    return {"review_status": to, "reviewed_by": actor, "note": scenario.review_note}


def assumption_diff(old: dict, new: dict, prefix: str = "") -> list[str]:
    """The changed top-level (and one-level-nested) assumption paths — the change log's payload.
    Deterministic, order-stable."""
    changed: list[str] = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        if a == b:
            continue
        path = f"{prefix}{k}"
        if isinstance(a, dict) and isinstance(b, dict) and not prefix:   # one level deep only
            changed.extend(assumption_diff(a, b, prefix=f"{k}."))
        else:
            changed.append(path)
    return changed


# --- locked reporting periods ---------------------------------------------------------------------

# finance modules covered by the period lock, and the field(s) carrying their accounting date.
# The first populated, parsable field decides the record's period.
LOCK_FIELDS: dict[str, tuple[str, ...]] = {
    "owner_invoice": ("period",),
    "sub_invoice": ("invoice_date", "period"),
    "direct_cost": ("date",),
    "journal_batch": ("period",),
}

_YM = re.compile(r"^\s*(\d{4})[-/](\d{1,2})")


def _year_month(value: Any) -> tuple[int, int] | None:
    """Parse 'YYYY-MM', 'YYYY-MM-DD', 'YYYY/MM' (prefix match) → (year, month), else None."""
    m = _YM.match(str(value or ""))
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    return (y, mo) if 1 <= mo <= 12 else None


def _lock_key(pid: str) -> str:
    return f"{pid}/finance_lock.json"


def get_lock(pid: str) -> dict[str, Any]:
    """The project's period lock, or an open (no-lock) shape."""
    data = _read_json(_lock_key(pid))
    if not isinstance(data, dict) or not data.get("lock_date"):
        return {"lock_date": None}
    return data


def set_lock(pid: str, lock_date: str | None, actor: str, note: str = "") -> dict[str, Any]:
    """Set (or clear, with None/'') the lock date. Validates 'YYYY-MM' / 'YYYY-MM-DD'."""
    if not lock_date:
        payload: dict[str, Any] = {"lock_date": None, "set_by": actor,
                                   "set_at": datetime.now(timezone.utc).isoformat(),
                                   "note": (note or "")[:300]}
        storage.put(_lock_key(pid), json.dumps(payload).encode("utf-8"))
        return payload
    if _year_month(lock_date) is None:
        raise ValueError("lock_date must be YYYY-MM or YYYY-MM-DD")
    payload = {"lock_date": str(lock_date)[:10], "set_by": actor,
               "set_at": datetime.now(timezone.utc).isoformat(), "note": (note or "")[:300]}
    storage.put(_lock_key(pid), json.dumps(payload).encode("utf-8"))
    return payload


def locked_reason(key: str, pid: str, data: dict | None) -> str | None:
    """Why a mutation on this record is refused under the project's period lock, or None if open.
    A record is locked when its accounting month ≤ the lock month. Records with no parsable date
    are OPEN (the lock governs postings into closed periods, it does not quarantine undated rows)."""
    fields = LOCK_FIELDS.get(key)
    if not fields:
        return None
    lock = get_lock(pid)
    lock_ym = _year_month(lock.get("lock_date"))
    if lock_ym is None:
        return None
    for f in fields:
        ym = _year_month((data or {}).get(f))
        if ym is not None:
            if ym <= lock_ym:
                return (f"period {ym[0]}-{ym[1]:02d} is locked (books closed through "
                        f"{lock['lock_date']}) — post the adjustment into an open period")
            return None
    return None
