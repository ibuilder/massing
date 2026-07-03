"""AI drafting assists (optional) — turn source documents into first-draft construction records so
teams stop retyping from PDFs (the report's "18% of project time is spent searching for data").

Mirrors review.py / ai.py: uses Claude when ANTHROPIC_API_KEY is set, otherwise a deterministic
rules engine so it works fully offline and never fabricates — the fallback only extracts language it
actually matched, always with a page citation. Everything here produces an EDITABLE DRAFT for a human
to review before it becomes a record (human-in-the-loop); nothing is auto-submitted.

Reuses review.extract_text (per-page text for citations)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from . import settings_store
from .ai import ai_enabled
from .review import _sentence_around, extract_text  # noqa: F401  (extract_text re-used by the router)

_log = logging.getLogger("aec.drafting")

_MAX_CHARS = 400_000
_DISCIPLINES = ["Architectural", "Structural", "MEP", "Civil", "Geotechnical", "Fire Protection",
                "Low Voltage"]


def _model() -> str:
    return settings_store.get("AEC_AI_MODEL", "claude-opus-4-8")


def _claude_json(system: str, user: str, schema: dict, max_tokens: int = 4096) -> dict:
    """One structured Claude call returning a validated JSON object (raises on any failure)."""
    from anthropic import Anthropic
    client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"), timeout=60.0, max_retries=1)
    resp = client.messages.create(
        model=_model(), max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user[:120000]}],
        output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "medium"})
    out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    return json.loads(out)


# --- RFI drafting ------------------------------------------------------------
_RFI_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["subject", "question", "discipline", "priority"],
    "properties": {
        "subject": {"type": "string"}, "question": {"type": "string"},
        "discipline": {"type": "string", "enum": _DISCIPLINES},
        "spec_section": {"type": "string"}, "priority": {"type": "string",
            "enum": ["Low", "Normal", "High", "Critical"]},
        "suggested_assignee": {"type": "string"}, "background": {"type": "string"}}}

_RFI_SYSTEM = (
    "You are a construction project engineer drafting a clear, specific Request for Information (RFI) "
    "for the design team. From the user's note and any document context, produce a concise subject, a "
    "precise question that can be answered unambiguously, the most likely discipline, a spec section if "
    "one is referenced, and a priority. Reference the drawing/spec/detail if cited. Never invent facts "
    "not supported by the input; if the note is vague, ask the narrower clarifying question.")

_DISC_HINTS = {
    "Structural": r"beam|column|footing|rebar|slab|structural|load|shear|moment|foundation",
    "MEP": r"\bhvac\b|duct|plumb|pipe|electric|conduit|panel|mechanical|fixture|\bvav\b|\bmep\b",
    "Civil": r"grading|storm|sanitary|utility|site\s?work|paving|curb|drainage|civil",
    "Fire Protection": r"sprinkler|fire\s?(?:protection|alarm)|standpipe|\bfp\b",
    "Low Voltage": r"data|security|\bav\b|low\s?voltage|telecom|access control",
    "Geotechnical": r"soil|bearing|geotech|compaction|subgrade",
}


def _rfi_rules(note: str, pages: list[dict]) -> dict[str, Any]:
    low = note.lower()
    disc = next((d for d, pat in _DISC_HINTS.items() if re.search(pat, low)), "Architectural")
    spec = ""
    m = re.search(r"\b(\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?)\b", note) or re.search(
        r"\b(\d{2}\s?\d{2}\s?\d{2})\b", _first_text(pages))
    if m:
        spec = m.group(1)
    cite = _first_citation(pages, note)
    subj = re.sub(r"\s+", " ", note).strip()
    subj = (subj[:70] + "…") if len(subj) > 72 else subj
    return {"subject": subj or "RFI", "question": note.strip()
            + ("\n\nPlease confirm/clarify." if note else "Please clarify."),
            "discipline": disc, "spec_section": spec, "priority": "Normal",
            "suggested_assignee": "", "background": "",
            "citations": cite, "source": "rules",
            "message": "Drafted with the offline template. Set an Anthropic API key in Settings for a "
                       "sharper AI-written RFI."}


def draft_rfi(note: str, pages: list[dict] | None = None) -> dict[str, Any]:
    """Draft an RFI from a short note (+ optional source-document pages for context/citations)."""
    note = (note or "").strip()
    pages = pages or []
    if not note and not pages:
        return {"source": "empty", "message": "Describe the question, or attach the drawing/spec."}
    if ai_enabled():
        try:
            ctx = _context_block(pages)
            data = _claude_json(_RFI_SYSTEM, f"Note: {note}\n\n{ctx}".strip(), _RFI_SCHEMA, 2048)
            data["citations"] = _first_citation(pages, note)
            data["source"] = "claude"
            return data
        except Exception as e:                               # noqa: BLE001
            _log.warning("AI RFI draft failed (%s) — using rules", e)
    return _rfi_rules(note, pages)


# --- submittal summary -------------------------------------------------------
_SUBMITTAL_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "summary"],
    "properties": {
        "title": {"type": "string"}, "spec_section": {"type": "string"},
        "type": {"type": "string"}, "summary": {"type": "string"},
        "key_items": {"type": "array", "items": {"type": "string"}},
        "missing_or_review": {"type": "array", "items": {"type": "string"}}}}

_SUBMITTAL_SYSTEM = (
    "You are a construction submittal reviewer. From the submittal document, produce a short title, the "
    "spec section, the submittal type (product data / shop drawing / sample / etc.), a two-sentence "
    "summary, the key items included, and anything that appears missing or needs the reviewer's "
    "attention relative to a typical submittal for this scope. Only state what the document supports.")


def _submittal_rules(pages: list[dict]) -> dict[str, Any]:
    text = _first_text(pages)
    spec = ""
    m = re.search(r"\b(\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?)\b", text)
    if m:
        spec = m.group(1)
    stype = next((t for t in ("shop drawing", "product data", "sample", "manufacturer", "cut sheet")
                  if t in text.lower()), "")
    head = re.sub(r"\s+", " ", text[:120]).strip()
    return {"title": head or "Submittal", "spec_section": spec, "type": stype.title(),
            "summary": _sentence_around(text, 0, 400) if text else "",
            "key_items": [], "missing_or_review": [],
            "citations": [{"page": p["page"]} for p in pages[:3]], "source": "rules",
            "message": "Extracted with the offline reader. Set an Anthropic API key for a full "
                       "AI summary + completeness check."}


def summarize_submittal(pages: list[dict]) -> dict[str, Any]:
    pages = pages or []
    if not pages or not _first_text(pages):
        return {"source": "empty", "message": "Upload the submittal PDF to summarize."}
    if ai_enabled():
        try:
            data = _claude_json(_SUBMITTAL_SYSTEM, _context_block(pages, 8000), _SUBMITTAL_SCHEMA, 2048)
            data["citations"] = [{"page": p["page"]} for p in pages[:3]]
            data["source"] = "claude"
            return data
        except Exception as e:                               # noqa: BLE001
            _log.warning("AI submittal summary failed (%s) — using rules", e)
    return _submittal_rules(pages)


# --- scope-of-work drafting (the Belidor counter) ----------------------------
_SCOPE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["trade", "inclusions"],
    "properties": {
        "trade": {"type": "string"},
        "inclusions": {"type": "array", "items": {"type": "string"}},
        "exclusions": {"type": "array", "items": {"type": "string"}},
        "clarifications": {"type": "array", "items": {"type": "string"}},
        "spec_sections": {"type": "array", "items": {"type": "string"}}}}

_SCOPE_SYSTEM = (
    "You are a preconstruction estimator writing a clear, trade-by-trade Scope of Work to send to "
    "subcontractors for bidding. For the requested trade, from the plans/specs provided, list the "
    "specific work INCLUDED, work explicitly EXCLUDED (by others), and CLARIFICATIONS/allowances the "
    "bidder must acknowledge. Cite spec sections you rely on. Be specific and buildable; do not invent "
    "scope the documents don't support.")


def _scope_rules(pages: list[dict], trade: str) -> dict[str, Any]:
    text = _first_text(pages)
    specs = sorted(set(re.findall(r"\b(\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?)\b", text)))[:12]
    incl, excl = [], []
    for m in re.finditer(r"([A-Z][^.\n]{15,140}?(?:shall|provide|install|furnish)[^.\n]{0,120})", text):
        incl.append(re.sub(r"\s+", " ", m.group(1)).strip())
        if len(incl) >= 12:
            break
    for pat, note in (("by others", "By others"), ("not in contract", "Not in contract"),
                      ("n.i.c", "N.I.C.")):
        if pat in text.lower():
            excl.append(f"Items marked '{note}' in the documents")
    return {"trade": trade, "inclusions": incl, "exclusions": excl,
            "clarifications": (["Verify all dimensions and quantities in field."] if text else []),
            "spec_sections": specs,
            "citations": [{"page": p["page"]} for p in pages[:3]], "source": "rules",
            "message": "Extracted candidate scope with the offline reader. Set an Anthropic API key for "
                       "a clean, buildable AI-drafted scope."}


def draft_scope(pages: list[dict], trade: str) -> dict[str, Any]:
    pages = pages or []
    trade = (trade or "").strip() or "General"
    if not pages or not _first_text(pages):
        return {"source": "empty", "message": "Upload the plan/spec set to draft a scope."}
    if ai_enabled():
        try:
            data = _claude_json(_SCOPE_SYSTEM, f"Trade: {trade}\n\n{_context_block(pages, 12000)}",
                                _SCOPE_SCHEMA, 3072)
            data.setdefault("trade", trade)
            data["citations"] = [{"page": p["page"]} for p in pages[:3]]
            data["source"] = "claude"
            return data
        except Exception as e:                               # noqa: BLE001
            _log.warning("AI scope draft failed (%s) — using rules", e)
    return _scope_rules(pages, trade)


# --- shared helpers ----------------------------------------------------------
def _first_text(pages: list[dict]) -> str:
    return "\n".join(p.get("text") or "" for p in pages)[:_MAX_CHARS]


def _context_block(pages: list[dict], per_page: int = 4000) -> str:
    if not pages:
        return ""
    return "Document excerpts:\n" + "\n\n".join(
        f"[page {p['page']}]\n{(p.get('text') or '')[:per_page]}" for p in pages[:6] if p.get("text"))


def _first_citation(pages: list[dict], note: str) -> list[dict]:
    terms = [t for t in re.findall(r"[a-z0-9]{3,}", (note or "").lower())]
    for p in pages:
        low = (p.get("text") or "").lower()
        idx = next((low.find(t) for t in terms if t in low), -1)
        if idx >= 0:
            return [{"page": p["page"], "snippet": _sentence_around(p["text"], idx)}]
    return [{"page": p["page"]} for p in pages[:1]]
