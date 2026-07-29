"""R22-NOTICE-CLOCK — contractual notice periods and time bars, computed from the field record.

**The problem.** A contract gives you a fixed number of days to notify the other party of an event
before you lose the right to be paid or given time for it. The events are already in this system —
a stoppage in a daily report, an unforeseen condition on a change event, an RFI the contractor has
flagged as cost-impacting — and the clock starts running the day they are recorded. Nothing in the
platform counts. This module counts, and says what it is counting *under*.

**The contract governs, not this table.** `CLAUSES` holds the standard notice provisions of the
common contract families with their citations, because most projects run on one of them unamended.
They are **starting points to verify against the executed contract**, not law: a single amended
sub-clause changes the number, and an amended contract that this module quietly reports under the
standard form is worse than no tracking at all — it produces confidence in a deadline that does not
apply. Two consequences in the design:

* a project must **adopt** a family before anything is computed. `scan()` with no family returns
  nothing and says why; it does not guess from the project's country or fall back to a default.
* every clock carries the `clause`, `citation` and `consequence` it was computed from, so the number
  on screen can always be traced to the words it came from.

**This is a diary, not advice.** Whether late notice actually forfeits a claim depends on the
contract's wording, the governing law and the forum; the same words are enforced differently in
different places. So `consequence` distinguishes what the *contract text* says — `express_time_bar`
(the clause itself states the claim is barred), `condition_precedent`, `contractual_requirement` —
and stops there. It never renders a legal conclusion.

**Three counting traps, each of which silently produces a wrong date:**

1. **What starts the clock.** AIA A201 runs from the *later of* occurrence and first recognition;
   FIDIC and NEC4 run from *awareness*. When a clause runs from awareness and no awareness date has
   been recorded, this module reports `indeterminate` and names the missing field. It does **not**
   substitute the occurrence date. That substitution looks conservative — an earlier date means an
   earlier deadline — and it is not: an event that occurred forty days ago and was discovered
   yesterday reads as *expired* when three weeks remain, and a claimant told the bar has fallen
   abandons a claim that was live.

2. **Which days count.** Calendar days, business days and NEC's weeks are three different counts.
   Business days need a holiday list; without one the count is silently short every public holiday.
   `Calendar.holidays` is therefore an explicit input, and `holidays_supplied` is reported on every
   business-day clock so a total computed without one is visible as such.

3. **Which days are the weekend.** Saturday–Sunday is a local convention, not a universal one — much
   of the Gulf runs Friday–Saturday, and a project there counts business days differently. The
   weekend is a `Calendar` field and is reported with the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

# --- what kind of event a notice answers to -------------------------------------------------------
#: Deliberately coarse. These are the categories contracts actually write notice provisions about;
#: a finer taxonomy would not map onto any clause and would only make matching look more precise
#: than it is.
EVENT_TYPES = (
    "change_directed",            # an instruction/directive changing the work
    "change_constructive",        # conduct having the effect of a change, not instructed as one
    "differing_site_condition",   # concealed / unknown / unforeseeable physical conditions
    "weather_delay",              # abnormal weather delaying the work
    "delay_other",                # any other delay to the critical path
    "suspension",                 # suspension of the work
    "defect_nonconformance",      # defective or non-conforming work
)

BASIS = ("calendar", "business", "weeks", "promptly")

#: What the contract *text* says about missing the period. Not a prediction of how a tribunal rules.
CONSEQUENCES = {
    "express_time_bar": "the clause states in terms that the claim is barred if notice is late",
    "condition_precedent": "notice is expressed as a condition precedent to the entitlement",
    "contractual_requirement": "the contract requires notice within the period; it does not state "
                               "the effect of lateness in terms",
}


@dataclass(frozen=True)
class Clause:
    """One notice provision. `days is None` means the clause fixes no period (e.g. 'promptly')."""
    id: str
    family: str
    reference: str
    event_types: tuple[str, ...]
    days: int | None
    basis: str
    starts_on: str                 # "occurrence" | "awareness" | "later_of"
    consequence: str
    notify: str
    citation: str
    roll_forward: bool = False     # a deadline landing on a non-working day moves to the next one


#: Contract families this module knows the standard notice provisions of.
FAMILIES: dict[str, str] = {
    "aia_a201_2017": "AIA A201–2017 General Conditions",
    "fidic_red_2017": "FIDIC Red Book 2017 (2nd Ed.)",
    "fidic_red_1999": "FIDIC Red Book 1999 (1st Ed.)",
    "nec4_ecc": "NEC4 Engineering and Construction Contract",
    "consensusdocs_200": "ConsensusDocs 200 (2017)",
    "ejcdc_c700_2018": "EJCDC C-700 (2018)",
    "far_us_federal": "US Federal — FAR construction clauses",
}

#: Standard notice provisions. VERIFY EACH AGAINST THE EXECUTED CONTRACT — an amended sub-clause
#: changes the number, and this table cannot know that it was amended.
CLAUSES: tuple[Clause, ...] = (
    # --- AIA A201–2017 ---------------------------------------------------------------------------
    Clause(
        id="aia_a201_2017.15.1.3.1", family="aia_a201_2017", reference="§15.1.3.1 — Notice of Claims",
        event_types=("change_constructive", "delay_other", "weather_delay", "suspension"),
        days=21, basis="calendar", starts_on="later_of", consequence="contractual_requirement",
        notify="the other party, and to the Initial Decision Maker if one is designated",
        citation="Claims must be initiated by notice within 21 days after occurrence of the event "
                 "giving rise to the Claim, or within 21 days after the claimant first recognizes "
                 "the condition giving rise to it, whichever is later.",
    ),
    Clause(
        id="aia_a201_2017.3.7.4", family="aia_a201_2017",
        reference="§3.7.4 — Concealed or Unknown Conditions",
        event_types=("differing_site_condition",),
        days=14, basis="calendar", starts_on="awareness", consequence="contractual_requirement",
        notify="the Architect and the Owner",
        citation="Notice promptly before conditions are disturbed and in no event later than 14 days "
                 "after first observance of the conditions.",
    ),
    Clause(
        id="aia_a201_2017.15.1.6.2", family="aia_a201_2017",
        reference="§15.1.6.2 — Claims for Additional Time (weather)",
        event_types=("weather_delay",),
        days=21, basis="calendar", starts_on="later_of", consequence="contractual_requirement",
        notify="the other party, with substantiating data",
        citation="A claim for additional time on account of weather must be documented by data "
                 "substantiating that the weather was abnormal for the period, could not have been "
                 "reasonably anticipated, and had an adverse effect on the scheduled construction.",
    ),
    # --- FIDIC ------------------------------------------------------------------------------------
    Clause(
        id="fidic_red_2017.20.2.1", family="fidic_red_2017", reference="Sub-Clause 20.2.1 — Notice of Claim",
        event_types=EVENT_TYPES,
        days=28, basis="calendar", starts_on="awareness", consequence="express_time_bar",
        notify="the Engineer",
        citation="Notice within 28 days after the claiming Party became aware, or should have become "
                 "aware, of the event or circumstance. If not given within 28 days the claiming Party "
                 "is not entitled to the additional payment or extension of time and the other Party "
                 "is discharged from liability in connection with the claim.",
    ),
    Clause(
        id="fidic_red_2017.20.2.4", family="fidic_red_2017",
        reference="Sub-Clause 20.2.4 — fully detailed Claim",
        event_types=EVENT_TYPES,
        days=84, basis="calendar", starts_on="awareness", consequence="condition_precedent",
        notify="the Engineer",
        citation="A fully detailed Claim within 84 days after the claiming Party became aware, or "
                 "should have become aware, of the event or circumstance.",
    ),
    Clause(
        id="fidic_red_1999.20.1", family="fidic_red_1999", reference="Sub-Clause 20.1 — Contractor's Claims",
        event_types=EVENT_TYPES,
        days=28, basis="calendar", starts_on="awareness", consequence="express_time_bar",
        notify="the Engineer",
        citation="Notice as soon as practicable, and not later than 28 days after the Contractor "
                 "became aware, or should have become aware, of the event or circumstance. If notice "
                 "is not given within 28 days the Time for Completion shall not be extended, the "
                 "Contractor is not entitled to additional payment, and the Employer is discharged "
                 "from all liability in connection with the claim.",
    ),
    # --- NEC4 — counted in WEEKS, which is why `basis` exists ------------------------------------
    Clause(
        id="nec4_ecc.61.3", family="nec4_ecc", reference="Clause 61.3 — notifying a compensation event",
        event_types=EVENT_TYPES,
        days=8, basis="weeks", starts_on="awareness", consequence="express_time_bar",
        notify="the Project Manager",
        citation="The Contractor notifies the Project Manager of an event which has happened and "
                 "which is a compensation event within eight weeks of becoming aware that the event "
                 "has happened. Otherwise the Prices, the Completion Date and the Key Dates are not "
                 "changed — unless the event arose from the Project Manager or Supervisor giving an "
                 "instruction or notification the contract required them to notify.",
    ),
    # --- ConsensusDocs -----------------------------------------------------------------------------
    Clause(
        id="consensusdocs_200.8.4", family="consensusdocs_200", reference="§8.4 — Notice of Claim",
        event_types=EVENT_TYPES,
        days=14, basis="calendar", starts_on="awareness", consequence="contractual_requirement",
        notify="the other party",
        citation="Written notice of a claim within fourteen (14) days after the occurrence giving "
                 "rise to the claim, or after the claimant first recognizes the condition.",
    ),
    # --- EJCDC --------------------------------------------------------------------------------------
    Clause(
        id="ejcdc_c700_2018.11.02", family="ejcdc_c700_2018", reference="§11.02 — Change Proposals",
        event_types=EVENT_TYPES,
        days=30, basis="calendar", starts_on="occurrence", consequence="contractual_requirement",
        notify="the Engineer",
        citation="A Change Proposal must be submitted within 30 days after the start of the event "
                 "giving rise to it.",
    ),
    # --- US Federal — the clause with NO fixed period, which the engine must not invent one for -----
    Clause(
        id="far.52.236-2", family="far_us_federal", reference="FAR 52.236-2 — Differing Site Conditions",
        event_types=("differing_site_condition",),
        days=None, basis="promptly", starts_on="awareness", consequence="condition_precedent",
        notify="the Contracting Officer",
        citation="The Contractor shall promptly, and before the conditions are disturbed, give a "
                 "written notice to the Contracting Officer. No fixed number of days is stated; the "
                 "operative limit is that the conditions must not have been disturbed.",
    ),
    Clause(
        id="far.52.243-4", family="far_us_federal", reference="FAR 52.243-4 — Changes",
        event_types=("change_directed", "change_constructive"),
        days=20, basis="calendar", starts_on="awareness", consequence="condition_precedent",
        notify="the Contracting Officer",
        citation="Written notice stating the general nature and amount of the proposal must be given "
                 "within 20 days after the Contractor is directed to, or begins, the changed work.",
    ),
)


@dataclass(frozen=True)
class Calendar:
    """Which days count. Both fields are reported alongside every result that depended on them.

    `weekend` holds `date.weekday()` indices — Monday is 0, Sunday is 6. The default is the
    Saturday–Sunday convention; it is a default, not a fact about the world.
    """
    weekend: tuple[int, ...] = (5, 6)
    holidays: frozenset[date] = field(default_factory=frozenset)

    def is_working(self, d: date) -> bool:
        return d.weekday() not in self.weekend and d not in self.holidays

    def describe(self) -> dict[str, Any]:
        names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        return {
            "weekend": [names[i] for i in sorted(self.weekend)],
            "holidays_supplied": len(self.holidays),
        }


def parse_date(value: Any) -> date | None:
    """Lenient ISO date read — the module records store dates as strings."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def add_period(start: date, n: int, basis: str, cal: Calendar) -> date:
    """`start` plus `n` periods on the given basis.

    The trigger day is day zero — "within 21 days after the occurrence" is occurrence + 21, which is
    the reading every one of these clauses takes. Business days step forward over working days only;
    weeks are calendar weeks, which is what NEC means by a week.
    """
    if basis == "calendar":
        return start + timedelta(days=n)
    if basis == "weeks":
        return start + timedelta(weeks=n)
    if basis == "business":
        # Fail closed before entering the loop. `Calendar` is a plain dataclass, so a weekend
        # covering every day is constructible without going through `parse_calendar` — and this
        # `while` only terminates when a working day is found. With none, it walks to `date.max`:
        # ~2.9 million iterations of CPU and then an OverflowError from unrelated code, which
        # presents as a slow endpoint rather than a bad calendar.
        if not any(w not in cal.weekend for w in range(7)):
            raise ValueError(
                "this calendar has no working days — the weekend covers all seven, so no business "
                "day can ever elapse. Business-day periods are uncountable against it.")
        d, remaining = start, n
        while remaining > 0:
            d += timedelta(days=1)
            if cal.is_working(d):
                remaining -= 1
        return d
    raise ValueError(f"cannot count a period on basis {basis!r}")


