"""CRE-CLAUSE (R20) — **the clause-position playbook and its deviation register.**

Contract review is uneven because the firm's position lives in a partner's head, so what gets
flagged depends on who read it and when. Writing the standard down once fixes that — and the
standard is data, not prose: for each clause that costs money, the position you **accept**, the
position you **negotiate**, and the position you **refuse**.

This leaf owns two halves:

* the **playbook** — a validated per-contract-type registry of clause positions, with severity and
  a fallback, stored per project;
* the **deviation register** — for one reviewed document, each clause recorded as `accept` /
  `negotiate` / `refuse` / `absent`, rolled up into a verdict, with **every playbook clause the
  review never addressed listed as `not_reviewed`** rather than assumed fine.

What is deliberately *not* here: reading the contract. Extracting positions from legal prose is a
human (and counsel) job, and an LLM guess about an indemnity is exactly the kind of confident
wrongness this platform refuses to ship. The register is what the reading produces, and it is what
makes two reviews comparable.
"""
from __future__ import annotations

import json
from typing import Any

from . import storage

POSITIONS = ("accept", "negotiate", "refuse", "absent")
SEVERITIES = ("low", "medium", "high")
MAX_CLAUSES = 200

# a starting standard for ground-up work — the clauses that actually cost money. Curated, editable,
# and never treated as legal advice: it is a checklist shape, not a position on your deal.
STARTER_CLAUSES: list[dict[str, Any]] = [
    {"clause": "Standard of care", "severity": "high",
     "accept": "Ordinary professional care in the same locale",
     "refuse": "Highest / best-in-industry standard, or any warranty of results"},
    {"clause": "Indemnity", "severity": "high",
     "accept": "Mutual, comparative-fault, tied to negligence",
     "refuse": "One-way, or covering the indemnitee's own sole negligence"},
    {"clause": "Limitation of liability", "severity": "high",
     "accept": "Capped at fee or insurance proceeds, mutual",
     "refuse": "Uncapped, or capped only in our counterparty's favour"},
    {"clause": "Mutual waiver of consequential damages", "severity": "high",
     "accept": "Mutual waiver", "refuse": "Waiver running one way only"},
    {"clause": "Insurance limits", "severity": "medium",
     "accept": "Limits meeting the project requirements with additional-insured status",
     "refuse": "Claims-made cover with no tail, or limits below the requirement"},
    {"clause": "Payment terms", "severity": "medium",
     "accept": "Net 30 from approved application", "refuse": "Pay-if-paid"},
    {"clause": "Retainage", "severity": "medium",
     "accept": "Reducing at substantial completion", "refuse": "Held in full through final"},
    {"clause": "Termination for convenience", "severity": "medium",
     "accept": "With demobilization and earned fee", "refuse": "No compensation on termination"},
    {"clause": "Ownership of instruments of service", "severity": "medium",
     "accept": "Licence for the project on payment", "refuse": "Full assignment of copyright"},
    {"clause": "Dispute resolution", "severity": "low",
     "accept": "Mediation first, venue in the project's jurisdiction",
     "refuse": "Binding arbitration in a foreign venue"},
]


def _key(pid: str) -> str:
    return f"{pid}/clause_playbook.json"


def validate(playbook: dict) -> dict[str, Any]:
    """`{contract_type: [{clause, severity, accept, negotiate?, refuse, fallback?}]}`."""
    if not isinstance(playbook, dict):
        raise ValueError("the playbook must be an object keyed by contract type")
    clean: dict[str, list[dict[str, Any]]] = {}
    for ctype, clauses in playbook.items():
        ct = str(ctype).strip()[:60]
        if not ct:
            raise ValueError("a contract type name is required")
        if not isinstance(clauses, list) or not clauses:
            raise ValueError(f"{ct}: needs at least one clause")
        if len(clauses) > MAX_CLAUSES:
            raise ValueError(f"{ct}: at most {MAX_CLAUSES} clauses")
        seen: set[str] = set()
        rows = []
        for i, c in enumerate(clauses):
            if not isinstance(c, dict):
                raise ValueError(f"{ct}: clause {i} must be an object")
            name = str(c.get("clause") or "").strip()
            if not name:
                raise ValueError(f"{ct}: clause {i} needs a name")
            if name.lower() in seen:
                raise ValueError(f"{ct}: duplicate clause {name!r}")
            seen.add(name.lower())
            sev = str(c.get("severity") or "medium").lower()
            if sev not in SEVERITIES:
                raise ValueError(f"{ct} / {name}: severity must be one of {SEVERITIES}")
            if not str(c.get("refuse") or "").strip():
                raise ValueError(f"{ct} / {name}: a 'refuse' position is required — a clause with "
                                 "no red line is not a standard")
            rows.append({"clause": name[:120], "severity": sev,
                         "accept": str(c.get("accept") or "")[:400],
                         "negotiate": str(c.get("negotiate") or "")[:400],
                         "refuse": str(c.get("refuse") or "")[:400],
                         "fallback": str(c.get("fallback") or "")[:400]})
        clean[ct] = rows
    return clean


