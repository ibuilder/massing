"""Preconstruction intelligence (optional AI): review an incoming contract for risky clauses, find
scope gaps in specs/notes, and answer questions about a document with source citations.

Mirrors ai.py: uses Claude when ANTHROPIC_API_KEY is set, otherwise a deterministic rules engine so
the feature works fully offline (never fabricates — the fallback only flags language it actually
matched). This is the "generate contracts" platform learning to *review* incoming ones."""
from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

from . import settings_store
from .ai import ai_enabled

_log = logging.getLogger("aec.review")

SEVERITY = ("high", "medium", "low")
# bound the regex/scan work on very large uploads (the global body cap allows big files; a contract
# is small — cap the analysed text so a huge PDF can't drive CPU). ~800k chars ≈ a long spec manual.
_MAX_REVIEW_CHARS = 800_000


# --- text extraction ---------------------------------------------------------
def extract_text(data: bytes, filename: str = "") -> list[dict]:
    """→ [{page, text}] for a PDF (per page, for citations) or a single page for plain text."""
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, pg in enumerate(reader.pages):
                try:
                    pages.append({"page": i + 1, "text": pg.extract_text() or ""})
                except Exception:                       # noqa: BLE001 — skip an unreadable page
                    pages.append({"page": i + 1, "text": ""})
            return pages
        except Exception as e:                           # noqa: BLE001
            _log.warning("PDF text extraction failed (%s)", e)
            return []
    # plain text / other → one page
    try:
        return [{"page": 1, "text": data.decode("utf-8", "ignore")}]
    except Exception:                                    # noqa: BLE001
        return []


def _full_text(pages: list[dict]) -> str:
    return "\n\n".join(p["text"] for p in pages if p.get("text"))


def _sentence_around(text: str, idx: int, span: int = 240) -> str:
    lo = max(0, idx - span // 2)
    hi = min(len(text), idx + span // 2)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


# --- contract risk review ----------------------------------------------------
# (pattern, severity, category, why it matters, suggested position) — the offline reviewer's
# knowledge base of commonly-negotiated GC/subcontract risk terms.
_RISK_PATTERNS: list[tuple[str, str, str, str, str]] = [
    (r"pay[\s-]*if[\s-]*paid", "high", "Payment",
     "Pay-if-paid makes owner non-payment the subcontractor's risk (contingent payment).",
     "Push for pay-when-paid (timing only) or strike; unenforceable in many states."),
    (r"pay[\s-]*when[\s-]*paid", "medium", "Payment",
     "Pay-when-paid can defer payment indefinitely if not time-bounded.",
     "Cap the delay to a reasonable period regardless of owner payment."),
    (r"no[\s-]*damage[s]?[\s-]*for[\s-]*delay", "high", "Delay",
     "No-damage-for-delay bars delay-cost recovery even for owner-caused delay.",
     "Add carve-outs for owner/AE-caused, concurrent, and unreasonable delays."),
    (r"liquidated damages", "medium", "Delay",
     "Liquidated damages set a fixed daily penalty for late completion.",
     "Confirm the rate is a reasonable estimate, add a cap and a mutual bonus."),
    (r"indemnif", "medium", "Indemnity",
     "Broad indemnity can require covering the other party's own negligence.",
     "Limit to comparative fault; check anti-indemnity statutes in the state."),
    (r"terminat\w+ for convenience", "medium", "Termination",
     "Termination for convenience lets the owner cancel at will.",
     "Ensure recovery of costs incurred + reasonable close-out and demob."),
    (r"sole (?:and absolute )?discretion", "medium", "Discretion",
     "'Sole discretion' gives one party unilateral, unreviewable decisions.",
     "Change to 'reasonable discretion' / an objective standard."),
    (r"waiv\w+ of (?:mechanic'?s? )?lien|lien waiver", "medium", "Lien",
     "Upfront or broad lien waivers can waive rights before payment is received.",
     "Waive only for amounts actually paid; use conditional waivers."),
    (r"consequential damages", "medium", "Damages",
     "Consequential-damage exposure can dwarf the contract value.",
     "Add a mutual waiver of consequential damages."),
    (r"flow[\s-]*down|incorporat\w+ by reference", "low", "Flow-down",
     "Flow-down binds you to prime-contract terms you may not have seen.",
     "Request the prime contract; limit flow-down to scope/technical terms."),
    (r"back[\s-]*charge", "medium", "Backcharge",
     "Unilateral back-charges can be deducted without agreement.",
     "Require written notice + opportunity to cure before any back-charge."),
    (r"retainage|retention", "low", "Payment",
     "Retainage withholds a % of each payment until the end.",
     "Confirm the %, reduction at 50%, and separate release for stored materials."),
    (r"time is of the essence", "low", "Schedule",
     "'Time is of the essence' strengthens strict-deadline enforcement.",
     "Acceptable if the schedule and float are realistic and defined."),
    (r"as[\s-]*is\b", "medium", "Warranty",
     "'As-is' can disclaim warranties or shift existing-condition risk.",
     "Add a differing-site-conditions clause and reasonable warranties."),
    (r"warrant\w+", "low", "Warranty",
     "Warranty terms define the correction period and obligations.",
     "Confirm a standard 1-year period and clear start (substantial completion)."),
    (r"differing site conditions", "low", "Site",
     "A differing-site-conditions clause is favorable — verify it exists.",
     "Keep it; ensure prompt notice mechanics are workable."),
]


def _review_rules(text: str) -> dict[str, Any]:
    findings = []
    seen: set[str] = set()
    for pat, sev, cat, why, action in _RISK_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if not m or cat in seen and sev == "low":
            continue
        seen.add(cat)
        findings.append({
            "clause": cat, "severity": sev, "category": cat, "rationale": why,
            "suggested_action": action, "snippet": _sentence_around(text, m.start()),
        })
    order = {s: i for i, s in enumerate(SEVERITY)}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY}
    return {"findings": findings, "counts": counts, "source": "rules",
            "message": ("Reviewed with the built-in clause library. Set an Anthropic API key in "
                        "Settings for full AI review of the whole document." if findings else
                        "No commonly-risky clauses matched — a full AI review may still find nuanced terms.")}


_REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["findings"],
    "properties": {
        "findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["clause", "severity", "category", "rationale", "suggested_action", "snippet"],
            "properties": {
                "clause": {"type": "string"}, "severity": {"type": "string", "enum": list(SEVERITY)},
                "category": {"type": "string"}, "rationale": {"type": "string"},
                "suggested_action": {"type": "string"}, "snippet": {"type": "string"},
            }}}}}

