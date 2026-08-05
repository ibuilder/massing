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
  5. **No IO through the exposed objects** — removing `open` from the namespace is not enough on its own:
     `model` is a real `ifcopenshell.file` and brings its own API surface, including file IO that a
     builtins denylist cannot see. Its file-touching attributes are denied by name.
  6. **Bounded runtime** — banning `while` does not bound execution (`for i in range(10**9)` is the same
     unbounded loop), so a wall-clock deadline (`AEC_IFC_CODE_TIMEOUT`, default 5s) is enforced by a
     line-level trace hook, and integer-blowup shapes (`9**9**9`) are rejected at the AST.

Not a claim of perfect isolation — it is a gated, authenticated, editor-only, opt-in escape hatch, layered.
Known residual limit: the deadline is enforced between *snippet* lines, so a single call into a slow
library routine is bounded only by that routine, not by the hook.
"""
from __future__ import annotations

import ast
import os
import sys
import time
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
# denied ATTRIBUTE names (defence-in-depth on top of the restricted namespace, which is the real fix): a
# walk of any exposed object's non-dunder attributes must never reach a module, reflection helper, or the
# string-format machinery (str.format does dunder attribute access at runtime, bypassing the AST no-dunder
# check). These are module / stdlib names; the intended authoring call `ifcopenshell.api.run(...)` is a
# bound function on the facade, so `.run` itself is *not* denied.
_DENIED_ATTRS = frozenset({
    "format", "format_map", "format_spec",        # str.format runtime dunder access
    "os", "sys", "subprocess", "builtins", "importlib", "inspect", "ctypes", "ctypeslib", "shutil",
    "tempfile", "pickle", "socket", "io", "zipfile", "pathlib", "runpy", "code", "codeop", "pty",
    "system", "popen", "spawn", "spawnv", "spawnl", "spawnve", "execv", "execve", "execl", "fork", "kill",
    "import_module", "load_module", "exec_module", "get_data",
    "environ", "getenv", "putenv", "wrapped_data",
    # SEC: `model` is a real ifcopenshell.file, and that object's public API carries its own IO
    # surface. Removing `open` from the namespace is NOT enough, because a builtins denylist cannot
    # see methods reached through an object we handed in. The snippet authors entities; persisting
    # the model is the *caller's* job, so none of these have a legitimate use inside a snippet.
    "write", "from_string", "from_pointer", "assign_header_from", "storage",
})
#: SEC-PLUGIN-SANDBOX — the lowercase attribute names a snippet may reach. Everything else lowercase
#: is refused, so an escape route nobody enumerated is closed by default rather than after someone
#: finds it. The split works because of a property of the domain, not a coincidence: **IFC entity
#: attributes are CamelCase** (`Name`, `GlobalId`, `ObjectPlacement`) while the dangerous stdlib
#: surface is lowercase (`os`, `system`, `environ`, `import_module`, `format_map`, `wrapped_data`).
#: So CamelCase passes and lowercase must be named here.
#:
#: Kept deliberately generous — a sandbox that rejects ordinary authoring gets its flag switched on
#: permanently and then off again, which is worse than a slightly wider allowlist. Add to this list
#: rather than removing the check.
_ALLOWED_LOWER_ATTRS = frozenset({
    # the authoring facade the snippet is actually here to use
    "api", "run", "guid", "new", "create_entity",
    # ifcopenshell.file read surface
    "by_type", "by_id", "by_guid", "get_inverse", "traverse", "schema", "types", "is_a", "id",
    # ordinary value manipulation
    "append", "extend", "insert", "index", "count", "sort", "reverse", "copy",
    "keys", "values", "items", "get", "add", "update", "pop",
    "strip", "lstrip", "rstrip", "lower", "upper", "title", "split", "rsplit", "join",
    "replace", "startswith", "endswith", "find", "isdigit", "isalpha", "zfill", "ljust", "rjust",
    "real", "imag",
})


def _attr_allowed(attr: str) -> bool:
    """True for an attribute a snippet may read.

    CamelCase (an IFC entity attribute) passes; anything else must be on `_ALLOWED_LOWER_ATTRS`.

    There is deliberately NO separate leading-underscore branch. The obvious one —
    `if attr.startswith("_"): return False` — was written first and removed: `_foo` already fails
    `isupper()` and is not on the allowlist, so it was rejected either way. Mutation testing caught
    it as a branch that could not change any outcome. A redundant clause in security code is worse
    than none, because it reads as a distinct protection and invites relying on it.
    """
    if not attr:
        return False
    if attr[0].isupper():
        return True                      # IfcWall.Name, .GlobalId, .ObjectPlacement, …
    return attr in _ALLOWED_LOWER_ATTRS


_MAX_LEN = 8000
# SEC: wall-clock budget for a snippet. `while` is rejected by the AST allowlist, but `for` over a
# large range is an equivalent unbounded loop and pins a uvicorn worker forever (a handful of requests
# takes the API down). A line-level trace hook enforces the deadline portably (signal.setitimer is
# POSIX-only and this also runs on Windows dev boxes).
_MAX_SECONDS = float(os.environ.get("AEC_IFC_CODE_TIMEOUT", "5"))
# SEC: a nested power (`9**9**9`) is a single bytecode op — it computes inside CPython's integer
# routine where no trace hook can interrupt it, so the deadline above cannot catch it. IFC authoring
# has no use for a tower of exponents, so reject the shape outright.
_MAX_POW_EXPONENT = 1024


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
        if isinstance(node, ast.Attribute):
            if "__" in node.attr:
                raise SandboxError(f"disallowed attribute: {node.attr}")
            if node.attr in _DENIED_ATTRS:
                raise SandboxError(f"disallowed attribute: {node.attr}")
            # SEC-PLUGIN-SANDBOX: the denylist above stays as defence-in-depth, but the ALLOWLIST
            # below is what actually holds. A denylist over an injected object's API is unclosable —
            # it blocks what someone thought of, and `model` is a real `ifcopenshell.file` whose
            # surface nobody here enumerated. Every escape in the red-team suite above
            # (`ifcopenshell.os.system`, `.express.subprocess`, `.api.importlib`, `format_map`,
            # `wrapped_data`) is a *lowercase* attribute that had to be discovered and added by hand.
            if not _attr_allowed(node.attr):
                raise SandboxError(
                    f"attribute not on the allowlist: {node.attr} "
                    "(IFC attributes are CamelCase; only a fixed set of lowercase helpers is exposed)")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            # a**b**c chains, or a single huge constant exponent, are integer-blowup DoS shapes
            if isinstance(node.right, ast.BinOp) and isinstance(node.right.op, ast.Pow):
                raise SandboxError("disallowed expression: chained ** (integer-blowup guard)")
            if (isinstance(node.right, ast.Constant) and isinstance(node.right.value, int)
                    and abs(node.right.value) > _MAX_POW_EXPONENT):
                raise SandboxError(f"exponent too large (> {_MAX_POW_EXPONENT})")


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
    import types

    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.guid
    # CRITICAL: never expose the real `ifcopenshell` module — a module leaks its transitive imports (os,
    # sys, subprocess, importlib…) as plain non-dunder attributes, which is a full RCE escape. Expose a
    # minimal **facade** carrying only the authoring callables we intend. Each is a bound function (not a
    # module), so there is no attribute path from it back to a module.
    ifc_facade = types.SimpleNamespace(
        api=types.SimpleNamespace(run=ifcopenshell.api.run),
        guid=types.SimpleNamespace(new=ifcopenshell.guid.new),
        create_entity=ifcopenshell.api.run,   # convenience alias
    )
    safe_builtins = {n: getattr(_b, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_b, n)}
    before = len(list(model))
    ns: dict[str, Any] = {"__builtins__": safe_builtins, "model": model, "ifcopenshell": ifc_facade}
    # SEC: enforce the wall-clock budget with a line-level trace hook. The hook fires per executed
    # line *of the snippet only* (frames whose filename is our compiled unit), so a runaway `for`
    # loop is interrupted while ifcopenshell's own internals run untraced and unslowed.
    deadline = time.monotonic() + _MAX_SECONDS

    def _guard(frame, event, arg):
        if frame.f_code.co_filename != "<ifc_code>":
            return None                      # don't trace into library code
        if time.monotonic() > deadline:
            raise TimeoutError(f"snippet exceeded the {_MAX_SECONDS:g}s budget")
        return _guard

    prev = sys.gettrace()
    try:
        sys.settrace(_guard)
        exec(compile(tree, "<ifc_code>", "exec"), ns)  # noqa: S102 — sandboxed per the module docstring
    except SandboxError:
        raise
    except TimeoutError as e:
        raise SandboxError(str(e)) from e
    except Exception as e:  # noqa: BLE001 — surface the snippet's runtime error, don't leak a traceback
        raise SandboxError(f"runtime error: {type(e).__name__}: {e}") from e
    finally:
        sys.settrace(prev)
    after = len(list(model))
    return {"ok": True, "created": max(0, after - before), "deleted": max(0, before - after),
            "entities_before": before, "entities_after": after,
            "message": f"ran ok — net entity change {after - before:+d}"}
