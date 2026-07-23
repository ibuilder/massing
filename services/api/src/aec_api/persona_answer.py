"""PERSONA-ANSWER (R17 Sprint A) — persona lenses + a structured envelope over a CitedAnswer.

The same data answers differently for different seats: an **exec** wants two sentences and the risk; a
**pm** wants the breakdown; a **field** user wants one short line. This shapes a `CitedAnswer` (see
`cited_answer.py`) into `{answer, insight, follow_ups, persona}` — the *insight* is a one-line plain-English
read and the *follow_ups* are tappable next questions, both **template-derived from the data** (coverage,
conflicts, match counts), never an LLM. Composes on the provenance contract: the shaped answer keeps every
claim + citation intact.
"""
from __future__ import annotations

from typing import Any

_PERSONAS = ("exec", "pm", "field")
_MAX_CLAIMS = {"exec": 2, "pm": 8, "field": 1}


def shape(cited: dict[str, Any], persona: str = "pm") -> dict[str, Any]:
    """Shape a CitedAnswer for a persona: trim the prose to the lens, add a deterministic one-line
    insight + follow-up chips. Claims/citations are NEVER dropped — only the prose summary is trimmed."""
    p = str(persona or "pm").strip().lower()
    if p not in _PERSONAS:
        p = "pm"
    claims = cited.get("claims") or []
    conflicts = cited.get("conflicts") or []
    uncited = cited.get("uncited_claims") or []
    matched = cited.get("matched")
    coverage = cited.get("coverage")

    # persona-trimmed prose (the full claims list stays on the payload)
    texts = [c.get("text", "") for c in claims]
    answer = " ".join(texts[:_MAX_CLAIMS[p]]).strip() or cited.get("answer", "")

    # a deterministic one-line insight — worst signal first
    if conflicts:
        insight = (f"{len(conflicts)} source conflict(s) need resolution — the model and another source "
                   f"disagree; both provenances are preserved below.")
    elif uncited:
        insight = f"{len(uncited)} claim(s) carry no citation — treat those as unverified until sourced."
    elif matched == 0:
        insight = "Nothing in the model matches this query — check the selector or load a model."
    elif coverage == 1.0:
        insight = ("Fully cited: every claim traces to its source"
                   + (f" across {matched} matched element(s)." if matched is not None else "."))
    else:
        insight = f"Coverage {round((coverage or 0) * 100)}% — most claims are sourced; review the rest."

    # follow-up chips derived from what the answer actually contains
    follow_ups: list[str] = []
    if conflicts:
        follow_ups.append(f"Show the {len(conflicts)} conflicting source(s)")
    if uncited:
        follow_ups.append(f"List the {len(uncited)} uncited claim(s)")
    if matched:
        follow_ups.append("Break the result down by another property")
        follow_ups.append("Jump to the cited elements in the viewer")
    if p == "exec" and matched:
        follow_ups.append("What is the cost exposure on these elements?")
    if p == "pm" and matched:
        follow_ups.append("Which of these have an open RFI or issue?")
    if p == "field" and matched:
        follow_ups.append("Show these on my level")

    return {**cited, "persona": p, "answer": answer, "insight": insight, "follow_ups": follow_ups[:4],
            "persona_note": {
                "exec": "Executive lens: two sentences, risk first. Full claims + citations retained below.",
                "pm": "PM lens: the working breakdown. Full claims + citations retained.",
                "field": "Field lens: one line. Full claims + citations retained.",
            }[p]}
