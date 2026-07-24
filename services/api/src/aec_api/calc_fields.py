"""SCHED-CALC (R18) — deterministic **calculated fields** over tabular rows: computed schedules and
module records get formula columns (`width * height`, `"D-" + mark`, conditionals) with **no scripting
runtime**. Expressions are parsed with Python's `ast` and executed by walking a strict node whitelist —
no attribute access, no subscripts, no comprehensions, no imports, no double-star power — so a stored
expression can compute, but never reach.

Field names resolve against the row: keys are normalized (lower-cased, non-alphanumerics → `_`, so the
schedule column ``Width (m)`` is ``width_m`` in a formula), and string values that parse as numbers are
auto-coerced so arithmetic works over text tables. A runtime error in one row (bad types, divide by
zero) yields None for that cell — one bad row never kills the column.
"""
from __future__ import annotations

import ast
import re
from typing import Any

_MAX_EXPR_LEN = 500
_MAX_NODES = 200
_MAX_CALCS = 12

_FUNCS: dict[str, Any] = {"round": round, "min": min, "max": max, "abs": abs, "len": len,
                          "num": None, "text": None}     # num/text are bound in _eval

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Constant, ast.Name, ast.Load, ast.Call,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
)


def norm_key(name: str) -> str:
    """A row key / column title → the formula identifier: lower-case, runs of non-alphanumerics → `_`."""
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("$", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _coerce(v: Any) -> Any:
    """A row value entering a formula: numeric-looking strings become numbers (text tables stay usable)."""
    if isinstance(v, str):
        n = _num(v)
        return n if n is not None else v
    return v


def validate(expr: str) -> str | None:
    """Return an error message when the expression is not allowed, else None. Checked at definition
    time so a bad formula 422s instead of silently yielding empty columns."""
    if not isinstance(expr, str) or not expr.strip():
        return "expression is required"
    if len(expr) > _MAX_EXPR_LEN:
        return f"expression too long (max {_MAX_EXPR_LEN} chars)"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"syntax error: {e.msg}"
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_NODES:
        return f"expression too complex (max {_MAX_NODES} nodes)"
    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            return f"'{type(node).__name__}' is not allowed in a calculated field"
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
                return ("only these functions are allowed: " + ", ".join(sorted(_FUNCS)))
            if node.keywords:
                return "keyword arguments are not allowed"
    return None


def evaluate(expr: str, row: dict[str, Any]) -> Any:
    """Evaluate a VALIDATED expression against one row (normalized keys). Runtime errors → None."""
    env = {norm_key(k): _coerce(v) for k, v in row.items()}

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return env.get(node.id)
        if isinstance(node, ast.UnaryOp):
            v = _eval(node.operand)
            if isinstance(node.op, ast.Not):
                return not v
            n = _num(v)
            if n is None:
                return None
            return -n if isinstance(node.op, ast.USub) else n
        if isinstance(node, ast.BinOp):
            a, b = _eval(node.left), _eval(node.right)
            if isinstance(node.op, ast.Add) and (isinstance(a, str) or isinstance(b, str)):
                return ("" if a is None else str(a)) + ("" if b is None else str(b))
            na, nb = _num(a), _num(b)
            if na is None or nb is None:
                return None
            if isinstance(node.op, ast.Add):
                return na + nb
            if isinstance(node.op, ast.Sub):
                return na - nb
            if isinstance(node.op, ast.Mult):
                return na * nb
            if isinstance(node.op, ast.Div):
                return na / nb if nb else None
            if isinstance(node.op, ast.FloorDiv):
                return na // nb if nb else None
            if isinstance(node.op, ast.Mod):
                return na % nb if nb else None
            return None
        if isinstance(node, ast.BoolOp):
            vals = [_eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                out: Any = True
                for v in vals:
                    out = v
                    if not v:
                        return v
                return out
            for v in vals:
                if v:
                    return v
            return vals[-1] if vals else None
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = _eval(comp)
                try:
                    if isinstance(op, ast.Eq):
                        ok = left == right
                    elif isinstance(op, ast.NotEq):
                        ok = left != right
                    else:
                        la, ra = _num(left), _num(right)
                        if la is None or ra is None:
                            return None
                        ok = {ast.Lt: la < ra, ast.LtE: la <= ra,
                              ast.Gt: la > ra, ast.GtE: la >= ra}[type(op)]
                except TypeError:
                    return None
                if not ok:
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return _eval(node.body) if _eval(node.test) else _eval(node.orelse)
        if isinstance(node, ast.Call):
            args = [_eval(a) for a in node.args]
            name = node.func.id  # type: ignore[attr-defined]
            if name == "num":
                return _num(args[0]) if args else None
            if name == "text":
                return "" if not args or args[0] is None else str(args[0])
            fn = _FUNCS[name]
            try:
                return fn(*args)
            except (TypeError, ValueError):
                return None
        return None

    try:
        return _eval(ast.parse(expr, mode="eval"))
    except (ZeroDivisionError, RecursionError, TypeError, ValueError, KeyError):
        return None


def check_calcs(calcs: list[dict]) -> list[dict]:
    """Validate a calc list ({name, expr} each) → the cleaned list. Raises ValueError with the FIRST
    problem (name + message) so the caller can 422."""
    if not isinstance(calcs, list) or not calcs:
        raise ValueError("calcs must be a non-empty list of {name, expr}")
    if len(calcs) > _MAX_CALCS:
        raise ValueError(f"too many calculated fields (max {_MAX_CALCS})")
    out = []
    for c in calcs:
        name = str((c or {}).get("name") or "").strip()
        expr = str((c or {}).get("expr") or "")
        if not name:
            raise ValueError("every calculated field needs a name")
        err = validate(expr)
        if err:
            raise ValueError(f"{name}: {err}")
        out.append({"name": name[:60], "expr": expr})
    return out


def _fmt(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 4)
    return v


def add_calculated(table: dict, calcs: list[dict]) -> dict:
    """Extend a `{columns, rows}` table (rows = lists aligned to columns) with validated calc columns."""
    cols = list(table.get("columns") or [])
    rows = [list(r) for r in (table.get("rows") or [])]
    for r in rows:
        row_map = dict(zip(cols, r))
        for c in calcs:
            r.append(_fmt(evaluate(c["expr"], row_map)))
    return {**table, "columns": cols + [c["name"] for c in calcs], "rows": rows,
            "calculated": [c["name"] for c in calcs]}
