"""R22-PROVENANCE ② — where a deal's assumptions came from, and which ones came from nowhere.

The ring entry asks that *"every proforma assumption, estimate line and agent answer"* be traceable to
a source page. Two thirds of that sentence were already true and were verified before this was
written:

* **agent answers** — `cited_answer.py` is a full provenance contract: `cite_doc(document_id,
  revision, sheet, page, bbox, span)`, coverage, conflict detection, and a stale-revision penalty.
* **estimate lines** — `boe_ledger.py` carries `source` / `quote_ref` / `basis_date` per line and
  reports which lines lack one.

The third was not. A proforma scenario's assumptions — the numbers that produce the IRR an investment
committee acts on — carried no provenance at all, and `cited_answer` was consumed only by
`decision_gate.py`, `persona_answer.py` and `rfi_qa.py`, never by the proforma path.

**Citations key off the dotted paths that already exist.** `sensitivity._set_path` addresses
assumptions as `operations.potential_rent_annual` / `exit.exit_cap`, and `monte_carlo` states it
reuses them "so the same paths work". Provenance uses the same ones, so a driver a sensitivity table
varies is addressed identically to the citation that justifies it.

**Coverage is reported over MATERIAL assumptions, not over every key.** Counting all keys is a metric
anyone can inflate: a deal with fifty trivially-cited booleans and an uncited exit cap would score
well. The material set is the numeric leaves — the values that move the answer — and everything
outside it is excluded from the denominator rather than quietly counted as covered.

**An uncited assumption is `uncited`, never assumed sound.** The same rule the option card, the
quality chain and the clawback all landed on: the absence of evidence is reported as an absence. A
coverage figure with no named gaps is the shape that gets quoted in a memo; the named list is the
part that gets fixed.
"""
from __future__ import annotations

from typing import Any

#: Assumption sub-trees whose numeric leaves are genuinely deal drivers. `cost_lines` is handled
#: separately — it is a LIST of lines, each of which is really an estimate line, and `boe_ledger`
#: already owns provenance for those. Double-counting them here would both inflate the denominator
#: and imply this module supersedes a ledger that is already doing the job.
MATERIAL_ROOTS = ("timing", "debt", "equity", "operations", "exit", "waterfall")

#: Keys that are switches rather than quantities. Citing "american" or "compounding" is not a
#: provenance claim about a number, and including them would pad coverage.
_NON_QUANTITY = {"style", "funding", "pref_accrual", "clawback", "curve", "name", "category"}

STATUS_CITED = "cited"
STATUS_UNCITED = "uncited"

_WHY = {
    STATUS_CITED: "at least one source is recorded for this assumption",
    STATUS_UNCITED: ("no source this contract can read is recorded — this is the ABSENCE of "
                     "provenance, not a judgement that the value is sound. A recorded entry that is "
                     "not a recognisable citation counts as absent, and is named in "
                     "`malformed_citation_paths`"),
}


