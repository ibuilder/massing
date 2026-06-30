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


_BOQ_SYSTEM = (
    "You are a senior quantity surveyor / cost estimator. From a plain-language project description, "
    "draft a realistic construction Bill of Quantities: the major trades implied by the scope, each "
    "with a quantity, unit, a market unit rate in USD, and a CSI MasterFormat division. Be "
    "reasonable and conservative; do not invent scope the description doesn't imply."
)
_BOQ_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["description", "quantity", "unit", "rate"],
        "properties": {
            "description": {"type": "string"},
            "quantity": {"type": "number"},
            "unit": {"type": "string"},
            "rate": {"type": "number"},
            "division": {"type": "string"},
        }}}},
}


def estimate_boq(description: str) -> dict[str, Any]:
    """Draft a Bill of Quantities from a plain-text project description. Uses Claude when configured;
    without a key returns a graceful stub so the UI degrades cleanly (no fabricated numbers)."""
    desc = (description or "").strip()
    if not desc:
        return {"lines": [], "total": 0.0, "source": "empty", "message": "Describe the project to draft a BOQ."}
    if not ai_enabled():
        return {"lines": [], "total": 0.0, "source": "disabled",
                "message": "AI estimating isn't configured — set an Anthropic API key in Settings to "
                           "draft a Bill of Quantities from a description."}
    try:
        from anthropic import Anthropic  # lazy: only when a key is configured

        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        msg = (f"Project description:\n{desc}\n\nDraft the Bill of Quantities as JSON.")
        resp = client.messages.create(
            model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=2048,
            system=_BOQ_SYSTEM, messages=[{"role": "user", "content": msg}],
            output_config={"format": {"type": "json_schema", "schema": _BOQ_SCHEMA}, "effort": "low"})
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        lines = data.get("lines", [])
        for ln in lines:
            ln["amount"] = round(float(ln.get("quantity", 0) or 0) * float(ln.get("rate", 0) or 0), 2)
        data["total"] = round(sum(ln.get("amount", 0) for ln in lines), 2)
        data["source"] = "claude"
        return data
    except Exception as e:           # noqa: BLE001 — never fail the request over an AI assist
        _log.warning("AI BOQ draft failed (%s)", e)
        return {"lines": [], "total": 0.0, "source": "error",
                "message": "Couldn't reach the AI service just now — try again shortly."}


# --- spec -> submittal extraction (build the submittal log from a spec book) -------
_SUBMITTAL_TYPES = ["Product Data", "Shop Drawing", "Sample", "Mock-up", "Certificate",
                    "Test Report", "Calculations", "O&M Manual", "Warranty"]
_EXTRACT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "type"],
        "properties": {
            "section_number": {"type": "string"},
            "title": {"type": "string"},
            "type": {"type": "string", "enum": _SUBMITTAL_TYPES},
        }}}},
}
_EXTRACT_SYSTEM = (
    "You read CSI-format construction specification text and extract every required submittal. For each, "
    "return the governing MasterFormat section number (if present, e.g. '03 30 00'), a concise title, and "
    "the submittal type from the allowed set. Pull from the Part 1 'Submittals' article and Part 2 products. "
    "Be exhaustive and conservative — do not invent submittals that aren't required by the text.")


def extract_submittals(text: str) -> dict[str, Any]:
    """Extract a typed submittal list from pasted/uploaded spec text. Uses Claude when configured; falls
    back to a deterministic rules parser so the feature works offline (no fabricated items)."""
    spec = (text or "").strip()
    if not spec:
        return {"items": [], "source": "empty", "message": "Paste spec text to extract submittals."}
    if ai_enabled():
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=4096,
                system=_EXTRACT_SYSTEM, messages=[{"role": "user", "content": spec[:60000]}],
                output_config={"format": {"type": "json_schema", "schema": _EXTRACT_SCHEMA}, "effort": "low"})
            out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(out)
            data["source"] = "claude"
            return data
        except Exception as e:                 # noqa: BLE001 — fall back to rules, never fail the request
            _log.warning("AI submittal extraction failed (%s) — using rules", e)
    # deterministic fallback (also the offline path): reuse the spec parser
    from . import specs
    section = specs.parse_section_number(spec)
    items = specs.parse_required_submittals(spec)
    for it in items:
        if section:
            it["section_number"] = section
    return {"items": items, "source": "rules",
            "message": ("Extracted with the built-in parser. Set an Anthropic API key in Settings for "
                        "AI extraction across a full project manual." if items else
                        "No submittal items found — paste the section's Part 1 'Submittals' article.")}


# --- RFI triage (auto-categorize + ball-in-court + draft response) -----------
_TRIAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["discipline", "category", "urgency", "ball_in_court", "draft_response"],
    "properties": {
        "discipline": {"type": "string"},
        "category": {"type": "string", "enum": ["Design", "Field Condition", "Coordination", "Submittal", "Other"]},
        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
        "ball_in_court": {"type": "string", "enum": ["GC", "Owner", "OwnersRep", "Consultant", "Subcontractor"]},
        "draft_response": {"type": "string"},
    },
}
_TRIAGE_SYSTEM = (
    "You triage construction RFIs. From the RFI's subject/question/discipline, classify it, judge "
    "urgency, name the party whose court the ball is in (who must respond), and draft a concise, "
    "professional response or the question the responder must answer. Be specific and conservative.")


def _triage_template(rfi: dict[str, Any]) -> dict[str, Any]:
    ci = str(rfi.get("cost_impact") or "").lower()
    urgency = "high" if ci in ("yes", "high") else "medium" if ci in ("possible", "maybe") else "low"
    return {"discipline": rfi.get("discipline") or "General",
            "category": "Design", "urgency": urgency, "ball_in_court": "Consultant",
            "draft_response": "Pending design-team review; a formal response will follow.",
            "source": "template"}


def triage_rfi(rfi: dict[str, Any]) -> dict[str, Any]:
    """Categorize an RFI (discipline/category/urgency), name the ball-in-court party, and draft a
    response. Uses Claude when configured; a deterministic template otherwise."""
    if not ai_enabled():
        return _triage_template(rfi)
    try:
        from anthropic import Anthropic  # lazy

        client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
        msg = ("RFI (JSON):\n" + json.dumps({k: rfi.get(k) for k in ("subject", "question", "discipline", "cost_impact", "location")})
               + "\n\nTriage it. Return JSON only.")
        resp = client.messages.create(
            model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=1024,
            system=_TRIAGE_SYSTEM, messages=[{"role": "user", "content": msg}],
            output_config={"format": {"type": "json_schema", "schema": _TRIAGE_SCHEMA}, "effort": "low"})
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        data = json.loads(text)
        data["source"] = "claude"
        return data
    except Exception as e:  # noqa: BLE001 — never fail the request over an AI assist
        _log.warning("AI RFI triage failed (%s); using template", e)
        return _triage_template(rfi)
