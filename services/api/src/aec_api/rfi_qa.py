"""RFI-0 · NL-QA — natural-language question answering over the model, grounded in **cited sources**.

The point of RFI prevention is that a builder can *ask a question and get a sourced answer* instead of
issuing an RFI. This routes a plain-language question to the right substrate and returns an answer whose
every claim carries a citation (an element GUID, a spec section, a document sheet, a code section):

  • "what governs column C-3 / <guid>?"        → docgraph.element_sources  (spec + document + location)
  • "what's missing / blocking approval?"       → rfi_prevention.decision_readiness (ranked gaps + fixes)
  • "what spec section is 05 12 00?"            → docgraph.build spec-section lookup
  • anything else                                → a model overview + how to ask a sourced question

Fully deterministic — the cited facts *are* the answer, so it works with no API key (an LLM, when
configured, only rephrases; it never invents a citation). This is the read/QA sibling of the AI authoring
command bar.
"""
from __future__ import annotations

import re
from typing import Any

# an IFC GlobalId is 22 base64 chars over this alphabet
# IFC GUIDs use a base64 alphabet that includes `$` and `_`. `` fails on a GUID that
# starts/ends with `$` ($ is not a \w char, so there is no word boundary next to it) —
# a ~4%-of-models flake. Use explicit alphabet lookarounds instead of .
_GUID_RE = re.compile(r"(?<![0-9A-Za-z_$])[0-9A-Za-z_$]{22}(?![0-9A-Za-z_$])")
# a MasterFormat/UniFormat-style section code, e.g. "05 12 00"
_CODE_RE = re.compile(r"\b\d{2} \d{2} \d{2}\b")
_READINESS_HINTS = ("missing", "blocking", "block", "ready", "readiness", "approve", "approval",
                    "gap", "gaps", "rfi", "issue", "incomplete", "resolve", "outstanding")
_GOVERN_HINTS = ("govern", "spec", "section", "detail", "sheet", "source", "cite", "which spec",
                 "what spec", "masterformat")


def _named_element(model, question: str):
    """Best-effort: an element whose Name appears (case-insensitively) in the question. Longest name
    first so 'Column 12' beats 'Column'. Returns the entity or None."""
    q = question.lower()
    best = None
    best_len = 0
    for el in model.by_type("IfcElement"):
        nm = getattr(el, "Name", None)
        if nm and len(nm) > best_len and nm.lower() in q:
            best, best_len = el, len(nm)
    return best


# NL-QA "audit + suggest fixes": gap category → the executable recipe that closes it (only where a
# deterministic, safe recipe exists — everything else keeps its prose fix for a human).
_FIX_RECIPES: dict[str, dict[str, Any]] = {
    "detail": {"recipe": "apply_detailing_rules", "params": {},
               "why": "the D3 rule engine attaches the required keynote/spec codes + governing details "
                      "to every element a seed rule applies to"},
}


def audit(db, pid: str, model) -> dict[str, Any]:
    """NL-QA: audit the model (the ranked decision-readiness gaps) and attach an **executable fix**
    to every gap a deterministic recipe can close — the returned `fix_steps` list drops straight into
    `POST /projects/{pid}/edit/batch` (one version, one undo). Gaps without a safe automatic fix keep
    their prose guidance; nothing is applied here."""
    from . import rfi_prevention

    r = rfi_prevention.decision_readiness(db, pid, model)
    gaps = r.get("gaps", [])
    fix_steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for g in gaps:
        fx = _FIX_RECIPES.get(g.get("category", ""))
        if fx:
            g["fix_step"] = {"recipe": fx["recipe"], "params": fx["params"]}
            g["fix_why"] = fx["why"]
            if fx["recipe"] not in seen:            # one batch step per recipe, not per gap
                seen.add(fx["recipe"])
                fix_steps.append({"recipe": fx["recipe"], "params": fx["params"]})
    return {"gaps": gaps, "gap_count": len(gaps), "verdict": r.get("verdict"),
            "fix_steps": fix_steps, "fixable": len(fix_steps),
            "apply_hint": f"POST /projects/{pid}/edit/batch with {{steps: fix_steps}} applies every "
                          "executable fix as ONE undoable version." if fix_steps else
                          "No automatic fixes for the current gaps — each carries prose guidance.",
            "disclaimer": r.get("disclaimer") or "Pre-check assist; not a substitute for professional "
                                                "review or the AHJ."}