def _leaves(node: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Every numeric leaf under `node`, as (dotted_path, value)."""
    out: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _NON_QUANTITY:
                continue
            out += _leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, bool):
        return []                      # a flag is not a quantity (and bool is an int in Python)
    elif isinstance(node, (int, float)):
        out.append((prefix, node))
    return out


def material_paths(assumptions: dict[str, Any]) -> list[str]:
    """The dotted paths whose values move the answer — the coverage denominator."""
    paths: list[str] = []
    for root in MATERIAL_ROOTS:
        if root in assumptions:
            paths += [p for p, _ in _leaves(assumptions[root], root)]
    return sorted(paths)


def _cites_for(sources: dict[str, Any], path: str) -> tuple[list[dict], int]:
    """The citations recorded against `path`, split into (recognised, malformed-count).

    Any dict used to count. `Assumptions.sources` is typed `dict[str, list[dict]]` and only a comment
    said what those dicts must be, so an **empty dict scored this module 100% coverage** — on a module
    whose stated thesis is that the absence of a source is reported as an absence. Worse,
    `{"source_type": "ifc"}` with no GUID out-scored a complete record citation, because rank was read
    off a self-declared string. Recognition is `cited_answer.is_citation`, the contract's own rule, so
    there is one definition of a citation rather than a second one here.

    A malformed entry is COUNTED, not dropped silently: a caller who POSTs a citation this contract
    cannot read has the same problem as `orphaned_sources` — they believe an assumption is sourced and
    it is not — and the earlier bug in this exact field was also one the caller could not see.

    **Non-dicts count too**, which the first version of this fix got wrong in the same way as the bug
    it was fixing. It filtered `isinstance(c, dict)` while building the list, so the count was taken
    *after* the discard: `sources = {"exit.exit_cap": ["Appraisal p.12"]}` — a plain string where a
    citation belongs, the most natural way to get this wrong — reported **0 malformed** and rendered
    as plainly uncited. That is once again a caller with no way to see that what they recorded was
    thrown away. Anything recorded and unreadable is counted; only an absent or empty value is
    silence, because nothing was claimed.
    """
    from .cited_answer import is_citation
    v = (sources or {}).get(path)
    if v is None or v == [] or v == {}:
        return [], 0                              # nothing recorded is not a malformed record
    if isinstance(v, dict):
        raw: list = [v]
    elif isinstance(v, (list, tuple)):
        raw = list(v)                             # EVERY entry, dict or not — see below
    else:
        raw = [v]                                 # a bare string/number: one unreadable entry
    good = [c for c in raw if is_citation(c)]
    return good, len(raw) - len(good)


def provenance(assumptions: dict[str, Any], *,
               current_revision: str | None = None) -> dict[str, Any]:
    """Which of a deal's material assumptions are sourced, and which are not.

    Pure — takes the assumptions dict (including its `sources` block), so it is testable without a
    database or a scenario row.
    """
    sources = assumptions.get("sources") or {}
    paths = material_paths(assumptions)

    rows: list[dict[str, Any]] = []
    for p in paths:
        cites, malformed = _cites_for(sources, p)
        status = STATUS_CITED if cites else STATUS_UNCITED
        row: dict[str, Any] = {
            "path": p, "status": status, "status_note": _WHY[status],
            "citation_count": len(cites), "citations": cites,
        }
        if malformed:
            row["malformed_citations"] = malformed
        if cites:
            # Reuse cited_answer's deterministic trust signal rather than inventing a second one.
            # It rewards independent sources and penalises a citation whose revision is stale.
            try:
                from .cited_answer import provenance_confidence
                row["confidence"] = provenance_confidence(cites, current_revision)
            except Exception:
                row["confidence"] = None
            stale = [c for c in cites
                     if current_revision and c.get("revision")
                     and c.get("revision") != current_revision]
            row["stale_citations"] = len(stale)
        rows.append(row)

    uncited = [r["path"] for r in rows if r["status"] == STATUS_UNCITED]
    cited = [r for r in rows if r["status"] == STATUS_CITED]
    # Paths whose recorded "source" is not a citation this contract recognises. Named for the same
    # reason `orphaned_sources` is: the caller thinks these are sourced, and only a named list is
    # actionable. A path can appear here AND in `uncited` — that is the point of separating them.
    malformed = [r["path"] for r in rows if r.get("malformed_citations")]

    # Sources pointing at a path that is not a material assumption — a typo'd path, or a citation
    # left behind when an assumption was renamed. Reported rather than ignored: a citation nobody
    # can reach is indistinguishable from no citation, and it inflates a naive count of `sources`.
    orphaned = sorted(set(sources) - set(paths))

    return {
        "material_count": len(paths),
        "cited_count": len(cited),
        "uncited_count": len(uncited),
        "coverage_pct": round(100 * len(cited) / len(paths), 1) if paths else 0.0,
        "assumptions": rows,
        # Named, not just counted — the count gets quoted, the list gets fixed.
        "uncited": uncited,
        "orphaned_sources": orphaned,
        "malformed_citation_paths": malformed,
        "malformed_citation_count": sum(r.get("malformed_citations") or 0 for r in rows),
        "stale_citation_count": sum(r.get("stale_citations") or 0 for r in rows),
        "current_revision": current_revision,
        "status_meanings": _WHY,
        "basis": ("coverage is over MATERIAL assumptions — the numeric drivers under "
                  f"{', '.join(MATERIAL_ROOTS)}. Switches (style, funding, clawback…) are excluded "
                  "because citing them is not a provenance claim about a number, and cost lines are "
                  "excluded because `boe_ledger` already owns their sources"),
        "note": ("An uncited assumption is reported as uncited. It is not a finding that the value "
                 "is wrong, and it is not a pass — it is the absence of a source."),
        "message": (None if paths else
                    "This scenario carries no material assumptions to trace."),
    }


def scenario_provenance(scenario: Any, current_revision: str | None = None) -> dict[str, Any]:
    """`provenance()` for a stored `Scenario` row, with its identity attached."""
    a = getattr(scenario, "assumptions", None) or {}
    out = provenance(a, current_revision=current_revision)
    out["scenario_id"] = getattr(scenario, "id", None)
    out["scenario_name"] = getattr(scenario, "name", None)
    return out
