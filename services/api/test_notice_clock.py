"""R22-NOTICE-CLOCK — the arithmetic and the refusals.

A notice clock is a feature whose failure mode is a confident wrong date. Nothing throws, nothing
looks odd, and somebody relies on it. So most of what is asserted here is not that the module
computes a deadline — it is that it **declines to** in the four situations where any computed date
would be a fabrication:

* a clause that runs from awareness, with no awareness recorded;
* a clause that runs from "whichever is later", with only one of the two dates;
* a clause that fixes no period at all (FAR's "promptly");
* a project that has not adopted a contract family.

The temptation in each case is a sensible-looking fallback. Each one is tested for absence.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_notice_clock.py
"""
import json
import sys
from datetime import date

sys.path.insert(0, "src")

from aec_api import notice_clock as nc  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def by_id(cid):
    return next(c for c in nc.CLAUSES if c.id == cid)


# --- 1. the library is internally consistent ----------------------------------------------------
check("every clause belongs to a known family",
      all(c.family in nc.FAMILIES for c in nc.CLAUSES),
      sorted({c.family for c in nc.CLAUSES} - set(nc.FAMILIES)))
check("every clause uses a known basis", all(c.basis in nc.BASIS for c in nc.CLAUSES))
check("every clause uses a known consequence",
      all(c.consequence in nc.CONSEQUENCES for c in nc.CLAUSES))
check("every clause names only known event types",
      all(set(c.event_types) <= set(nc.EVENT_TYPES) for c in nc.CLAUSES))
check("every clause carries a citation and a reference",
      all(c.citation.strip() and c.reference.strip() for c in nc.CLAUSES))
check("clause ids are unique", len({c.id for c in nc.CLAUSES}) == len(nc.CLAUSES))
check("a clause with no fixed period declares basis 'promptly'",
      all((c.days is None) == (c.basis == "promptly") for c in nc.CLAUSES))

# The select on prime_contract and the label map are two tables encoding one vocabulary. They drift
# silently: a renamed option becomes an unresolvable family, `scan` reports "no family adopted", and
# the register goes quietly empty on a project that has adopted one.
mod = json.load(open("modules/prime_contract/module.json", encoding="utf-8"))
opts = next(f for f in mod["fields"] if f["name"] == "notice_family")["options"]
check("the prime_contract select and FAMILY_BY_LABEL agree, both ways",
      set(opts) == set(nc.FAMILY_BY_LABEL),
      {"only_in_module": sorted(set(opts) - set(nc.FAMILY_BY_LABEL)),
       "only_in_map": sorted(set(nc.FAMILY_BY_LABEL) - set(opts))})
check("every label resolves to a real family",
      all(v in nc.FAMILIES for v in nc.FAMILY_BY_LABEL.values()))
check("every family is reachable from some label",
      set(nc.FAMILY_BY_LABEL.values()) == set(nc.FAMILIES),
      sorted(set(nc.FAMILIES) - set(nc.FAMILY_BY_LABEL.values())))

# --- 2. counting ---------------------------------------------------------------------------------
cal = nc.Calendar()
check("calendar days: the trigger day is day zero",
      nc.add_period(date(2026, 3, 2), 21, "calendar", cal) == date(2026, 3, 23))
check("weeks are calendar weeks (NEC counts in weeks)",
      nc.add_period(date(2026, 3, 2), 8, "weeks", cal) == date(2026, 4, 27))
# Mon 2 Mar + 10 business days = Mon 16 Mar (two weekends skipped).
check("business days skip the weekend",
      nc.add_period(date(2026, 3, 2), 10, "business", cal) == date(2026, 3, 16))
holiday_cal = nc.Calendar(holidays=frozenset({date(2026, 3, 9)}))
check("business days skip a supplied holiday too",
      nc.add_period(date(2026, 3, 2), 10, "business", holiday_cal) == date(2026, 3, 17))
gulf = nc.Calendar(weekend=(4, 5))          # Fri/Sat, as much of the Gulf runs
# Wed 4 Mar 2026 + 2 business days. Sat/Sun: Thu 5, Fri 6. Fri/Sat: Thu 5, then Fri and Sat are the
# weekend, so Sun 8. Two days apart on the same clause — which is why the weekend is an input rather
# than a constant. Choose the dates with care: across a whole week both conventions skip two days
# and the difference cancels, so a carelessly chosen pair passes while asserting nothing. The first
# version of this check did exactly that.
check("the Sat/Sun weekend gives Fri 6 Mar",
      nc.add_period(date(2026, 3, 4), 2, "business", cal) == date(2026, 3, 6),
      nc.add_period(date(2026, 3, 4), 2, "business", cal))
