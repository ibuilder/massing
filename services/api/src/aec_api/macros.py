"""RECIPE-MACROS (R16) — save a **chained edit-recipe** as a named, parameterized, reusable command.

A macro is an ordered list of authoring-recipe steps (the same ``{recipe, params}`` shape ``/edit/batch``
runs) with **declared parameters** that its steps reference as ``${name}`` placeholders. Save once
(``add_bay``: two columns + a beam + a slab, parameterized on span + storey), then run it with concrete
args against any model — the whole chain applies as ONE GUID-stable version, exactly like a hand-written
batch. This is the reuse multiplier the edit-recipe spine was built for: a firm captures its standard
assemblies as commands instead of re-typing the same step sequence.

Storage mirrors ``rule_library`` — a single validated JSON blob per project (``{pid}/edit_macros.json``),
no migration, with caps so a stored macro an editor parks can't be amplified into an unbounded apply.
``expand(macro, args)`` resolves placeholders + defaults into a concrete step list (pure, model-free —
so a client can preview/validate before it ever touches the model); the router applies that list through
``aec_data.edit.apply_recipes`` under the same per-project lock + edit-history the other edit routes use.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from . import storage

_KEY = "{pid}/edit_macros.json"

# Caps — a macro is stored by an editor and later expanded+applied; bound what one save can park so the
# run path (and a preview GET) stay predictable. Mirrors rule_library.MAX_*.
MAX_MACROS = 100
MAX_STEPS = 60
MAX_PARAMS = 40
MAX_ID_LEN = 40
MAX_NAME_LEN = 120
MAX_DESC_LEN = 500

_PLACEHOLDER = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class MacroError(ValueError):
    """Bad macro definition (save) or bad run args (expand) → the router maps this to 422/400."""


def _valid_recipes() -> set[str]:
    """The authoring-recipe names a macro step may call (the edit engine's registry)."""
    try:
        from aec_data import edit as ed  # type: ignore

        return set(ed.RECIPES.keys())
    except Exception:                                  # noqa: BLE001 — engine import unavailable; skip the check
        return set()


_IDENT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _norm_param(p: dict) -> dict:
    name = str((p or {}).get("name") or "").strip()
    if not name or not _IDENT.fullmatch(name):
        raise MacroError(f"parameter name '{name}' must be a simple identifier (letters/digits/underscore)")
    out: dict[str, Any] = {"name": name, "label": (str(p.get("label") or name).strip() or name)[:MAX_NAME_LEN]}
    if "default" in (p or {}):
        out["default"] = p["default"]
    if p.get("required"):
        out["required"] = True
    return out


def _norm(m: dict, recipes: set[str]) -> dict:
    """Validate + normalize one macro; raises MacroError on a missing/garbage/oversized field."""
    name = str((m or {}).get("name") or "").strip()
    if not name:
        raise MacroError("each macro needs a 'name'")
    steps = (m or {}).get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise MacroError(f"macro '{name}' needs at least one step")
    if len(steps) > MAX_STEPS:
        raise MacroError(f"macro '{name}' has too many steps ({len(steps)}) — max {MAX_STEPS}")
    clean_steps: list[dict] = []
    for i, s in enumerate(steps):
        recipe = str((s or {}).get("recipe") or "").strip()
        if not recipe:
            raise MacroError(f"macro '{name}' step {i + 1} is missing a 'recipe'")
        if recipes and recipe not in recipes:
            raise MacroError(f"macro '{name}' step {i + 1}: unknown recipe '{recipe}'")
        params = (s or {}).get("params") or {}
        if not isinstance(params, dict):
            raise MacroError(f"macro '{name}' step {i + 1}: 'params' must be an object")
        clean_steps.append({"recipe": recipe, "params": params})
    decl = (m or {}).get("params") or []
    if not isinstance(decl, list):
        raise MacroError(f"macro '{name}': 'params' must be a list of parameter declarations")
    if len(decl) > MAX_PARAMS:
        raise MacroError(f"macro '{name}' declares too many parameters ({len(decl)}) — max {MAX_PARAMS}")
    return {
        "id": str((m or {}).get("id") or uuid.uuid4().hex[:12])[:MAX_ID_LEN],
        "name": name[:MAX_NAME_LEN],
        "description": str((m or {}).get("description") or "").strip()[:MAX_DESC_LEN],
        "params": [_norm_param(p) for p in decl],
        "steps": clean_steps,
    }


def load(pid: str) -> list[dict]:
    """The project's saved macros ([] if none saved yet)."""
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("macros", [])
    except Exception:                                  # noqa: BLE001 — no blob yet / unreadable
        return []


def save(pid: str, macros: list[dict]) -> list[dict]:
    """Validate + persist the macro library. Raises MacroError on any bad macro (nothing is written)."""
    if len(macros or []) > MAX_MACROS:
        raise MacroError(f"too many macros ({len(macros)}) — max {MAX_MACROS}")
    recipes = _valid_recipes()
    clean = [_norm(m, recipes) for m in (macros or [])]   # validate ALL before persisting (atomic)
    ids = [c["id"] for c in clean]
    if len(set(ids)) != len(ids):
        raise MacroError("macro ids must be unique")
    storage.put(_KEY.format(pid=pid), json.dumps({"macros": clean}).encode("utf-8"))
    return clean


def get(pid: str, macro_id: str) -> dict | None:
    """One macro by id (None if absent)."""
    return next((m for m in load(pid) if m.get("id") == macro_id), None)


def _subst(value: Any, args: dict[str, Any]) -> Any:
    """Resolve ``${name}`` placeholders in one param value.

    * A value that is exactly ``"${name}"`` is replaced by the raw arg — **type preserved** (so a
      ``[x, y]`` point or a number survives, not just strings).
    * Placeholders embedded in a longer string are string-interpolated.
    * Lists/dicts are resolved recursively so ``"end": ["${x}", 0]`` works.
    """
    if isinstance(value, str):
        full = _PLACEHOLDER.fullmatch(value)
        if full:
            key = full.group(1)
            if key not in args:
                raise MacroError(f"missing value for parameter '{key}'")
            return args[key]

        def _one(mtch: re.Match[str]) -> str:
            key = mtch.group(1)
            if key not in args:
                raise MacroError(f"missing value for parameter '{key}'")
            return str(args[key])

        return _PLACEHOLDER.sub(_one, value)
    if isinstance(value, list):
        return [_subst(v, args) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, args) for k, v in value.items()}
    return value


