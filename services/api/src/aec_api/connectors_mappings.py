"""REL-3 leaf: Procore ⇄ module-record field mapping — the pure data-transform half of `connectors.py`.

No network, no DB, no app imports — just the dotted-path reader, the default/override field maps, and the
payload↔record mappers. Extracted so the connector engine's I/O (`connectors.py`) and its mapping logic
can evolve independently; `connectors.py` re-exports every name here, so callers importing
`connectors.map_procore` / `connectors.DEFAULT_MAPPINGS` are unaffected (façade).
"""
from __future__ import annotations

from typing import Any

# Default Procore source path for each module field (dotted, with array indexes). Admins can
# override any of these per connection (connection.config["mappings"][kind][field] = path).
DEFAULT_MAPPINGS: dict[str, dict[str, str]] = {
    "rfi": {"subject": "subject", "question": "questions.0.body",
            "discipline": "discipline", "spec_section": "specification_section"},
    "submittal": {"title": "title", "spec_section": "specification_section",
                  "type": "type", "disposition": "status"},
    "change_event": {"subject": "title"},   # rom is computed from line items (not a plain path)
}


def extract_path(payload: Any, path: str) -> Any:
    """Read a dotted path with optional array indexes, e.g. 'questions.0.body'."""
    cur = payload
    for part in (path or "").split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def effective_mapping(kind: str, override: dict | None = None) -> dict[str, str]:
    """Default mapping for `kind`, with non-empty admin overrides applied (known fields only)."""
    m = dict(DEFAULT_MAPPINGS.get(kind, {}))
    for f, p in ((override or {}).get(kind, {}) if override else {}).items():
        if f in m and (p or "").strip():
            m[f] = p
    return m


def _ce_amount(ce: dict) -> float:
    amt = 0.0
    for li in (ce.get("change_event_line_items") or []):
        try:
            amt += float(li.get("amount") or 0)
        except (TypeError, ValueError):
            pass
    if not amt:
        try:
            amt = float(ce.get("rom") or 0)
        except (TypeError, ValueError):
            amt = 0.0
    return amt


def map_procore(kind: str, payload: dict, override: dict | None = None) -> dict[str, Any]:
    """Map a Procore payload to module record data via the effective field mapping, with
    code-level fallbacks for title/subject and the computed change-event ROM."""
    mapping = effective_mapping(kind, override)
    data: dict[str, Any] = {}
    for field, path in mapping.items():
        v = extract_path(payload, path)
        data[field] = v if v is not None else ""
    num = payload.get("number")
    if kind == "rfi":
        if not data.get("subject"):
            data["subject"] = f"RFI {num}" if num else "Imported RFI"
        if not data.get("question"):
            data["question"] = payload.get("body") or ""
    elif kind == "submittal":
        if not data.get("title"):
            data["title"] = f"Submittal {num}" if num else "Imported submittal"
    elif kind == "change_event":
        if not data.get("subject"):
            data["subject"] = f"CE {num}" if num else "Imported change event"
        data["rom"] = _ce_amount(payload)
    return {"procore_id": str(payload.get("id")), "data": data}


# back-compat wrappers (default mapping, no override)
def map_procore_rfi(r: dict) -> dict[str, Any]:
    return map_procore("rfi", r)


def map_procore_submittal(s: dict) -> dict[str, Any]:
    return map_procore("submittal", s)


def map_procore_change_event(ce: dict) -> dict[str, Any]:
    return map_procore("change_event", ce)


def map_rfi_to_procore(record: dict) -> dict[str, Any]:
    """Normalize one of our rfi records into a Procore RFI update payload (status + answer).
    The exact PATCH body shape is applied in procore_update_rfi (Procore API-version specific)."""
    d = record.get("data") or {}
    status = {"answered": "open", "closed": "closed"}.get(record.get("workflow_state"), "open")
    return {"status": status, "answer": d.get("answer") or ""}
