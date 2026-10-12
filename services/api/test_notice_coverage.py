"""NOTICE-CLOCK-TRUNC — the time-bar register was computed over the OLDEST 500 records.

`routers/notices.py` read the field record with `me.list_records(db, key, pid, limit=limit)`, where
`limit` was a query parameter defaulting to **500** — and `list_records` applies `ORDER BY
created_at` **ascending** before the limit. So the notice register was assembled from the *oldest*
500 daily reports, change events and RFIs, and the events whose notice periods are still running
are by definition the **newest**. On a project with 600 daily reports the hundred most recent were
invisible, and the register said "nothing expired" in exactly the words it uses when nothing has.

WHY NOTHING CAUGHT IT
---------------------
* **The engine is careful to a fault.** `notice_clock`'s header enumerates three counting traps —
  what starts the clock, which days count, which days are the weekend — and refuses rather than
  guessing on every one. It reports `indeterminate` and names the missing field instead of
  substituting a date, because *"a claimant told the bar has fallen abandons a claim that was
  live."* All of that care is about the events it is handed. *A guard is only as sound as the
  evidence it is given, and nothing was checking the evidence* — the same defeat-from-outside as
  CLASH-TRUNC, on a register where the cost of an omission is a forfeited claim.
* **The payload carried `events_found`**, the number of triggering events DETECTED, which reads as
  the number there is.
* **Every other engine over these same tables scans everything.** `changeorders`, `dailylog`,
  `resilience`, `selections` and `tm` all pass `limit=100000`. This one route was the exception.

The repository's own hardening checklist names the shape: *"Payload caps must keep the NEWEST rows:
`order_by(asc).limit()` silently hides everything created after row N."* It was written about
response payloads. This is the same mistake one layer earlier, where the cap decides what is
COMPUTED rather than what is shown — and there the loss is silent, because a page that is short is
visibly short while a register that is short is just a shorter list of deadlines.

WHAT THIS GATE HOLDS
--------------------
1. The **mechanism** the fix rests on: `list_records` really is ascending, and `sort_dir="desc"`
   really reverses it. If a future change made that argument a no-op the register would revert in
   silence, and nothing else in the tree asserts it.
2. The **route**, with `SCAN_CAP` patched small: the newest records are the ones scanned, the
   omission is reported per source, and `complete` is false.
3. The **pre-fix call replayed** against the same data — it must lose the newest event, and the
   gate must see it lose it, before anything may be reported.
4. The coverage keys are **derived from `nc.detect`'s own signature**, not listed, so a fourth
   source cannot be added to the scan without appearing in what the scan reports.

Run: cd services/api && PYTHONPATH="src:../data/src" ./.venv/bin/python test_notice_coverage.py
"""
import inspect
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_notice_coverage.db"
os.environ["STORAGE_DIR"] = "./test_storage_notice_coverage"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_notice_coverage.db"):
    os.remove("./test_notice_coverage.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules as me  # noqa: E402
from aec_api import notice_clock as nc  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.routers import notices  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


# A weather day that trips `WEATHER_TRIGGERS`, so each report is a triggering event.
DAYS = ["2026-03-02", "2026-03-10", "2026-03-20"]
TODAY = "2026-03-30"

with TestClient(app) as c:
    c.headers.update({"X-User": "notice-coverage@test"})
    pid = c.post("/projects", json={"name": "Coverage Tower"}).json()["id"]

    def create(key, data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
        return r.json()

    # Created oldest-first, which is also `created_at` order — so "the newest record" and "the
    # latest report_date" are the same row and a reversal is unambiguous.
    for d in DAYS:
        create("daily_report", {"report_date": d, "weather": "Snow",
                                "weather_impact": "Full-Day Lost"})
    create("prime_contract", {"name": "Prime", "owner": "Owner LLC",
                              "notice_family": "AIA A201-2017"})

    # ── 1. the mechanism, asserted directly ─────────────────────────────────────────────────────
    from aec_api.db import SessionLocal  # noqa: E402
    db = SessionLocal()
    try:
        asc = me.list_records(db, "daily_report", pid, limit=2)
        desc = me.list_records(db, "daily_report", pid, limit=2,
                               sort="created_at", sort_dir="desc")
        ok([r["data"]["report_date"] for r in asc] == DAYS[:2],
           "list_records caps the OLDEST rows by default — the hazard, pinned where it lives")
        ok(sorted(r["data"]["report_date"] for r in desc) == DAYS[1:],
           "...and `sort_dir=desc` really reverses it, which is what the fix rests on: got "
           f"{[r['data']['report_date'] for r in desc]}")
        ok(me.count_records(db, "daily_report", pid) == len(DAYS),
           "count_records sees all of them, so the denominator is real")
    finally:
        db.close()

    # ── 2. the route, with the scan cap patched down ────────────────────────────────────────────
    real_cap = notices.SCAN_CAP
    notices.SCAN_CAP = 2
    try:
        R = c.get(f"/projects/{pid}/notices?as_of={TODAY}").json()
    finally:
        notices.SCAN_CAP = real_cap

    dates = {i["event"]["date"] for i in R["items"]}
    ok(DAYS[-1] in dates,
       f"the NEWEST event is in the register — the one with a live deadline; got {sorted(dates)}")
    ok(DAYS[0] not in dates,
       "...and the oldest fell outside the cap, which is the right end to lose")
    src = R["sources"]["daily_report"]
    ok(src["total"] == len(DAYS) and src["scanned"] == 2 and src["truncated"] is True,
       f"the omission is reported per source: {src}")
    ok(R["complete"] is False,
       "`complete` is False, which is the only thing that makes 'nothing expired' mean anything")
    # The cut-off is a RECORDING date, not an event date, because the slice is ordered by
    # `created_at` — and asserting the event date here is what surfaced that distinction on this
    # gate's first run. Keeping the newest *recorded* rows is the right choice (a back-dated report
    # entered today has a clock running today), so the sentence has to say "recorded" and the test
    # has to check the same thing the code means.
    ok(src["oldest_scanned"][:10] in (R["coverage"] or "")
       and "RECORDED" in (R["coverage"] or ""),
       f"the coverage sentence names the cut-off in the units it is measured in: {R['coverage']!r}")
    ok("not by when the event happened" in (R["coverage"] or ""),
       "...and says which date that is, because a bound in the wrong units is acted on")

    # ...and unpatched, the same project is complete and says so.
    full = c.get(f"/projects/{pid}/notices?as_of={TODAY}").json()
    ok(full["complete"] is True and "every record" in full["coverage"],
       f"with the real cap the register is complete and says so: {full['coverage']!r}")
    ok(full["sources"]["rfi"]["present"] is False
       or full["sources"]["rfi"]["total"] == 0,
       "a source with no records is reported as empty rather than omitted from the report")

    # ── 3. the pre-fix call, replayed — it must LOSE the newest event ────────────────────────────
    db = SessionLocal()
    try:
        prefix_rows = me.list_records(db, "daily_report", pid, limit=2)      # as shipped
    finally:
        db.close()
    prefix_events = nc.detect(daily_reports=prefix_rows)
    prefix_dates = {e["date"].isoformat() if hasattr(e["date"], "isoformat") else str(e["date"])
                    for e in prefix_events}
    ok(DAYS[-1] not in prefix_dates,
       "PROOF OF REACH: the pre-fix slice loses the newest event, so this gate is ruling on a "
       f"difference that exists; got {sorted(prefix_dates)}")
    ok(len(prefix_events) == 2,
       "...and it is a truncation, not an empty read — the pre-fix register looked perfectly normal")

# ── 4. the coverage keys are DERIVED from the engine's own signature ────────────────────────────
#
# Listing them would let a fourth source join the scan without joining the report. `detect`'s
# keyword parameters ARE the sources; the module key is the singular of each.
_params = [p for p in inspect.signature(nc.detect).parameters
           if p not in ("weather_triggers",)]
_expected = {p[:-1] if p.endswith("s") else p for p in _params}
ok(_expected == {"daily_report", "change_event", "rfi"},
   f"the derivation finds the engine's sources — a precondition, not the rule: {sorted(_expected)}")
ok(set(full["sources"]) == _expected,
   f"every source the engine reads is covered in what the scan reports: "
   f"{sorted(set(full['sources']))} vs {sorted(_expected)}")

# ── the route may not take a scan limit from the caller again ───────────────────────────────────
_sig = set(inspect.signature(notices.notice_register).parameters)
ok("limit" not in _sig,
   "the register takes no caller-supplied scan limit — a caller passing a small number got a "
   f"register that silently omitted events; signature is {sorted(_sig)}")
_src = inspect.getsource(notices.notice_register)
ok("_source_slice(db, key, pid)" in _src and "me.list_records" not in _src,
   "...and it reads the field record only through `_source_slice`, which is where the ordering and "
   "the coverage live together")

print()
if FAILED:
    print(f"FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("NOTICE-CLOCK-TRUNC: the register scans the newest records and reports what it left out.")
