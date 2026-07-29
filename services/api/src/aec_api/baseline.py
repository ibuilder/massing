"""R24-BASELINE — the adoption metrics the interface ring is supposed to be scored against.

The R24 entry lists six metrics and reads as though they were one kind of thing. They are not, and
pretending otherwise is how a dashboard ends up quoting a number nobody computed:

  DERIVABLE HERE, from `record_activity` (every create/update/transition is already logged with an
  actor and a timestamp — see `modules._log`):
    * rooms touched per user per week      — module -> section -> room, via `rooms.room_of`
    * field captures per super per day     — `field_verification` creates, per actor per day
    * median RFI turnaround                — paired transitions into `open` then into `answered`

  NOT DERIVABLE HERE, and reported as unavailable rather than estimated:
    * time-to-first-meaningful-action      — starts when a browser paints; no server event exists
    * p95 *interaction* latency            — measured at the click, not at the request boundary
    * "where is X" support threads          — lives in a support inbox this product cannot see

`available: false` with a reason is the whole point. A baseline that silently substitutes a
server-side proxy for a client-side measure produces a number that looks like the target and answers
a different question — the shape this repo has paid for repeatedly (see `qto-measured-area`, and the
draw that was priced at zero because an unsolvable case stayed in the denominator).

Every figure carries its `basis` and its `n`. A median over three users is not a baseline, and the
caller needs to be able to see that without asking.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import rooms
from .models import RecordActivity

#: Creating one of these is a field capture. Kept as a set so adding a second field module is a
#: one-line change rather than an edit to a query.
FIELD_MODULES = {"field_verification"}

#: The RFI clock starts when it reaches the responder and stops when it is answered. Not
#: created->closed: a draft sitting in someone's queue for a week is not turnaround, and closing is
#: an administrative act that can happen long after the answer.
RFI_MODULE = "rfi"
RFI_START_STATE = "open"
RFI_END_STATE = "answered"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Rows written before the TZ-aware migration can come back naive; treat those as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"available": False, "reason": reason, **extra}


def _stats(values: list[float], basis: str, unit: str) -> dict[str, Any]:
    """A distribution plus the population it came from. Empty is `available: false`, never 0."""
    if not values:
        return _unavailable(f"no {basis} in the window", basis=basis, n=0)
    ordered = sorted(values)
    return {
        "available": True,
        "unit": unit,
        "median": round(statistics.median(ordered), 3),
        "mean": round(statistics.fmean(ordered), 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "n": len(ordered),
        "basis": basis,
    }


def _iso_week(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def rooms_touched_per_user_per_week(db: Session, since: datetime) -> dict[str, Any]:
    """Distinct rooms each actor touched, per ISO week.

    Resolves module -> room through `rooms.room_of`, so this cannot drift from the rail: if a module
    is moved to another room the metric follows, and an unmapped section is *counted as unmapped*
    rather than silently dropped, because a quietly shrinking denominator is the failure mode here.
    """
    from . import modules_registry

    rows = db.execute(
        select(RecordActivity.actor, RecordActivity.module, RecordActivity.ts)
        .where(RecordActivity.ts >= since)
    ).all()

    per: dict[tuple[str, str], set[str]] = defaultdict(set)
    unmapped: set[str] = set()
    for actor, module, ts in rows:
        ts = _aware(ts)
        if not actor or not module or ts is None:
            continue
        try:
            mod = modules_registry.get_module(module)
        except Exception:  # noqa: BLE001 — a module deleted since the activity was logged
            unmapped.add(module)
            continue
        room = rooms.room_of(mod)
        if not room:
            unmapped.add(module)
            continue
        per[(actor, _iso_week(ts))].add(room)

    out = _stats([float(len(v)) for v in per.values()], "actor-weeks with any activity", "rooms")
    out["n_actors"] = len({a for a, _ in per})
    out["n_weeks"] = len({w for _, w in per})
    out["total_rooms"] = len(rooms.ROOMS)
    if unmapped:
        # Surfaced, not swallowed: an unmapped module means the metric is measuring less than it says.
        out["unmapped_modules"] = sorted(unmapped)
    return out


def field_captures_per_user_per_day(db: Session, since: datetime) -> dict[str, Any]:
    """`field_verification` creations per actor per calendar day (UTC).

    Only days on which a given actor captured anything are counted. Including their idle days would
    average toward zero and answer "how often does a super work" rather than "how much do they
    capture when they do".
    """
    rows = db.execute(
        select(RecordActivity.actor, RecordActivity.ts)
        .where(RecordActivity.ts >= since)
        .where(RecordActivity.module.in_(FIELD_MODULES))
        .where(RecordActivity.action == "create")
    ).all()

    per: dict[tuple[str, str], int] = defaultdict(int)
    for actor, ts in rows:
        ts = _aware(ts)
        if not actor or ts is None:
            continue
        per[(actor, ts.date().isoformat())] += 1

    out = _stats([float(v) for v in per.values()], "actor-days with at least one capture", "captures")
    out["n_actors"] = len({a for a, _ in per})
    out["modules_counted"] = sorted(FIELD_MODULES)
    return out


def rfi_turnaround_days(db: Session, since: datetime) -> dict[str, Any]:
    """Days from an RFI reaching `open` to reaching `answered`.

    Pairs transition activity per record. An RFI opened but not yet answered is **excluded from the
    numerator and reported separately** rather than counted as zero or as "still fast" — the exact
    mistake that made an unsolvable draw look like a worthless project.
    """
    rows = db.execute(
        select(RecordActivity.record_id, RecordActivity.ts, RecordActivity.detail)
        .where(RecordActivity.ts >= since)
        .where(RecordActivity.module == RFI_MODULE)
        .where(RecordActivity.action.like("transition:%"))
    ).all()

    opened: dict[str, datetime] = {}
    answered: dict[str, datetime] = {}
    for rid, ts, detail in rows:
        ts = _aware(ts)
        to = (detail or {}).get("to") if isinstance(detail, dict) else None
        if not rid or ts is None or not to:
            continue
        if to == RFI_START_STATE:
            # earliest open — a re-opened RFI starts its clock once
            if rid not in opened or ts < opened[rid]:
                opened[rid] = ts
        elif to == RFI_END_STATE:
            if rid not in answered or ts < answered[rid]:
                answered[rid] = ts

    durations: list[float] = []
    negative = 0
    for rid, a_ts in answered.items():
        o_ts = opened.get(rid)
        if o_ts is None:
            continue  # answered inside the window, opened before it — no valid duration
        delta = (a_ts - o_ts).total_seconds() / 86400.0
        if delta < 0:
            negative += 1
            continue
        durations.append(delta)

    out = _stats(durations, "RFIs opened and answered within the window", "days")
    out["open_unanswered"] = len(set(opened) - set(answered))
    out["answered_without_open_in_window"] = len(set(answered) - set(opened))
    if negative:
        out["discarded_negative_durations"] = negative
    return out


def adoption(db: Session, *, days: int = 28, now: datetime | None = None) -> dict[str, Any]:
    """The six R24 metrics — three measured, three declared unavailable with a reason.

    `days` defaults to 28 so the per-week metric has four whole weeks to work with.
    """
    now = now or _now()
    since = now - timedelta(days=days)
    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "since": since.isoformat(),
        "metrics": {
            "rooms_touched_per_user_per_week": rooms_touched_per_user_per_week(db, since),
            "field_captures_per_super_per_day": field_captures_per_user_per_day(db, since),
            "rfi_turnaround_days": rfi_turnaround_days(db, since),
            "time_to_first_meaningful_action_seconds": _unavailable(
                "starts when the browser paints and ends at the user's first authoring action; no "
                "server-side event marks either end. Needs a client beacon (R24-BASELINE phase 2). "
                "The target is < 60 s.",
                target_seconds=60,
            ),
            "p95_interaction_latency_ms": _unavailable(
                "this is latency at the click, which only the client can time. The server's request "
                "latency is a DIFFERENT measure and is exposed separately as the "
                "http_request_duration_seconds histogram on /metrics — read that as request p95, "
                "not as interaction p95.",
                server_side_proxy="http_request_duration_seconds (histogram, /metrics)",
                target_ms=100,
            ),
            "where_is_x_support_threads": _unavailable(
                "counts threads in a support inbox this product does not have access to. Not "
                "measurable in-product; track it wherever support actually lives.",
            ),
        },
    }
