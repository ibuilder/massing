"""S3 — LLM-backed natural-language authoring.

When an ANTHROPIC_API_KEY is set, Claude turns a plain-English instruction into a **multi-step authoring
plan** (an ordered list of {recipe, params}) constrained to the shared `nlauthor.RECIPE_SPECS`; every step
is then re-validated by `nlauthor.validate_call` before it ever reaches the user. No key → the deterministic
keyword baseline in `nlauthor.interpret`. Either way this is interpretation ONLY — nothing is written; the
client shows the plan for confirmation and applies each step through the audited GUID-stable /edit path.

The LLM never invents GUIDs: recipes that target an existing element (door/window/LOD/phase) get their
host/target filled server-side from the current selection, exactly like the keyword path. Destructive
recipes (delete) are withheld from the model entirely — deletion stays a deliberate, selection-driven act.
"""
from __future__ import annotations

import json
import logging

from . import settings_store
from .ai import ai_enabled

_log = logging.getLogger("aec.nlauthor")


def _llm_recipes() -> dict[str, dict]:
    """The recipes the model may plan — everything non-destructive."""
    from aec_data import nlauthor  # type: ignore
    return {name: spec for name, spec in nlauthor.RECIPE_SPECS.items() if not spec.get("destructive")}


def _fill_context(recipe: str, params: dict, spec: dict, ctx: dict) -> dict:
    """Inject the active storey and current selection the model isn't allowed to fabricate — mirrors the
    keyword baseline so LLM and keyword plans behave identically for selection-targeted recipes."""
    sel = list(ctx.get("selected_guids") or [])
    storey = ctx.get("active_storey")
    p = dict(params or {})
    pm = spec["params"]
    if "storey" in pm and not p.get("storey") and storey:
        p["storey"] = storey
    for name, meta in pm.items():
        if meta["type"] == "guid" and not p.get(name) and sel:
            p[name] = sel[0]
        elif meta["type"] == "guids" and not p.get(name) and sel:
            p[name] = sel
    return p


def _coerce_params(raw) -> dict:
    """A step's `params` may arrive as a dict (keyword/tests) or a JSON string (the LLM path — strict
    structured outputs can't express an open object, so the model returns params as a JSON string).
    Normalise either to a dict; anything unparseable becomes empty (validation then reports what's missing)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _steps_to_plan(steps: list[dict], ctx: dict) -> dict:
    """Turn raw {recipe, params} steps (from the model) into a validated plan. Network-free — the unit of
    logic worth testing without a live API. Unknown/invalid steps become a clarification, never an apply."""
    from aec_data import nlauthor  # type: ignore
    recipes = _llm_recipes()
    plan: list[dict] = []
    errors: list[str] = []
    for step in steps or []:
        recipe = (step or {}).get("recipe")
        spec = recipes.get(recipe)
        if spec is None:
            errors.append(f"unknown or unavailable recipe {recipe!r}")
            continue
        params = _fill_context(recipe, _coerce_params((step or {}).get("params")), spec, ctx)
        call = nlauthor.validate_call(recipe, params)
        if call["ok"]:
            call["summary"] = nlauthor._summary(call)
            plan.append(call)
        else:
            errors.append(f"{recipe}: {'; '.join(call['errors'])}")
    if not plan:
        return {"source": "claude", "plan": [],
                "needs_clarification": "; ".join(errors) or "I couldn't turn that into an authoring step."}
    # partial success still surfaces what was dropped, but returns the usable steps
    return {"source": "claude", "plan": plan,
            "needs_clarification": ("some steps were skipped — " + "; ".join(errors)) if errors else None}


# Strict structured outputs require additionalProperties:false on EVERY object, which can't express the
# per-recipe `params` object (its keys vary by recipe). So `params` is a JSON STRING the model fills and
# `_coerce_params` parses — keeping every object in the schema closed.
_PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["steps", "clarification"],
    "properties": {
        "steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["recipe", "params"],
            "properties": {
                "recipe": {"type": "string"},
                "params": {"type": "string",
                           "description": "a JSON object of the recipe's parameters, e.g. "
                                          '{"start":[0,0],"end":[5,0],"height":3}'}}}},
        "clarification": {"type": "string",
                          "description": "empty string unless the request is too vague to place geometry"},
    },
}


def _spec_brief() -> str:
    """A compact catalogue of the available recipes + their params for the system prompt."""
    lines = []
    for name, spec in _llm_recipes().items():
        parts = []
        for pn, meta in spec["params"].items():
            # the model never supplies these — they come from the selection/storey server-side
            if meta["type"] in ("guid", "guids") or pn == "storey":
                continue
            req = "required" if meta.get("required") else f"default {meta.get('default')}"
            parts.append(f"{pn}:{meta['type']} ({req})")
        lines.append(f"- {name}: {spec['desc']} params: {', '.join(parts) or '(none)'}")
    return "\n".join(lines)


def _system(ctx: dict) -> str:
    sel = ctx.get("selected_guids") or []
    storey = ctx.get("active_storey")
    return (
        "You convert a builder's plain-English instruction into an ordered authoring PLAN for a BIM model. "
        "Return steps as {recipe, params} using ONLY these recipes:\n" + _spec_brief() + "\n\n"
        "Each step's `params` is a JSON STRING — a JSON object of that recipe's parameters, e.g. "
        '"{\\"start\\":[0,0],\\"end\\":[5,0],\\"height\\":3}". '
        "Rules: coordinates are [Easting, Northing] pairs in METRES; lengths/heights/thicknesses are in "
        "metres (convert feet/inches/mm yourself). Emit one step per element (e.g. a room of 4 walls = 4 "
        "add_wall steps). Do NOT output GUIDs, the `storey`, or any host/target element id — the app fills "
        "those from the current selection and active level. For door/window/LOD/phase, the target IS the "
        f"current selection ({len(sel)} element(s) selected). Active level: {storey or 'none set'}. "
        "If the instruction is too vague to place geometry, return an empty steps list and put a short "
        "question in `clarification`. Never delete anything.")


def _llm_plan(text: str, ctx: dict) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"), timeout=60.0, max_retries=1)
    resp = client.messages.create(
        model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=2048,
        system=_system(ctx), messages=[{"role": "user", "content": (text or "")[:2000]}],
        output_config={"format": {"type": "json_schema", "schema": _PLAN_SCHEMA}, "effort": "low"})
    out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    data = json.loads(out)
    result = _steps_to_plan(data.get("steps") or [], ctx)
    if not result["plan"] and data.get("clarification"):
        result["needs_clarification"] = data["clarification"]
    return result


def plan(text: str, context: dict | None = None) -> dict:
    """Interpret `text` into a validated authoring plan. Claude when a key is set (multi-step, natural),
    else the deterministic keyword baseline. Any LLM failure falls back to keyword — never an error."""
    from aec_data import nlauthor  # type: ignore
    ctx = context or {}
    if not ai_enabled():
        return nlauthor.interpret(text, ctx)
    try:
        return _llm_plan(text, ctx)
    except Exception as e:  # noqa: BLE001 — degrade to the offline parser, never 500
        _log.warning("LLM authoring failed (%s) — keyword fallback", e)
        return nlauthor.interpret(text, ctx)
