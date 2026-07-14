"""IFC5-style non-destructive property-override layers (Wave 9 · W9-3).

IFC5's model is compositional: multiple authors contribute independent, non-destructive *layers* that
compose into a final result (USD-inspired). This engine brings that to our data layer TODAY — without
waiting on the upstream IFC5 geometry alpha. A project holds an ordered stack of named layers; each layer
carries property overrides `{guid, pset, prop, value}`. They compose over the base model **without
mutating the IFC** until explicitly baked: the strongest (highest) enabled layer that sets a given
`(guid, pset, prop)` wins; disagreements across enabled layers surface as conflicts (the data-world twin
of clash detection). Resolution is pure — it takes the stack + an optional base-value lookup.

Stack shape: `{"layers": [{"name": str, "enabled": bool, "overrides": [{guid, pset, prop, value}]}]}`
(index 0 = weakest/base-most, last = strongest).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _key(o: dict) -> tuple[str, str, str]:
    return (o["guid"], o["pset"], o["prop"])


def resolve(layers: list[dict], base_lookup: Callable[[str, str, str], Any] | None = None) -> dict[str, Any]:
    """Compose the enabled layers into effective values with provenance + conflicts. `base_lookup`
    (guid, pset, prop) -> current model value (or None) annotates each override with what it overrides."""
    setters: dict[tuple[str, str, str], list[dict]] = {}
    for i, layer in enumerate(layers):
        if not layer.get("enabled", True):
            continue
        name = layer.get("name") or f"Layer {i + 1}"
        for o in layer.get("overrides", []):
            if not (o.get("guid") and o.get("pset") and o.get("prop")):
                continue
            setters.setdefault(_key(o), []).append({"layer": name, "value": o.get("value")})

    overrides: list[dict] = []
    conflicts: list[dict] = []
    for (guid, pset, prop), s in setters.items():
        winner = s[-1]                                   # highest enabled layer wins
        base = base_lookup(guid, pset, prop) if base_lookup else None
        row = {"guid": guid, "pset": pset, "prop": prop, "base": base,
               "effective": winner["value"], "winning_layer": winner["layer"],
               "setters": [x["layer"] for x in s]}
        overrides.append(row)
        if len({str(x["value"]) for x in s}) > 1:        # >1 enabled layer disagrees
            conflicts.append({**row, "values": [{"layer": x["layer"], "value": x["value"]} for x in s]})

    summary = [{"name": layer.get("name") or f"Layer {i + 1}",
                "enabled": bool(layer.get("enabled", True)),
                "overrides": len(layer.get("overrides", []))}
               for i, layer in enumerate(layers)]
    return {"layers": summary, "overrides": overrides, "conflicts": conflicts,
            "effective_count": len(overrides), "conflict_count": len(conflicts)}


def bake_overrides(layers: list[dict]) -> list[dict]:
    """The resolved effective overrides to write into the IFC when baking the composition (top wins)."""
    return [{"guid": o["guid"], "pset": o["pset"], "prop": o["prop"], "value": o["effective"]}
            for o in resolve(layers)["overrides"]]
