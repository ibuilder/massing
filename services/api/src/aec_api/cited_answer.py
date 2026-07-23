"""CITED-ANSWER (R17 Sprint A, flagship) — a provenance contract so every AI/analytical answer **traces to
its source**. A regulated industry can't act on a black-box answer; because our data is GUID-first and
structured we never *lose* provenance — we attach it deterministically.

An answer is composed **from cited atomic facts**. Each claim carries one or more ``CitationRef`` (a pointer
to a model element by GlobalId, a data record, a rule, or a document location + revision). The engine then
computes, with **no model confidence and no LLM**:

- **coverage** — the fraction of claims backed by ≥1 citation (a hard *uncited-claim* guard: < 100% warns);
- **conflicts** — when two claims about the *same target* assert different values (surfaced with both
  provenances, never silently resolved);
- **provenance-as-confidence** — a deterministic trust signal per claim from the number of independent
  sources, whether the cited revision is current (stale-revision penalty), and source-type rank
  (rule / IFC-property > record > document text).

The schema is emitted across the AI command bar, RFI-QA, and knowledge-graph answers; ``cited_query`` is
the first deterministic producer (a model query whose every claim cites the GUIDs it is derived from).
"""
from __future__ import annotations

from typing import Any

# source-type rank: a rule or an IFC property is stronger provenance than free document text
_RANK = {"rule": 3, "ifc": 3, "record": 2, "doc": 1}


def _cite(source_type: str, **kw: Any) -> dict[str, Any]:
    ref = {"source_type": source_type, "document_id": None, "revision": None, "guid": None,
           "sheet": None, "page": None, "bbox": None, "record_ref": None, "rule_id": None, "span": None}
    ref.update({k: v for k, v in kw.items() if k in ref})
    return ref


def cite_ifc(guid: str, document_id: str | None = None, revision: str | None = None) -> dict[str, Any]:
    """A model-element citation — the IFC GlobalId is the source of truth."""
    return _cite("ifc", guid=guid, document_id=document_id, revision=revision)


def cite_record(module: str, rid: Any, revision: str | None = None) -> dict[str, Any]:
    """A data-platform record citation (``module/{key}/{rid}``)."""
    return _cite("record", record_ref=f"module/{module}/{rid}", document_id=module, revision=revision)


def cite_rule(rule_id: str) -> dict[str, Any]:
    """A rule/code-check citation (the strongest, most reproducible provenance)."""
    return _cite("rule", rule_id=rule_id)


def cite_doc(document_id: str, revision: str | None = None, sheet: str | None = None,
             page: int | None = None, bbox: list | None = None, span: list | None = None) -> dict[str, Any]:
    """A document citation — down to the sheet / page / location + the revision it came from."""
    return _cite("doc", document_id=document_id, revision=revision, sheet=sheet, page=page, bbox=bbox, span=span)


def _src_key(c: dict) -> tuple:
    """An identity for an independent source (to count independence without double-counting one source)."""
    return (c.get("source_type"), c.get("document_id"), c.get("guid"), c.get("record_ref"), c.get("rule_id"))


def provenance_confidence(citations: list[dict], current_revision: str | None = None) -> float:
    """A deterministic [0,1] trust signal from citation strength — NOT a model-emitted number. Rises with
    independent-source count and best source rank; a stale cited revision applies a penalty."""
    if not citations:
        return 0.0
    ranks = [_RANK.get(c.get("source_type"), 1) for c in citations]
    rank = max(ranks) / 3.0
    independence = min(1.0, len({_src_key(c) for c in citations}) / 3.0)
    fresh = 1.0
    if current_revision is not None:
        revs = [c.get("revision") for c in citations]
        if revs and all(r not in (None, current_revision) for r in revs):
            fresh = 0.7                                   # every citation is on a superseded revision
    return round(min(1.0, 0.4 + 0.2 * rank + 0.4 * independence) * fresh, 3)


