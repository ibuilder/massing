"""UX-DEMO — schema-driven demo records for **every** module, so no register in the app renders an
empty state in a demo project.

The hand-written `seed_demo.py` threads realistic relation chains through ~24 modules — the ones the
dashboards and rollups read. The other 108 registered modules had nothing, which is what makes the
product look thinner than it is: a customer clicking through the nav hits blank screen after blank
screen even though the engine behind each one ships.

Hand-authoring 108 more registers would be filler. Instead this generates records **from each
module's own field definitions** (`module.json` is already the single source of truth — see
`module_schema`), so a module added tomorrow gets demo content for free and nothing drifts.

The values are deterministic (seeded by module + row index, never `random`) so two runs produce the
same demo and a captured snapshot stays stable. They are *plausible*, not real: this exists to make
empty screens look like a working project, never to stand in for actual data.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

# Deterministic word pools — plausible AEC vocabulary rather than "Lorem ipsum", which reads as
# unfinished. Chosen per-field by a stable hash so the same field always gets the same shape of value.
_NOUNS = ("Level 2 slab", "East curtain wall", "Mechanical room", "Stair core", "Podium deck",
          "Lobby ceiling", "Roof screen", "Loading dock", "Chiller plant", "Elevator shaft",
          "North facade", "Basement wall", "Riser closet", "Canopy steel", "Parking ramp")
_ACTIONS = ("coordination", "inspection", "submittal", "closeout", "verification", "review",
            "handover", "commissioning", "punch", "survey")
_PARTIES = ("Northline Construction", "Braid & Co Architects", "Vantage MEP", "Keystone Structural",
            "Harbor Electric", "Summit Mechanical", "Ironwood Concrete", "Delta Glazing")
_PEOPLE = ("A. Reyes", "M. Okafor", "J. Lindqvist", "P. Nandi", "S. Bauer", "T. Moreau",
           "K. Alvarez", "R. Duval")


def _h(*parts: Any) -> int:
    """A stable non-negative int from the parts — deterministic across runs and platforms
    (`hash()` is salted per-process, so it cannot be used here)."""
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8], 16)


def _pick(pool, *seed):
    return pool[_h(*seed) % len(pool)]


def _value(field: dict, module: str, i: int, today: date) -> Any:
    """A plausible, schema-valid value for one field — or None to leave it unset."""
    ftype = str(field.get("type") or "text")
    name = str(field.get("name") or "")
    seed = (module, name, i)

    if ftype == "select" or ftype == "multiselect":
        opts = [o for o in (field.get("options") or []) if o]
        if not opts:
            return None
        chosen = opts[_h(*seed) % len(opts)]
        return [chosen] if ftype == "multiselect" else chosen
    if ftype == "checkbox":
        return _h(*seed) % 3 != 0                      # mostly true, some false — not a uniform column
    if ftype in ("number", "percent"):
        n = _h(*seed) % 100
        return n if ftype == "number" else min(99, n)
    if ftype == "currency":
        # a spread across magnitudes so charts and money cards have something to shape
        return round((_h(*seed) % 900 + 5) * (10 ** (_h("mag", *seed) % 3)) + 0.0, 2)
    if ftype == "date":
        # dates straddle today so "overdue" / "upcoming" filters both have members
        return str(today + timedelta(days=(_h(*seed) % 120) - 45))
    if ftype == "email":
        who = _pick(_PEOPLE, *seed).replace(". ", ".").replace(" ", ".").lower()
        return f"{who}@example.com"
    if ftype == "phone":
        return f"+1-555-{_h(*seed) % 9000 + 1000}"
    if ftype == "textarea":
        return (f"{_pick(_NOUNS, *seed)} — {_pick(_ACTIONS, 'a', *seed)} noted during the weekly walk. "
                f"Coordinate with {_pick(_PARTIES, 'p', *seed)} before the next pour.")
    if ftype in ("reference", "rollup", "signature", "file"):
        return None                                    # links/uploads are the relation-chain seeder's job
    # text
    if "name" in name or "title" in name or "subject" in name or "description" in name:
        return f"{_pick(_NOUNS, *seed)} {_pick(_ACTIONS, 'a', *seed)}"
    if "company" in name or "vendor" in name or "contractor" in name or "party" in name:
        return _pick(_PARTIES, *seed)
    if "by" in name or "owner" in name or "assignee" in name or "person" in name or "contact" in name:
        return _pick(_PEOPLE, *seed)
    return f"{_pick(_NOUNS, *seed)} {i + 1}"


_UNINVENTABLE = ("reference", "file", "signature", "rollup")


def needs_references(mod: dict) -> list[str]:
    """Required fields this generator refuses to invent — a **required reference** (and likewise a
    required upload or signature).

    A module gated this way cannot be demo-seeded on its own: the field must point at a real parent
    record, and a fabricated id renders as a broken link rather than as content. Rather than fake it
    or silently emit a record the engine will reject, the generator reports the dependency so the
    caller seeds the parent first (that is what the hand-written relation-chain seeder is for).
    """
    return [f["name"] for f in (mod.get("fields") or [])
            if f.get("name") and f.get("required") and f.get("type") in _UNINVENTABLE]


def record(mod: dict, i: int, today: date | None = None) -> dict[str, Any]:
    """One demo record for module `mod`, row `i`. Every **required** field this generator can honestly
    fill is filled (a record that fails the engine's own required-field check would be worse than no
    demo data); optional fields are filled about two thirds of the time so the UI shows real sparseness
    rather than a suspiciously complete grid.

    Returns ``{}`` when the module has a required field we refuse to invent — see `needs_references`.
    """
    if needs_references(mod):
        return {}
    today = today or date(2026, 7, 24)
    out: dict[str, Any] = {}
    for f in (mod.get("fields") or []):
        name = f.get("name")
        if not name:
            continue
        required = bool(f.get("required"))
        if f.get("type") in _UNINVENTABLE:
            continue                                   # never invent a link or an upload
        if not required and _h("fill", mod.get("key"), name, i) % 3 == 0:
            continue                                   # deliberately sparse
        v = _value(f, str(mod.get("key")), i, today)
        if v is None and required:
            v = f"{_pick(_NOUNS, mod.get('key'), name, i)} {i + 1}"   # never leave a required field empty
        if v is not None:
            out[name] = v
    return out


def records(mod: dict, count: int = 4, today: date | None = None) -> list[dict[str, Any]]:
    """`count` demo records for a module."""
    return [record(mod, i, today) for i in range(max(0, count))]