check("the Fri/Sat weekend gives Sun 8 Mar — two days later, same clause",
      nc.add_period(date(2026, 3, 4), 2, "business", gulf) == date(2026, 3, 8),
      nc.add_period(date(2026, 3, 4), 2, "business", gulf))

# --- 3. AIA 21 days, running from the LATER of occurrence and recognition -----------------------
aia = by_id("aia_a201_2017.15.1.3.1")
c = nc.clock(aia, occurred_on="2026-03-02", became_aware_on="2026-03-09", today="2026-03-10")
check("later_of takes the later date", c["start_date"] == "2026-03-09")
check("  21 calendar days from it", c["due_date"] == "2026-03-30")
check("  days remaining are counted from today", c["days_remaining"] == 20)
check("  status is open", c["status"] == "open")
check("  the citation rides along", "21 days" in c["citation"])
check("  and what missing it means, per the contract text",
      c["consequence"] == "contractual_requirement" and c["consequence_means"])

late = nc.clock(aia, occurred_on="2026-03-02", became_aware_on="2026-03-02", today="2026-04-01")
check("a passed deadline is expired", late["status"] == "expired" and late["days_remaining"] < 0)
soon = nc.clock(aia, occurred_on="2026-03-02", became_aware_on="2026-03-02", today="2026-03-20")
check("within the window it is due_soon", soon["status"] == "due_soon", soon["days_remaining"])
today_due = nc.clock(aia, occurred_on="2026-03-02", became_aware_on="2026-03-02", today="2026-03-23")
check("on the day it is due_today", today_due["status"] == "due_today")

# --- 4. THE REFUSALS -----------------------------------------------------------------------------
# 4a. awareness-based clause with no awareness date. The wrong answer here is to quietly use the
# occurrence date: it looks conservative and it is not. An event that occurred 40 days ago and was
# discovered yesterday would read as time-barred while three weeks remain.
fidic = by_id("fidic_red_2017.20.2.1")
ind = nc.clock(fidic, occurred_on="2026-02-01", today="2026-03-13")
check("an awareness clause with no awareness date is indeterminate", ind["status"] == "indeterminate")
check("  it names the field that is missing", ind["missing"] == ["became_aware_on"], ind.get("missing"))
check("  and produces NO due date", ind["due_date"] is None and ind["days_remaining"] is None)
check("  in particular it does not silently fall back to the occurrence date",
      ind["start_date"] is None)
# Given the awareness date, the same clause computes — and lands 27 days AFTER the naive answer.
ok = nc.clock(fidic, occurred_on="2026-02-01", became_aware_on="2026-03-12", today="2026-03-13")
check("  with awareness recorded it computes", ok["due_date"] == "2026-04-09")
check("  the naive fallback would have said expired; the truth is 27 days remain",
      ok["status"] == "open" and ok["days_remaining"] == 27, ok["days_remaining"])
check("  FIDIC 20.2.1 is an express time bar in its own words",
      ok["consequence"] == "express_time_bar")

# 4b. later_of with only one of the two dates: the missing one could be the later one.
half = nc.clock(aia, occurred_on="2026-03-02", today="2026-03-10")
check("later_of with one date missing is indeterminate", half["status"] == "indeterminate")
check("  and says which", half["missing"] == ["became_aware_on"], half.get("missing"))

# 4c. a clause with no fixed period must not acquire one.
far = by_id("far.52.236-2")
p = nc.clock(far, became_aware_on="2026-03-02", today="2026-03-10")
check("a 'promptly' clause reports no_fixed_period", p["status"] == "no_fixed_period")
check("  with no invented deadline", p["due_date"] is None and p["days_remaining"] is None)
check("  but it still states the obligation", "promptly" in p["why"])

# 4d. no adopted family.
events = nc.detect(daily_reports=[{"id": "d1", "data": {"report_date": "2026-03-02",
                                                        "weather_impact": "Stoppage", "weather": "Snow"}}])
none = nc.scan(events, None, today="2026-03-10")
check("no adopted family yields an empty register", none["items"] == [] and none["adopted"] is False)
check("  and says why rather than choosing one", "cannot be inferred" in none["why"])
bogus = nc.scan(events, "aia_a201_1997", today="2026-03-10")
check("an unknown family is refused, not defaulted", bogus["adopted"] is False and not bogus["items"])

# --- 5. the business-day warning -----------------------------------------------------------------
biz = nc.Clause(id="x.1", family="aia_a201_2017", reference="§X", event_types=("delay_other",),
                days=10, basis="business", starts_on="occurrence",
                consequence="contractual_requirement", notify="the other party", citation="test")
