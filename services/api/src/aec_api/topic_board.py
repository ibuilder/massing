"""TOPIC-BOARD (R17 Sprint B, backend half) — a deterministic **kanban board + smart filters** over the BCF
topics we already store.

Groups the topic list into columns by `status` / `priority` / `assignee` / `type`, with an optional
**selector filter** reusing the QUERY-DSL grammar over the topic fields (`status=open & priority=High`,
`title~duct`, `assignee!=`) — one grammar for model elements *and* topics. Columns come back in a stable
workflow order (open → in progress → resolved → closed → reopened) so the board renders identically
everywhere. Pure over the supplied topic dicts.
"""
from __future__ import annotations

from typing import Any

_GROUPS = ("status", "priority", "assignee", "type")
_STATUS_ORDER = ["open", "in progress", "in_progress", "resolved", "closed", "reopened"]
_PRIORITY_ORDER = ["critical", "high", "medium", "normal", "low"]


def _order_key(group_by: str, key: str) -> tuple:
    k = key.lower()
    order = _STATUS_ORDER if group_by == "status" else _PRIORITY_ORDER if group_by == "priority" else []
    try:
        return (0, order.index(k))
    except ValueError:
        return (1, 0) if k in ("—", "(unassigned)") else (0.5, k)   # unassigned last, unknown keys alphabetical


def board(topics: list[dict], group_by: str = "status", dsl: str | None = None) -> dict[str, Any]:
    """Group (optionally filtered) topics into ordered kanban columns. Raises QueryError on a bad filter."""
    from . import query_dsl as qd

    gb = str(group_by or "status").strip().lower()
    if gb not in _GROUPS:
        raise ValueError(f"group_by must be one of {', '.join(_GROUPS)}")
    rows = [t for t in topics or [] if isinstance(t, dict)]
    if dsl and str(dsl).strip():
        preds = qd.parse(str(dsl))                     # QueryError on a bad selector → 422 at the route
        rows = [t for t in rows if qd.matches(t, preds)]

    cols: dict[str, list[dict]] = {}
    for t in rows:
        key = str(t.get(gb) or "").strip() or "(unassigned)"
        cols.setdefault(key, []).append(t)
    columns = [{"key": k, "count": len(v),
                "topics": sorted(v, key=lambda x: str(x.get("modified_at") or x.get("created_at") or ""),
                                 reverse=True)}
               for k, v in cols.items()]
    columns.sort(key=lambda c: _order_key(gb, c["key"]))
    return {
        "group_by": gb, "filter": dsl or None,
        "total": len(rows), "column_count": len(columns), "columns": columns,
        "note": "Kanban board over the BCF topics — columns in stable workflow order, newest-modified first "
                "within a column; the filter reuses the QUERY-DSL grammar over topic fields (one selector "
                "grammar for model elements and topics).",
    }
