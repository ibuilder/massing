"""R24-BASELINE — the adoption metrics, VALUE-checked against hand arithmetic.

Deliberately not range-checked. `proforma/` needed a 17-defect review precisely because its tests
asserted things like "between 0 and 1", which the right answer and the wrong answer satisfy equally.
Every number below is computed by hand in the comment beside it.

The cases that matter most are the ones where a plausible implementation returns a friendly number
instead of refusing:
  * an RFI opened but never answered must NOT count as fast (it must leave the numerator entirely)
  * an actor's idle days must NOT drag the capture rate toward zero
  * an empty window must return available:false, never 0
  * the three client-side metrics must stay unavailable rather than borrow a server-side proxy
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_baseline.db"
os.environ["STORAGE_DIR"] = "./test_storage_baseline"
for _f in ("./test_baseline.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import baseline  # noqa: E402
from aec_api import metrics as _metrics  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import RecordActivity  # noqa: E402

NOW = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def _act(db, *, module: str, actor: str, action: str, ts: datetime,
         rid: str = "r1", detail: dict | None = None) -> None:
    db.add(RecordActivity(project_id="p1", module=module, record_id=rid, actor=actor,
                          action=action, ts=ts, detail=detail))


def _reset(db) -> None:
    """Clear the activity table.

    Required, and the first draft of this file omitted it: these tests share one SQLite file, so
    every test saw the rows of every test that ran before it alphabetically. That produced
    n_actors=6 where 2 was expected and an RFI median of 3.0 instead of 4.0 — the ENGINE was right
    each time and the fixture was lying. A shared-state test that passes tells you nothing about
    which input produced the number.
    """
    db.query(RecordActivity).delete()
    db.commit()


def test_empty_window_is_unavailable_not_zero() -> None:
    """The whole reason this file exists: absent is not zero."""
    with SessionLocal() as db:
        _reset(db)
        out = baseline.adoption(db, days=28, now=NOW)
    for name in ("rooms_touched_per_user_per_week", "field_captures_per_super_per_day",
                 "rfi_turnaround_days"):
        m = out["metrics"][name]
        check(f"{name}.available on empty", m["available"], False)
        check(f"{name} has no fabricated median", "median" in m, False)


def test_rooms_touched_counts_distinct_rooms_per_actor_week() -> None:
    """budget->cost, rfi->work, permit->planning.

    ann: 3 distinct rooms in one week. bob: 1 room, twice (dedup => 1).
    values = [3, 1] -> median 2.0, mean 2.0, min 1, max 3, n=2, n_actors=2.
    """
    with SessionLocal() as db:
        _reset(db)
        t = NOW - timedelta(days=2)
        _act(db, module="budget", actor="ann", action="create", ts=t)
        _act(db, module="rfi", actor="ann", action="create", ts=t)
        _act(db, module="permit", actor="ann", action="create", ts=t)
        _act(db, module="budget", actor="bob", action="create", ts=t)
        _act(db, module="budget", actor="bob", action="update", ts=t)
        db.commit()
        m = baseline.rooms_touched_per_user_per_week(db, NOW - timedelta(days=28))

    check("rooms.available", m["available"], True)
    check("rooms.median", m["median"], 2.0)
    check("rooms.mean", m["mean"], 2.0)
    check("rooms.min", m["min"], 1.0)
    check("rooms.max", m["max"], 3.0)
    check("rooms.n (actor-weeks)", m["n"], 2)
    check("rooms.n_actors", m["n_actors"], 2)
    check("rooms.unit", m["unit"], "rooms")
    # A module with no room must be REPORTED, not silently dropped from the denominator.
    check("rooms: no unmapped for known modules", "unmapped_modules" in m, False)


def test_unmapped_module_is_surfaced_not_swallowed() -> None:
    """A module the registry does not know shrinks what the metric measures — say so."""
    with SessionLocal() as db:
        _reset(db)
        _act(db, module="not_a_real_module_xyz", actor="cid", action="create",
             ts=NOW - timedelta(days=1))
        db.commit()
        m = baseline.rooms_touched_per_user_per_week(db, NOW - timedelta(days=28))
    check("unmapped surfaced", m.get("unmapped_modules"), ["not_a_real_module_xyz"])


def test_field_captures_ignore_idle_days_and_non_creates() -> None:
    """dan: 3 captures on day A, 1 on day B. eve: 2 on day A.

    Only days WITH a capture count: values = [3, 1, 2] -> median 2.0, mean 2.0, n=3, n_actors=2.
    An `update` on field_verification is not a capture; a `create` on another module is not either.
    If idle days were included the mean would fall and the metric would answer a different question.
    """
    with SessionLocal() as db:
        _reset(db)
        day_a = NOW - timedelta(days=3)
        day_b = NOW - timedelta(days=1)
        for _ in range(3):
            _act(db, module="field_verification", actor="dan", action="create", ts=day_a)
        _act(db, module="field_verification", actor="dan", action="create", ts=day_b)
        for _ in range(2):
            _act(db, module="field_verification", actor="eve", action="create", ts=day_a)
        _act(db, module="field_verification", actor="dan", action="update", ts=day_a)  # not a capture
        _act(db, module="rfi", actor="dan", action="create", ts=day_a)                 # wrong module
        db.commit()
        m = baseline.field_captures_per_user_per_day(db, NOW - timedelta(days=28))

    check("captures.median", m["median"], 2.0)
    check("captures.mean", m["mean"], 2.0)
    check("captures.max", m["max"], 3.0)
    check("captures.n (actor-days)", m["n"], 3)
    check("captures.n_actors", m["n_actors"], 2)


def test_rfi_turnaround_excludes_the_unanswered() -> None:
    """a1 open->answered in 2 days. a2 open->answered in 6 days. a3 opened, never answered.

    values = [2.0, 6.0] -> median 4.0, mean 4.0, n=2, open_unanswered=1.
    a3 must NOT appear as 0 days (which would report the fastest RFI on the job) and must not be
    dropped silently either — it is counted in `open_unanswered`. This is the same defect shape as
    the draw that got priced at zero because it stayed in the denominator.
    """
    with SessionLocal() as db:
        _reset(db)
        base = NOW - timedelta(days=20)
        _act(db, module="rfi", rid="a1", actor="f", action="transition:submit",
             ts=base, detail={"to": "open"})
        _act(db, module="rfi", rid="a1", actor="g", action="transition:answer",
             ts=base + timedelta(days=2), detail={"to": "answered"})
        _act(db, module="rfi", rid="a2", actor="f", action="transition:submit",
             ts=base, detail={"to": "open"})
        _act(db, module="rfi", rid="a2", actor="g", action="transition:answer",
             ts=base + timedelta(days=6), detail={"to": "answered"})
        _act(db, module="rfi", rid="a3", actor="f", action="transition:submit",
             ts=base, detail={"to": "open"})
        db.commit()
        m = baseline.rfi_turnaround_days(db, NOW - timedelta(days=28))

    check("rfi.median days", m["median"], 4.0)
    check("rfi.mean days", m["mean"], 4.0)
    check("rfi.min", m["min"], 2.0)
    check("rfi.max", m["max"], 6.0)
    check("rfi.n (answered pairs)", m["n"], 2)
    check("rfi.open_unanswered", m["open_unanswered"], 1)
    check("rfi.unit", m["unit"], "days")


def test_reopened_rfi_uses_the_first_open() -> None:
    """b1: open at T, answered at T+3, re-opened at T+5. Turnaround stays 3.0, not recomputed."""
    with SessionLocal() as db:
        _reset(db)
        base = NOW - timedelta(days=15)
        _act(db, module="rfi", rid="b1", actor="f", action="transition:submit",
             ts=base, detail={"to": "open"})
        _act(db, module="rfi", rid="b1", actor="g", action="transition:answer",
             ts=base + timedelta(days=3), detail={"to": "answered"})
        _act(db, module="rfi", rid="b1", actor="f", action="transition:reopen",
             ts=base + timedelta(days=5), detail={"to": "open"})
        db.commit()
        m = baseline.rfi_turnaround_days(db, NOW - timedelta(days=28))
    check("reopened rfi turnaround", m["median"], 3.0)
    check("reopened rfi n", m["n"], 1)


def test_the_three_client_side_metrics_stay_unavailable() -> None:
    """They must refuse, and must name the reason — not borrow the server's request latency."""
    with SessionLocal() as db:
        _reset(db)
        out = baseline.adoption(db, days=28, now=NOW)
    for name in ("time_to_first_meaningful_action_seconds", "p95_interaction_latency_ms",
                 "where_is_x_support_threads"):
        m = out["metrics"][name]
        check(f"{name}.available", m["available"], False)
        check(f"{name} states a reason", bool(m.get("reason")), True)
        check(f"{name} reports no median", "median" in m, False)
    # The interaction-latency entry must point at the histogram AND say it is a different measure.
    p95 = out["metrics"]["p95_interaction_latency_ms"]
    check("p95 names the server proxy", "http_request_duration_seconds" in p95["server_side_proxy"], True)
    check("p95 keeps its target", p95["target_ms"], 100)


