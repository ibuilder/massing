"""UX-ACT (R16) — the shared **resolve-action** vocabulary: turn a computed diagnostic (an over-budget
cost code, a schedule conflict, a rule violation) into a small, deterministic *action descriptor* the
frontend renders as a one-click button next to the diagnosis, instead of leaving it a passive read-only
alert. One shape across every feed so the portal renders them uniformly.

An action is ``{kind, label, …}``. The kinds are a closed vocabulary the client knows how to dispatch:

* ``open_module``  — open a config-module's records view (``module``, optional ``q`` free-text filter).
* ``navigate``     — jump to a portal destination (``target`` = a nav-destination key like ``__margin__``).
* ``open_record``  — open one module record (``module`` + ``ref``).

Pure + tiny — no I/O, no model. Feeds compose these; the client maps ``kind`` → behaviour.
"""
from __future__ import annotations

from typing import Any

KINDS = ("open_module", "navigate", "open_record")


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
