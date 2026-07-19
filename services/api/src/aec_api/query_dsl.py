"""QUERY-DSL — a compact selector language over the model property index.

An ifcopenshell-selector / ECSQL-flavoured filter string picks a set of elements by class, storey,
type, discipline, or any ``Pset.Property``, so one grammar can scope a clash run, a view filter, a
schedule, a bulk edit, or an MCP tool call — instead of every feature inventing its own filter shape.

Grammar (AND-only, left→right, whitespace-insensitive)::

    IfcWall & Pset_WallCommon.FireRating=2HR & storey=L3
    IfcColumn & Pset_ColumnCommon.Reference~"C-"        (~ is contains)
    IfcSlab & Pset_SlabCommon.LoadBearing=true & Pset_SlabCommon.FireRating

Each ``&``-separated term is one predicate:
  * a bare ``IfcClass`` token (starts with "Ifc")  → ``ifc_class`` equals it (case-insensitive)
  * ``field OP value``                             → compare
  * a bare ``field``                               → the field exists / is truthy

Fields: ``ifc_class`` · ``storey`` · ``type_name`` (alias ``type``) · ``name`` · ``discipline`` · or
``Pset.Prop`` (a single dot splits pset from property). Operators: ``=`` ``!=`` ``>=`` ``<=`` ``>``
``<`` ``~`` (contains). Values may be quoted to include spaces. A comparison is numeric when both
sides parse as numbers, otherwise a case-insensitive string compare.

The reusable entry point is ``select(idx, dsl)`` → matching GUIDs; ``matches(element, predicates)``
lets a caller reuse a parsed query per-element (e.g. a bulk edit walking its own element list).
"""
from __future__ import annotations

from typing import Any

from .model_query import _val  # field resolution (ifc_class/storey/discipline/Pset::Prop) — reused

_FIELD_ALIAS = {"type": "type_name", "class": "ifc_class"}
_MISSING = (None, "", [], {})


class QueryError(ValueError):
    """Raised on an unparseable query string (surface as a 422, not a 500)."""


def _field(name: str) -> str:
    name = name.strip()
    low = name.lower()
    if low in _FIELD_ALIAS:
        return _FIELD_ALIAS[low]
    if "." in name and "::" not in name:        # Pset.Prop → Pset::Prop (split on the FIRST dot)
        pset, prop = name.split(".", 1)
        return f"{pset}::{prop}"
    return name


def _num(x: Any) -> float | None:
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return None


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _cmp(actual: Any, op: str, target: str) -> bool:
    if actual is None:
        return op == "!="                        # a missing value only satisfies "not equal"
    a_num, t_num = _num(actual), _num(target)
    numeric = a_num is not None and t_num is not None
    if op in (">", "<", ">=", "<="):
        if numeric:
            return {">": a_num > t_num, "<": a_num < t_num,
                    ">=": a_num >= t_num, "<=": a_num <= t_num}[op]
        a_s, t_s = str(actual).lower(), str(target).lower()
        return {">": a_s > t_s, "<": a_s < t_s, ">=": a_s >= t_s, "<=": a_s <= t_s}[op]
    a_s, t_s = str(actual).strip().lower(), str(target).strip().lower()
    if op == "=":
        return a_num == t_num if numeric else a_s == t_s
    if op == "!=":
        return not (a_num == t_num if numeric else a_s == t_s)
    if op == "~":
        return t_s in a_s
    return False


def _find_op(term: str) -> tuple[str, int] | None:
    """The LEFTMOST unquoted operator in a term (2-char ops win at the same position), or None.

    HARDEN-2 (B2): the previous split took the first operator in precedence order found ANYWHERE, so a
    quoted value containing an operator character (``name~"a=b"``) split at the ``=`` inside the
    quotes and silently matched nothing. Scanning left-to-right (and skipping quoted spans outright)
    always finds the real operator first."""
    in_q: str | None = None
    i = 0
    while i < len(term):
        c = term[i]
        if in_q:
            if c == in_q:
                in_q = None
        elif c in "\"'":
            in_q = c
        else:
            if term[i:i + 2] in ("!=", ">=", "<=") and i > 0:   # non-empty field must precede the op
                return (term[i:i + 2], i)
            if c in "=<>~" and i > 0:
                return (c, i)
        i += 1
    return None


def parse(dsl: str) -> list[tuple[str, str, str | None]]:
    """Compile a query string into ``[(field, op, value)]`` predicates. ``op`` is one of the operators
    or ``"__has__"`` (bare-field existence). Raises :class:`QueryError` on empty/garbage input."""
    if not dsl or not dsl.strip():
        raise QueryError("empty query")
    preds: list[tuple[str, str, str | None]] = []
    for raw in dsl.split("&"):
        term = raw.strip()
        if not term:
            continue
        split_at = _find_op(term)
        if split_at:
            op, i = split_at
            preds.append((_field(term[:i]), op, _unquote(term[i + len(op):])))
        # bare-IfcClass shorthand — but never hijack a bare-FIELD existence test: real IFC class
        # tokens (IfcWall) carry no "_"/"." while the ifc-prefixed fields (ifc_class, Pset paths) do.
        elif term[:3].lower() == "ifc" and " " not in term and "_" not in term and "." not in term:
            preds.append(("ifc_class", "=", term))
        else:
            preds.append((_field(term), "__has__", None))
    if not preds:
        raise QueryError("no predicates parsed from query")
    return preds


def matches(e: dict, preds: list[tuple[str, str, str | None]]) -> bool:
    """True when element ``e`` satisfies every predicate (AND)."""
    for field, op, value in preds:
        actual = _val(e, field)
        if op == "__has__":
            if actual in _MISSING:
                return False
        elif not _cmp(actual, op, value):
            return False
    return True


def _pred_dicts(preds: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    return [{"field": f, "op": ("exists" if op == "__has__" else op), "value": v} for f, op, v in preds]


def select(idx: dict[str, dict] | None, dsl: str, limit: int = 5000) -> dict[str, Any]:
    """Evaluate a query against the property index → matching GUIDs (capped at ``limit``). The reusable
    core for clash scopes, view filters, schedules, bulk edits, and MCP tools. Raises
    :class:`QueryError` on a bad query."""
    preds = parse(dsl)
    if not idx:
        return {"query": dsl, "predicates": _pred_dicts(preds), "matched": 0,
                "guids": [], "truncated": False, "note": "No model loaded — load a model to query it."}
    guids = [g for g, e in idx.items() if matches(e, preds)]
    return {"query": dsl, "predicates": _pred_dicts(preds), "matched": len(guids),
            "guids": guids[:max(1, limit)], "truncated": len(guids) > max(1, limit)}