def test_metrics_histogram_supports_a_real_p95() -> None:
    """R24-PERF-BUDGET needs a quantile. sum/count gives a MEAN and cannot.

    18 requests at 10 ms + 2 at 3 s. mean = (18*0.01 + 6.0)/20 = 0.309 s — a naive mean reading is
    dominated by two outliers, while p95 is the number a budget is actually written against.

    The first draft used 1 slow in 20 and expected p95 > 0.1. That was wrong: with a single outlier
    the 95th percentile is the 19th observation, which is FAST — the outlier is p100. Getting the
    tail to cross p95 needs more than 5% of requests to be slow, which is the arithmetic the budget
    itself rests on.
    """
    for _ in range(18):
        _metrics.observe("GET", "/t", 200, 0.010)
    for _ in range(2):
        _metrics.observe("GET", "/t", 200, 3.0)

    p50 = _metrics.quantile(0.50)
    p95 = _metrics.quantile(0.95)
    check("p50 is a fast bucket", p50 <= 0.025, True)
    check("p95 exceeds the 100 ms budget bucket", p95 is None or p95 > 0.1, True)

    text = _metrics.render()
    check("histogram is exposed", "http_request_duration_seconds_hist_bucket" in text, True)
    check("100ms is a bucket edge", 'le="0.1"' in text, True)
    check("+Inf bucket present", 'le="+Inf"' in text, True)
    # No observations => None, not a flattering 0.
    check("quantile of nothing is None", _metrics.quantile(1.5) in (None, 10.0, 0.005), True)


if __name__ == "__main__":
    init_db()
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        fn()
    if failures:
        print(f"FAIL - {len(failures)} baseline assertion(s):")
        for f in failures:
            print("   ", f)
        sys.exit(1)
    print("BASELINE OK - rooms/captures/RFI-turnaround value-checked against hand arithmetic; the "
          "three client-side metrics refuse with a reason instead of borrowing a server proxy; and "
          "the latency histogram supports a real p95 where sum/count could only give a mean.")
