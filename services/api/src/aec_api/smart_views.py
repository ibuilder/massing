"""SMART-VIEWS (R15) — user-authored, per-project **saved view presets** over the model.

A smart view is a name + a QUERY-DSL selector + a display mode (isolate / color / hide) + an optional
colour. It's the Solibri/Navisworks "saved search → view" staple: a coordinator saves
``IfcDuctSegment & storey=L3`` as "L3 supply ducts", and anyone can re-apply it to isolate or colour
those elements in the viewer. Built entirely on the pieces that already ship — QUERY-DSL
(``query_dsl.select`` over the property index) for resolution and the storage sidecar for persistence —
so it's cheap glue, not a new subsystem.

Storage is one JSON blob per project (``{pid}/smart_views.json``) — no migration. ``run(idx, view)``
resolves a view's selector to the matching GUIDs the viewer isolates/colours.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from . import query_dsl, storage
from .query_dsl import QueryError

MODES = ("isolate", "color", "hide")
_KEY = "{pid}/smart_views.json"
# HARDEN: a stored view is resolved on every viewer-level apply — bound what one save can park.
MAX_VIEWS = 200
MAX_SELECTOR_LEN = 500
MAX_NAME_LEN = 120
MAX_ID_LEN = 40
_HEX = frozenset("0123456789abcdefABCDEF")


def _valid_color(c: Any) -> str | None:
    """Accept a #RRGGBB hex colour (else None) — never trust a stored string into a style sink."""
    s = str(c or "").strip()
    if len(s) == 7 and s[0] == "#" and all(ch in _HEX for ch in s[1:]):
        return s.lower()
    return None


def _norm(v: dict) -> dict:
    """Validate + normalize one view; raises QueryError (→422) on a missing/garbage/oversized selector."""
    selector = str(v.get("selector") or "").strip()
    if not selector:
        raise QueryError("each smart view needs a 'selector' (QUERY-DSL)")
    if len(selector) > MAX_SELECTOR_LEN:
        raise QueryError(f"selector too long (max {MAX_SELECTOR_LEN} chars)")
    query_dsl.parse(selector)                         # validate the grammar now, not at apply time
    mode = str(v.get("mode") or "isolate").strip().lower()
    if mode not in MODES:
        raise QueryError(f"mode must be one of {MODES}")
    return {"id": str(v.get("id") or uuid.uuid4().hex[:12])[:MAX_ID_LEN],
            "name": (str(v.get("name") or "View").strip() or "View")[:MAX_NAME_LEN],
            "selector": selector, "mode": mode,
            "color": _valid_color(v.get("color")) if mode == "color" else None}


def load(pid: str) -> list[dict]:
    """The project's saved smart views ([] if none saved yet)."""
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("views", [])
    except Exception:                                 # noqa: BLE001 — no blob yet / unreadable
        return []


def save(pid: str, views: list[dict]) -> list[dict]:
    """Validate + persist the view set atomically. Raises QueryError on any bad view (nothing written)."""
    if len(views or []) > MAX_VIEWS:
        raise QueryError(f"too many smart views ({len(views)}) — max {MAX_VIEWS}")
    clean = [_norm(v) for v in (views or [])]         # validate ALL before persisting
    storage.put(_KEY.format(pid=pid), json.dumps({"views": clean}).encode("utf-8"))
    return clean


def run(idx: dict[str, dict] | None, view: dict, limit: int = 20000) -> dict[str, Any]:
    """Resolve a view's selector to the matching GUIDs (for the viewer to isolate / colour / hide)."""
    try:
        sel = query_dsl.select(idx, view["selector"], limit=limit)
    except QueryError:
        # a saved view's selector is validated at save time, so this is defensive — return a fixed
        # message rather than echoing the exception (py/stack-trace-exposure) into the response.
        return {"id": view.get("id"), "name": view.get("name"),
                "error": "this view's selector could not be evaluated — re-save it", "guids": []}
    return {"id": view.get("id"), "name": view.get("name"), "mode": view.get("mode"),
            "color": view.get("color"), "selector": view["selector"],
            "matched": sel.get("matched", 0), "truncated": sel.get("truncated", False),
            "guids": sel.get("guids", [])}
