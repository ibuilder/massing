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


def register_order(table):
    """The capped register read's ORDER BY, as one definition the test can compile.

    Newest first (see `resolve_pins`), and **`nulls_last()` because PostgreSQL sorts NULLs FIRST
    under DESC** while a register's `created_at` is nullable — `_table()` builds it as a bare
    Core column. Without it an undated row is "newest" in production and eats the capped window
    ahead of a pin filed today: this PR's own defect, one dialect over. SQLite already puts NULLs
    last, so no behavioural test on SQLite can catch it; `test_pin_cap.py` compiles THIS function
    against the Postgres dialect instead.

    It is a function rather than an inline clause because the first version of that test rebuilt
    the expression itself and therefore passed with the fix removed — a narrative copy of the
    code, not a check of it.

    `Topic.created_at` needs no such guard: it is `Mapped[datetime]`, hence NOT NULL.
    """
    return (table.c.created_at.desc().nulls_last(), table.c.id.desc())


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


def pin_fields(anchor, element_guids):
    """The EXACT "is this a pin" test, as one definition both read loops call.

    Returns `(anchor_or_None, non_blank_guids)`. A row is a pin when either is truthy.

    **This is the exact half of the pair whose SQL half is `_topic_pin_where`.** A stored `{}`, `[]`
    or `[""]` is non-NULL, so it passes the SQL superset and fails here — which is the entire reason
    `pin_total` is reported as an upper bound when the cap actually bit.

    Deliberately byte-equivalent to the two inline copies it replaced, including the fact that a
    non-list `element_guids` (corrupt data) iterates rather than being rejected: this extraction is a
    refactor, and changing behaviour while claiming to share a definition is how a "shared" predicate
    stops matching what it was shared from.
    """
    a = anchor if isinstance(anchor, dict) and anchor else None
    guids = [g for g in (element_guids or []) if g]
    return a, guids


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

    The registers were capped at `_MAX_PINS` **each** and the concatenation then truncated to
    `_MAX_PINS`. That does **not** change which pins come back — a per-source cap plus a final
    slice keeps the same prefix a shared budget does, and an earlier draft of this docstring said
    otherwise until the mutation written for it refused to fail. What it changes is that a source
    the budget cannot reach is now **counted** rather than concatenated and sliced away uncounted,
    so a project whose topics fill the window no longer reports that window as its whole. It also
    bounds the work: the old shape could build up to twelve times `_MAX_PINS` rows in order to
    return `_MAX_PINS` of them.
    """
    from sqlalchemy import func, select

    from .models import Topic

    out: list[dict] = []
    need: set[str] = set()          # element GUIDs whose position we have to resolve
    candidates = 0                  # rows the SQL predicates admit, summed over every source
    truncated = False

    # --- topics -------------------------------------------------------------------------------
    where = _topic_pin_where(pid)
    # **NEWEST first, then reversed for display.** Ordering ascending and cutting at the cap keeps
    # the OLDEST pins, so a project past the cap never shows a pin placed today — which is the
    # symptom this whole function exists to fix, merely moved from "more than 2,000 topics" to
    # "more than 2,000 pins". A capped overlay should drop the oldest, the way a capped timeline
    # does not. `id` breaks ties, because `created_at` is not unique and an unordered boundary
    # picks different rows per call.
    #
    # It also disposes of the residual below: a legacy row storing `{}` / `[]` passes the SQL
    # predicate and is then dropped in Python, spending budget on a non-pin. Those rows are the
    # OLD ones, so newest-first pushes them out of the window instead of letting them crowd out
    # real pins. New writes are normalised at the source (see `modules.py`), so the class shrinks.
    #
    # `count(*) OVER ()` rather than a second statement: the count and the window then come from
    # ONE snapshot, so a concurrent insert cannot leave `pin_total` describing a different
    # population from `pins`. Exactly the fix #491 applied to `load_timings`, which was open in
    # this session while this function was being written with the two-statement shape.
    hits = (db.query(Topic, func.count().over().label("_n")).filter(*where)
            .order_by(Topic.created_at.desc(), Topic.id.desc()).limit(_MAX_PINS).all())
    rows = [h[0] for h in hits]
    here = int(hits[0][1]) if hits else 0
    candidates += here
    truncated = truncated or here > len(rows)
    rows.reverse()                  # back to oldest — newest for display
    for t in rows:
        a, guids = pin_fields(t.anchor, t.element_guids)
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
            if budget <= 0:
                # No room left. Count it anyway — an unreachable source that says so beats a
                # source that vanishes, which is what the old final slice did. This is the one
                # count with no window beside it, so there is nothing for it to disagree with.
                total_here = db.execute(
                    select(func.count()).select_from(table).where(*cond)).scalar() or 0
                truncated = truncated or total_here > 0
                candidates += total_here
                continue
            # Newest first and reversed, for the reason given on the topic query above; `id`
            # breaks ties. `count(*) OVER ()` keeps this source's count and window in one
            # snapshot rather than two statements a write can land between.
            hits = db.execute(
                select(table.c.id, table.c.ref, table.c.title, table.c.element_guids,
                       table.c.workflow_state, func.count().over().label("_n"))
                .where(*cond)
                .order_by(*register_order(table)).limit(budget)).all()
        except Exception:           # noqa: BLE001 — a register without these columns simply has no pins
            continue
        rows = list(reversed(hits))
        total_here = int(hits[0]._mapping["_n"]) if hits else 0
        truncated = truncated or total_here > len(rows)
        candidates += total_here
        for r in rows:
            _, guids = pin_fields(None, r.element_guids)
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