def _start_date(clause: Clause, occurred: date | None, aware: date | None) -> tuple[date | None, list[str]]:
    """The date the clock starts, or None plus the fields that would have to be recorded first."""
    if clause.starts_on == "occurrence":
        return (occurred, [] if occurred else ["occurred_on"])
    if clause.starts_on == "awareness":
        # Deliberately NOT falling back to `occurred`. See the module docstring, trap 1.
        return (aware, [] if aware else ["became_aware_on"])
    if clause.starts_on == "later_of":
        if occurred and aware:
            return (max(occurred, aware), [])
        # "whichever is later" with one date missing is genuinely unknown: the missing one could be
        # later. Reporting the one we have would understate the time available.
        return (None, [f for f, v in (("occurred_on", occurred), ("became_aware_on", aware)) if not v])
    raise ValueError(f"unknown starts_on {clause.starts_on!r}")


def clock(clause: Clause, *, occurred_on: Any = None, became_aware_on: Any = None,
          today: Any = None, calendar: Calendar | None = None, due_soon_days: int = 7) -> dict[str, Any]:
    """The state of one notice period against one clause.

    Never returns a deadline it had to guess at. The three non-computable outcomes are distinct and
    all of them say what is missing:

    * `indeterminate` — a date the clause depends on has not been recorded;
    * `no_fixed_period` — the clause states no number of days (FAR's "promptly"), so there is a duty
      but no date; inventing one would be a fabrication dressed as a deadline;
    * a normal clock otherwise.
    """
    cal = calendar or Calendar()
    now = parse_date(today) or date.today()
    occurred, aware = parse_date(occurred_on), parse_date(became_aware_on)
    start, missing = _start_date(clause, occurred, aware)

    base: dict[str, Any] = {
        "clause": clause.id,
        "family": clause.family,
        "reference": clause.reference,
        "citation": clause.citation,
        "consequence": clause.consequence,
        "consequence_means": CONSEQUENCES[clause.consequence],
        "notify": clause.notify,
        "basis": clause.basis,
        "period": clause.days,
        "starts_on": clause.starts_on,
        "start_date": start.isoformat() if start else None,
        "calendar": cal.describe(),
        "as_of": now.isoformat(),
    }

    if start is None:
        return {**base, "status": "indeterminate", "due_date": None, "days_remaining": None,
                "missing": missing,
                "why": f"this clause runs from {clause.starts_on.replace('_', ' ')}; "
                       f"record {' and '.join(missing)} to start the clock"}

    if clause.days is None:
        return {**base, "status": "no_fixed_period", "due_date": None, "days_remaining": None,
                "why": "the clause fixes no number of days — the obligation is to notify promptly, "
                       "and no deadline can be computed from it"}

    due = add_period(start, clause.days, clause.basis, cal)
    rolled = None
    if clause.roll_forward and not cal.is_working(due):
        rolled = due
        while not cal.is_working(due):
            due += timedelta(days=1)

    remaining = (due - now).days
    if remaining < 0:
        status = "expired"
    elif remaining == 0:
        status = "due_today"
    elif remaining <= due_soon_days:
        status = "due_soon"
    else:
        status = "open"

    out = {**base, "status": status, "due_date": due.isoformat(), "days_remaining": remaining}
    if rolled is not None:
        out["rolled_forward_from"] = rolled.isoformat()
    if clause.basis == "business" and not cal.holidays:
        # A business-day count with no holiday list is short by one day per public holiday in the
        # window. Silently plausible, and wrong in the direction that loses the claim.
        out["warning"] = ("counted in business days with no holiday calendar supplied — the deadline "
                          "is later than shown by one day for each public holiday in the period")
    return out


