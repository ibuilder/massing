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
MAX_STYLES = 60
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# ── R21-VG-OVERRIDES: object styles — CUT vs PROJECTION ──────────────────────────────────────────
# The single distinction that separates a drawing from a dump. The same element draws two ways in one
# view: heavy where the view plane cuts it, light where it is merely seen beyond the cut. Colour alone
# — which is all this module carried before — cannot express that, because it is not a colour
# difference. It is a LINE WEIGHT difference, and it is the first thing a reader's eye uses to read
# depth off a flat sheet.
#
# Weights are millimetres ON THE SHEET. Same reasoning as the hatch patterns in `drawings.py`: pen
# weight is a paper-space property, so a wall reads with the same weight at 1:100 and at 1:10.
LINE_PATTERNS = ("solid", "dashed", "dotted", "dash_dot", "hidden", "center")
MIN_WEIGHT, MAX_WEIGHT = 0.05, 4.0
_APPLIES = ("both", "cut", "projection")

# Category defaults, cut heavier than projection in every case. Grouped by what a drafter actually
# distinguishes: structure reads heaviest, then enclosure, then fittings, then annotation-weight stuff.
_STYLE_GROUPS: dict[str, tuple[float, float]] = {
    "structure": (0.70, 0.25),
    "enclosure": (0.50, 0.18),
    "interior": (0.35, 0.13),
    "opening": (0.35, 0.18),
    "mep": (0.25, 0.13),
    "site": (0.25, 0.10),
    "other": (0.35, 0.13),
}
_CLASS_GROUP: dict[str, str] = {
    "ifcfooting": "structure", "ifcpile": "structure", "ifccolumn": "structure",
    "ifcbeam": "structure", "ifcslab": "structure", "ifcmember": "structure",
    "ifcplate": "structure", "ifcreinforcingbar": "structure",
    "ifcwall": "enclosure", "ifcwallstandardcase": "enclosure", "ifccurtainwall": "enclosure",
    "ifcroof": "enclosure",
    "ifcdoor": "opening", "ifcwindow": "opening",
    "ifccovering": "interior", "ifcfurnishingelement": "interior", "ifcfurniture": "interior",
    "ifcrailing": "interior", "ifcstair": "interior", "ifcstairflight": "interior",
    "ifcramp": "interior", "ifcspace": "interior",
    "ifcductsegment": "mep", "ifcductfitting": "mep", "ifcpipesegment": "mep",
    "ifcpipefitting": "mep", "ifcflowterminal": "mep", "ifccablecarriersegment": "mep",
    "ifcairterminal": "mep", "ifcsanitaryterminal": "mep", "ifclightfixture": "mep",
    "ifcsite": "site", "ifcgeographicelement": "site",
}


def default_style(ifc_class: str) -> dict[str, Any]:
    """The out-of-the-box graphics for a category: cut weight, projection weight, colour, pattern.

    An unrecognised class gets the neutral "other" group rather than the heaviest one — guessing heavy
    would make an unfamiliar element shout on every sheet it appears in.
    """
    grp = _CLASS_GROUP.get(str(ifc_class or "").lower(), "other")
    cut_w, proj_w = _STYLE_GROUPS[grp]
    return {"group": grp,
            "cut": {"weight": cut_w, "color": "#111111", "pattern": "solid", "halftone": False},
            "projection": {"weight": proj_w, "color": "#444444", "pattern": "solid",
                           "halftone": False}}


def _norm_override(o: Any, where: str) -> dict[str, Any]:
    """A graphic override is a PARTIAL: it names only what it changes.

    This is load-bearing. A rule that sets colour alone must leave weight and pattern exactly as the
    object style had them — if an override were a full replacement, every colour rule would silently
    flatten the cut/projection weight distinction it knows nothing about, which is the whole feature.
    """
    # only None means "not set". An explicitly-supplied {} is a caller who thinks they configured
    # something and did not, so it must reach the "sets nothing" refusal below rather than short-circuit
    # to an empty override that is silently stored and silently does nothing.
    if o is None:
        return {}
    if not isinstance(o, dict):
        raise QueryError(f"{where} must be an object")
    out: dict[str, Any] = {}
    if "color" in o and o["color"] is not None:
        col = str(o["color"]).strip()
        if not _HEX.match(col):
            raise QueryError(f"{where}.color must be #rrggbb (got {col!r})")
        out["color"] = col.lower()
    if "weight" in o and o["weight"] is not None:
        try:
            w = float(o["weight"])
        except (TypeError, ValueError):
            raise QueryError(f"{where}.weight must be a number (mm)") from None
        if not (MIN_WEIGHT <= w <= MAX_WEIGHT):
            raise QueryError(f"{where}.weight must be {MIN_WEIGHT}–{MAX_WEIGHT} mm (got {w})")
        out["weight"] = round(w, 3)
    if "pattern" in o and o["pattern"] is not None:
        p = str(o["pattern"]).strip().lower()
        if p not in LINE_PATTERNS:
            raise QueryError(f"{where}.pattern must be one of {list(LINE_PATTERNS)} (got {p!r})")
        out["pattern"] = p
    if "halftone" in o and o["halftone"] is not None:
        out["halftone"] = bool(o["halftone"])
    if not out:
        raise QueryError(f"{where} sets nothing — omit it instead of storing an empty override")
    return out