_REVIEW_SYSTEM = (
    "You are a senior construction contracts manager reviewing an incoming contract on behalf of the "
    "general contractor or subcontractor. Identify clauses that create commercial/legal risk or shift "
    "risk unfavorably (payment, indemnity, delay, termination, warranty, insurance, liens, LDs, scope). "
    "For each, give the clause name, a severity (high/medium/low), the category, a one-sentence rationale, "
    "a concise suggested redline/negotiating position, and the exact snippet from the text. Only flag "
    "language actually present; do not invent clauses.")


def review_contract(text: str) -> dict[str, Any]:
    body = (text or "").strip()[:_MAX_REVIEW_CHARS]
    if not body:
        return {"findings": [], "counts": dict.fromkeys(SEVERITY, 0), "source": "empty",
                "message": "No contract text — upload a contract PDF or paste its text."}
    if ai_enabled():
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=8192,
                system=_REVIEW_SYSTEM, messages=[{"role": "user", "content": body[:120000]}],
                output_config={"format": {"type": "json_schema", "schema": _REVIEW_SCHEMA}, "effort": "medium"})
            out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(out)
            fnd = data.get("findings", [])
            order = {s: i for i, s in enumerate(SEVERITY)}
            fnd.sort(key=lambda f: order.get(f.get("severity"), 9))
            return {"findings": fnd, "counts": {s: sum(1 for f in fnd if f.get("severity") == s) for s in SEVERITY},
                    "source": "claude"}
        except Exception as e:                           # noqa: BLE001 — fall back to the rules engine
            _log.warning("AI contract review failed (%s) — using rules", e)
    return _review_rules(body)


# --- scope-gap detection -----------------------------------------------------
# ambiguity/gap markers that commonly hide missing or conflicting scope
_GAP_MARKERS: list[tuple[str, str]] = [
    (r"\bby others\b", "Work assigned 'by others' — confirm it is truly out of your scope."),
    (r"\bn\.?i\.?c\.?\b|not in contract", "'Not in contract' — verify the exclusion is intended and priced."),
    (r"\bto be determined\b|\btbd\b", "'TBD' — undefined scope; price an allowance or RFI it."),
    (r"\bas required\b", "'As required' — open-ended obligation; bound the quantity/extent."),
    (r"\bor equal\b|\bor approved equal\b", "'Or equal' — substitution latitude; confirm acceptance basis."),
    (r"\ballowance\b", "Allowance item — carries scope + cost risk if under-defined."),
    (r"\bverify in field\b|\bvif\b", "'Verify in field' — field-condition risk shifted to the trade."),
    (r"\bcoordinate with\b", "'Coordinate with' — interface scope; define who provides/installs."),
    (r"\bmatch existing\b", "'Match existing' — undefined standard; document the reference."),
    (r"\bcomplete\b.*\boperational\b|turnkey", "'Turnkey/complete & operational' — broad catch-all scope."),
]


