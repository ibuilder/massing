"""WARN-1 — a single **model-warnings feed**: every individual defect the model checks surface, flattened
from the hygiene lens (``model_qa`` — duplicate GUIDs, orphans, overlaps, unenclosed spaces, blank names,
wrong-storey) and the normative-conformance lens (``norm_valid`` — header/schema/GlobalId/containment
rules) into one severity-ranked list. Where ``model_ci`` gives a pass/warn/fail *badge* per check, this
gives the coordinator the actual **actionable punch list** — one row per failing rule, ``fail`` before
``warn``, each carrying its offender sample so the viewer can zoom to the GUIDs.

Pure over an opened ifcopenshell model (no I/O), so it unit-tests without fixtures and runs as a job.
"""
from __future__ import annotations

from typing import Any

_SEV_RANK = {"fail": 0, "warn": 1, "info": 2}

# hygiene checks (model_qa) carry no status of their own — any offender count is a warning. A label +
# the severity we assign when the count is non-zero; a clean check contributes nothing to the feed.
_QA_LABELS: dict[str, tuple[str, str]] = {
    "duplicate_guids":        ("Duplicate GlobalIds (copied without regenerating the GUID)", "fail"),
    "orphaned_elements":      ("Elements not contained in any spatial structure (orphaned)", "warn"),
    "overlapping_duplicates": ("Overlapping duplicate elements stacked at one location", "warn"),
    "unenclosed_spaces":      ("IfcSpace with no space boundaries (unenclosed room)", "warn"),
    "blank_names":            ("Elements with a blank Name", "warn"),
    "wrong_storey":           ("Elements placed closer to a storey other than the one assigned", "warn"),
}


def _qa_sample(check: dict[str, Any]) -> list:
    """model_qa checks stash their offenders under different keys — normalise to one sample list."""
    for key in ("sample", "groups"):
        if isinstance(check.get(key), list):
            return check[key][:20]
    return []


def feed(model) -> dict[str, Any]:
    """Aggregate the hygiene + conformance checks into ``{total, by_severity, warnings:[…]}``.

    Each warning row: ``{source, id, severity, label, count, sample}``, ordered ``fail`` → ``warn`` and
    by descending count within a severity — the worst-first punch list.
    """
    from . import model_qa as _qa
    warnings: list[dict[str, Any]] = []

    # --- hygiene lens (model_qa) — a row per check with a non-zero offender count ---------------------
    try:
        qa = _qa.model_qa(model)
    except Exception:                                # noqa: BLE001 — malformed model: skip the lens
        qa = {"checks": {}}
    for cid, check in (qa.get("checks") or {}).items():
        cnt = int(check.get("count", 0) or 0)
        if cnt <= 0:
            continue
        label, sev = _QA_LABELS.get(cid, (cid.replace("_", " "), "warn"))
        warnings.append({"source": "hygiene", "id": cid, "severity": sev, "label": label,
                         "count": cnt, "sample": _qa_sample(check)})

    # --- conformance lens (norm_valid) — a row per warn/fail check (pass checks stay silent) ----------
    try:
        from aec_data import norm_valid  # type: ignore
        nv = norm_valid.validate(model)
    except Exception:                                # noqa: BLE001 — engine/model unavailable
        nv = {"checks": []}
    for check in (nv.get("checks") or []):
        status = check.get("status")
        if status not in ("warn", "fail"):
            continue
        warnings.append({"source": "conformance", "id": check.get("id"), "severity": status,
                         "label": check.get("label", ""), "count": int(check.get("count", 0) or 0),
                         "sample": (check.get("sample") or [])[:20], "note": check.get("note", "")})

    warnings.sort(key=lambda w: (_SEV_RANK.get(w["severity"], 9), -w["count"]))
    by_sev = {s: sum(1 for w in warnings if w["severity"] == s) for s in ("fail", "warn", "info")}
    return {"total": len(warnings), "by_severity": by_sev, "warnings": warnings,
            "clean": len(warnings) == 0,
            "note": "Unified model-warnings feed — the flattened, worst-first punch list across the "
                    "hygiene (model_qa) and normative-conformance (norm_valid) lenses; fails before warns."}