def expand(macro: dict, args: dict[str, Any] | None = None) -> list[dict]:
    """Resolve a macro into a concrete ``[{recipe, params}, …]`` step list ready for ``apply_recipes``.

    Declared-param defaults fill anything the caller omitted; a declared ``required`` param with no
    value (and no default) raises MacroError; every ``${name}`` placeholder in the steps is substituted.
    Pure — no model needed, so a client can preview/validate the expansion before applying it.
    """
    args = dict(args or {})
    resolved: dict[str, Any] = {}
    for p in macro.get("params", []):
        name = p["name"]
        if name in args:
            resolved[name] = args[name]
        elif "default" in p:
            resolved[name] = p["default"]
        elif p.get("required"):
            raise MacroError(f"parameter '{name}' is required")
    # allow ad-hoc args not formally declared (a step may reference them directly)
    for k, v in args.items():
        resolved.setdefault(k, v)
    return [{"recipe": s["recipe"], "params": _subst(s.get("params") or {}, resolved)}
            for s in macro.get("steps", [])]


# A small starter set a firm can edit/extend — real, useful chained assemblies. Not auto-seeded (macros
# are opt-in per project); offered by the UI as templates.
STARTER_MACROS: list[dict[str, Any]] = [
    {"id": "bay-frame", "name": "Structural bay (2 columns + beam)",
     "description": "Two columns joined by a beam at their tops — the repeating unit of a frame.",
     "params": [{"name": "x0", "label": "Column 1 X", "default": 0.0},
                {"name": "x1", "label": "Column 2 X", "default": 6.0},
                {"name": "y", "label": "Y", "default": 0.0},
                {"name": "height", "label": "Column height (m)", "default": 3.5},
                {"name": "storey", "label": "Storey", "default": None}],
     "steps": [
         {"recipe": "add_column", "params": {"point": ["${x0}", "${y}"], "height": "${height}", "storey": "${storey}"}},
         {"recipe": "add_column", "params": {"point": ["${x1}", "${y}"], "height": "${height}", "storey": "${storey}"}},
         {"recipe": "add_beam", "params": {"start": ["${x0}", "${y}", "${height}"],
                                           "end": ["${x1}", "${y}", "${height}"], "storey": "${storey}"}},
     ]},
]