def load(pid: str) -> dict[str, Any]:
    try:
        data = json.loads(storage.get(_key(pid)).decode("utf-8"))
    except Exception:                                  # noqa: BLE001 — absent blob = no playbook
        return {}
    return data if isinstance(data, dict) else {}


def save(pid: str, playbook: dict) -> dict[str, Any]:
    clean = validate(playbook)
    storage.put(_key(pid), json.dumps(clean).encode("utf-8"))
    return clean


def review(playbook_clauses: list[dict], findings: list[dict],
           document: str = "") -> dict[str, Any]:
    """Record one document's review against the playbook.

    `findings` = [{clause, position: accept|negotiate|refuse|absent, note?, reference?}].
    Any playbook clause with no finding is reported **not_reviewed** — never assumed acceptable.
    """
    by_name = {c["clause"].lower(): c for c in (playbook_clauses or [])}
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    unknown: list[str] = []
    for f in findings or []:
        name = str(f.get("clause") or "").strip()
        spec = by_name.get(name.lower())
        if spec is None:
            unknown.append(name)
            continue
        seen.add(name.lower())
        pos = str(f.get("position") or "").lower()
        if pos not in POSITIONS:
            pos = "absent"
        rows.append({"clause": spec["clause"], "severity": spec["severity"], "position": pos,
                     "deviation": pos in ("refuse", "absent"),
                     "note": str(f.get("note") or "")[:400] or None,
                     "reference": str(f.get("reference") or "")[:120] or None,
                     "our_position": spec.get("accept"), "red_line": spec.get("refuse"),
                     "fallback": spec.get("fallback") or None})
    not_reviewed = [{"clause": c["clause"], "severity": c["severity"]}
                    for c in (playbook_clauses or []) if c["clause"].lower() not in seen]
    refused = [r for r in rows if r["position"] == "refuse"]
    absent = [r for r in rows if r["position"] == "absent"]
    negotiate = [r for r in rows if r["position"] == "negotiate"]
    high_open = [r for r in (refused + absent) if r["severity"] == "high"]

    verdict = ("blocked" if high_open or any(c["severity"] == "high" for c in not_reviewed)
               else "negotiate" if refused or absent or negotiate
               else "acceptable")
    rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: (not r["deviation"], rank.get(r["severity"], 3), r["clause"]))
    return {
        "document": document or None, "verdict": verdict,
        "clauses": rows,
        "deviations": refused + absent,
        "negotiable": negotiate,
        "not_reviewed": not_reviewed,
        "unknown_clauses": unknown,
        "counts": {"playbook": len(playbook_clauses or []), "reviewed": len(rows),
                   "not_reviewed": len(not_reviewed), "refused": len(refused),
                   "absent": len(absent), "negotiate": len(negotiate),
                   "high_severity_open": len(high_open)},
        "note": ("A playbook clause with no finding is reported as NOT REVIEWED, never as "
                 "acceptable — an unread clause is an open risk, not a silent pass. Reading the "
                 "contract stays a human job; this records what the reading found so two reviews "
                 "are comparable. Not legal advice."),
    }


def from_project(db, pid: str, contract_type: str, findings: list[dict],
                 document: str = "") -> dict[str, Any]:
    pb = load(pid)
    clauses = pb.get(contract_type)
    if not clauses:
        return {"verdict": "no_playbook", "document": document or None,
                "reason": f"no clause playbook stored for contract type {contract_type!r}",
                "available_types": sorted(pb),
                "note": "Store a playbook first — reviewing without a written standard is the "
                        "problem this feature exists to fix."}
    return review(clauses, findings, document)
