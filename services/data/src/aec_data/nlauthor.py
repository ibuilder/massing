"""Natural-language authoring — map a plain-English instruction to a validated authoring **plan**
(a list of {recipe, params}) WITHOUT executing anything. The plan is returned for the user to confirm,
then applied through the existing GUID-stable `/edit` recipe path — interpretation is never mutation.

This module is the deterministic, no-API-key baseline (regex + keyword matching) plus the shared
**recipe spec table + validator** the LLM tool-use path also uses. "Add a 3 m wall from 0,0 to 5,0",
"put a window in the selected wall", "column at 3,2", "set LOD 300 on the selection" all resolve here
with zero network dependency — the biggest barrier-to-entry reducer for non-experts.
"""
from __future__ import annotations

import re
from typing import Any

# ── recipe spec table: the single source of truth for NL mapping, validation, and (later) LLM tools.
# Each: description, params {name: {type, required, default}}, whether it mutates existing elements
# (destructive → needs an explicit second confirm), and NL trigger words.
RECIPE_SPECS: dict[str, dict[str, Any]] = {
    "add_wall": {
        "desc": "Add a straight wall between two [E,N] points (metres) on a storey.",
        "params": {"start": {"type": "point", "required": True}, "end": {"type": "point", "required": True},
                   "height": {"type": "number", "default": 3.0}, "thickness": {"type": "number", "default": 0.2},
                   "storey": {"type": "string"}},
        "triggers": ["wall", "partition"],
    },
    "add_column": {
        "desc": "Add a rectangular column at an [E,N] point.",
        "params": {"point": {"type": "point", "required": True}, "height": {"type": "number", "default": 3.0},
                   "width": {"type": "number", "default": 0.4}, "depth": {"type": "number", "default": 0.4},
                   "storey": {"type": "string"}},
        "triggers": ["column", "post", "pier"],
    },
    "add_beam": {
        "desc": "Add a beam between two [E,N] points.",
        "params": {"start": {"type": "point", "required": True}, "end": {"type": "point", "required": True},
                   "width": {"type": "number", "default": 0.3}, "depth": {"type": "number", "default": 0.5},
                   "storey": {"type": "string"}},
        "triggers": ["beam", "girder", "joist"],
    },
    "add_steel_column": {
        "desc": "Add a steel column (AISC W-shape) at an [E,N] point.",
        "params": {"point": {"type": "point", "required": True}, "height": {"type": "number", "default": 3.0},
                   "section": {"type": "string", "default": "W12x26"}, "storey": {"type": "string"}},
        "triggers": ["steel column", "w-shape column", "wide flange column"],
    },
    "add_steel_beam": {
        "desc": "Add a steel beam (AISC W-shape) between two [E,N] points.",
        "params": {"start": {"type": "point", "required": True}, "end": {"type": "point", "required": True},
                   "section": {"type": "string", "default": "W12x26"}, "storey": {"type": "string"}},
        "triggers": ["steel beam", "w-shape beam"],
    },
    "add_door": {
        "desc": "Add a door into the host wall (its GUID).",
        "params": {"host_guid": {"type": "guid", "required": True}, "width": {"type": "number", "default": 0.9},
                   "height": {"type": "number", "default": 2.1}},
        "triggers": ["door"],
    },
    "add_window": {
        "desc": "Add a window into the host wall (its GUID).",
        "params": {"host_guid": {"type": "guid", "required": True}, "width": {"type": "number", "default": 1.2},
                   "height": {"type": "number", "default": 1.2}, "sill": {"type": "number", "default": 0.9}},
        "triggers": ["window"],
    },
    "add_curtain_wall": {
        "desc": "Add a curtain wall (mullions + glazing) between two [E,N] points.",
        "params": {"start": {"type": "point", "required": True}, "end": {"type": "point", "required": True},
                   "height": {"type": "number", "default": 3.5}, "cols": {"type": "int", "default": 3},
                   "rows": {"type": "int", "default": 2}, "storey": {"type": "string"}},
        "triggers": ["curtain wall", "curtainwall", "glazing wall", "glass wall"],
    },
    "add_spaces": {
        "desc": "Author room/space objects gridded over each floor.",
        "params": {"rooms_per_storey": {"type": "int", "default": 4}, "ceiling_height": {"type": "number", "default": 3.0}},
        "triggers": ["room", "rooms", "space", "spaces"],
    },
    "set_lod": {
        "desc": "Set the LOD stage (100-500) on elements (the selection).",
        "params": {"guids": {"type": "guids", "required": True}, "stage": {"type": "string", "required": True}},
        "triggers": ["lod", "level of development", "level of detail"],
    },
    "set_phase": {
        "desc": "Tag elements new/existing/demolish/temporary (the selection).",
        "params": {"guids": {"type": "guids", "required": True}, "phase": {"type": "string", "required": True}},
        "triggers": ["phase", "existing", "demolish", "demo", "new construction", "temporary"],
    },
    "delete_element": {
        "desc": "Delete an element (the selection). Destructive.",
        "params": {"guid": {"type": "guid", "required": True}},
        "destructive": True, "triggers": ["delete", "remove", "erase"],
    },
}

