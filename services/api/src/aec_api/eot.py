"""R40-EOT — extension of time, with the method it was computed by attached to it.

The pieces were already here and had never been joined: `schedule_cpm.compute()` gives ES/EF/LS/LF and
the critical path, `schedule_baselines` holds named baselines ("GMP", "post-ASI-014", "Recovery") with
per-activity planned dates, and `notice_clock` already types delay events — `weather_delay`,
`change_constructive`, `suspension`, `delay_other` — and cites AIA §15.1.6.2 for the weather claim.

What was missing is the step between them: baseline + as-built + delay events → **entitlement**.

## Why this module states its method, and refuses without one

Forensic delay analysis has a published method taxonomy (AACE 29R-03; SCL Delay & Disruption Protocol
2nd ed). The methods are **not interchangeable — the same facts give different answers**, which is why
they are argued over in arbitration rather than settled:

* **as-planned vs as-built** compares the two end states. Simple, and it attributes everything that
  moved to whatever the analyst thinks moved it.
* **impacted as-planned** inserts delay events into the baseline and re-runs CPM. Prospective, and it
  ignores what the contractor actually did afterwards.
* **time impact analysis** inserts each event into the schedule *current at the time of that event*.
  The method most protocols prefer, and the one that needs schedule updates most projects do not keep.
* **windows** slices the job into periods and analyses each. Most defensible, most data-hungry.

An EOT number without its method is not a weak answer, it is an **unreadable** one: the reader cannot
tell whether they are looking at a 61-day entitlement or a 61-day arithmetic artefact. So `METHODS` is
a closed set, the method is required, and it travels in the payload beside the number.

## The other refusals

* **Concurrency is REPORTED, never apportioned.** When an employer-risk and a contractor-risk delay
  overlap, whether the contractor gets time, money, both or neither is a *contract and jurisdiction*
  question that the protocols themselves disagree on. This module names the concurrent pairs and
  stops. Splitting them 50/50 — or by any other silent rule — would manufacture the most contested
  number in the discipline and present it as arithmetic.
* **Float belongs to the project until it is consumed.** A delay that does not exhaust an activity's
  TOTAL float does not extend the completion date, and is reported as absorbed rather than as zero
  entitlement — those are different findings, and only the second reads as "no delay happened".
* **An unclassified event yields no entitlement and says so.** Excusability is a contract reading, not
  a property of a date. An event with no stated type is `unclassified`, never defaulted to excusable
  (which would inflate entitlement) or to non-excusable (which would deny it).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: The published method taxonomy. A closed set: an unrecognised method is refused rather than run,
#: because "some method" is not a thing a reader can weigh.
METHOD_AS_PLANNED_VS_AS_BUILT = "as_planned_vs_as_built"
METHOD_IMPACTED_AS_PLANNED = "impacted_as_planned"
METHOD_TIME_IMPACT = "time_impact"
METHOD_WINDOWS = "windows"

METHODS = {
    METHOD_AS_PLANNED_VS_AS_BUILT: "compares planned and actual end states. Simplest, and the weakest "
                                   "at attributing WHICH event moved the finish — it shows that the "
                                   "job moved, not why",
    METHOD_IMPACTED_AS_PLANNED: "inserts delay events into the baseline and re-runs CPM. Prospective: "
                                "it ignores how the contractor actually sequenced the work afterwards",
    METHOD_TIME_IMPACT: "inserts each event into the schedule current AT THAT EVENT. Preferred by most "
                        "protocols, and needs the schedule updates many projects never kept",
    METHOD_WINDOWS: "slices the job into periods and analyses each. Most defensible, most data-hungry",
}

#: Entitlement classes. These are contract readings, not properties of a date.
EXCUSABLE_COMPENSABLE = "excusable_compensable"      # time AND money — typically employer-risk
EXCUSABLE_NON_COMPENSABLE = "excusable"              # time only — typically neutral (weather)
NON_EXCUSABLE = "non_excusable"                      # neither — typically contractor-risk
UNCLASSIFIED = "unclassified"                        # not stated; NOT a synonym for either

#: `notice_clock`'s event vocabulary mapped to the entitlement it TYPICALLY carries. "Typically" is
#: load-bearing: the contract governs, so this is a starting point a reviewer overrides, and every row
#: reports which of the two it used.
DEFAULT_ENTITLEMENT = {
    "weather_delay": EXCUSABLE_NON_COMPENSABLE,
    "change_constructive": EXCUSABLE_COMPENSABLE,
    "suspension": EXCUSABLE_COMPENSABLE,
    "delay_other": UNCLASSIFIED,
}

STATUS_OK = "analysed"
STATUS_NO_METHOD = "method_required"
STATUS_NO_BASELINE = "baseline_required"

STATUS_MEANING = {
    STATUS_OK: "an EOT was computed, and the method it was computed by is stated with it",
    STATUS_NO_METHOD: "no analysis was run. An EOT number without its method cannot be weighed — the "
                      "same facts give different answers under different methods, which is why the "
                      "taxonomy exists",
    STATUS_NO_BASELINE: "no baseline was supplied, so there is nothing to measure the delay against. "
                        "This is an absence of the contract's plan-of-record, not a finding of zero "
                        "delay",
}


def _d(v: Any) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.fromisoformat(v.strip()[:10]).date()
    except ValueError:
        return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def total_float(activity: dict) -> int | None:
    """Total float from a `schedule_cpm` activity row: LS − ES.

    `compute()` returns `free_float` directly but not total float, and the distinction decides
    everything here — free float is slack before the NEXT activity slips, total float is slack before
    the PROJECT does. Only the second governs an extension of time."""
    ls, es = activity.get("ls"), activity.get("es")
    if ls is None or es is None:
        return None
    return int(ls) - int(es)


def classify(event: dict, override: str | None = None) -> dict[str, Any]:
    """The entitlement an event carries, and where that reading came from.

    An unclassified event stays unclassified. Defaulting it to excusable inflates entitlement and
    defaulting it to non-excusable denies it — both are contract readings dressed as data handling."""
    stated = override or event.get("entitlement")
    if stated in (EXCUSABLE_COMPENSABLE, EXCUSABLE_NON_COMPENSABLE, NON_EXCUSABLE):
        return {"entitlement": stated, "basis": "stated",
                "note": "read from the record or supplied by the reviewer"}
    kind = event.get("kind") or event.get("type")
    mapped = DEFAULT_ENTITLEMENT.get(kind)
    if mapped and mapped != UNCLASSIFIED:
        return {"entitlement": mapped, "basis": "typical_for_event_type",
                "note": f"a {kind!r} event TYPICALLY carries this entitlement — the contract governs, "
                        "so a reviewer should confirm it rather than inherit it"}
    return {"entitlement": UNCLASSIFIED, "basis": "unstated",
            "note": "no entitlement is stated and the event type does not imply one. Excusability is "
                    "a contract reading, not a property of a date — this is left open rather than "
                    "defaulted in either direction"}


def analyse(events: list[dict] | None, activities: list[dict] | None = None,
            method: str | None = None, baseline_finish: Any = None,
            actual_finish: Any = None) -> dict[str, Any]:
    """Compute an extension of time, with the method stated beside it.

    `activities` are `schedule_cpm.compute()` rows, used for the total float that decides whether a
    delay reaches the completion date at all. `events` carry `{id, kind|type, days, activity_id?,
    start?, entitlement?}`."""
    if method not in METHODS:
        return {"status": STATUS_NO_METHOD, "eot_days": None, "method": None,
                "methods_available": dict(METHODS),
                "status_meaning": STATUS_MEANING[STATUS_NO_METHOD],
                "reason": f"method must be one of {sorted(METHODS)} — the same facts give different "
                          "answers under different methods, so an unmethodded EOT cannot be weighed"}

    b_finish, a_finish = _d(baseline_finish), _d(actual_finish)
    if b_finish is None:
        return {"status": STATUS_NO_BASELINE, "eot_days": None, "method": method,
                "status_meaning": STATUS_MEANING[STATUS_NO_BASELINE],
                "reason": "no baseline finish date — there is nothing to measure the delay against"}

    by_id = {a.get("id"): a for a in (activities or []) if a.get("id")}
    rows: list[dict] = []
    for i, ev in enumerate(events or []):
        days = _num(ev.get("days"))
        cls = classify(ev)
        act = by_id.get(ev.get("activity_id"))
        tf = total_float(act) if act else None

        if days is None:
            rows.append({"id": ev.get("id") or f"#{i}", "kind": ev.get("kind") or ev.get("type"),
                         "days": None, "critical": None, "absorbed_by_float": None,
                         "eot_days": None, **cls,
                         "reason": "the event states no duration, so its impact cannot be computed"})
            continue

        # Float belongs to the project until consumed. A delay inside total float moves nothing, and
        # "absorbed" is a different finding from "no delay" — the second reads as though nothing
        # happened, which is what a claim reviewer must not be told.
        absorbed = tf is not None and days <= tf
        impact = 0.0 if absorbed else (days - tf if tf is not None else days)
        entitled = impact if cls["entitlement"] in (EXCUSABLE_COMPENSABLE,
                                                    EXCUSABLE_NON_COMPENSABLE) else 0.0
        rows.append({
            "id": ev.get("id") or f"#{i}", "kind": ev.get("kind") or ev.get("type"),
            "activity_id": ev.get("activity_id"), "days": days,
            "total_float": tf, "absorbed_by_float": absorbed,
            "critical": (tf == 0) if tf is not None else None,
            "impact_days": round(impact, 2), "eot_days": round(entitled, 2), **cls,
            "reason": ("this delay sits inside the activity's total float, so it does not move "
                       "completion — absorbed, which is not the same as no delay having occurred"
                       if absorbed else
                       "no entitlement: the event is not classified as excusable"
                       if entitled == 0 and impact > 0 else
                       "extends completion by its impact beyond available float"),
        })

    # CONCURRENCY IS REPORTED, NOT APPORTIONED. Overlapping employer-risk and contractor-risk delay is
    # the single most contested question in the discipline and the protocols disagree with each other.
    # Naming the pairs is a finding; splitting them by a silent rule would be a fabrication.
    concurrent = _concurrency(events or [])

    granted = sum(r["eot_days"] or 0 for r in rows)
    variance = (a_finish - b_finish).days if a_finish else None

    return {
        "status": STATUS_OK,
        "method": method,
        "method_meaning": METHODS[method],
        "status_meaning": STATUS_MEANING[STATUS_OK],
        "baseline_finish": b_finish.isoformat(),
        "actual_finish": a_finish.isoformat() if a_finish else None,
        "actual_variance_days": variance,
        "eot_days": round(granted, 2),
        "revised_finish": (b_finish.toordinal() + int(round(granted))) and
                          date.fromordinal(b_finish.toordinal() + int(round(granted))).isoformat(),
        "events": rows,
        "by_entitlement": {k: round(sum(r["eot_days"] or 0 for r in rows
                                        if r.get("entitlement") == k), 2)
                           for k in (EXCUSABLE_COMPENSABLE, EXCUSABLE_NON_COMPENSABLE,
                                     NON_EXCUSABLE, UNCLASSIFIED)},
        "unclassified_count": sum(1 for r in rows if r.get("entitlement") == UNCLASSIFIED),
        "concurrency": concurrent,
        "note": ("EOT is the sum of impact beyond available float on EXCUSABLE events only. "
                 f"Method: {method}. Concurrency is named, never apportioned — whether overlapping "
                 "employer-risk and contractor-risk delay yields time, money, both or neither is a "
                 "contract and jurisdiction question the protocols themselves disagree on."),
    }


def _concurrency(events: list[dict]) -> dict[str, Any]:
    """Overlapping delays of opposing risk, named as pairs. No apportionment."""
    dated = []
    for ev in events:
        s = _d(ev.get("start"))
        d = _num(ev.get("days"))
        if s and d is not None:
            dated.append((ev, s, s.toordinal() + int(d)))
    pairs = []
    for i in range(len(dated)):
        for j in range(i + 1, len(dated)):
            (a, a_s, a_e), (b, b_s, b_e) = dated[i], dated[j]
            if a_s.toordinal() >= b_e or b_s.toordinal() >= a_e:
                continue
            ca, cb = classify(a)["entitlement"], classify(b)["entitlement"]
            opposing = {ca, cb} & {NON_EXCUSABLE} and {ca, cb} & {EXCUSABLE_COMPENSABLE,
                                                                  EXCUSABLE_NON_COMPENSABLE}
            if opposing:
                overlap = min(a_e, b_e) - max(a_s.toordinal(), b_s.toordinal())
                pairs.append({"a": a.get("id"), "b": b.get("id"),
                              "a_entitlement": ca, "b_entitlement": cb,
                              "overlap_days": max(0, overlap)})
    return {
        "pairs": pairs, "count": len(pairs),
        "apportioned": False,
        "note": ("overlapping delays of opposing risk are NAMED here and deliberately not split. "
                 "Apportionment is contested between the published protocols and governed by the "
                 "contract; a silent 50/50 would manufacture the most argued number in the discipline "
                 "and present it as arithmetic." if pairs else
                 "no opposing-risk overlaps were found among events carrying both a start and a "
                 "duration. Events missing either were not tested — that is unexamined, not clear."),
    }