def _element_answer(model, guid: str) -> dict[str, Any]:
    from aec_data import docgraph  # type: ignore

    src = docgraph.element_sources(model, guid)
    if not src["found"]:
        return {"intent": "element", "answer": f"No element with GUID {guid} is in the model.",
                "citations": [], "found": False}
    name = src.get("name") or src["class"]
    cites = src["citations"]
    if cites:
        spec = [c["ref"] for c in cites if c["kind"] == "spec"]
        docs = [c["ref"] for c in cites if c["kind"] == "document"]
        loc = next((c["ref"] for c in cites if c["kind"] == "location"), None)
        parts = []
        if spec:
            parts.append("specified by " + ", ".join(spec))
        if docs:
            parts.append("detailed on " + ", ".join(docs))
        if loc:
            parts.append(f"located on {loc}")
        answer = f"{name} ({src['class']}) is " + "; ".join(parts) + "."
    else:
        answer = (f"{name} ({src['class']}) carries no governing spec section or detail document — that "
                  f"itself is an information gap worth resolving before issuing.")
    return {"intent": "element", "answer": answer, "citations": cites, "guid": guid,
            "element": {"name": name, "class": src["class"]}, "found": True}


def _readiness_answer(db, pid: str, model) -> dict[str, Any]:
    from . import rfi_prevention

    r = rfi_prevention.decision_readiness(db, pid, model)
    gaps = r["gaps"]
    if not gaps:
        return {"intent": "readiness", "answer": "No obvious information gaps — the model looks "
                "decision-ready. Confirm with the AHJ and trades.", "citations": [], "gaps": [],
                "ready": True}
    top = gaps[:5]
    lines = [f"{g['title']} ({g['severity']}, {g.get('count', 0)}×) — {g['fix']}" for g in top]
    answer = (f"{r['summary']}. Top items: " + "; ".join(lines) + ".")
    citations = []
    for g in top:
        citations.append({"kind": "gap", "ref": g["title"], "category": g["category"],
                          "severity": g["severity"], "guids": (g.get("guids") or [])[:20],
                          "source": g.get("citation") or "readiness-check"})
    return {"intent": "readiness", "answer": answer, "citations": citations,
            "gaps": top, "ready": False, "total_gaps": r["total_gaps"]}


def _spec_answer(model, code: str) -> dict[str, Any]:
    from aec_data import docgraph  # type: ignore

    g = docgraph.build(model)
    sec = next((s for s in g["spec_sections"] if s["code"] == code), None)
    if sec is None:
        return {"intent": "spec", "answer": f"No element in the model is classified under {code}.",
                "citations": [], "found": False}
    n = len(sec["elements"])
    answer = (f"{sec['system']} {code}"
              + (f" — {sec['title']}" if sec["title"] else "")
              + f" governs {n} element(s) in the model.")
    return {"intent": "spec", "answer": answer, "found": True,
            "citations": [{"kind": "spec", "ref": f"{sec['system']} {code}", "title": sec["title"],
                           "guids": sec["elements"][:20], "source": "classification"}]}


def _overview_answer(model) -> dict[str, Any]:
    from aec_data import docgraph  # type: ignore

    g = docgraph.build(model)
    n_el = len(model.by_type("IfcElement"))
    answer = (f"The model has {n_el} elements, {g['counts']['spec_sections']} governing spec section(s) "
              f"and {g['counts']['documents']} referenced document(s). Ask about a specific element "
              f"(\"what governs <name/GUID>?\"), what's blocking approval, or a spec section code.")
    return {"intent": "overview", "answer": answer, "citations": [],
            "counts": {"elements": n_el, **g["counts"]}}