w = nc.clock(biz, occurred_on="2026-03-02", today="2026-03-03")
check("a business-day count with no holiday list warns", "holiday calendar" in (w.get("warning") or ""))
check("  and the warning names the direction of the error", "later than shown" in w["warning"])
w2 = nc.clock(biz, occurred_on="2026-03-02", today="2026-03-03", calendar=holiday_cal)
check("  with holidays supplied there is no warning", "warning" not in w2)
check("  and the calendar used is reported", w2["calendar"]["holidays_supplied"] == 1)
check("  including which days are the weekend", w2["calendar"]["weekend"] == ["Sat", "Sun"])

roll = nc.Clause(id="x.2", family="aia_a201_2017", reference="§Y", event_types=("delay_other",),
                 days=5, basis="calendar", starts_on="occurrence",
                 consequence="contractual_requirement", notify="x", citation="y", roll_forward=True)
r = nc.clock(roll, occurred_on="2026-03-02", today="2026-03-03")   # +5 = Sat 7 Mar
check("a deadline landing on a weekend rolls forward when the clause says so",
      r["due_date"] == "2026-03-09" and r["rolled_forward_from"] == "2026-03-07", r["due_date"])

# --- 6. detection from the field record ----------------------------------------------------------
daily = [
    {"id": "d1", "ref": "DR-001", "data": {"report_date": "2026-03-02", "weather": "Snow",
                                           "weather_impact": "Full-Day Lost"}},
    {"id": "d2", "ref": "DR-002", "data": {"report_date": "2026-03-03", "weather": "Rain",
                                           "weather_impact": "Minor Delay"}},
    {"id": "d3", "ref": "DR-003", "data": {"report_date": "2026-03-04",
                                           "delays": "Crane down, no steel erected"}},
    {"id": "d4", "data": {"weather_impact": "Stoppage"}},                       # no date
]
ce = [
    {"id": "c1", "ref": "CE-001", "created_at": "2026-03-05T10:00:00",
     "data": {"reason": "Unforeseen Condition", "subject": "Rock at footing F-3"}},
    {"id": "c2", "created_at": "2026-03-06T10:00:00",
     "data": {"reason": "Allowance Reconciliation", "subject": "Carpet allowance"}},
    {"id": "c3", "created_at": "2026-03-07T10:00:00",
     "data": {"reason": "Owner Request", "subject": "Add rooftop screen",
              "schedule_impact_days": 6}},
]
rfis = [
    {"id": "r1", "ref": "RFI-014", "created_at": "2026-03-08T10:00:00",
     "data": {"subject": "Beam conflict", "cost_impact": "Yes", "schedule_impact": "None"}},
    {"id": "r2", "created_at": "2026-03-08T10:00:00",
     "data": {"subject": "Paint colour", "cost_impact": "None", "schedule_impact": "None"}},
]
found = nc.detect(daily_reports=daily, change_events=ce, rfis=rfis)
types = [(e["source_id"], e["type"]) for e in found]
check("a full-day weather loss is a triggering event", ("d1", "weather_delay") in types)
check("a minor delay is NOT — a clause on every drizzle buries the real one",
      ("d2", "weather_delay") not in types)
check("a free-text delay entry is a triggering event", ("d3", "delay_other") in types)
check("a daily report with no date is skipped", not any(e["source_id"] == "d4" for e in found))
check("an unforeseen condition maps to differing_site_condition",
      ("c1", "differing_site_condition") in types)
check("an allowance reconciliation is not a notifiable event",
      not any(e["source_id"] == "c2" for e in found))
check("a change with schedule impact raises a delay event too",
      ("c3", "change_directed") in types and ("c3", "delay_other") in types)
check("an RFI flagged cost-impacting is a constructive-change event",
      ("r1", "change_constructive") in types)
check("an RFI with no impact flagged is not", not any(e["source_id"] == "r2" for e in found))

# The date_basis field is the honest part: a daily report knows when it happened, an RFI only knows
# when someone wrote it down.
basis = {e["source_id"]: e["date_basis"] for e in found}
check("a daily report's date is labelled 'occurred'", basis["d1"] == "occurred")
check("an RFI's date is labelled 'reported' — it is a proxy, and says so", basis["r1"] == "reported")
check("nothing infers an awareness date",
      all(e["became_aware_on"] is None for e in found))
check("detection is deterministic", [e["source_id"] for e in nc.detect(
    daily_reports=daily, change_events=ce, rfis=rfis)] == [e["source_id"] for e in found])

# --- 7. the register ------------------------------------------------------------------------------
reg = nc.scan(found, "aia_a201_2017", today="2026-03-30")
check("the register is adopted and labelled", reg["adopted"] and "A201" in reg["family_label"])
check("it carries the verify warning", "executed contract" in reg["verify"])
statuses = [i.get("status") for i in reg["items"]]
check("expired items sort first",
      statuses == sorted(statuses, key=lambda s: nc._STATUS_ORDER.get(s, 9)), statuses)
