"""AI assists (optional). Uses Claude when ANTHROPIC_API_KEY is set; otherwise falls back to a
deterministic template so the feature degrades gracefully with no external dependency.

Currently: draft an RFI (subject / question / discipline / priority) from a selected element's
IFC context — the competitive parity feature (cf. Procore's Draft RFI Agent)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger("aec.ai")

# default to the most capable model; a scoped drafting task runs fine at low effort
_MODEL = os.environ.get("AEC_AI_MODEL", "claude-opus-4-8")
_PRIORITIES = ("low", "normal", "high", "urgent")

_RFI_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "question": {"type": "string"},
        "discipline": {"type": "string"},
        "suggested_priority": {"type": "string", "enum": list(_PRIORITIES)},
    },
    "required": ["subject", "question", "discipline", "suggested_priority"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a senior construction project engineer drafting a Request for Information (RFI) "
    "about a specific building element. Given the element's IFC data and an optional note, "
    "write a concise, professional RFI: a short subject line, a clear question for the design "
    "team, the most likely discipline (Architectural/Structural/MEP/Civil), and a suggested "
    "priority. Be specific to the element; do not invent facts not implied by the data."
)


def ai_enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _element_summary(element: dict[str, Any]) -> str:
    parts = [f"IFC class: {element.get('ifc_class') or 'unknown'}"]
    if element.get("name"):
        parts.append(f"name: {element['name']}")
    if element.get("type_name"):
        parts.append(f"type: {element['type_name']}")
    if element.get("storey"):
        parts.append(f"storey: {element['storey']}")
    psets = element.get("psets") or {}
    for pset, props in list(psets.items())[:4]:
        if isinstance(props, dict):
            kv = ", ".join(f"{k}={v}" for k, v in list(props.items())[:5])
            parts.append(f"{pset}: {kv}")
    return "\n".join(parts)


def _template_draft(element: dict[str, Any], note: str | None) -> dict[str, Any]:
    cls = (element.get("ifc_class") or "Element").replace("Ifc", "")
    name = element.get("name") or cls
    storey = element.get("storey")
    where = f" on {storey}" if storey else ""
    disc = {"Wall": "Architectural", "Slab": "Structural", "Beam": "Structural",
            "Column": "Structural", "Door": "Architectural", "Window": "Architectural",
            "Pipe": "MEP", "Duct": "MEP", "FlowTerminal": "MEP"}.get(cls, "Architectural")
    q = note.strip() if note and note.strip() else (
        f"Please confirm the specification and installation requirements for {name}{where}. "
        f"Clarify any conflicts with adjacent work and the applicable detail.")
    return {"subject": f"RFI: {name}{where}", "question": q,
            "discipline": disc, "suggested_priority": "normal", "source": "template"}


def draft_rfi(element: dict[str, Any], note: str | None = None) -> dict[str, Any]:
    """Return {subject, question, discipline, suggested_priority, source}. Uses Claude when
    configured; on any error (or no key) returns a deterministic template draft."""
    if not ai_enabled():
        return _template_draft(element, note)
    try:
        from anthropic import Anthropic  # lazy: only needed when a key is configured

        client = Anthropic()
        user = "Element:\n" + _element_summary(element)
        if note and note.strip():
            user += f"\n\nEngineer's note: {note.strip()}"
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": _RFI_SCHEMA},
                           "effort": "low"},
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        if data.get("suggested_priority") not in _PRIORITIES:
            data["suggested_priority"] = "normal"
        data["source"] = "claude"
        return data
    except Exception as e:           # noqa: BLE001 — never fail the request over an AI assist
        _log.warning("AI RFI draft failed (%s); using template", e)
        return _template_draft(element, note)
