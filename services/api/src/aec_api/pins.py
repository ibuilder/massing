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


def _topic_pin_where(pid: str):
    """The "is this a pin" test, in SQL, so the cap is spent on CANDIDATES rather than on topics.

    **This predicate is a deliberate SUPERSET of the exact check in `resolve_pins`**: a stored `{}`
    or `[]` is non-NULL and passes here, then fails there. Superset is the safe direction — it can
    never exclude a real pin — and it is the whole reason `pin_total` is reported as an upper bound
    when, and only when, the cap actually bit.
    """
    from sqlalchemy import or_

    from .models import Topic
    return (Topic.project_id == pid,
            or_(Topic.anchor.isnot(None), Topic.element_guids.isnot(None)))


def resolve_pins(db: Session, pid: str, model=None) -> dict:
    """Every pin for a project: explicit anchors, plus issues located by the element they reference.

    `model` is an open IFC file. Without one, only explicitly-anchored pins can be placed — the
    element-derived ones are still returned, with `x`/`y`/`z` as None, so a caller reports "3 not
    located" rather than pretending they do not exist. Silence is the failure mode; an unplaced pin
    that says so is not.

    Returns an envelope, not a bare list, because the bare list was silent about its own cap:

    * `pins` — the pins, up to `_MAX_PINS` across **all** sources sharing one budget;
    * `pin_total` — how many the project has;
    * `total_counts_candidates` — whether `pin_total` counts rows the SQL predicate admitted
      rather than pins verified one by one, i.e. whether it may overstate (see `_topic_pin_where`);
    * `truncated` — whether the budget stopped us.

    **The topic query used to cap 2,000 rows and THEN drop the ones that are not pins.** Ordered
    oldest-first, so a project whose 2,000 oldest topics are ordinary un-pinned issues — which is
    most projects, because most RFIs are never placed — drew **no topic pins at all**, and newly
    placed ones never appeared, because the window never advanced past the same 2,000 rows. The
    overlay did not degrade gracefully as a project got busier; it went blank and stayed blank.
    That is the LIMIT-FILTER shape, and it survived a review that judged the Python `if` a
    *dispatch* rather than a filter. **Which it is does not matter. What matters is which rows the
    cap can be spent on.**

    The registers were capped at `_MAX_PINS` **each** and then the concatenation truncated to
    `_MAX_PINS`, so topics filling the budget deleted every register pin without a word. One
    shared budget now, spent in a fixed order, and what it could not reach is counted rather than
    dropped.
    """
    from sqlalchemy import func, select

    from .models import Topic

    out: list[dict] = []
    need: set[str] = set()          # element GUIDs whose position we have to resolve
    candidates = 0                  # rows the SQL predicates admit, summed over every source
    truncated = False

    # --- topics -------------------------------------------------------------------------------
    where = _topic_pin_where(pid)
    # `_MAX_PINS + 1` rather than a second count query: one extra row is all it takes to know the
    # cap bit, and when it did not, `len(out)` is already the exact answer.
    rows = (db.query(Topic).filter(*where)
            .order_by(Topic.created_at.asc()).limit(_MAX_PINS + 1).all())
    if len(rows) > _MAX_PINS:
        truncated = True
        candidates += db.query(func.count()).select_from(Topic).filter(*where).scalar() or 0
        rows = rows[:_MAX_PINS]
    else:
        candidates += len(rows)
    for t in rows:
        a = t.anchor if isinstance(t.anchor, dict) and t.anchor else None
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

    # --- register records tied to elements: the half that was invisible ------------------------
    for key, table in _record_tables(db).items():
        budget = _MAX_PINS - len(out)
        cond = (table.c.project_id == pid, table.c.element_guids.isnot(None))
        try:
            total_here = db.execute(
                select(func.count()).select_from(table).where(*cond)).scalar() or 0
            if budget <= 0:
                # No room left. Count it anyway — an unreachable source that says so beats a
                # source that vanishes, which is what the old final slice did.
                truncated = truncated or total_here > 0
                candidates += total_here
                continue
            # `order_by(id)` because a cap without an order silently picks different rows per run.
            rows = db.execute(
                select(table.c.id, table.c.ref, table.c.title, table.c.element_guids,
                       table.c.workflow_state)
                .where(*cond).order_by(table.c.id).limit(budget + 1)).all()
        except Exception:           # noqa: BLE001 — a register without these columns simply has no pins
            continue
        if len(rows) > budget:
            truncated = True
            rows = rows[:budget]
        candidates += total_here
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

    # When nothing was capped every candidate was read and the exact test applied to each, so the
    # pin count IS `len(out)`. Only a cap forces us back onto the candidate count, which may
    # overstate — and it says so rather than being dressed as a total. A number that overstates
    # while carrying the population's name is the defect this envelope exists to end.
    #
    # `total_counts_candidates` equals `truncated` TODAY, and is a separate field because it is a
    # separate claim: `truncated` means "we returned fewer than exist", this means "the number we
    # gave you may overstate". They coincide only because the superset predicate is the sole
    # reason for imprecision; normalise the two write sites that can store `{}`/`[]` and backfill
    # the rows that already do, and this goes False while `truncated` stays True.
    #
    # The first draft computed it as `truncated and candidates != len(out)`, which can never be
    # False when truncated — `out` is capped, so the two are unequal by construction. **A flag
    # derived from a comparison the cap itself forces is not measuring anything**, and the
    # assertion written for the honest-negative case is what caught it.
    return {"pins": out,
            "pin_total": candidates if truncated else len(out),
            "total_counts_candidates": truncated,
            "truncated": truncated}


def located(pins: list[dict]) -> list[dict]:
    """Only the pins that have a real position. The caller keeps the full list to count what it
    could not place, because a sheet that draws 4 of 7 pins and says nothing is the bug."""
    return [p for p in pins if p.get("x") is not None and p.get("y") is not None]