def _norm_styles(styles: Any) -> dict[str, dict]:
    if styles in (None, {}):
        return {}
    if not isinstance(styles, dict) or len(styles) > MAX_STYLES:
        raise QueryError(f"object_styles must be an object (max {MAX_STYLES} categories)")
    out: dict[str, dict] = {}
    for cls, spec in styles.items():
        key = str(cls or "").strip().lower()
        if not key:
            raise QueryError("object_styles keys must be IFC class names")
        if not isinstance(spec, dict):
            raise QueryError(f"object_styles[{key}] must be an object")
        entry = {}
        for side in ("cut", "projection"):
            if spec.get(side) is not None:
                entry[side] = _norm_override(spec[side], f"object_styles[{key}].{side}")
        if not entry:
            raise QueryError(f"object_styles[{key}] must set cut and/or projection")
        out[key] = entry
    return out


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
        r = r or {}
        sel = str(r.get("selector") or "").strip()
        if not sel or len(sel) > MAX_SELECTOR_LEN:
            raise QueryError("every color rule needs a selector (bounded)")
        query_dsl.parse(sel)
        # R21-VG-OVERRIDES: a rule may now override weight/pattern/halftone as well as colour, and may
        # scope itself to the cut or the projection side. `color` stays REQUIRED and keeps its exact
        # old meaning so every template saved before this change still validates and still resolves
        # identically — the new expressiveness is additive.
        col = str(r.get("color") or "").strip()
        if not _HEX.match(col):
            raise QueryError(f"color must be #rrggbb (got {col!r})")
        applies = str(r.get("applies") or "both").strip().lower()
        if applies not in _APPLIES:
            raise QueryError(f"applies must be one of {list(_APPLIES)} (got {applies!r})")
        rule = {"selector": sel, "color": col.lower(), "applies": applies}
        extra = _norm_override({k: r[k] for k in ("weight", "pattern", "halftone") if k in r},
                               "rule") if any(k in r for k in ("weight", "pattern", "halftone")) else {}
        rule.update(extra)
        clean_rules.append(rule)
    styles = _norm_styles(t.get("object_styles"))
    if not hide and not isolate and not clean_rules and not styles:
        raise QueryError("a template needs at least one of hide_classes / isolate / rules / "
                         "object_styles")
    return {"id": str(t.get("id") or uuid.uuid4().hex[:12])[:40], "name": name,
            "hide_classes": hide, "isolate": isolate, "rules": clean_rules,
            "object_styles": styles}


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


def graphics(idx: dict[str, dict] | None, template: dict, cut_guids: set[str] | None = None,
             limit: int = 200000) -> dict[str, Any]:
    """Resolve the FULL graphic state of every visible element: weight, colour, pattern, halftone —
    separately for the cut side and the projection side.

    Precedence, lowest to highest:

    1. the category default (`default_style`) — cut heavy, projection light;
    2. the template's `object_styles` for that category;
    3. the template's rules in order, later winning, each applied only to the side it declares.

    Every layer above the first is a PARTIAL. A rule that names only a colour changes only the colour
    and leaves the weight the object style gave it. Treating an override as a full replacement would
    make any colour rule silently erase the cut/projection weight difference for everything it touched
    — which is precisely the distinction this exists to express.

    `cut_guids` names the elements the view plane actually cuts. When it is None nothing is cut, which
    is the honest answer for a 3D view: the cut side is still resolved and reported so a caller can
    apply it later, but no element is claimed to be cut.
    """
    idx = idx or {}
    base = resolve(idx, template)
    styles = template.get("object_styles") or {}
    cut_set = cut_guids or set()

    # rule → matching guids, evaluated once per rule rather than once per element
    rule_hits: list[tuple[dict, set[str]]] = []
    for rule in (template.get("rules") or []):
        hits = set(query_dsl.select(idx, rule["selector"], limit=limit)["guids"])
        rule_hits.append((rule, hits))

    out: dict[str, dict] = {}
    for g in base["visible"]:
        cls = str((idx.get(g) or {}).get("ifc_class") or "").lower()
        style = default_style(cls)
        sides = {"cut": dict(style["cut"]), "projection": dict(style["projection"])}
        for side in ("cut", "projection"):
            sides[side].update((styles.get(cls) or {}).get(side) or {})
        for rule, hits in rule_hits:
            if g not in hits:
                continue
            patch = {k: v for k, v in rule.items()
                     if k in ("color", "weight", "pattern", "halftone")}
            for side in ("cut", "projection"):
                if rule["applies"] in ("both", side):
                    sides[side].update(patch)
        out[g] = {"group": style["group"], "cut": sides["cut"], "projection": sides["projection"],
                  "is_cut": g in cut_set}

    return {"template": template["id"], "name": template.get("name"),
            "visible_count": base["visible_count"], "hidden_count": base["hidden_count"],
            "cut_count": sum(1 for g in out if out[g]["is_cut"]),
            "graphics": out,
            "note": "Cut lines are heavier than projection lines — that weight difference, not "
                    "colour, is how a reader reads depth off a flat sheet. Overrides layer as "
                    "partials, so a colour rule never flattens the weights beneath it."}
