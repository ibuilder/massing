"""VIEW-TEMPLATES (R18) — reusable, layered view presets over the model: a per-template **class
visibility matrix** (`hide_classes`), an optional **isolate scope** (QUERY-DSL), and stacked **color
rules** (selector → hex, later rules win) — the graphics-override layer desktop authoring suites call
a view template, built on the same QUERY-DSL spine as smart views and the rule library.

The whole point is determinism: ``resolve(idx, template)`` maps the same template + the same model to
the SAME visible/hidden/color sets every time (sorted, capped, no ambient state), so the viewer, the
drawing generators, and a test can all consume one answer. Storage is a per-project JSON blob (like
smart views / the rule library) — validated atomically, bounded, no migration.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from . import query_dsl, storage
from .query_dsl import QueryError

_KEY = "{pid}/view_templates.json"
MAX_TEMPLATES = 100
MAX_RULES = 20
MAX_HIDE_CLASSES = 100
MAX_SELECTOR_LEN = 500
MAX_NAME_LEN = 120
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _norm(t: dict) -> dict:
    """Validate + normalize one template. Raises QueryError on anything malformed."""
    if not isinstance(t, dict):
        raise QueryError("each template must be an object")
    name = (str(t.get("name") or "Template").strip() or "Template")[:MAX_NAME_LEN]
    hide = t.get("hide_classes") or []
    if not isinstance(hide, list) or len(hide) > MAX_HIDE_CLASSES:
        raise QueryError(f"hide_classes must be a list (max {MAX_HIDE_CLASSES})")
    hide = [str(h).strip() for h in hide if str(h).strip()]
    isolate = str(t.get("isolate") or "").strip() or None
    if isolate:
        if len(isolate) > MAX_SELECTOR_LEN:
            raise QueryError(f"isolate selector too long (max {MAX_SELECTOR_LEN})")
        query_dsl.parse(isolate)
    rules = t.get("rules") or []
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise QueryError(f"rules must be a list (max {MAX_RULES})")
    clean_rules = []
    for r in rules:
        sel = str((r or {}).get("selector") or "").strip()
        col = str((r or {}).get("color") or "").strip()
        if not sel or len(sel) > MAX_SELECTOR_LEN:
            raise QueryError("every color rule needs a selector (bounded)")
        query_dsl.parse(sel)
        if not _HEX.match(col):
            raise QueryError(f"color must be #rrggbb (got {col!r})")
        clean_rules.append({"selector": sel, "color": col.lower()})
    if not hide and not isolate and not clean_rules:
        raise QueryError("a template needs at least one of hide_classes / isolate / rules")
    return {"id": str(t.get("id") or uuid.uuid4().hex[:12])[:40], "name": name,
            "hide_classes": hide, "isolate": isolate, "rules": clean_rules}


def load(pid: str) -> list[dict]:
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("templates", [])
    except Exception:                                     # noqa: BLE001 — absent blob = none saved
        return []


def save(pid: str, templates: list[dict]) -> list[dict]:
    if not isinstance(templates, list) or len(templates) > MAX_TEMPLATES:
        raise QueryError(f"templates must be a list (max {MAX_TEMPLATES})")
    clean = [_norm(t) for t in templates]
    if len({t["id"] for t in clean}) != len(clean):
        raise QueryError("duplicate template ids")
    storage.put(_KEY.format(pid=pid), json.dumps({"templates": clean}).encode("utf-8"))
    return clean


def resolve(idx: dict[str, dict] | None, template: dict) -> dict[str, Any]:
    """Deterministically resolve a template against the property index → sorted visible / hidden GUID
    lists + the color map (later rules win). Same template + same index = same answer, always."""
    idx = idx or {}
    hide = {h.lower() for h in (template.get("hide_classes") or [])}
    isolate = template.get("isolate")
    scope = set(query_dsl.select(idx, isolate, limit=200000)["guids"]) if isolate else set(idx)

    visible, hidden = [], []
    for g in sorted(idx):
        cls = str((idx.get(g) or {}).get("ifc_class") or "").lower()
        if g in scope and cls not in hide:
            visible.append(g)
        else:
            hidden.append(g)

    colors: dict[str, str] = {}
    vis = set(visible)
    for rule in (template.get("rules") or []):            # later rules override earlier ones
        for g in query_dsl.select(idx, rule["selector"], limit=200000)["guids"]:
            if g in vis:
                colors[g] = rule["color"]

    return {"template": template["id"], "name": template.get("name"),
            "visible": visible, "hidden_count": len(hidden),
            "visible_count": len(visible), "colors": colors, "colored_count": len(colors),
            "note": "Deterministic: the same template + the same model resolves to the same "
                    "visible/hidden/color sets — the viewer and the drawing generators consume one answer."}