_UNITS_TO_M = {"m": 1.0, "mm": 0.001, "cm": 0.01, "ft": 0.3048, "'": 0.3048, "in": 0.0254, '"': 0.0254}
_LOD_WORDS = re.compile(r"\b(100|200|300|350|400|500)\b")
_PHASE_WORDS = {"existing": "existing", "demolish": "demolish", "demo": "demolish",
                "temporary": "temporary", "new": "new"}


def _len_m(text: str, default: float | None = None) -> float | None:
    """First length in the text → metres (e.g. '3m'→3.0, '300mm'→0.3, "10ft"/"10'"→3.048)."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mm|cm|m|ft|in|'|\")", text)
    if not m:
        return default
    return float(m.group(1)) * _UNITS_TO_M.get(m.group(2), 1.0)


def _points(text: str) -> list[list[float]]:
    """All coordinate pairs `x,y` (parens optional) in order — the [E,N] points in the instruction."""
    return [[float(a), float(b)] for a, b in
            re.findall(r"\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?", text)]


def validate_call(recipe: str, params: dict) -> dict:
    """Validate a {recipe, params} candidate against RECIPE_SPECS. Returns
    {ok, recipe, params(cleaned+defaults), destructive, errors:[…]}. The guardrail before any apply."""
    spec = RECIPE_SPECS.get(recipe)
    if spec is None:
        return {"ok": False, "recipe": recipe, "params": params, "destructive": False,
                "errors": [f"unknown recipe {recipe!r}"]}
    cleaned: dict[str, Any] = {}
    errors: list[str] = []
    for name, meta in spec["params"].items():
        val = params.get(name)
        if val is None or val == "":
            if meta.get("required"):
                errors.append(f"missing {name}")
            elif "default" in meta:
                cleaned[name] = meta["default"]
            continue
        try:
            if meta["type"] == "number":
                cleaned[name] = float(val)
            elif meta["type"] == "int":
                cleaned[name] = int(val)
            elif meta["type"] == "point":
                p = list(val)
                if len(p) != 2:
                    raise ValueError
                cleaned[name] = [float(p[0]), float(p[1])]
            elif meta["type"] == "guids":
                cleaned[name] = [str(g) for g in (val if isinstance(val, list) else [val])]
            else:
                cleaned[name] = str(val)
        except (TypeError, ValueError):
            errors.append(f"bad {name}")
    return {"ok": not errors, "recipe": recipe, "params": cleaned,
            "destructive": bool(spec.get("destructive")), "errors": errors}


def _summary(call: dict) -> str:
    r, p = call["recipe"], call["params"]
    if r in ("add_wall", "add_beam", "add_steel_beam", "add_curtain_wall") and p.get("start") and p.get("end"):
        extra = f", {p['height']} m tall" if p.get("height") else ""
        return f"{RECIPE_SPECS[r]['desc'].split(' between')[0]} from {p['start']} to {p['end']}{extra}"
    if p.get("point"):
        return f"{RECIPE_SPECS[r]['desc'].split(' at')[0]} at {p['point']}"
    return RECIPE_SPECS[r]["desc"]


def interpret(text: str, context: dict | None = None) -> dict:
    """Deterministic NL → plan. `context` may carry {selected_guids, active_storey}. Returns
    {source:'keyword', plan:[validated calls], needs_clarification: str|None}. Never executes."""
    ctx = context or {}
    t = (text or "").lower().strip()
    sel = list(ctx.get("selected_guids") or [])
    storey = ctx.get("active_storey")
    pts = _points(text)

    def _need(msg):
        return {"source": "keyword", "plan": [], "needs_clarification": msg}

    # pick the recipe by the most specific trigger phrase present
    recipe = None
    best = 0
    for name, spec in RECIPE_SPECS.items():
        for trig in spec["triggers"]:
            if trig in t and len(trig) > best:
                recipe, best = name, len(trig)
    if recipe is None:
        return _need("I couldn't tell what to add. Try e.g. 'add a wall from 0,0 to 5,0' or 'window in the selected wall'.")

    params: dict[str, Any] = {}
    if storey and "storey" in RECIPE_SPECS[recipe]["params"]:
        params["storey"] = storey
    length = _len_m(text)

    if recipe in ("add_wall", "add_beam", "add_steel_beam", "add_curtain_wall"):
        if len(pts) >= 2:
            params["start"], params["end"] = pts[0], pts[1]
        else:
            return _need(f"For a {recipe.replace('add_', '')} I need two points, e.g. 'from 0,0 to 5,0'.")
        if recipe == "add_wall" and (h := _wall_height(text)) is not None:
            params["height"] = h
        if recipe == "add_wall" and (th := _thickness(text)) is not None:
            params["thickness"] = th
        if recipe in ("add_steel_beam",) and (sec := _section(text)):
            params["section"] = sec
    elif recipe in ("add_column", "add_steel_column"):
        if pts:
            params["point"] = pts[0]
        else:
            return _need("Where should the column go? e.g. 'column at 3,2'.")
        if length is not None:
            params["height"] = length
        if recipe == "add_steel_column" and (sec := _section(text)):
            params["section"] = sec
    elif recipe in ("add_door", "add_window"):
        if not sel:
            return _need(f"Select the wall to host the {recipe.replace('add_', '')}, then try again.")
        params["host_guid"] = sel[0]
        if length is not None:
            params["width"] = length
    elif recipe == "add_spaces":
        n = re.search(r"(\d+)\s+(?:rooms|spaces)", t)
        if n:
            params["rooms_per_storey"] = int(n.group(1))
    elif recipe == "set_lod":
        if not sel:
            return _need("Select elements first, then set their LOD (e.g. 'set LOD 300 on selection').")
        m = _LOD_WORDS.search(text)
        if not m:
            return _need("Which LOD stage? 100, 200, 300, 350, 400, or 500.")
        params["guids"], params["stage"] = sel, m.group(1)
    elif recipe == "set_phase":
        if not sel:
            return _need("Select elements first, then set their phase.")
        ph = next((v for k, v in _PHASE_WORDS.items() if k in t), "new")
        params["guids"], params["phase"] = sel, ph
    elif recipe == "delete_element":
        if not sel:
            return _need("Select the element to delete first.")
        params["guid"] = sel[0]

    call = validate_call(recipe, params)
    if not call["ok"]:
        return _need("; ".join(call["errors"]))
    call["summary"] = _summary(call)
    return {"source": "keyword", "plan": [call], "needs_clarification": None}


def _wall_height(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|mm|cm|ft|in|'|\")?\s*(?:tall|high|height)", text.lower())
    return _len_m(m.group(0)) if m else None


def _thickness(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|mm|cm|ft|in|'|\")?\s*(?:thick|thickness|wide)", text.lower())
    return _len_m(m.group(0)) if m else None


def _section(text: str) -> str | None:
    m = re.search(r"\bW\d+x\d+\b", text, re.IGNORECASE)
    return m.group(0).upper().replace("X", "x") if m else None