def _scope_rules(text: str) -> dict[str, Any]:
    gaps = []
    for pat, note in _GAP_MARKERS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            gaps.append({"marker": re.sub(r"\s+", " ", m.group(0)).strip(), "note": note,
                         "snippet": _sentence_around(text, m.start())})
            break                                        # one example per marker
    return {"gaps": gaps, "source": "rules",
            "message": ("Flagged ambiguous-scope language with the built-in markers. Set an Anthropic "
                        "API key for AI gap + conflict detection across the full spec." if gaps else
                        "No ambiguous-scope markers found in this text.")}


_SCOPE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["gaps"],
    "properties": {"gaps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["marker", "note", "snippet"],
        "properties": {"marker": {"type": "string"}, "note": {"type": "string"}, "snippet": {"type": "string"}}}}}}

_SCOPE_SYSTEM = (
    "You review construction specs and drawing notes for scope gaps and conflicts before pricing. "
    "Identify missing scope, ambiguous responsibility ('by others', 'as required', 'TBD'), and any "
    "conflicts between requirements. For each, give a short marker/title, a one-sentence note on the "
    "risk, and the snippet. Only flag issues supported by the text.")


def scope_gaps(text: str) -> dict[str, Any]:
    body = (text or "").strip()[:_MAX_REVIEW_CHARS]
    if not body:
        return {"gaps": [], "source": "empty", "message": "No text — upload specs/notes or paste them."}
    if ai_enabled():
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
            resp = client.messages.create(
                model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=6144,
                system=_SCOPE_SYSTEM, messages=[{"role": "user", "content": body[:120000]}],
                output_config={"format": {"type": "json_schema", "schema": _SCOPE_SCHEMA}, "effort": "medium"})
            out = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            data = json.loads(out)
            data["source"] = "claude"
            return data
        except Exception as e:                           # noqa: BLE001
            _log.warning("AI scope-gap detection failed (%s) — using rules", e)
    return _scope_rules(body)


# --- document Q&A with citations ---------------------------------------------
def _rank_pages(pages: list[dict], question: str, k: int = 4) -> list[dict]:
    terms = [t for t in re.findall(r"[a-z0-9]+", question.lower()) if len(t) > 2]
    scored = []
    for p in pages:
        low = (p.get("text") or "").lower()
        score = sum(low.count(t) for t in terms)
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:k]]


def ask_doc(question: str, pages: list[dict]) -> dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {"answer": "", "citations": [], "source": "empty", "message": "Ask a question."}
    hits = _rank_pages(pages, q)
    citations = [{"page": p["page"], "snippet": _sentence_around(p["text"],
                  max(0, (p["text"] or "").lower().find(next((t for t in re.findall(r"[a-z0-9]+", q.lower())
                       if len(t) > 2 and t in (p["text"] or "").lower()), "")))), } for p in hits]
    if ai_enabled():
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings_store.get("ANTHROPIC_API_KEY"))
            ctx = "\n\n".join(f"[page {p['page']}]\n{p['text'][:6000]}" for p in hits)
            resp = client.messages.create(
                model=settings_store.get("AEC_AI_MODEL", "claude-opus-4-8"), max_tokens=1500,
                system=("Answer the question using ONLY the provided document excerpts. Cite the page "
                        "number(s) you used inline like (p. 3). If the answer isn't in the excerpts, say so."),
                messages=[{"role": "user", "content": f"Question: {q}\n\nExcerpts:\n{ctx}"}])
            answer = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
            return {"answer": answer.strip(), "citations": citations, "source": "claude"}
        except Exception as e:                           # noqa: BLE001
            _log.warning("AI doc Q&A failed (%s) — using extract", e)
    if not hits:
        return {"answer": "", "citations": [], "source": "rules",
                "message": "No matching passages found for that question in the document."}
    answer = " … ".join(f"(p. {c['page']}) {c['snippet']}" for c in citations)
    return {"answer": answer, "citations": citations, "source": "rules",
            "message": "Showing the most relevant passages. Set an Anthropic API key for a synthesized answer."}
