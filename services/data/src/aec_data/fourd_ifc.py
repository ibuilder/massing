"""R25-TASK-BIND — the 4D binding written **into** the model, not beside it.

`cost_ifc` did this for money: `IfcRelAssignsToControl` → `IfcCostItem`, so a priced element carries
its price in the file. This is the time half, and the asymmetry it fixes is worth naming.

`schedule.from_ifc` has always been able to **read** `IfcTask` and its outputs — but nothing in the
platform could **write** them. So a schedule authored anywhere else could be consumed, while the
platform's own schedule lived only in its database: it could not travel with the file, no other tool
could see it, and it drifted on every re-export. The read half without the write half is not a
partial feature, it is a one-way door.

**The native link is `IfcRelAssignsToProduct`** — the task's *output*: `RelatedObjects=[task]`,
`RelatingProduct=element`, read back through `task.HasAssignments`. Getting this wrong is easy and
silent, and the first version of this file did: it wrote `IfcRelAssignsToProcess`, which is the task's
**input** relation (`task.OperatesOn`, "this task operates on that product"). Both are real IFC and
both round-trip through a reader written to match — but they say different things, and every tool
that asks "what does this task build" reads outputs. The binding would have been invisible to all of
them, including this repo's own `schedule.from_ifc`, which is what caught it.

Grouped by `IfcWorkSchedule`, exactly as `IfcRelAssignsToControl` → `IfcCostItem` is for cost. Using
the native relation rather than a bespoke join table is the same decision the 5D research forced: a
join table puts the spine *outside* the model.

Three behaviours are deliberate and each has a test:

* **A task whose GlobalIds are not in the model is still written**, without an assignment, and the
  unmatched ids are returned. The work is real; dropping it would make a programme quietly shorter
  than the project, and the caller would find out from a missed date rather than from a report.
* **Dates are written only when both ends parse.** A task with a start and an unreadable finish gets
  no `TaskTime` at all rather than half of one, because a duration computed from half a date range is
  a number that looks authoritative and is not.
* **The round trip is asserted in both directions.** Two functions encoding one format drift; a
  binding that can be written but not read back is a sidecar with extra steps.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell

#: Cap on tasks written in one pass — the same bound `cost_ifc` applies, for the same reason: an
#: unbounded write turns one bad import into an unopenable file.
MAX_TASKS = 5000

#: `IfcTask.PredefinedType` values this writer accepts. IFC4 defines the enumeration; anything else
#: is refused rather than silently written as NOTDEFINED, because a mislabelled task type is invisible
#: in the file and wrong in every downstream filter.
TASK_TYPES = (
    "ATTENDANCE", "CONSTRUCTION", "DEMOLITION", "DISMANTLE", "DISPOSAL",
    "INSTALLATION", "LOGISTIC", "MAINTENANCE", "MOVE", "OPERATION",
    "REMOVAL", "RENOVATION", "USERDEFINED", "NOTDEFINED",
)


def _owner(model):
    hist = model.by_type("IfcOwnerHistory")
    return hist[0] if hist else None


def _iso(value: Any) -> str | None:
    """An ISO date/datetime string, or None when it is not one.

    Deliberately strict. A date the platform cannot read is not a date, and guessing at a format
    produces a schedule that is confidently wrong about when work happens.
    """
    s = str(value or "").strip()
    if not s:
        return None
    from datetime import date, datetime
    for parse in (datetime.fromisoformat, lambda x: datetime.combine(date.fromisoformat(x[:10]),
                                                                     datetime.min.time())):
        try:
            return parse(s).isoformat()
        except (ValueError, TypeError):
            continue
    return None


def write_work_schedule(model: ifcopenshell.file, tasks: list[dict[str, Any]],
                        name: str = "Programme",
                        predefined_type: str = "PLANNED") -> dict[str, Any]:
    """Write an `IfcWorkSchedule` of `IfcTask`s, each bound to the elements it builds.

    `tasks` are dicts of ``{id, name, start, finish, task_type?, guids}``. Returns the entities plus
    the GlobalIds that matched nothing, so the caller can report the gap rather than discover it from
    a missed date.
    """
    owner = _owner(model)
    by_guid = {}
    for e in model.by_type("IfcProduct"):
        gid = getattr(e, "GlobalId", None)
        if gid:
            by_guid[gid] = e

    schedule = model.create_entity(
        "IfcWorkSchedule", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
        Name=name, PredefinedType=predefined_type)

    written, missing, undated = [], [], []
    for t in tasks[:MAX_TASKS]:
        # ABSENT defaults to CONSTRUCTION — most tasks on a building programme build something, and
        # making every caller repeat it adds no information. EMPTY does not default: that is somebody
        # who tried to state a type and failed, and quietly writing CONSTRUCTION over it would put a
        # confident wrong label in the file. Same distinction `cost_ifc` draws for `basis`.
        raw_type = t.get("task_type")
        ttype = "CONSTRUCTION" if raw_type is None else str(raw_type).strip().upper()
        if ttype not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {sorted(TASK_TYPES)}, got {ttype!r}")
        task = model.create_entity(
            "IfcTask", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
            Name=str(t.get("name") or t.get("id") or "Task"),
            Identification=str(t.get("id") or ""),
            PredefinedType=ttype)

        start, finish = _iso(t.get("start")), _iso(t.get("finish"))
        if start and finish:
            task.TaskTime = model.create_entity(
                "IfcTaskTime", Name=task.Name, ScheduleStart=start, ScheduleFinish=finish)
        elif start or finish:
            # Half a range is not a range. Writing one end would let every downstream duration and
            # float calculation read as authoritative while resting on a date nobody supplied.
            undated.append(t.get("id") or task.Name)

        guids = list(t.get("guids") or [])
        found = [by_guid[g] for g in guids if g in by_guid]
        missing.extend(g for g in guids if g not in by_guid)
        for product in found:
            # THE 4D LINK: this task OUTPUTS this element. `RelatingProduct` is singular, so it is one
            # relationship per element — not a wart, it is what makes "which task builds this wall"
            # answerable from the element side without scanning every task.
            model.create_entity(
                "IfcRelAssignsToProduct", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
                RelatedObjects=[task], RelatingProduct=product)
        written.append(task)

    if written:
        model.create_entity(
            "IfcRelAssignsToControl", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
            RelatedObjects=written, RelatingControl=schedule)

    return {"schedule": schedule, "tasks": written, "written": len(written),
            "missing_guids": sorted({g for g in missing if g}),
            "partial_dates": sorted(str(u) for u in undated)}


def read_work_schedule(model: ifcopenshell.file) -> list[dict[str, Any]]:
    """Read the tasks back, with the elements each one builds.

    The round trip is the point: a binding written into the model that cannot be read back out is a
    sidecar with extra steps. `test_task_bind` asserts the two agree in **both** directions.
    """
    # index the assignments once — scanning every relationship per task is quadratic on a real model
    by_task: dict[int, list[str]] = {}
    for rel in model.by_type("IfcRelAssignsToProduct"):
        product = getattr(rel, "RelatingProduct", None)
        gid = getattr(product, "GlobalId", None) if product is not None else None
        if not gid:
            continue
        for o in (rel.RelatedObjects or []):
            if o.is_a("IfcTask"):
                by_task.setdefault(o.id(), []).append(gid)

    out: list[dict[str, Any]] = []
    for task in model.by_type("IfcTask"):
        time = task.TaskTime
        out.append({
            "id": task.Identification or "",
            "name": task.Name or "",
            "task_type": task.PredefinedType,
            "start": getattr(time, "ScheduleStart", None) if time else None,
            "finish": getattr(time, "ScheduleFinish", None) if time else None,
            "guids": sorted(set(by_task.get(task.id(), []))),
        })
    return out
