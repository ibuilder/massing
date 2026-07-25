"""R21-DETAIL-REF — the section↔detail cross-reference graph.

A drawing set is a graph, not a pile of sheets. A wall section carries numbered bubbles pointing at
enlarged details elsewhere ("12/A-501" = detail 12 on sheet A-501), and each detail carries its own
bubble, title and scale. Today nothing links the two, so the set cannot be navigated — and, more
importantly, cannot be CHECKED.

Two defects matter, and they are different problems with different owners:

* **dangling** — a callout points at a detail that does not exist. The reader follows the reference
  and finds nothing. This is the one that gets caught in the field, at the worst possible moment.
* **orphan** — a detail exists that nothing points at. It was drawn, it costs sheet area, and no
  reader will ever be routed to it. Usually the residue of a section that got deleted or renumbered.

Dangling splits further, because the fix differs: an unknown SHEET is usually a typo or a sheet that
was never issued; a known sheet with an unknown DETAIL number is usually a renumber that was not
propagated. Collapsing them into one "broken reference" count would hide which.
"""
from __future__ import annotations

import re
from typing import Any

# "12/A-501", "12 / A501", "A-501/12" is NOT accepted — the convention is detail-over-sheet, and
# guessing the order would silently invert half a set. A reference we cannot read is reported as
# unparseable rather than coerced into a plausible pair.
_REF_RE = re.compile(r"^\s*([0-9]{1,3}[A-Za-z]?)\s*/\s*([A-Za-z]{1,3}[\s\-.]?[0-9]{1,4}[A-Za-z]?)\s*$")

MAX_REFS = 5000          # a set this size is already unmanageable; the cap keeps a cheap GET cheap


def parse_ref(text: Any) -> dict[str, str] | None:
    """`"12/A-501"` → `{"detail": "12", "sheet": "A-501"}`; None when it is not a reference at all.

    Returning None rather than raising is deliberate: a set contains free text, and a note that merely
    happens to contain a slash is not a broken reference — it is not a reference.
    """
    m = _REF_RE.match(str(text or ""))
    if not m:
        return None
    return {"detail": m.group(1).upper(), "sheet": norm_sheet(m.group(2))}


def norm_sheet(number: Any) -> str:
    """Sheet numbers are written inconsistently across a set — `A-501`, `A501`, `A 501` are one sheet.
    Normalising before comparison is what stops the graph reporting a dangling reference that is only a
    punctuation difference."""
    return re.sub(r"[\s\-.]", "", str(number or "")).upper()


def _details_of(data: dict) -> list[dict]:
    out = []
    for d in (data.get("details") or [])[:MAX_REFS]:
        if isinstance(d, dict) and str(d.get("number") or "").strip():
            out.append({"number": str(d["number"]).strip().upper(),
                        "title": str(d.get("title") or "").strip(),
                        "scale": str(d.get("scale") or "").strip()})
    return out


def _callouts_of(data: dict) -> list[Any]:
    return list(data.get("callouts") or [])[:MAX_REFS]


def graph(db, pid: str) -> dict[str, Any]:
    """Build the reference graph over the project's drawing register and report its defects.

    Nodes are *details* (a detail number on a sheet), edges are *callouts* (a sheet pointing at one).
    """
    from . import modules as me
    recs = me.list_records(db, "drawing", pid, limit=100000) if "drawing" in me.TABLES else []

    sheets: dict[str, dict] = {}        # normalised number → sheet
    targets: dict[tuple[str, str], dict] = {}
    for r in recs:
        data = r.get("data") or {}
        raw = str(data.get("sheet_number") or data.get("number") or r.get("ref") or "").strip()
        if not raw:
            continue
        key = norm_sheet(raw)
        sheets[key] = {"sheet": raw, "id": r.get("id"), "title": str(data.get("title") or "")}
        for det in _details_of(data):
            targets[(key, det["number"])] = {**det, "sheet": raw}

    edges: list[dict] = []
    dangling: list[dict] = []
    unparseable: list[dict] = []
    for r in recs:
        data = r.get("data") or {}
        raw = str(data.get("sheet_number") or data.get("number") or r.get("ref") or "").strip()
        for c in _callouts_of(data):
            text = c.get("ref") if isinstance(c, dict) else c
            ref = parse_ref(text)
            if not ref:
                unparseable.append({"from_sheet": raw, "text": str(text or "")[:120]})
                continue
            edge = {"from_sheet": raw, "to_sheet": ref["sheet"], "detail": ref["detail"],
                    "label": f'{ref["detail"]}/{ref["sheet"]}'}
            if (ref["sheet"], ref["detail"]) in targets:
                edges.append(edge)
            elif ref["sheet"] not in sheets:
                # the sheet itself is missing — a typo, or a sheet that was never issued
                dangling.append({**edge, "reason": "sheet_not_in_set"})
            else:
                # the sheet is there but carries no such detail — almost always an un-propagated renumber
                dangling.append({**edge, "reason": "detail_not_on_sheet",
                                 "available": sorted(n for (s, n) in targets if s == ref["sheet"])[:20]})

    pointed = {(norm_sheet(e["to_sheet"]), e["detail"]) for e in edges}
    orphans = [{"sheet": t["sheet"], "detail": t["number"], "title": t["title"], "scale": t["scale"]}
               for k, t in targets.items() if k not in pointed]
    orphans.sort(key=lambda o: (o["sheet"], o["detail"]))

    return {
        "sheet_count": len(sheets),
        "detail_count": len(targets),
        "reference_count": len(edges) + len(dangling),
        "resolved": len(edges),
        "edges": edges,
        "dangling": dangling,
        "orphans": orphans,
        "unparseable": unparseable,
        # a set is navigable when every callout resolves AND every detail is reachable
        "navigable": not dangling and not orphans and not unparseable,
    }
