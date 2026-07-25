"""R26-INSPECTOR — the six-state lifecycle strip for one element.

**designed · checked · priced · scheduled · installed · verified**, read left to right, always.

This is the payoff surface for work already shipped. Every state below is a fact the platform already
holds against the *same GlobalId* — the model, the QA lenses, the 5D cost binding (v0.3.684), the
schedule, the field record, and the LOD-500 verification stamp. The audit's point was that they live
in separate panels in separate workspaces, so the one genuinely unusual thing about this product —
that all of it shares one key — is invisible in the interface.

**Three rules the strip has to follow to be worth having:**

* **Unknown is not "no".** An element nobody has priced and an element priced at zero are different
  facts. A state is `done`, `none`, or **`unknown`** when the platform cannot see the answer, and the
  strip says which. Colouring an unknown as a failure trains people to ignore the strip.
* **A later state cannot be more complete than an earlier one it depends on.** An element cannot be
  *verified* installed if nothing records it as installed. Where the data claims otherwise the strip
  reports the inconsistency rather than smoothing it over — that is a data defect worth seeing.
* **Every state names what would advance it.** A strip that shows six greys and no next step is a
  diagnosis with no prescription.
"""
from __future__ import annotations

from typing import Any

#: Ordered, and the order is load-bearing — each state's prerequisite is the one before it.
STATES: list[dict[str, str]] = [
    {"key": "designed", "label": "Designed",
     "means": "The element exists in the model with a class and geometry",
     "advance": "Author or import the element"},
    {"key": "checked", "label": "Checked",
     "means": "It has passed the model-quality lenses — no duplicate GUID, orphan or blank",
     "advance": "Run Model Health and clear its findings"},
    {"key": "priced", "label": "Priced",
     "means": "A cost rule matched it and produced a rate against a measured quantity",
     "advance": "Add a cost rule whose selector matches it"},
    {"key": "scheduled", "label": "Scheduled",
     "means": "A schedule activity claims it as work to be done",
     "advance": "Bind it to an activity (needs a task→element link)"},
    {"key": "installed", "label": "Installed",
     "means": "The field recorded it as placed",
     "advance": "Log installation from the field"},
    {"key": "verified", "label": "Verified",
     "means": "Measured in place, with a stated accuracy — LOD 500",
     "advance": "Verify against a scan or a field measurement"},
]
STATE_KEYS = [s["key"] for s in STATES]

DONE, NONE, UNKNOWN = "done", "none", "unknown"


def _state(key: str, status: str, detail: str = "") -> dict[str, Any]:
    spec = next(s for s in STATES if s["key"] == key)
    return {"key": key, "label": spec["label"], "status": status,
            "means": spec["means"], "detail": detail,
            # only an incomplete state carries a next step; telling someone how to finish something
            # they already finished is noise
            "advance": None if status == DONE else spec["advance"]}


def strip(element: dict[str, Any] | None, *,
          checked: bool | None = None,
          priced: dict[str, Any] | None = None,
          scheduled: dict[str, Any] | None = None,
          installed: dict[str, Any] | None = None,
          verified: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the strip for one element.

    Each keyword is the corresponding engine's answer, or **None meaning "not consulted"** — which is
    reported as `unknown` rather than as absence. The distinction matters: "no cost rule matched this"
    and "nobody ran the estimate" look identical on a screen and mean very different things.
    """
    e = element or {}
    out: list[dict[str, Any]] = []

    # designed — the element is in the model at all
    has_class = bool(str(e.get("ifc_class") or "").strip())
    out.append(_state("designed", DONE if has_class else NONE,
                      str(e.get("ifc_class") or "") if has_class else "not in the model"))

    # checked — the QA lenses
    out.append(_state("checked", UNKNOWN if checked is None else (DONE if checked else NONE),
                      "" if checked is None else ("no findings" if checked else "has findings")))

    # priced — a cost rule matched AND produced an amount
    if priced is None:
        out.append(_state("priced", UNKNOWN))
    elif priced.get("amount") is not None:
        out.append(_state("priced", DONE,
                          f"{priced.get('code', '')} · {priced.get('amount')}".strip(" ·")))
    else:
        out.append(_state("priced", NONE, "no cost rule matched"))

    # scheduled — an activity claims it
    if scheduled is None:
        out.append(_state("scheduled", UNKNOWN))
    else:
        act = scheduled.get("activity")
        out.append(_state("scheduled", DONE if act else NONE, str(act or "no activity")))

    # installed — the field says so
    if installed is None:
        out.append(_state("installed", UNKNOWN))
    else:
        on = bool(installed.get("installed"))
        out.append(_state("installed", DONE if on else NONE, str(installed.get("date") or "")))

    # verified — LOD 500, with its stated accuracy
    if verified is None:
        out.append(_state("verified", UNKNOWN))
    elif verified.get("verified"):
        dev = verified.get("deviation_m")
        out.append(_state("verified", DONE,
                          f"±{dev} m" if dev is not None else "measured in place"))
    else:
        out.append(_state("verified", NONE, "not measured in place"))

    by_key = {s["key"]: s for s in out}

    # A later state cannot outrun the one it depends on. Rather than silently downgrade, REPORT it —
    # "verified but not installed" is a real data defect and hiding it loses the signal.
    inconsistencies = []
    for i in range(1, len(STATE_KEYS)):
        cur, prev = by_key[STATE_KEYS[i]], by_key[STATE_KEYS[i - 1]]
        if cur["status"] == DONE and prev["status"] == NONE:
            inconsistencies.append(
                f"{cur['label']} is complete but {prev['label']} is not — one of them is wrong")

    done = [s["key"] for s in out if s["status"] == DONE]
    unknown = [s["key"] for s in out if s["status"] == UNKNOWN]
    # the furthest CONTIGUOUS state reached: the honest answer to "how far has this got"
    reached = None
    for k in STATE_KEYS:
        if by_key[k]["status"] == DONE:
            reached = k
        else:
            break
    nxt = next((s for s in out if s["status"] != DONE), None)

    return {
        "guid": e.get("guid") or e.get("GlobalId"),
        "states": out,
        "reached": reached,
        "done_count": len(done),
        "unknown_count": len(unknown),
        "next": {"key": nxt["key"], "advance": nxt["advance"]} if nxt else None,
        "inconsistencies": inconsistencies,
        "note": ("`unknown` means the platform was not asked, not that the answer is no — an unpriced "
                 "element and an unexamined one are different facts. `reached` is the furthest "
                 "CONTIGUOUS state, so a later state cannot flatter an incomplete earlier one."),
    }
