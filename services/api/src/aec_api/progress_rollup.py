"""PROGRESS-ROLLUP (R17 Sprint E) — **% complete** rolled up from as-built element presence.

Given the design model's expected element set (each keyed by GlobalId, with its IFC class / discipline /
level, and optionally a cost) and the set of GUIDs verified **installed** (from field verification, a scan
match, or the verified-progress log), this computes percent-complete **by IFC class, by trade/discipline, by
level, and overall — by count *and* by value**. Count and value diverge exactly where it matters (lots of
cheap elements up vs. a few expensive ones outstanding), so both are reported.

Pure over the elements + installed GUIDs supplied; the installed set comes from whatever presence source the
caller has. Feeds the GC portal + earned value.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _discipline(el: dict) -> str:
    d = el.get("discipline") or el.get("trade")
    if d:
        return str(d)
    try:
        from . import classification
        return classification.discipline_name(classification.discipline_of_ifc_class(el.get("ifc_class") or "")) \
            or "General"
    except Exception:                                    # noqa: BLE001
        return "General"


def _bucket(rows: dict, key: str, installed: bool, value: float) -> None:
    b = rows.setdefault(key, {"expected": 0, "installed": 0, "value_total": 0.0, "value_installed": 0.0})
    b["expected"] += 1
    b["value_total"] += value
    if installed:
        b["installed"] += 1
        b["value_installed"] += value


def _finish(rows: dict, label: str) -> list[dict]:
    out = []
    for k, b in rows.items():
        out.append({
            label: k, "expected": b["expected"], "installed": b["installed"],
            "pct_complete": round(b["installed"] / b["expected"], 3) if b["expected"] else 0.0,
            "value_total": round(b["value_total"], 2),
            "pct_complete_value": round(b["value_installed"] / b["value_total"], 3) if b["value_total"] else None,
        })
    return sorted(out, key=lambda r: -r["expected"])


#: CAPTURE-SESSION. The source a derived capture is built from. A string rather than a bool, because
#: there will be a second one (a scan import, a true point-in-time capture) and `derived_from: true`
#: would not say which.
DERIVED_FIELD_VERIFICATION = "field_verification"

_DERIVED_NOTE = (
    "A DERIVED capture, not a stored one: the installed set is every element the Field Verification "
    "register observed on or before that date. Two consequences. It is CUMULATIVE, so it can only "
    "grow — which means `removed` is structurally empty and this diff cannot raise a rework flag; an "
    "element that was observed once and never re-observed is still counted as installed. And it is "
    "only as complete as the register: elements nobody verified are absent from both sides, so the "
    "delta is over what the crew recorded, not over the building."
)


def installed_as_of(records: list[dict], as_of: str | None) -> dict[str, Any]:
    """The GUIDs the Field Verification register observed on or before `as_of`.

    **CAPTURE-SESSION — a capture at a moment, derived from a register that already exists.** The
    roadmap entry recorded that nothing in this product persists a capture and that a caller would
    have to invent the concept. That is true of a stored capture ROW and not of the SET: every
    `field_verification` record carries a REQUIRED `guid` and an `observed_date`, so *"what was
    observed installed as of 2026-09-30"* is a filter, not a new concept. *"There is no stored X"
    and "X is not available" are different claims, and the entry read the first as the second.*

    **CUMULATIVE on purpose, and this is the load-bearing decision.** `observed_date <= as_of`
    rather than `== as_of`, because a point-in-time reading would report every element not
    re-verified on the later date as *disappeared* — manufacturing rework flags out of a crew's
    ordinary habit of not re-walking finished work. The cost is that the set can only grow, so
    `capture_diff`'s `removed` half is structurally empty on a derived capture and says so.
    *Choosing which half to make unreachable is better than leaving a half that lies.*

    A record with no readable date is EXCLUDED and COUNTED, never silently dropped — the same rule
    `capture_diff` had to learn for the GUIDs the model does not know. An undated verification is a
    row somebody has to go and date, which only shows up if the number is reported.
    """
    from datetime import date

    def _d(v: Any) -> date | None:
        s = str(v or "").strip()[:10]
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None

    cutoff = _d(as_of)
    guids: set[str] = set()
    undated = 0
    dates: list[date] = []
    for r in records or []:
        data = r.get("data") if isinstance(r.get("data"), dict) else r
        g = str(data.get("guid") or "").strip()
        if not g:
            continue
        d = _d(data.get("observed_date"))
        if d is None:
            undated += 1
            continue
        dates.append(d)
        if cutoff is None or d <= cutoff:
            guids.add(g)
    return {
        "guids": sorted(guids),
        "count": len(guids),
        "as_of": as_of,
        # Rows the register holds that this set could not use. A verification with no observed date
        # is invisible to every capture, at every date, for ever.
        "undated": undated,
        # The dated range the register actually covers, so a caller can tell a date INSIDE its data
        # from one before it begins — an `as_of` before the first observation returns an empty set,
        # which is a correct answer and an alarming-looking one.
        "earliest": min(dates).isoformat() if dates else None,
        "latest": max(dates).isoformat() if dates else None,
        "source": DERIVED_FIELD_VERIFICATION,
        "note": _DERIVED_NOTE,
    }


def capture_diff(elements: list[dict], installed_t1: list | set, installed_t2: list | set,
                 t1: str | None = None, t2: str | None = None) -> dict[str, Any]:
    """SCAN-4D — the deterministic diff between two capture timestamps: what got installed between t1 and
    t2 (per class / level), what *disappeared* (present at t1, absent at t2 — a re-scan or rework flag,
    never silently dropped), and the progress delta + daily rate when dates are given."""
    from datetime import date

    s1 = {str(g) for g in (installed_t1 or [])}
    s2 = {str(g) for g in (installed_t2 or [])}
    known = {str(el.get("guid") or el.get("GlobalId") or ""): el for el in elements or [] if isinstance(el, dict)}
    added = sorted(g for g in (s2 - s1) if g in known)
    removed = sorted(g for g in (s1 - s2) if g in known)
    # EVERY capture GUID THE MODEL DOES NOT KNOW is dropped from both sets above, and the note used
    # to promise the opposite: "never silently dropped". It was true only among elements the CURRENT
    # model still contains — which excludes exactly the case a rework flag is for, an element taken
    # out of the model and off the site between captures. The filter stays (a diff is scoped to the
    # model it is about, and a GUID with no element has no class or storey to group by), but the
    # count no longer does: unmatched is reported, so a capture aimed at the wrong model version is
    # visible instead of arriving as a quietly smaller diff.
    unmatched_t1 = sorted(g for g in s1 if g not in known)
    unmatched_t2 = sorted(g for g in s2 if g not in known)

    def _grp(guids: list[str], key: str, fallback: str) -> list[dict]:
        counts: dict[str, int] = {}
        for g in guids:
            k = str(known[g].get(key) or fallback)
            counts[k] = counts.get(k, 0) + 1
        return sorted(({key: k, "count": n} for k, n in counts.items()), key=lambda r: -r["count"])

    r1 = rollup(elements, s1)
    r2 = rollup(elements, s2)
    days = None
    try:
        if t1 and t2:
            days = (date.fromisoformat(str(t2)[:10]) - date.fromisoformat(str(t1)[:10])).days
    except (TypeError, ValueError):
        days = None
    return {
        "t1": t1, "t2": t2, "days": days,
        "installed_t1": len(s1 & set(known)), "installed_t2": len(s2 & set(known)),
        "newly_installed": len(added), "disappeared": len(removed),
        "added_guids": added[:200], "disappeared_guids": removed[:200],
        "unmatched_t1": len(unmatched_t1), "unmatched_t2": len(unmatched_t2),
        "unmatched_guids": sorted(set(unmatched_t1) | set(unmatched_t2))[:200],
        "added_by_class": _grp(added, "ifc_class", "Unclassified"),
        "added_by_level": _grp(added, "storey", "—"),
        "pct_complete_t1": r1["pct_complete"], "pct_complete_t2": r2["pct_complete"],
        "pct_delta": round(r2["pct_complete"] - r1["pct_complete"], 3),
        "elements_per_day": round(len(added) / days, 2) if days and days > 0 else None,
        "note": ("Capture-to-capture change log: newly installed per class/level + the progress delta "
                 "(+ a daily rate when dates are given). An element present at t1 and absent at t2 is "
                 "surfaced as 'disappeared' — a re-scan or rework flag. BOTH sets cover only GUIDs the "
                 "model still contains; anything else is counted in `unmatched_t1`/`unmatched_t2` "
                 "rather than dropped, because a capture aimed at a different model version otherwise "
                 "arrives as a quietly smaller diff."
                 + (f" {len(unmatched_t1) + len(unmatched_t2)} capture GUID(s) matched no element."
                    if (unmatched_t1 or unmatched_t2) else "")),
    }


def rollup(elements: list[dict], installed_guids: list | set) -> dict[str, Any]:
    """Percent-complete by class / discipline / level / overall, by count and by value."""
    installed = {str(g) for g in (installed_guids or [])}
    by_class: dict[str, dict] = {}
    by_disc: dict[str, dict] = {}
    by_level: dict[str, dict] = {}
    n = done = 0
    v_total = v_done = 0.0
    for el in elements or []:
        if not isinstance(el, dict):
            continue
        guid = str(el.get("guid") or el.get("GlobalId") or "")
        is_in = guid in installed
        val = _num(el.get("value") or el.get("cost"))
        _bucket(by_class, el.get("ifc_class") or "Unclassified", is_in, val)
        _bucket(by_disc, _discipline(el), is_in, val)
        _bucket(by_level, str(el.get("storey") or el.get("level") or "—"), is_in, val)
        n += 1
        done += is_in
        v_total += val
        if is_in:
            v_done += val
    return {
        "element_count": n, "installed_count": done,
        "pct_complete": round(done / n, 3) if n else 0.0,
        "value_total": round(v_total, 2), "value_installed": round(v_done, 2),
        "pct_complete_value": round(v_done / v_total, 3) if v_total else None,
        "by_class": _finish(by_class, "ifc_class"),
        "by_discipline": _finish(by_disc, "discipline"),
        "by_level": _finish(by_level, "level"),
        "note": "Percent-complete from as-built element presence (installed GUIDs vs the design set), rolled "
                "up by IFC class · discipline · level, by count AND by value — the two diverge where cheap "
                "elements are up but expensive ones are outstanding. Feeds the GC portal + earned value.",
    }
