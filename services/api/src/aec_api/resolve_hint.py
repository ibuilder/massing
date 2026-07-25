"""UX-ACT (R16) — the shared **resolve-action** vocabulary: turn a computed diagnostic (an over-budget
cost code, a schedule conflict, a rule violation) into a small, deterministic *action descriptor* the
frontend renders as a one-click button next to the diagnosis, instead of leaving it a passive read-only
alert. One shape across every feed so the portal renders them uniformly.

An action is ``{kind, label, …}``. The kinds are a closed vocabulary the client knows how to dispatch:

* ``open_module``     — open a config-module's records view (``module``, optional ``q`` free-text filter).
* ``navigate``        — jump to a portal destination (``target`` = a nav-destination key like ``__margin__``).
* ``open_record``     — open one module record (``module`` + ``ref``).
* ``select_elements`` — select model elements by GlobalId in the viewer (``guids``, optional ``selector``).

Pure + tiny — no I/O, no model. Feeds compose these; the client maps ``kind`` → behaviour.
"""
from __future__ import annotations

from typing import Any

KINDS = ("open_module", "navigate", "open_record", "select_elements")

# A diagnostic can name thousands of elements; an action descriptor is a button payload, not a data
# feed. Cap the GUIDs it carries and say when the list was cut, so the client never silently selects
# a subset while looking like it selected everything.
MAX_ACTION_GUIDS = 200


def open_module(module: str, label: str, q: str | None = None) -> dict[str, Any]:
    """Open a module's list/CRUD view, optionally pre-filtered by a free-text query."""
    a: dict[str, Any] = {"kind": "open_module", "module": module, "label": label}
    if q:
        a["q"] = q
    return a


def navigate(target: str, label: str) -> dict[str, Any]:
    """Jump to a portal nav-destination (e.g. ``__margin__``, ``__selections__``)."""
    return {"kind": "navigate", "target": target, "label": label}


def open_record(module: str, ref: str, label: str) -> dict[str, Any]:
    """Open one specific module record by its ref."""
    return {"kind": "open_record", "module": module, "ref": ref, "label": label}


def select_elements(guids, label: str, selector: str | None = None) -> dict[str, Any]:
    """Select model elements by GlobalId — the action for a diagnostic that names *geometry* rather
    than records (a rule violation, a clash, a validation failure).

    ``selector`` carries the QUERY-DSL expression the guids came from when there is one, so a client
    can re-evaluate against the current model instead of acting on a snapshot. When the list is
    capped, ``truncated`` and the true ``total`` say so — a button that selects 200 of 4,000 elements
    while looking like it selected all of them is worse than one that admits the cut.
    """
    all_guids = [g for g in (guids or []) if g]
    a: dict[str, Any] = {"kind": "select_elements", "label": label,
                         "guids": all_guids[:MAX_ACTION_GUIDS], "total": len(all_guids)}
    if len(all_guids) > MAX_ACTION_GUIDS:
        a["truncated"] = True
    if selector:
        a["selector"] = selector
    return a
