"""Import a Solibri / Navisworks (or any tabular) clash / coordination report from XLSX into the
`coordination_issue` module — each data row becomes a coordination issue (which already round-trips
to BCF and drops a pin). GCs receive these reports constantly from the BIM coordinator; this turns a
spreadsheet into tracked, model-anchored issues without re-keying.

Tolerant by design: it sniffs the header row, maps a wide set of column aliases (Solibri's
Name/Description/Status/Component GUIDs; Navisworks' Clash Name/Status/Grid Location/Item 1/Item 2)
onto our fields, and skips blank rows. Pure parse function (testable without a DB) + a DB writer."""
from __future__ import annotations

import io
import re
from typing import Any

# our coordination_issue fields -> accepted column-name aliases (lowercased, punctuation-stripped)
_ALIASES: dict[str, tuple[str, ...]] = {
    "subject": ("name", "title", "clash name", "clashname", "issue", "issue name", "clash", "subject", "topic"),
    "description": ("description", "comment", "comments", "details", "detail", "notes", "remark", "remarks"),
    "discipline": ("discipline", "category", "ruleset", "rule", "rule name", "trade", "type", "clash type"),
    "location": ("location", "grid location", "grid", "level", "storey", "story", "zone", "space", "room", "floor"),
    "priority": ("severity", "priority", "status", "criticality", "importance"),
    "guids": ("guid", "guids", "component", "components", "ifc guid", "ifcguid", "element", "elements",
              "item 1", "item 2", "item1", "item2", "item 1 id", "item 2 id", "object id", "global id"),
}
_SEVERITY_MAP = {
    "critical": "Critical", "blocker": "Critical", "severe": "Critical",
    "high": "High", "major": "High", "error": "High", "fail": "High",
    "medium": "Medium", "normal": "Medium", "moderate": "Medium", "warning": "Medium", "warn": "Medium",
    "low": "Low", "minor": "Low", "info": "Low", "trivial": "Low",
}
_GUID_RE = re.compile(r"[0-9A-Za-z_$]{22}")          # IFC base64 GlobalId


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(s or "").strip().lower())


def _map_priority(v: Any) -> str | None:
    t = _norm(v)
    for kw, val in _SEVERITY_MAP.items():
        if kw in t:
            return val
    return None


def parse_clash_xlsx(data: bytes) -> dict[str, Any]:
    """Parse an XLSX clash/coordination export -> {rows: [{subject, description, ...}], columns, sheet}."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    grid = [[c for c in row] for row in ws.iter_rows(values_only=True)]
    wb.close()
    if not grid:
        return {"rows": [], "columns": {}, "sheet": ws.title, "header_row": None}

    # find the header row: the first row (within the first 15) where >=2 cells map to a known field.
    # match a column to the field whose alias matches best (exact > longest whole-word match), so
    # "Component GUID" -> guids (not "component"), "Rule Name" -> discipline (not subject's "name").
    def _best_field(cell: Any) -> str | None:
        n = _norm(cell)
        if not n:
            return None
        best, best_key = None, (0, 0)
        for field, aliases in _ALIASES.items():
            for a in aliases:
                exact = (n == a)
                hit = exact or re.search(r"\b" + re.escape(a) + r"\b", n) is not None
                if hit:
                    key = (1 if exact else 0, len(a))
                    if key > best_key:
                        best, best_key = field, key
        return best

    def col_map(row: list) -> dict[int, str]:
        out: dict[int, str] = {}
        for i, cell in enumerate(row):
            f = _best_field(cell)
            if f is not None:
                out[i] = f
        return out

    header_idx, mapping = None, {}
    for r in range(min(15, len(grid))):
        m = col_map(grid[r])
        if len(set(m.values())) >= 2:
            header_idx, mapping = r, m
            break
    if header_idx is None:
        return {"rows": [], "columns": {}, "sheet": ws.title, "header_row": None}

    rows: list[dict[str, Any]] = []
    for raw in grid[header_idx + 1:]:
        rec: dict[str, Any] = {}
        guids: list[str] = []
        for i, field in mapping.items():
            val = raw[i] if i < len(raw) else None
            if val is None or str(val).strip() == "":
                continue
            if field == "guids":
                guids += _GUID_RE.findall(str(val))
            elif field == "priority":
                p = _map_priority(val)
                if p:
                    rec["priority"] = p
                # keep the raw status text in the description trail too
                rec.setdefault("_status_raw", str(val).strip())
            elif field in rec:                          # e.g. two component columns -> append
                rec[field] = f"{rec[field]} · {str(val).strip()}"[:2000]
            else:
                rec[field] = str(val).strip()
        if not rec.get("subject") and not rec.get("description") and not guids:
            continue                                    # blank / separator row
        if not rec.get("subject"):
            rec["subject"] = (rec.get("description") or "Coordination issue")[:120]
        status_raw = rec.pop("_status_raw", None)
        if status_raw and status_raw.lower() not in (rec.get("priority") or "").lower():
            rec["description"] = (rec.get("description", "") + (f"\nStatus: {status_raw}" if rec.get("description") else f"Status: {status_raw}")).strip()
        if guids:
            rec["_guids"] = sorted(set(guids))
        rows.append(rec)
    return {"rows": rows, "columns": {v: k for k, v in mapping.items()}, "sheet": ws.title, "header_row": header_idx}


def import_clash_xlsx(db, pid: str, data: bytes, actor: str) -> dict[str, Any]:
    """Parse + create a `coordination_issue` per row (GUIDs -> element_guids so it anchors on the model)."""
    from . import modules as me
    if "coordination_issue" not in me.TABLES:
        return {"error": "coordination_issue module not installed", "imported": 0}
    parsed = parse_clash_xlsx(data)
    created = 0
    for r in parsed["rows"]:
        guids = r.pop("_guids", None)
        body: dict[str, Any] = {"data": {k: v for k, v in r.items() if not k.startswith("_")}}
        if guids:
            body["element_guids"] = guids
        me.create_record(db, "coordination_issue", pid, body, actor, "GC")
        created += 1
    return {"imported": created, "detected_columns": list(parsed["columns"].keys()),
            "sheet": parsed["sheet"], "rows_parsed": len(parsed["rows"])}
