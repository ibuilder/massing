"""
What counts as a pin — resolved once, for every surface that shows one.

There were two ways to attach an issue to the model and they behaved differently. A **Topic** carries
an anchor and appeared in the viewer. A **module record** — the RFI in the register, the one with the
workflow that reaches `closed` — carries `element_guids` and appeared nowhere. Binding an RFI to a
wall returned `count: 1` and produced no pin, so a user could have the issue tracked to completion or
visible on the model, never both.

Neither table is wrong. What was missing is that "pin" is a **view over both**, not a row in one:

- a Topic with an explicit anchor — someone placed it at a point;
- a Topic bound to elements without an anchor — it is on that element, wherever it is now;
- a module record bound to elements — same, and this is the case that was invisible.

**Position is derived from the element, not stored beside it.** A stored coordinate is a copy of
where something was; the element's own geometry is where it is. Move the wall and a derived pin
follows it, while a stored one quietly points at empty air. That is the same reason this codebase
references elements by GlobalId and treats the IFC as the source of truth.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

#: Registers whose records are genuinely *about a place in the building*. A pin means "look here",
#: so this is deliberately not every module — a change order or a submittal is about the project,
#: not about a point, and putting one on a plan would be noise dressed as coordination.
SPATIAL_MODULES: tuple[str, ...] = (
    "rfi", "punchlist", "observation", "clash", "inspection", "snag", "defect",
    "safety_observation", "quality_issue", "field_report", "photo",
)

#: A pin has to be attributable to something a person can open. Anything we cannot name, we do not
#: draw — an unlabelled balloon on a sheet is worse than no balloon.
_MAX_PINS = 2000


def _record_tables(db: Session) -> dict:
    from . import modules as mod_engine
    return {k: t for k, t in getattr(mod_engine, "TABLES", {}).items() if k in SPATIAL_MODULES}


def resolve_pins(db: Session, pid: str, model=None) -> list[dict]:
    """Every pin for a project: explicit anchors, plus issues located by the element they reference.

    `model` is an open IFC file. Without one, only explicitly-anchored pins can be placed — the
    element-derived ones are still returned, with `x`/`y`/`z` as None, so a caller reports "3 not
    located" rather than pretending they do not exist. Silence is the failure mode; an unplaced pin
    that says so is not.
    """
    from sqlalchemy import select

    from .models import Topic

    out: list[dict] = []
    need: set[str] = set()          # element GUIDs whose position we have to resolve

    for t in (db.query(Topic).filter(Topic.project_id == pid)
              .order_by(Topic.created_at.asc()).limit(_MAX_PINS).all()):
        a = t.anchor if isinstance(t.anchor, dict) else None
        guids = [g for g in (t.element_guids or []) if g]
        if not a and not guids:
            continue                # neither placed nor attached — not a pin, just an issue
        pin = {"source": "topic", "id": t.id, "guid": t.guid, "kind": t.type,
               "label": t.title or "", "status": t.status, "element_guid": guids[0] if guids else None}
        if a:
            pin.update(x=a.get("x"), y=a.get("y"), z=a.get("z"))
        else:
            need.add(guids[0])
            pin.update(x=None, y=None, z=None)
        out.append(pin)

    # The half that was invisible: register records tied to elements.
    for key, table in _record_tables(db).items():
        try:
            rows = db.execute(
                select(table.c.id, table.c.ref, table.c.title, table.c.element_guids,
                       table.c.workflow_state)
                .where(table.c.project_id == pid, table.c.element_guids.isnot(None))
                .limit(_MAX_PINS)).all()
        except Exception:           # noqa: BLE001 — a register without these columns simply has no pins
            continue
        for r in rows:
            guids = [g for g in (r.element_guids or []) if g]
            if not guids:
                continue
            need.add(guids[0])
            out.append({"source": key, "id": r.id, "guid": r.ref or r.id, "kind": key,
                        "label": r.title or r.ref or "", "status": r.workflow_state,
                        "element_guid": guids[0], "x": None, "y": None, "z": None})

    if need and model is not None:
        from aec_data.qto import element_centroids  # type: ignore
        at = element_centroids(model, need)
        for p in out:
            if p["x"] is None and p.get("element_guid") in at:
                p["x"], p["y"], p["z"] = at[p["element_guid"]]

    return out[:_MAX_PINS]


def located(pins: list[dict]) -> list[dict]:
    """Only the pins that have a real position. The caller keeps the full list to count what it
    could not place, because a sheet that draws 4 of 7 pins and says nothing is the bug."""
    return [p for p in pins if p.get("x") is not None and p.get("y") is not None]