# --- turning the field record into events ---------------------------------------------------------
#: Daily-report weather impacts that are treated as a delay event worth a clock. "Minor Delay" is
#: excluded: a clause on every drizzle produces a register nobody reads, which is how a real one
#: gets missed. Overridable by the caller.
WEATHER_TRIGGERS = ("Half-Day Lost", "Full-Day Lost", "Stoppage")

#: change_event.reason → event type.
REASON_EVENT = {
    "Unforeseen Condition": "differing_site_condition",
    "Owner Request": "change_directed",
    "Design Change": "change_directed",
    "Code / AHJ": "change_directed",
    "Field Conflict": "change_constructive",
    "Errors & Omissions": "change_constructive",
    "Allowance Reconciliation": None,          # a reconciliation is not a notifiable event
}


def _rec(r: dict) -> dict:
    return r.get("data") or r


def detect(*, daily_reports: list[dict] | None = None, change_events: list[dict] | None = None,
           rfis: list[dict] | None = None,
           weather_triggers: tuple[str, ...] = WEATHER_TRIGGERS) -> list[dict[str, Any]]:
    """Triggering events found in the field record.

    Each event carries `date_basis`, and that field is the honest part. A daily report has a
    `report_date`, which is when the thing happened. An RFI has only a created timestamp, which is
    when somebody wrote it down — usually later, sometimes much later. Both are offered as the
    occurrence date because they are the best available, and both are labelled so a clock computed
    from a `reported` date is visibly resting on a proxy rather than on a recorded fact.

    Nothing here sets `became_aware_on`. No field in the registry records it, and for the clauses
    that run from awareness that date is the whole question — it has to be entered by the person who
    knows, not inferred by this function.
    """
    out: list[dict[str, Any]] = []

    for r in daily_reports or []:
        d = _rec(r)
        when = parse_date(d.get("report_date"))
        if not when:
            continue
        if (d.get("weather_impact") or "") in weather_triggers:
            out.append(_event("weather_delay", r, when, "occurred",
                              f"{d.get('weather') or 'weather'} — {d['weather_impact']}",
                              "daily_report"))
        if (d.get("delays") or "").strip():
            out.append(_event("delay_other", r, when, "occurred",
                              str(d["delays"]).strip()[:200], "daily_report"))

    for r in change_events or []:
        d = _rec(r)
        etype = REASON_EVENT.get(d.get("reason") or "")
        if etype is None:
            continue
        when = parse_date(d.get("occurred_on")) or parse_date(r.get("created_at"))
        if not when:
            continue
        basis = "occurred" if d.get("occurred_on") else "reported"
        out.append(_event(etype, r, when, basis, d.get("subject") or d.get("reason") or "", "change_event"))
        if float(d.get("schedule_impact_days") or 0) > 0 and etype != "delay_other":
            out.append(_event("delay_other", r, when, basis,
                              f"{d['schedule_impact_days']} day(s) schedule impact: "
                              f"{d.get('subject') or ''}".strip(), "change_event"))

    for r in rfis or []:
        d = _rec(r)
        if (d.get("cost_impact") or "") != "Yes" and (d.get("schedule_impact") or "") != "Yes":
            continue
        when = parse_date(r.get("created_at"))
        if not when:
            continue
        out.append(_event("change_constructive", r, when, "reported",
                          d.get("subject") or "RFI", "rfi"))

    out.sort(key=lambda e: (e["date"], e["source"], e["source_id"] or "", e["type"]))
    return out


