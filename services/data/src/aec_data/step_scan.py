"""Fast STEP (IFC-SPF) metadata scanner (G3) — a model summary without a full parse.

Inspired by Ara3D's StepParser tokenizer intent: for a quick "what's in this IFC?" we don't need to load
the whole model with ifcopenshell (heavy, seconds-to-minutes on large files). A cheap line scan of the
STEP text yields the header (FILE_DESCRIPTION / FILE_NAME / FILE_SCHEMA) and an **entity-type histogram**
(counts of IfcWall, IfcDoor, …) in a single streaming pass — milliseconds, bounded memory.

Use for instant model summaries, capability checks, and pre-flight sizing before a full parse.
"""
from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

# `#123 = IFCWALL(...)` — capture the entity type token after the '=' (case-insensitive in the wild).
_ENTITY_RE = re.compile(rb"^\s*#\d+\s*=\s*([A-Za-z][A-Za-z0-9_]+)")
_SCHEMA_RE = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", re.IGNORECASE)
_HDR_RE = {
    "description": re.compile(r"FILE_DESCRIPTION\s*\(\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL),
    "name": re.compile(r"FILE_NAME\s*\(\s*'([^']*)'", re.IGNORECASE),
}


def scan_file(path: str, top_n: int = 40) -> dict[str, Any]:
    """Stream a STEP/IFC file once: header + entity-type histogram + totals. No ifcopenshell."""
    if not path or not os.path.exists(path):
        return {"ok": False, "note": "no source model on this project"}
    size = os.path.getsize(path)
    counts: Counter[str] = Counter()
    total = 0
    header_bytes = bytearray()
    in_data = False
    with open(path, "rb") as fh:
        for raw in fh:
            if not in_data:
                header_bytes += raw
                if b"DATA;" in raw.upper():
                    in_data = True
                continue
            m = _ENTITY_RE.match(raw)
            if m:
                counts[m.group(1).decode("ascii", "ignore").upper()] += 1
                total += 1
            elif b"ENDSEC" in raw.upper():
                break
    head = header_bytes.decode("utf-8", "ignore")
    schema_m = _SCHEMA_RE.search(head)
    hist = [{"ifc_class": k, "count": v} for k, v in counts.most_common(top_n)]
    return {
        "ok": True, "file_size_bytes": size,
        "schema": schema_m.group(1).upper() if schema_m else None,
        "file_name": (_HDR_RE["name"].search(head) or [None, None])[1]
        if _HDR_RE["name"].search(head) else None,
        "total_entities": total, "distinct_types": len(counts),
        "histogram": hist,
        "note": "Streaming line-scan of the STEP text — header + entity-type histogram without a full "
                "ifcopenshell parse. For a quick model summary / pre-flight sizing.",
    }