def claim(text: str, citations: list[dict] | None = None, *, target: str | None = None,
          value: Any = None, current_revision: str | None = None) -> dict[str, Any]:
    """One cited claim. ``target``/``value`` (optional) let the builder detect conflicts across claims that
    assert different values for the same target (e.g. two sources disagree on a GUID's fire rating)."""
    cites = citations or []
    return {"text": text, "citations": cites, "confidence": provenance_confidence(cites, current_revision),
            "target": target, "value": value}


def build(claims: list[dict], *, note: str = "") -> dict[str, Any]:
    """Assemble claims into a CitedAnswer with coverage, an uncited-claim guard, and conflict surfacing."""
    claims = claims or []
    cited = [i for i, c in enumerate(claims) if c.get("citations")]
    uncited = [i for i, c in enumerate(claims) if not c.get("citations")]
    coverage = round(len(cited) / len(claims), 3) if claims else 1.0

    # conflicts: same target, differing value → surface both provenances
    by_target: dict[str, list[int]] = {}
    for i, c in enumerate(claims):
        t = c.get("target")
        if t is not None:
            by_target.setdefault(t, []).append(i)
    conflicts = []
    for t, idxs in by_target.items():
        values = {str(claims[i].get("value")) for i in idxs}
        if len(values) > 1:
            conflicts.append({
                "target": t, "values": sorted(values),
                "claims": [{"text": claims[i]["text"], "value": claims[i].get("value"),
                            "citations": claims[i]["citations"]} for i in idxs],
            })

    src_counts: dict[str, int] = {}
    for c in claims:
        for cit in c.get("citations", []):
            src_counts[cit["source_type"]] = src_counts.get(cit["source_type"], 0) + 1

    return {
        "answer": " ".join(c["text"] for c in claims).strip(),
        "claims": [{k: v for k, v in c.items() if k not in ("target", "value") or v is not None} for c in claims],
        "conflicts": conflicts,
        "coverage": coverage,
        "fully_cited": not uncited,
        "uncited_claims": uncited,
        "citation_count": sum(len(c.get("citations", [])) for c in claims),
        "source_types": src_counts,
        "note": note or ("Every claim traces to its source (GUID / record / rule / document + revision). "
                         "Coverage = share of claims with ≥1 citation" + (
                             " — WARNING: some claims are uncited." if uncited else "; fully cited.")
                         + (f" {len(conflicts)} source conflict(s) surfaced." if conflicts else "")),
    }


def cited_query(idx: dict[str, dict] | None, dsl: str, prop: str | None = None,
                model_id: str | None = None, revision: str | None = None, sample: int = 25) -> dict[str, Any]:
    """The first deterministic CitedAnswer producer: run a QUERY-DSL selection over the property index and
    return an answer whose every claim cites the GUIDs it is derived from. With ``prop``, break the matched
    set down by that property's value (each value backed by its own GUIDs)."""
    from . import query_dsl as qd

    sel = qd.select(idx, dsl, limit=200000)               # raises QueryError on a bad query
    guids = sel["guids"]
    matched = sel["matched"]
    claims = [claim(f"{matched} element(s) match `{dsl}`.",
                    [cite_ifc(g, model_id, revision) for g in guids[:sample]],
                    current_revision=revision)]

    if prop and idx:
        field = qd._field(prop)
        buckets: dict[str, list[str]] = {}
        for g in guids:
            v = qd._val(idx.get(g) or {}, field)
            key = str(v) if v not in (None, "", [], {}) else "∅ (missing)"
            buckets.setdefault(key, []).append(g)
        for val, gs in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
            claims.append(claim(f"{len(gs)} carry {prop} = {val}.",
                                [cite_ifc(g, model_id, revision) for g in gs[:sample]],
                                target=f"{prop}", value=None, current_revision=revision))

    out = build(claims)
    out["query"] = dsl
    out["matched"] = matched
    out["truncated"] = sel.get("truncated", False)
    return out