def _event(etype: str, record: dict, when: date, basis: str, description: str, source: str) -> dict[str, Any]:
    return {
        "type": etype,
        "date": when.isoformat(),
        "date_basis": basis,             # "occurred" = the record states when it happened
                                         # "reported" = the record only says when it was written down
        "description": description,
        "source": source,
        "source_id": record.get("id"),
        "source_ref": record.get("ref"),
        "became_aware_on": parse_date((record.get("data") or {}).get("became_aware_on")),
    }


def clauses_for(family: str, event_type: str | None = None) -> list[Clause]:
    return [c for c in CLAUSES
            if c.family == family and (event_type is None or event_type in c.event_types)]


#: Order the register is sorted in. Expired first — an expired time bar is the one thing that cannot
#: be fixed by acting sooner, and burying it under items still in hand is how it stays unnoticed.
_STATUS_ORDER = {"expired": 0, "due_today": 1, "due_soon": 2, "open": 3,
                 "indeterminate": 4, "no_fixed_period": 5}


def scan(events: list[dict[str, Any]], family: str | None, *, today: Any = None,
         calendar: Calendar | None = None, due_soon_days: int = 7) -> dict[str, Any]:
    """Every event crossed with every clause of the adopted family, most urgent first.

    With no family adopted this returns an empty register and says so. It does not pick one: a
    deadline computed under a contract the project is not on is not a conservative approximation of
    the right answer, it is a different answer that looks exactly like the right one.
    """
    if not family:
        return {"family": None, "adopted": False, "items": [], "counts": {},
                "why": "no contract family adopted for this project — notice periods are contract "
                       "terms and cannot be inferred; adopt one, having verified it against the "
                       "executed contract"}
    if family not in FAMILIES:
        return {"family": family, "adopted": False, "items": [], "counts": {},
                "why": f"unknown contract family {family!r}; known: {', '.join(sorted(FAMILIES))}"}

    cal = calendar or Calendar()
    items: list[dict[str, Any]] = []
    for ev in events:
        matched = clauses_for(family, ev["type"])
        if not matched:
            items.append({"event": ev, "clause": None, "status": "no_clause",
                          "why": f"{FAMILIES[family]} has no notice provision in this library for a "
                                 f"{ev['type'].replace('_', ' ')} event"})
            continue
        for cl in matched:
            c = clock(cl, occurred_on=ev["date"], became_aware_on=ev.get("became_aware_on"),
                      today=today, calendar=cal, due_soon_days=due_soon_days)
            items.append({"event": ev, **c})

    items.sort(key=lambda i: (_STATUS_ORDER.get(i.get("status"), 9),
                              i.get("days_remaining") if i.get("days_remaining") is not None else 9999,
                              i["event"]["date"]))
    counts: dict[str, int] = {}
    for i in items:
        counts[i.get("status", "no_clause")] = counts.get(i.get("status", "no_clause"), 0) + 1
    return {
        "family": family, "family_label": FAMILIES[family], "adopted": True,
        "as_of": (parse_date(today) or date.today()).isoformat(),
        "calendar": cal.describe(), "counts": counts, "items": items,
        "verify": "these are the standard provisions of the unamended form — verify each against "
                  "the executed contract before relying on a date",
    }


