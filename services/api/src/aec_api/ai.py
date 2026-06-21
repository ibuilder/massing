"""AI assists (optional). Uses Claude when ANTHROPIC_API_KEY is set; otherwise falls back to a
deterministic template so the feature degrades gracefully with no external dependency.

Currently: draft an RFI (subject / question / discipline / priority) from a selected element's
IFC context — the competitive parity feature (cf. Procore's Draft RFI Agent)."""
from __future__ import annotations

import json
import logging
from typing import Any

from . import settings_store

_log = logging.getLogger("aec.ai")

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
    return bool(settings_store.get("ANTHROPIC_API_KEY"))


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


def _template_risks(kpis: dict[str, Any], cost: dict[str, Any] | None) -> dict[str, Any]:
    """Deterministic rule-based risk read from the dashboard KPIs (no LLM needed)."""
    risks: list[dict[str, str]] = []
    over = (cost or {}).get("projected_over_under")
    if isinstance(over, (int, float)) and over > 0:
        risks.append({"level": "high", "text": f"Forecast is over budget by ${over:,.0f} — review pending change orders and committed costs."})
    if kpis.get("overdue"):
        risks.append({"level": "high", "text": f"{kpis['overdue']} item(s) are overdue and need immediate attention."})
    if kpis.get("pending_change_orders"):
        risks.append({"level": "medium", "text": f"{kpis['pending_change_orders']} change order(s) pending approval may impact cost/schedule."})
    if kpis.get("open_rfis"):
        risks.append({"level": "medium", "text": f"{kpis['open_rfis']} open RFI(s) awaiting response could delay dependent work."})
    if kpis.get("open_safety"):
        risks.append({"level": "high", "text": f"{kpis['open_safety']} open safety item(s) — verify resolution before proceeding."})
    if kpis.get("open_quality"):
        risks.append({"level": "medium", "text": f"{kpis['open_quality']} open quality item(s) (NCR/deficiency/inspection) outstanding."})
    if kpis.get("open_punchlist"):
        risks.append({"level": "low", "text": f"{kpis['open_punchlist']} open punchlist item(s) remain for closeout."})
    headline = ("No material risks flagged — project metrics are within normal ranges."
                if not risks else f"{len(risks)} risk area(s) need attention.")
    return {"headline": headline, "risks": risks, "source": "rules"}


def risk_summary(kpis: dict[str, Any], cost: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project risk read for owner/PM reporting. Uses Claude when configured to write a tighter
    narrative + prioritized risks; otherwise a deterministic rule-based summary."""
    if not ai_enabled():
        return _template_risks(kpis, cost)
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["headline", "risks"],
                  "properties": {
                      "headline": {"type": "string"},
                      "risks": {"type": "array", "items": {
                          "type": "object", "additionalProperties": False,
                          "required": ["level", "text"],
                          "properties": {"level": {"type": "string", "enum": ["low", "medium", "high"]},
                                         "text": {"type": "string"}}}}}}
        msg = ("Project dashboard metrics (JSON):\n" + json.dumps({"kpis": kpis, "cost": cost})
               + "\n\nWrite a concise executive risk summary: a one-line headline and the top "
                 "prioritized risks (level + one sentence each). Base it only on the data.")
        resp = client.messages.create(
            model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=1024,
            system="You are a senior construction project controls analyst writing an owner-facing risk brief.",
            messages=[{"role": "user", "content": msg}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"})
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        data["source"] = "claude"
        return data
    except Exception as e:           # noqa: BLE001
        _log.warning("AI risk summary failed (%s); using rules", e)
        return _template_risks(kpis, cost)


_ASK_SYSTEM = (
    "You are an assistant embedded in an AEC project platform. Answer the user's question about "
    "THIS project using only the supplied JSON snapshot (dashboard KPIs, cost, open items, model "
    "metrics). Be concise and concrete — cite the numbers. If the snapshot doesn't contain the "
    "answer, say so plainly and suggest where in the app to look. Never invent figures."
)


def ask(question: str, context: dict[str, Any]) -> dict[str, Any]:
    """Natural-language Q&A grounded in a project snapshot. Uses Claude when configured; without a
    key it returns the snapshot so the user still gets the underlying data (graceful degradation)."""
    if not ai_enabled():
        return {"answer": "The AI assistant isn't configured yet — set an Anthropic API key in "
                          "Settings to ask questions in plain English. Meanwhile, here is the "
                          "current project snapshot the assistant would use.",
                "snapshot": context, "source": "disabled"}
    try:
        from anthropic import Anthropic  # lazy: only when a key is configured

        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        msg = ("Project snapshot (JSON):\n" + json.dumps(context, default=str)
               + f"\n\nQuestion: {question.strip()}\n\nAnswer using only this data.")
        resp = client.messages.create(
            model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=1024,
            system=_ASK_SYSTEM, messages=[{"role": "user", "content": msg}],
            output_config={"effort": "low"})
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return {"answer": text.strip(), "source": "claude"}
    except Exception as e:           # noqa: BLE001 — never fail the request over an AI assist
        _log.warning("AI ask failed (%s)", e)
        return {"answer": "Couldn't reach the AI service just now. Here is the project snapshot.",
                "snapshot": context, "source": "error"}


def draft_rfi(element: dict[str, Any], note: str | None = None) -> dict[str, Any]:
    """Return {subject, question, discipline, suggested_priority, source}. Uses Claude when
    configured; on any error (or no key) returns a deterministic template draft."""
    if not ai_enabled():
        return _template_draft(element, note)
    try:
        from anthropic import Anthropic  # lazy: only needed when a key is configured

        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        model = settings_store.get("AEC_AI_MODEL", "claude-opus-4-8")
        user = "Element:\n" + _element_summary(element)
        if note and note.strip():
            user += f"\n\nEngineer's note: {note.strip()}"
        resp = client.messages.create(
            model=model,
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
