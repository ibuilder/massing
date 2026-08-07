"""R40-EOT ② — the two contested inputs come from the record, and the gaps are reported not filled.

`eot.analyse` already refuses well: method required and closed, concurrency named rather than
apportioned, absorbed float reported as absorbed. **Its inputs had no provenance.** `POST
/schedule/eot` took `baseline_finish`, `actual_finish` and the whole `events` list from the request
body while `schedule_baselines` and `notice_clock` sat wired to nothing — so two people could produce
different EOTs from one project by typing different dates, and every careful refusal downstream rested
on an input nobody could audit. On the number that ends up in arbitration.

The join is only honest because the two sources give different things, and this asserts that the gap
between them is reported rather than filled:

* `schedule_baselines.compute_variance` gives **quantum** — `finish_var` per activity vs a *named*
  baseline. Driven here through the REAL function, not a hand-made variance dict, because a fixture
  shaped to match my reader would agree with it no matter which of us was wrong. That mistake has
  cost this session repeatedly, and it is what nearly shipped here: I first read `activities[].id`
  and `summary.baseline_finish`, and **neither exists**.
* `notice_clock` gives **cause** — and carries **no `days` field at all**. Detection establishes that
  an event happened, never what it cost.

So the two refusals under test:

1.  **slip with no matching cause is `unattributed`, never `non_excusable`** — defaulting unexplained
    slip to contractor risk hands one party an entitlement finding nobody demonstrated;
2.  **an event with no stated duration is `needs_duration` and is excluded from the figure**, rather
    than being handed the slip it happens to sit near. Proximity is not causation, and causation is
    the contested half of every delay claim.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_eot_sourced.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import eot_sourced as es  # noqa: E402
from aec_api.schedule_baselines import compute_variance  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the variance comes from the REAL engine, so the key names have to line up for real -----------
BASE = {
    "a1": {"ref": "A-1", "name": "Excavation", "start": "2026-03-01", "finish": "2026-03-20"},
    "a2": {"ref": "A-2", "name": "Foundations", "start": "2026-03-21", "finish": "2026-04-15"},
    "a3": {"ref": "A-3", "name": "Steel", "start": "2026-04-16", "finish": "2026-05-30"},
    "a4": {"ref": "A-4", "name": "Roofing", "start": "2026-06-01", "finish": "2026-06-20"},
}
CURRENT = {
    # slipped 10 days, and there IS a quantified cause
    "a1": {"ref": "A-1", "title": "Excavation", "data": {"start": "2026-03-01", "finish": "2026-03-30"}},
    # slipped 5 days, cause detected but with NO duration
    "a2": {"ref": "A-2", "title": "Foundations", "data": {"start": "2026-03-21", "finish": "2026-04-20"}},
    # slipped 12 days, NO cause at all
    "a3": {"ref": "A-3", "title": "Steel", "data": {"start": "2026-04-16", "finish": "2026-06-11"}},
    # finished early — must not appear as slip
    "a4": {"ref": "A-4", "title": "Roofing", "data": {"start": "2026-06-01", "finish": "2026-06-15"}},
}
VAR = compute_variance(BASE, CURRENT)

check("the real variance engine reports per-activity finish_var",
      any(a.get("finish_var") for a in VAR["activities"]), VAR["summary"])
check("  and its rows key on `ref` — there is no `id`, which is what nearly shipped wrong",
      all("ref" in a for a in VAR["activities"]) and not any("id" in a for a in VAR["activities"]))
check("  its summary carries slip counts, NOT project finish dates",
      "max_slip_days" in VAR["summary"] and "baseline_finish" not in VAR["summary"],
      sorted(VAR["summary"]))

slipped = es._slipped(VAR)
check("only activities that finished LATE are slip", {s["ref"] for s in slipped} == {"A-1", "A-2", "A-3"},
      [s["ref"] for s in slipped])
check("  the early finish is excluded, not counted as zero slip",
      "A-4" not in {s["ref"] for s in slipped})
check("  largest slip first", [s["slip_days"] for s in slipped] == [12, 10, 5],
      [s["slip_days"] for s in slipped])

# --- attribution: quantified cause / cause without duration / no cause ----------------------------
EVENTS = [
    {"type": "weather", "activity_id": "A-1", "days": 10, "source": "daily_report", "source_id": "d1"},
    # notice_clock's real event shape: type/date/description/source/source_id and NO `days`
    {"type": "constructive_change", "activity_id": "A-2", "date": "2026-04-02",
     "description": "verbal direction", "source": "change_event", "source_id": "c9"},
    {"type": "suspension", "date": "2026-05-01", "source": "change_event", "source_id": "c10"},
]
A = es.attribute(slipped, EVENTS)
row = {r["ref"]: r for r in A["activities"]}

check("a slip with a QUANTIFIED cause is attributed", row["A-1"]["status"] == es.ATTRIBUTED,
      row["A-1"]["status"])
check("  carrying the days somebody actually stated", row["A-1"]["claimed_days"] == 10,
      row["A-1"]["claimed_days"])

check("THE EVENT WITH NO DURATION IS `needs_duration`, not given the slip it sits on",
      row["A-2"]["status"] == es.NEEDS_DURATION, row["A-2"]["status"])
check("  and contributes NO days to the figure", row["A-2"]["claimed_days"] is None,
      row["A-2"]["claimed_days"])
check("  while being listed so somebody can quantify it",
      [e["source_id"] for e in A["needs_duration"]] == ["c9"], A["needs_duration"])

check("SLIP WITH NO CAUSE IS `unattributed` — NOT non_excusable",
      row["A-3"]["status"] == es.UNATTRIBUTED, row["A-3"]["status"])
check("  its days are reported as their own bucket, not folded into the claim",
      A["unattributed_days"] == 12 and A["attributed_days"] == 10,
      (A["unattributed_days"], A["attributed_days"]))
check("  and it is named, so a reader sees which overrun has no established cause",
      [u["ref"] if "ref" in u else u["activity_id"] for u in A["unattributed"]] == ["A-3"],
      A["unattributed"])
check("an event linked to no activity is counted, not silently dropped",
      A["events_without_activity"] == 1, A["events_without_activity"])
check("the note states the refusal a reader would otherwise assume away",
      "NOT non-excusable" in A["note"])

# --- proximity is not causation --------------------------------------------------------------------
NEAR = es.attribute(slipped, [{"type": "weather", "date": "2026-06-10", "days": 12}])
check("an event NEAR a slip in time but not linked to it attributes nothing",
      all(r["status"] == es.UNATTRIBUTED for r in NEAR["activities"]),
      [(r["ref"], r["status"]) for r in NEAR["activities"]])
check("  so all the slip stays unattributed rather than being explained by coincidence",
      NEAR["unattributed_days"] == 27, NEAR["unattributed_days"])

check("no slip at all is an empty attribution, not a crash", es.attribute([], None)["activities"] == [])

print()
if FAILED:
    print(f"eot_sourced: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("eot_sourced: all checks passed")