def draft(item: dict[str, Any], *, project: str = "", from_party: str = "the Contractor",
          to_party: str = "") -> str:
    """A notice letter for one register item, in the form a contract administrator would send.

    The clause wording is quoted rather than paraphrased, and the reservation of rights is generic.
    A drafted notice is a starting document for a person who is accountable for it, which is why the
    signature block is left unfilled and the reference to the contract is explicit."""
    ev = item["event"]
    ref = item.get("reference") or "the Contract"
    to = to_party or item.get("notify") or "the other party"
    due = item.get("due_date")
    when = f"on {ev['date']}" if ev.get("date_basis") == "occurred" else f"recorded on {ev['date']}"
    lines = [
        f"NOTICE UNDER {ref.upper()}",
        "",
        f"Project: {project or '[project]'}",
        f"To: {to}",
        f"From: {from_party}",
        f"Date: {item.get('as_of', '')}",
        f"Our reference: {ev.get('source_ref') or ev.get('source_id') or '[ref]'}",
        "",
        f"1. {from_party} gives notice under {ref} of the following event or circumstance, "
        f"{when}:",
        "",
        f"   {ev.get('description') or ev['type'].replace('_', ' ')}",
        "",
        "2. The clause under which this notice is given provides:",
        "",
        f"   \"{item.get('citation', '')}\"",
        "",
        "3. This notice is given within the period stated in that clause"
        + (f", which expires on {due}." if due else "."),
        "",
        "4. The event is likely to affect the time for completion and/or the cost of the Works. "
        f"{from_party} is assessing the effect and will submit particulars in accordance with the "
        "Contract. All rights are reserved.",
        "",
        "Signed: ______________________    For and on behalf of " + from_party,
    ]
    if ev.get("date_basis") == "reported":
        lines.insert(9, "   [The date above is the date this was recorded, not necessarily the date "
                        "it occurred — confirm the occurrence date before issuing.]")
    return "\n".join(lines)