check("the counts add up to the items", sum(reg["counts"].values()) == len(reg["items"]))
check("a weather event picks up BOTH AIA clauses that apply to it",
      len([i for i in reg["items"]
           if i.get("event", {}).get("source_id") == "d1" and i.get("clause")]) == 2)
# AIA 15.1.3.1 runs from later_of, and detection never sets awareness — so under AIA the register is
# honest about being incomplete rather than confidently wrong.
check("under a later_of clause with no awareness recorded, items are indeterminate",
      all(i["status"] == "indeterminate" for i in reg["items"]
          if i.get("clause") == "aia_a201_2017.15.1.3.1"))

# An event type the family has no provision for is reported as such, not dropped.
dsc = [e for e in found if e["type"] == "differing_site_condition"]
nec = nc.scan(dsc, "nec4_ecc", today="2026-03-30")
check("NEC4 covers every event type", all(i.get("clause") for i in nec["items"]))
weather_only = nc.scan([e for e in found if e["type"] == "weather_delay"], "far_us_federal",
                       today="2026-03-30")
check("a family with no provision for the event says so rather than dropping it",
      all(i["status"] == "no_clause" for i in weather_only["items"]) and weather_only["items"])

# --- 8. the draft ---------------------------------------------------------------------------------
item = next(i for i in nc.scan(dsc, "fidic_red_2017", today="2026-03-10")["items"] if i.get("clause"))
letter = nc.draft(item, project="Riverside", from_party="Acme Construction")
check("the draft names the clause", "20.2.1" in letter)
check("  quotes the clause rather than paraphrasing", item["citation"][:40] in letter)
check("  names the project and the party", "Riverside" in letter and "Acme Construction" in letter)
check("  reserves rights", "rights are reserved" in letter)
check("  leaves the signature unfilled", "______" in letter)
check("  and flags a reported date as not necessarily the occurrence date",
      ("not necessarily the date" in letter) == (item["event"]["date_basis"] == "reported"))

# --- 9. parse_calendar refuses bad input rather than skipping it -----------------------------------
check("a good weekend parses", nc.parse_calendar("Fri,Sat").weekend == (4, 5))

# A weekend covering all seven days leaves no working day, and `add_period`'s business-day loop only
# terminates when it finds one — so it walks to date.max (~2.9M iterations) and raises OverflowError
# from unrelated code. That presents as a slow endpoint rather than a bad calendar. Latent today (no
# clause in the library uses basis="business"), but the branch is written, documented, and `BASIS`
# advertises it — so the first business-basis clause anyone adds makes it live.
try:
    nc.parse_calendar("Mon,Tue,Wed,Thu,Fri,Sat,Sun")
    check("a seven-day weekend is refused at parse time", False, "no exception")
except ValueError as e:
    check("a seven-day weekend is refused at parse time", True)
    check("  and the message names the consequence", "no business day" in str(e), str(e)[:90])

# Guarded at both layers: Calendar is a plain dataclass, so a caller can build one directly without
# going through parse_calendar. The loop must refuse rather than run.
try:
    nc.add_period(date(2026, 3, 2), 1, "business", nc.Calendar(weekend=tuple(range(7))))
    check("add_period refuses a no-working-day calendar", False, "no exception")
except ValueError as e:
    check("add_period refuses a no-working-day calendar", True)
    check("  as a ValueError, not an OverflowError 2.9M iterations later",
          "no working days" in str(e), str(e)[:90])

# The legitimate extreme still works: a six-day weekend leaves exactly one working day.
six = nc.Calendar(weekend=(0, 1, 2, 3, 4, 5))          # only Sunday works
check("a six-day weekend still terminates",
      nc.add_period(date(2026, 3, 2), 2, "business", six) == date(2026, 3, 15),
      nc.add_period(date(2026, 3, 2), 2, "business", six))
for bad in ("Funday", "Fri,Xyz"):
    try:
        nc.parse_calendar(bad)
        check(f"weekend {bad!r} is refused", False, "no exception")
    except ValueError:
        check(f"weekend {bad!r} is refused", True)
try:
    nc.parse_calendar(None, "2026-13-45")
    check("an unparseable holiday is refused", False, "no exception")
except ValueError:
    check("an unparseable holiday is refused", True)
check("holidays parse into the calendar",
      nc.parse_calendar(None, "2026-03-09, 2026-03-10").holidays
      == frozenset({date(2026, 3, 9), date(2026, 3, 10)}))
check("resolve_family accepts an id and a label, and rejects anything else",
      nc.resolve_family("nec4_ecc") == "nec4_ecc"
      and nc.resolve_family("NEC4 ECC") == "nec4_ecc"
      and nc.resolve_family("NEC 3") is None and nc.resolve_family(None) is None)

print()
if FAILED:
    print(f"notice_clock: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("notice_clock: all checks passed")
