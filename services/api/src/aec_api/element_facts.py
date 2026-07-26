"""R26-INSPECTOR — the six lifecycle facts for one GlobalId, gathered from where they already live.

`lifecycle_strip` decides how the six states *read*. This module answers what they **are**, and its
whole job is to distinguish three things a naive implementation conflates:

* **done** — the platform looked and the answer is yes.
* **none** — the platform looked and the answer is no.
* **unknown** (`None`) — the platform could not look.

Each of the three lookups below has a specific way of getting that wrong, and each is handled:

* **checked** — `model_qa` caps every check's offender list at 20 for payload size. Looking this
  element up in that sample would report *clean* for the 21st duplicate: a check that examined a
  different element, answering about this one. So the rules are re-evaluated for this GUID exactly
  (`model_qa.element_findings`), and an element not in the model reads unknown rather than clean.
* **scheduled** — an element not claimed by any activity looks like "not scheduled". But if **no**
  activity in the project binds any element, nothing was ever asked, and reporting `none` for every
  element would dress up a missing capability as a finding about the building. So the project-wide
  binding is checked first: no bindings at all → unknown for everyone.
* **installed / verified** — the field record and the LOD-500 stamp can both answer. The IFC stamp
  wins when present (IFC is the source of truth) and the field record is the fallback, with `source`
  stated either way, because "the model says so" and "somebody logged it" are different assurances.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

#: Field module whose records mean "the field observed this element in place".
INSTALL_MODULE = "field_verification"
#: Its states that assert verification (measured in place), not merely observation.
VERIFIED_STATES = ("verified", "resolved")
#: Rows scanned per module. Newest first — an ascending cap silently hides everything recent.
MAX_ROWS = 2000


def _rows(db: Session, key: str, pid: str) -> list[dict[str, Any]]:
    from .modules import TABLES
    t = TABLES.get(key)
    if t is None:
        return []
    q = (select(t).where(t.c.project_id == pid)
         .order_by(t.c.created_at.desc()).limit(MAX_ROWS))
    return [dict(r._mapping) for r in db.execute(q).all()]


def _claims(row: dict[str, Any], guid: str) -> bool:
    """Whether a record refers to this element — by pin, or by a `guid` field it stores."""
    if guid in (row.get("element_guids") or []):
        return True
    return str((row.get("data") or {}).get("guid") or "").strip() == guid


def checked(model, guid: str) -> bool | None:
    """True when the integrity lenses found nothing against this element; None when it was not read."""
    if model is None:
        return None
    from . import model_qa
    try:
        res = model_qa.element_findings(model, guid)
    except Exception:                      # noqa: BLE001 — an unreadable model is unknown, not clean
        return None
    if not res.get("found"):
        return None                        # not in the model: nothing was examined
    return bool(res.get("clean"))


def scheduled(db: Session, pid: str, guid: str) -> dict[str, Any] | None:
    """The activity claiming this element, `{}` when none does, or None when nothing binds at all.

    That last case is the one worth having. Task→element binding is a capability a project either
    uses or does not; where it is unused, every element would otherwise report a confident "not
    scheduled" that is really "we never asked".
    """
    rows = _rows(db, "schedule_activity", pid)
    if not rows:
        return None
    bound = [r for r in rows if (r.get("element_guids") or [])]
    if not bound:
        return None                        # nothing in this project binds tasks to elements
    hit = next((r for r in bound if _claims(r, guid)), None)
    if hit is None:
        return {}                          # binding IS in use here, and this element is not in it
    d = hit.get("data") or {}
    return {"activity": d.get("activity_id") or hit.get("ref") or hit.get("id"),
            "name": d.get("name") or hit.get("title"), "record_id": hit.get("id")}


def _field_records(db: Session, pid: str, guid: str) -> list[dict[str, Any]]:
    from .modules import TABLES
    if INSTALL_MODULE not in TABLES:
        return []
    return [r for r in _rows(db, INSTALL_MODULE, pid) if _claims(r, guid)]


def installed(db: Session, pid: str, guid: str) -> dict[str, Any] | None:
    """A field record for this element means the field saw it placed. No module → unknown."""
    from .modules import TABLES
    if INSTALL_MODULE not in TABLES:
        return None
    recs = _field_records(db, pid, guid)
    if not recs:
        return {"installed": False}        # the register exists and does not mention this element
    top = recs[0]
    d = top.get("data") or {}
    return {"installed": True, "date": d.get("observed_date"), "source": "field",
            "record_id": top.get("id"), "ref": top.get("ref")}


def verified(db: Session, pid: str, guid: str, element: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """LOD-500 verification: the IFC stamp first, a verified field record second.

    A verification without its accuracy is a tick, not a measurement — `deviation_m` carries through
    from whichever source answered, and `source` says which, because the two are not equivalent
    evidence even when they agree.
    """
    if element is not None:
        try:
            from . import lod
            v = lod.verification(element)
            if v.get("verified"):
                return {"verified": True, "deviation_m": v.get("deviation_m"), "source": "model"}
        except Exception:                  # noqa: BLE001 — fall through to the field record
            pass
    from .modules import TABLES
    if INSTALL_MODULE not in TABLES:
        return None if element is None else {"verified": False}
    recs = _field_records(db, pid, guid)
    if not recs:
        return None if element is None else {"verified": False}
    hit = next((r for r in recs if str(r.get("workflow_state") or "") in VERIFIED_STATES), None)
    if hit is None:
        return {"verified": False}
    mm = (hit.get("data") or {}).get("deviation_mm")
    return {"verified": True, "source": "field", "record_id": hit.get("id"),
            "deviation_m": round(float(mm) / 1000.0, 4) if mm not in (None, "") else None}


def gather(db: Session, pid: str, guid: str, *, model=None,
           element: dict[str, Any] | None = None,
           priced: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every keyword `lifecycle_strip.strip` takes, so the route stays a thin adapter."""
    return {
        "checked": checked(model, guid),
        "priced": priced,
        "scheduled": scheduled(db, pid, guid),
        "installed": installed(db, pid, guid),
        "verified": verified(db, pid, guid, element),
    }