#: The `prime_contract.notice_family` select renders the form's own name, because that is what a
#: contract administrator recognises on screen. This maps those labels onto the ids above. Kept
#: beside the labels it mirrors, and asserted equal to the module.json option list in
#: `test_notice_clock.py` — two tables encoding one vocabulary drift silently otherwise.
FAMILY_BY_LABEL: dict[str, str] = {
    "AIA A201-2017": "aia_a201_2017",
    "FIDIC Red Book 2017": "fidic_red_2017",
    "FIDIC Red Book 1999": "fidic_red_1999",
    "NEC4 ECC": "nec4_ecc",
    "ConsensusDocs 200": "consensusdocs_200",
    "EJCDC C-700 2018": "ejcdc_c700_2018",
    "US Federal (FAR)": "far_us_federal",
}


def resolve_family(value: str | None) -> str | None:
    """Accept either a family id or the label the contract record stores. Unknown → None, so an
    unrecognised value falls through to `scan()`'s "no family adopted" path rather than silently
    selecting one."""
    if not value:
        return None
    v = str(value).strip()
    if v in FAMILIES:
        return v
    return FAMILY_BY_LABEL.get(v)


_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def parse_calendar(weekend: str | None = None, holidays: str | None = None) -> Calendar:
    """Build a Calendar from the two things that vary by place: which days are the weekend and which
    dates are public holidays. An unparseable weekend token is an error rather than a skip — a
    weekend silently missing a day makes every business-day count wrong in the same direction."""
    days: tuple[int, ...] = (5, 6)
    if weekend:
        parsed = []
        for tok in str(weekend).split(","):
            key = tok.strip()[:3].lower()
            if key not in _WEEKDAYS:
                raise ValueError(f"unknown weekend day {tok.strip()!r}; use Mon..Sun")
            parsed.append(_WEEKDAYS[key])
        days = tuple(sorted(set(parsed)))
        # Reject at the point the mistake is made, naming the consequence. `add_period` guards this
        # too, but by then the caller is several layers from the field they got wrong.
        if len(days) >= 7:
            raise ValueError("a weekend cannot cover every day of the week — no business day would "
                             "ever elapse, so no notice period could be counted")
    dates: set[date] = set()
    for tok in str(holidays or "").split(","):
        if tok.strip():
            d = parse_date(tok.strip())
            if d is None:
                raise ValueError(f"unparseable holiday date {tok.strip()!r}; use YYYY-MM-DD")
            dates.add(d)
    return Calendar(weekend=days, holidays=frozenset(dates))
