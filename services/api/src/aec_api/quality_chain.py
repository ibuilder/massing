"""R22-ITP-NCR ② — the quality evidence chain, per ELEMENT, and what it refuses to conclude.

The registers are built and were never the gap. `itp` carries hold/witness points
(`point_type`, `acceptance_criteria`, `verifying_party`, planned→active→verified), `ncr` carries a
real lifecycle (`disposition`, `root_cause`, `corrective_action`, open→dispositioned→closed),
`inspection` records results, and `quality.py` rolls all three up **for the project**.

What did not exist is the *reach*: nothing read them **by element**, so the per-element evidence chain
the ring entry describes could not be assembled, and `turnover.py` — which issues the G704 certificate
and stamps the record model — referenced none of them. A project could be certified substantially
complete with the quality evidence never attached to the thing it inspected.

**No new field, no migration.** Quality records attach through `element_guids`, the column every
module record already has and which `modules.set_element_guids` already exposes over HTTP. Adding an
`element` text field would have been a second convention next to the platform's own — `data.element`
has one reader in the codebase, `element_guids` has the module engine.

**The rule this module exists to enforce: absence is not compliance.**

An element with no quality records is `unrecorded`, never `passed`. That distinction is the whole
value: a closeout report saying "0 open NCRs" across a building nobody inspected is not good news
dressed as good news — it is the *most* dangerous sentence the system can emit, because it is
literally true and completely misleading. The same trichotomy `element_facts` already draws:

* **clear**       — evidence exists and it is good.
* **outstanding** — evidence exists and something is open.
* **unrecorded**  — nothing was ever recorded against this element. NOT a pass.

And one level up, the project-wide guard: if **no** quality record in the project carries an element
at all, every element would read `unrecorded` and a reader could mistake a missing *capability* for a
finding about the building. `coverage_pct` and `any_attached` say which situation they are in.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

#: The three registers that constitute quality evidence, and the field naming each one's verdict.
QUALITY_MODULES = ("itp", "ncr", "inspection")

STATUS_CLEAR = "clear"
STATUS_OUTSTANDING = "outstanding"
STATUS_UNRECORDED = "unrecorded"

_WHY = {
    STATUS_CLEAR: "quality evidence exists for this element and nothing is outstanding",
    STATUS_OUTSTANDING: "an NCR is unresolved, an inspection failed, or a hold point is unverified",
    STATUS_UNRECORDED: ("no quality record is attached to this element — this is the ABSENCE of "
                        "evidence, not evidence of conformance"),
}

#: Workflow states that leave an element not yet clear. Read from the modules' own workflows rather
#: than invented: itp planned/active (not yet `verified`), ncr open/dispositioned (not yet `closed`).
_OPEN_STATES = {
    "itp": {"planned", "active"},
    "ncr": {"open", "dispositioned"},
    "inspection": {"scheduled", "failed"},
}


def _rows(db: Session, key: str, pid: str) -> list[dict[str, Any]]:
    return me.list_records(db, key, pid, limit=100_000) if key in me.TABLES else []


def _guids(row: dict[str, Any]) -> list[str]:
    """Elements a record claims. `element_guids` is the platform's attachment column; `data.guid` is
    honoured too because `field_verification` and `element_facts._claims` already use it."""
    out = list(row.get("element_guids") or [])
    g = str((row.get("data") or {}).get("guid") or "").strip()
    if g and g not in out:
        out.append(g)
    return out


def _is_open(key: str, row: dict[str, Any]) -> bool:
    return str(row.get("workflow_state") or "").strip().lower() in _OPEN_STATES[key]


def gather(db: Session, pid: str) -> dict[str, list[dict[str, Any]]]:
    """Every quality record, keyed by module, with its attached elements resolved once."""
    out: dict[str, list[dict[str, Any]]] = {}
    for key in QUALITY_MODULES:
        rows = []
        for r in _rows(db, key, pid):
            rows.append({"id": r.get("id"), "ref": r.get("ref"),
                         "state": r.get("workflow_state") or "",
                         "open": _is_open(key, r), "guids": _guids(r),
                         "data": r.get("data") or {}})
        out[key] = rows
    return out


def element_evidence(gathered: dict[str, list[dict[str, Any]]], guid: str) -> dict[str, Any]:
    """The quality chain for ONE element. Pure — takes gathered rows, so it is testable without a DB."""
    per: dict[str, list[dict[str, Any]]] = {}
    open_items: list[dict[str, Any]] = []
    total = 0
    for key in QUALITY_MODULES:
        hits = [r for r in gathered.get(key, []) if guid in r["guids"]]
        total += len(hits)
        per[key] = [{"id": r["id"], "ref": r["ref"], "state": r["state"], "open": r["open"]}
                    for r in hits]
        open_items += [{"module": key, "id": r["id"], "ref": r["ref"], "state": r["state"]}
                       for r in hits if r["open"]]

    if total == 0:
        status = STATUS_UNRECORDED
    elif open_items:
        status = STATUS_OUTSTANDING
    else:
        status = STATUS_CLEAR

    return {
        "guid": guid, "status": status, "status_note": _WHY[status],
        "record_count": total, "open_count": len(open_items),
        "open_items": open_items, "by_module": per,
        # A hold or witness point that has not been verified is the specific thing an ITP exists to
        # prevent being skipped, so it is named rather than folded into the open count.
        "unverified_hold_points": [
            {"id": r["id"], "ref": r["ref"], "point_type": r["data"].get("point_type"),
             "state": r["state"]}
            for r in gathered.get("itp", [])
            if guid in r["guids"] and r["open"] and r["data"].get("point_type")],
    }


def chain(db: Session, pid: str, guids: list[str] | None = None) -> dict[str, Any]:
    """The per-element quality chain across a project.

    `guids=None` reports only the elements quality records actually name — asking the model for every
    GlobalId would report `unrecorded` for tens of thousands of elements and drown the signal. Pass an
    explicit list (e.g. the elements a turnover package covers) to ask about specific ones.
    """
    gathered = gather(db, pid)
    attached = sorted({g for rows in gathered.values() for r in rows for g in r["guids"]})
    targets = list(guids) if guids is not None else attached
    elements = [element_evidence(gathered, g) for g in targets]

    counts = {s: sum(1 for e in elements if e["status"] == s)
              for s in (STATUS_CLEAR, STATUS_OUTSTANDING, STATUS_UNRECORDED)}
    record_total = sum(len(rows) for rows in gathered.values())
    unattached = {k: sum(1 for r in rows if not r["guids"]) for k, rows in gathered.items()}

    return {
        "elements": elements,
        "element_count": len(elements),
        "counts": counts,
        "attached_element_count": len(attached),
        # The capability guard. If nothing is attached anywhere, every element reads `unrecorded`
        # because nobody has linked records yet — a fact about the PROCESS, not about the building.
        "any_attached": bool(attached),
        # Coverage is the share of the ELEMENTS ASKED ABOUT that carry evidence — not the project's
        # attachment count over the request size. Those differ whenever the question names elements
        # the project has not attached: asking about [A, B] while C is attached elsewhere gave 100%,
        # which is the coverage metric reporting a comfortable number about the wrong population.
        # Caught by the route test's own assertion.
        "coverage_pct": (round(100 * sum(1 for e in elements if e["record_count"] > 0)
                               / len(targets), 1) if targets else 0.0),
        "records_total": record_total,
        "records_without_element": unattached,
        "status_meanings": _WHY,
        "note": ("An element with no quality record is `unrecorded`, never `clear`. Absence of "
                 "evidence is not evidence of conformance."),
        "message": (None if attached else
                    f"No quality record in this project is attached to an element "
                    f"({record_total} record(s) exist across itp/ncr/inspection). Attach them with "
                    f"POST /projects/{{pid}}/modules/{{key}}/{{rid}}/elements to build the chain."),
    }


def turnover_readiness(db: Session, pid: str, guids: list[str] | None = None) -> dict[str, Any]:
    """Whether the quality evidence supports closing out — the seam `turnover.py` never had.

    G704 substantial completion is certified WITH an outstanding punch list, so an open NCR does not
    by itself block certification. What this reports is what the certificate cannot currently say:
    which elements carry unresolved quality evidence, and — the part that matters more — how much of
    the package has no evidence at all.
    """
    c = chain(db, pid, guids)
    blocking = [e for e in c["elements"] if e["status"] == STATUS_OUTSTANDING]
    silent = [e for e in c["elements"] if e["status"] == STATUS_UNRECORDED]
    return {
        "ready": not blocking and not silent and c["any_attached"],
        "outstanding_elements": [{"guid": e["guid"], "open_items": e["open_items"]}
                                 for e in blocking],
        "unrecorded_elements": [e["guid"] for e in silent],
        "outstanding_count": len(blocking), "unrecorded_count": len(silent),
        "coverage_pct": c["coverage_pct"], "any_attached": c["any_attached"],
        "basis": ("`ready` requires evidence to EXIST and be resolved. An element with no quality "
                  "record counts against readiness rather than for it — otherwise a project nobody "
                  "inspected reads as perfectly clean, which is the failure this exists to prevent."),
        "message": (None if c["any_attached"] else c["message"]),
    }
