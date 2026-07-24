"""CRE-AUTHORITY (R20) — **the deal-room authority table.**

A data room accumulates three offering memoranda, two rent rolls and a tax bill from the year
before the reassessment. Every one of them is a real file; only one of each is *authoritative*.
Analysis that reads whichever copy it happened to open is how a superseded number reaches a
committee.

So authority is declared per **fact type**, not per file:

* one authoritative document per fact type, with its date;
* a **freshness threshold** per fact type — a tax bill goes stale on a different clock from an
  offering package;
* an explicit **supersedes** chain, so an older file is archived rather than merely older.

`assess()` returns the table plus what is missing, stale, or superseded-but-still-active, and —
the part that matters — a **`gate`**: whether downstream analysis should run at all. Required fact
types missing or stale block; advisory ones warn. The point is to stop the work, not to annotate
it after the fact.

Deterministic over records the platform already holds; nothing here reads a document's contents.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from . import storage

# fact type -> (label, default freshness in days, required for underwriting)
FACT_TYPES: dict[str, tuple[str, int, bool]] = {
    "offering": ("Offering package", 180, False),
    "rent_roll": ("Rent roll", 45, True),
    "operating_statement": ("Operating statement (T-12)", 60, True),
    "tax": ("Property tax bill", 365, True),
    "insurance": ("Insurance loss run / policy", 365, False),
    "title": ("Title commitment", 180, False),
    "survey": ("Survey", 730, False),
    "environmental": ("Environmental report", 730, False),
    "appraisal": ("Appraisal", 365, False),
    "loan": ("Loan documents", 3650, False),
}

MAX_ENTRIES = 200


def _key(pid: str) -> str:
    return f"{pid}/deal_authority.json"


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def validate(entries: list[dict]) -> list[dict[str, Any]]:
    """One authoritative document per fact type; anything else is a superseded/archived entry."""
    if not isinstance(entries, list):
        raise ValueError("the authority table must be a list of entries")
    if len(entries) > MAX_ENTRIES:
        raise ValueError(f"at most {MAX_ENTRIES} entries")
    clean: list[dict[str, Any]] = []
    seen_authoritative: set[str] = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            raise ValueError(f"entry {i} must be an object")
        ft = str(e.get("fact_type") or "").strip().lower()
        if ft not in FACT_TYPES:
            raise ValueError(f"entry {i}: fact_type must be one of {sorted(FACT_TYPES)}")
        doc = str(e.get("document") or "").strip()
        if not doc:
            raise ValueError(f"entry {i}: a document name is required")
        as_of = _parse(e.get("as_of"))
        if as_of is None:
            raise ValueError(f"entry {i} ({doc}): a valid as_of date is required — an undated "
                             "document cannot be judged fresh or stale")
        authoritative = bool(e.get("authoritative", True))
        if authoritative:
            if ft in seen_authoritative:
                raise ValueError(f"two authoritative documents for '{ft}' — exactly one wins; "
                                 "mark the older one authoritative=false with supersedes set")
            seen_authoritative.add(ft)
        freshness = e.get("freshness_days")
        clean.append({
            "fact_type": ft, "label": FACT_TYPES[ft][0], "document": doc[:200],
            "as_of": as_of.isoformat(), "authoritative": authoritative,
            "reviewer": str(e.get("reviewer") or "")[:80] or None,
            "supersedes": [str(x)[:200] for x in (e.get("supersedes") or [])][:20],
            "freshness_days": int(freshness) if str(freshness or "").strip().isdigit()
                              else FACT_TYPES[ft][1],
        })
    return clean


def load(pid: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(storage.get(_key(pid)).decode("utf-8"))
    except Exception:                                  # noqa: BLE001 — absent blob = empty table
        return []
    return data if isinstance(data, list) else []


def save(pid: str, entries: list[dict]) -> list[dict[str, Any]]:
    clean = validate(entries)
    storage.put(_key(pid), json.dumps(clean).encode("utf-8"))
    return clean


def assess(entries: list[dict], as_of: date | None = None,
           required: list[str] | None = None) -> dict[str, Any]:
    """The authority table with its gate. `required` overrides the default required fact types."""
    today = as_of or date.today()
    req = set(required) if required is not None else {k for k, v in FACT_TYPES.items() if v[2]}
    rows = entries or []
    # `authoritative` defaults to True when absent, matching validate() — so a hand-built table
    # behaves the same as a saved one rather than silently reading as "nothing is authoritative".
    authoritative = {r["fact_type"]: r for r in rows if r.get("authoritative", True)}

    table, stale, missing, superseded_active = [], [], [], []
    for ft, (label, default_days, _r) in FACT_TYPES.items():
        row = authoritative.get(ft)
        if not row:
            if ft in req:
                missing.append({"fact_type": ft, "label": label, "required": True})
            continue
        as_of_date = _parse(row["as_of"])
        age = (today - as_of_date).days if as_of_date else None
        limit = int(row.get("freshness_days") or default_days)
        is_stale = age is not None and age > limit
        entry = {"fact_type": ft, "label": label, "document": row["document"],
                 "as_of": row["as_of"], "age_days": age, "freshness_days": limit,
                 "fresh": not is_stale, "reviewer": row.get("reviewer"),
                 "required": ft in req, "supersedes": row.get("supersedes") or []}
        table.append(entry)
        if is_stale:
            stale.append({**entry, "days_over": age - limit})

    # a document named as superseded that is still flagged authoritative elsewhere
    superseded_names = {name for r in rows for name in (r.get("supersedes") or [])}
    for r in rows:
        if r.get("authoritative") and r["document"] in superseded_names:
            superseded_active.append({"fact_type": r["fact_type"], "document": r["document"],
                                      "issue": "still marked authoritative but named as superseded"})

    blocking = ([{"fact_type": m["fact_type"], "why": "required fact type has no authoritative document"}
                 for m in missing]
                + [{"fact_type": s["fact_type"], "why": f"authoritative document is {s['days_over']} "
                    f"day(s) past its {s['freshness_days']}-day freshness limit"}
                   for s in stale if s["required"]]
                + [{"fact_type": s["fact_type"], "why": s["issue"]} for s in superseded_active])
    advisory = [{"fact_type": s["fact_type"], "why": "stale (not required)"}
                for s in stale if not s["required"]]
    return {
        "as_of": today.isoformat(),
        "table": sorted(table, key=lambda r: r["fact_type"]),
        "missing": missing, "stale": stale, "superseded_still_active": superseded_active,
        "gate": {"passes": not blocking, "blocking": blocking, "advisory": advisory},
        "counts": {"declared": len(table), "missing": len(missing), "stale": len(stale),
                   "blocking": len(blocking), "advisory": len(advisory)},
        "note": ("Authority is declared per fact type, not per file. Required fact types that are "
                 "missing, stale, or superseded-but-active BLOCK downstream analysis — the point is "
                 "to stop the work, not to annotate it afterwards."),
    }


def from_project(db, pid: str, as_of: date | None = None) -> dict[str, Any]:
    return assess(load(pid), as_of)
