"""A1 — a **sandboxed** `execute_ifc_code` escape hatch: run a small snippet of ifcopenshell Python against
the model to author what the fixed recipe registry can't express, without a general RCE.

Defense-in-depth (this is arbitrary-code territory — treat every layer as load-bearing):
  1. **Feature flag OFF by default** — `AEC_ALLOW_IFC_CODE=1` must be set by the operator, who thereby
     accepts the risk (mirrors the "gate execute_blender_code" guidance in CLAUDE.md). Without it, this
     raises `PermissionError`, so the capability ships dormant.
  2. **AST allowlist** — only a fixed set of expression/statement nodes is permitted; `import`, `def`,
     `class`, `lambda`, `with`, `try`, `while` (no infinite loops), `del`, `global`, decorators, `exec`,
     comprehension-of-a-function, etc. are all rejected before anything runs.
  3. **No dunder access** — any Name/Attribute containing `__` is rejected (kills `__class__`/`__globals__`
     /`__subclasses__` escapes).
  4. **Curated builtins + denied names** — `open/eval/exec/getattr/setattr/__import__/type/globals/…` are
     unavailable; only a small safe set (`range/len/float/…`) plus `model` and `ifcopenshell` are in scope.

Not a claim of perfect isolation — it is a gated, authenticated, editor-only, opt-in escape hatch, layered.
"""
from __future__ import annotations

import ast
import os
from typing import Any

# statement/expression node types that may appear. Everything else is rejected.
_ALLOWED = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign,
    ast.Name, ast.Load, ast.Store, ast.Call, ast.Attribute, ast.keyword, ast.Starred,
    ast.Subscript, ast.Slice, ast.Index if hasattr(ast, "Index") else ast.Slice,
    ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Invert,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.For, ast.If, ast.Break, ast.Continue, ast.Pass,
    ast.comprehension, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
)

# builtin names the snippet may call (safe, no reflection / IO / class-creation).
_SAFE_BUILTIN_NAMES = (
    "range", "len", "enumerate", "float", "int", "str", "bool", "list", "dict", "tuple", "set",
    "min", "max", "abs", "round", "sum", "zip", "sorted", "reversed", "map", "filter", "any", "all",
    "isinstance", "print",
)
# explicitly-denied call targets (reflection, IO, dynamic exec, class machinery).
_DENIED_NAMES = frozenset({
    "open", "eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr", "hasattr",
    "globals", "locals", "vars", "input", "exit", "quit", "help", "breakpoint", "type", "object",
    "super", "memoryview", "bytearray", "bytes", "classmethod", "staticmethod", "property", "dir",
})
_MAX_LEN = 8000


class SandboxError(ValueError):
    """The snippet was rejected by the sandbox (disallowed construct / name)."""


def _check(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise SandboxError(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if "__" in node.id:
                raise SandboxError(f"disallowed name: {node.id}")
            if isinstance(node.ctx, ast.Load) and node.id in _DENIED_NAMES:
                raise SandboxError(f"disallowed builtin: {node.id}")
        if isinstance(node, ast.Attribute) and "__" in node.attr:
            raise SandboxError(f"disallowed attribute: {node.attr}")


def enabled() -> bool:
    return os.environ.get("AEC_ALLOW_IFC_CODE", "").strip() in ("1", "true", "True")


def execute_ifc_code(model, code: str) -> dict[str, Any]:
    """Validate + run `code` against `model` in a restricted namespace. `model` and `ifcopenshell` are in
    scope. Returns {ok, created, deleted, message} (net entity delta). Raises PermissionError when the
    feature flag is unset, or SandboxError when the snippet is rejected. GUID-stable for existing elements
    (the snippet gets the live model; it should create, not renumber)."""
    if not enabled():
        raise PermissionError("execute_ifc_code is disabled — set AEC_ALLOW_IFC_CODE=1 to enable (accepts "
                              "the arbitrary-code risk of this gated, editor-only escape hatch)")
    src = (code or "").strip()
    if not src:
        raise SandboxError("empty code")
    if len(src) > _MAX_LEN:
        raise SandboxError(f"code too long ({len(src)} > {_MAX_LEN} chars)")
    try:
        tree = ast.parse(src, mode="exec")
    except SyntaxError as e:
        raise SandboxError(f"syntax error: {e.msg}") from e
    _check(tree)

    import builtins as _b

    import ifcopenshell  # the snippet's authoring surface (ifcopenshell.api.run, etc.)
    safe_builtins = {n: getattr(_b, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_b, n)}
    before = len(list(model))
    ns: dict[str, Any] = {"__builtins__": safe_builtins, "model": model, "ifcopenshell": ifcopenshell}
    try:
        exec(compile(tree, "<ifc_code>", "exec"), ns)  # noqa: S102 — sandboxed per the module docstring
    except SandboxError:
        raise
    except Exception as e:  # noqa: BLE001 — surface the snippet's runtime error, don't leak a traceback
        raise SandboxError(f"runtime error: {type(e).__name__}: {e}") from e
    after = len(list(model))
    return {"ok": True, "created": max(0, after - before), "deleted": max(0, before - after),
            "entities_before": before, "entities_after": after,
            "message": f"ran ok — net entity change {after - before:+d}"}
