"""R26-MODULE-HOME — one canonical room per module.

The redesign's first finding is that seven workspaces carry **four different left-rail taxonomies**,
so nothing a user learns in one transfers to the next — and modules land in more than one of them
(Facility Condition appears twice in the Developer rail alone). The fix is one constant spine of five
rooms, with every module having exactly **one** canonical home and being referenced, never re-listed,
anywhere else.

**Why the mapping lives here rather than in 132 `module.json` files.** `module_schema` is the single
source of truth for a module's shape, and every module already declares a `section`. A room is a
property of the *section*, not of each module, so deriving it from one table means a new module
inherits a room automatically and cannot be added to two rooms by an editing slip. It also means the
allocation can be reviewed as a single readable list instead of by grepping a hundred files.

**A section with no room fails the gate rather than defaulting.** A default would make a
mis-sectioned module silently unreachable — which is exactly the failure an IA restructure is most
likely to cause and least likely to notice. Same rule the rest of the codebase follows: the absence
of an answer is not an answer.
"""
from __future__ import annotations

from typing import Any

#: The five rooms. Professional terms are primary — the users are builders, developers, architects
#: and engineers who already own the vocabulary; there is deliberately no second string table.
ROOMS: list[dict[str, str]] = [
    {"id": "design", "label": "Design",
     "job": "Model it, draw it, specify it — the architect's and engineer's room"},
    {"id": "planning", "label": "Planning",
     "job": "Take it off, estimate it, bid it, buy it out and contract it"},
    {"id": "cost", "label": "Cost",
     "job": "Budget it, change it, bill it and account for it"},
    {"id": "schedule", "label": "Schedule",
     "job": "Sequence it, run the field, and track what got built"},
    {"id": "deal", "label": "Deal",
     "job": "Underwrite it, fund it, lease it and dispose of it"},
    {"id": "work", "label": "Work",
     "job": "Whatever is in your court right now"},
]
ROOM_IDS = {r["id"] for r in ROOMS}

#: section → room. Every section present in `services/api/modules/*/module.json` must appear here;
#: `test_module_rooms` fails the build if one is missing, so a new section is a deliberate decision
#: rather than an accident.
ROOM_OF_SECTION: dict[str, str] = {
    # ── Design: the building and everything that describes it ───────────────────────────────────
    # Named for the *discipline*, not the artifact. "Model" described one output of this room and
    # left drawings and specifications looking like they belonged somewhere else — which is exactly
    # where specifications had ended up (filed under Preconstruction, and therefore under Cost).
    # An architect or engineer does all of it here: model, draw, specify, analyse.
    "BIM": "design",
    "Design": "design",
    "Design Phases": "design",
    "Engineering": "design",
    "Specifications": "design",      # the written half of the documents; the drawings are the other
    "Information Management": "design",
    "Programming": "design",
    "Quality": "design",             # inspections/ITP describe the built thing against the design
    "Sustainability": "design",
    "Resilience": "design",
    # ── Planning: turning a design into a bought, contracted scope ──────────────────────────────
    # Split out of Cost. Estimating, taking off and buying out are *planning* work with an outcome
    # in money — filing them under Cost put a quantity surveyor and an accounts clerk in one room,
    # and buried the takeoff a preconstruction lead uses daily under a general ledger they never open.
    "Preconstruction": "planning",
    "Contracts": "planning",
    # ── Cost: money against the building, once the scope is bought ──────────────────────────────
    "Cost": "cost",
    "Change Management": "cost",
    "Capital": "cost",
    # ── Schedule: time, and the field that consumes it ──────────────────────────────────────────
    "Schedule": "schedule",
    "Field": "schedule",
    "Resources": "schedule",
    "Safety": "schedule",            # safety is a field-operations concern, logged where work happens
    "Project Controls": "schedule",
    "Closeout": "schedule",          # the end of the sequence
    # ── Deal: the asset as an investment ────────────────────────────────────────────────────────
    "Acquisition": "deal",
    "Feasibility": "deal",
    "Finance": "deal",
    "Market & Sales": "deal",
    "Operations": "deal",            # operating the asset is the back half of owning it
}


def room_of_section(section: str) -> str | None:
    """The room a section belongs to, or None when the section is unmapped (which is a failure)."""
    return ROOM_OF_SECTION.get(str(section or "").strip())


def room_of(module: dict[str, Any]) -> str | None:
    return room_of_section(str((module or {}).get("section") or ""))


def unmapped_sections(sections: set[str]) -> list[str]:
    """Sections with no room. A non-empty result must fail a build, not warn."""
    return sorted(s for s in sections if s and s not in ROOM_OF_SECTION)


def allocate(modules: list[dict[str, Any]]) -> dict[str, Any]:
    """Group modules into rooms, and report anything that could not be placed.

    `unplaced` is the number an IA restructure lives or dies on: a module with no room is a module a
    user can no longer reach, and it would otherwise be invisible until someone went looking for it.
    """
    by_room: dict[str, list[str]] = {r["id"]: [] for r in ROOMS}
    unplaced: list[dict[str, str]] = []
    for m in modules or []:
        key = str(m.get("key") or m.get("name") or "?")
        room = room_of(m)
        if room in by_room:
            by_room[room].append(key)
        else:
            unplaced.append({"key": key, "section": str(m.get("section") or "")})
    for k in by_room:
        by_room[k].sort()
    return {
        "rooms": [{**r, "count": len(by_room[r["id"]]), "modules": by_room[r["id"]]} for r in ROOMS],
        "placed": sum(len(v) for v in by_room.values()),
        "unplaced": sorted(unplaced, key=lambda u: u["key"]),
        "unplaced_count": len(unplaced),
        "note": ("Every module has exactly one canonical room; it may be REFERENCED from elsewhere "
                 "but is never re-listed under a second heading. An unmapped section is a failure, "
                 "not a default — a silently unreachable module is the defect an IA change is most "
                 "likely to cause and least likely to notice."),
    }