def to_cited(result: dict[str, Any]) -> dict[str, Any]:
    """CITED-ANSWER emission (R17 flagship follow-through): map an NL-QA result onto the CitedAnswer
    provenance contract. Every legacy citation becomes a typed CitationRef — element GUIDs → `cite_ifc`,
    readiness gaps → `cite_rule` (+ the offending GUIDs), spec/document refs → `cite_doc` — so coverage,
    the uncited-claim guard, and provenance-as-confidence apply to NL-QA exactly as to cited-query."""
    from . import cited_answer as ca

    claims: list[dict[str, Any]] = []
    intent = result.get("intent")
    if intent == "readiness" and result.get("gaps"):
        for g in result["gaps"]:
            cites = [ca.cite_rule(f"readiness/{g.get('category', 'gap')}")]
            cites += [ca.cite_ifc(x) for x in (g.get("guids") or [])[:10]]
            claims.append(ca.claim(f"{g['title']} ({g['severity']}, {g.get('count', 0)}×) — {g['fix']}",
                                   cites))
    else:
        cites = []
        for c in result.get("citations", []):
            kind = c.get("kind")
            if kind in ("spec", "document", "location"):
                cites.append(ca.cite_doc(str(c.get("ref") or c.get("doc") or "document"),
                                         page=c.get("page")))
            elif kind == "gap":
                cites.append(ca.cite_rule(f"readiness/{c.get('category', 'gap')}"))
            for g in (c.get("guids") or [])[:10]:
                cites.append(ca.cite_ifc(g))
        if result.get("guid"):
            cites.insert(0, ca.cite_ifc(result["guid"]))
        claims.append(ca.claim(str(result.get("answer") or ""), cites))
    out = ca.build(claims)
    out["intent"] = intent
    return out


def ask(db, pid: str, model, question: str) -> dict[str, Any]:
    """Route a plain-language question to the doc-graph / decision-readiness and answer it with citations.
    Deterministic: the cited facts are the answer. Returns {question, intent, answer, citations, ...} plus
    `cited` — the same answer emitted on the CitedAnswer provenance contract."""
    q = (question or "").strip()
    ql = q.lower()
    result: dict[str, Any]

    guid_m = _GUID_RE.search(q)
    code_m = _CODE_RE.search(q)
    if guid_m:
        result = _element_answer(model, guid_m.group(0))
    elif any(h in ql for h in _READINESS_HINTS):
        result = _readiness_answer(db, pid, model)
    elif code_m:
        result = _spec_answer(model, code_m.group(0))
    else:
        named = _named_element(model, q) if any(h in ql for h in _GOVERN_HINTS) else None
        if named is not None:
            result = _element_answer(model, named.GlobalId)
        else:
            # W9-4 harder half: before falling back to the overview, try the ingested document text —
            # a question about the spec's own words answers extractively with doc·section·page cites
            from . import doc_text
            doc = doc_text.answer(pid, q)
            if doc.get("answer"):
                result = {"intent": "document", "answer": doc["answer"],
                          "answered_from": doc.get("answered_from"),
                          "citations": [{"kind": "document", "ref": f"{c['doc']}"
                                        + (f" §{c['section']}" if c.get("section") else "")
                                        + f" p.{c['page']}", **c}
                                        for c in doc.get("citations", [])]}
            else:
                result = _overview_answer(model)

    result["question"] = q
    result.setdefault("citations", [])
    result["cited"] = to_cited(result)          # the CitedAnswer provenance contract, alongside legacy
    result["disclaimer"] = ("A cited-source answer from the model's own data — spec sections, documents, "
                            "and readiness checks. Not a substitute for professional review or the AHJ.")
    return result
