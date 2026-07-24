"""CRE-DECISION-GATE (R20) — **the pre-committee readiness gate.**

The failure this exists to prevent is specific: a package that *looks* finished reaching a
committee, because nothing between the analyst and the room ever asked whether the numbers were
sourced. Everything before this module produces evidence; this one refuses to let a deal through
without it.

Seven gates, each deterministic and each grounded in something the platform already computes:

1. **sourced** — the answer's citation coverage (the CITED-ANSWER contract) meets a threshold and
   carries no uncited claims.
2. **comps_tiered** — no market number rests on an unattributed source, and the weakest
   contributing tier meets the floor (CRE-COMP-TIER).
3. **income_tied** — the T-12 tie-out passed, so an adjusted NOI exists at all (CRE-T12).
4. **rent_roll_scrubbed** — the rent-roll reconciliation ran and is clean (CRE-RRSCRUB).
5. **authority** — the deal-room authority gate passes: nothing required is missing or stale
   (CRE-AUTHORITY).
6. **exhibits** — every required exhibit is present.
7. **signed_off** — a named human has signed off. Not a role, a person.

Two rules make it honest rather than decorative. **A gate whose evidence was not supplied is
`unknown`, and unknown blocks** — the whole point is that absent evidence cannot read as a pass.
And the verdict lists what to *do*, not merely what failed, so it is actionable at the moment it
stops someone.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MIN_COVERAGE = 0.90          # share of claims that must carry a citation
DEFAULT_MIN_TIER_RANK = 5            # weakest acceptable comp tier (5 = listing/asking)

_STATUS_ORDER = {"fail": 0, "unknown": 1, "pass": 2}


def _gate(name: str, label: str, status: str, detail: str, action: str = "",
          **extra) -> dict[str, Any]:
    return {"gate": name, "label": label, "status": status, "detail": detail,
            "action": action or ("" if status == "pass" else detail), **extra}


def evaluate(evidence: dict | None = None, *, min_coverage: float = DEFAULT_MIN_COVERAGE,
             min_tier_rank: int = DEFAULT_MIN_TIER_RANK,
             required_exhibits: list[str] | None = None) -> dict[str, Any]:
    """Run the gates over whatever evidence was supplied.

    `evidence` keys (all optional — an absent one makes its gate `unknown`, which blocks):
      `cited_answer`   — a CitedAnswer contract ({coverage, fully_cited, uncited_claims})
      `comps`          — CRE-COMP-TIER output ({statistics: {...}} or a single statistic)
      `t12`            — CRE-T12 output ({tie_out: {reconciles}, adjusted_noi})
      `rent_scrub`     — CRE-RRSCRUB output ({clean, counts, findings})
      `authority`      — CRE-AUTHORITY assess() output ({gate: {passes, blocking}})
      `exhibits`       — list of exhibit names present
      `sign_off`       — {by, at} — a named person, not a role
    """
    ev = evidence or {}
    gates: list[dict[str, Any]] = []

    # 1) sourced ------------------------------------------------------------------------------------
    ca = ev.get("cited_answer")
    if not isinstance(ca, dict):
        gates.append(_gate("sourced", "Every material number cites a source", "unknown",
                           "no cited-answer contract was supplied",
                           "Run the analysis through the cited-answer path and attach the result."))
    else:
        coverage = float(ca.get("coverage") or 0.0)
        uncited = list(ca.get("uncited_claims") or [])
        ok = coverage >= min_coverage and not uncited
        gates.append(_gate(
            "sourced", "Every material number cites a source", "pass" if ok else "fail",
            f"citation coverage {coverage:.0%} against a {min_coverage:.0%} floor"
            + (f"; {len(uncited)} uncited claim(s)" if uncited else ""),
            "Cite or remove the uncited claims before this goes to committee.",
            coverage=round(coverage, 4), uncited_claims=uncited[:20],
            min_coverage=min_coverage))

    # 2) comps tiered -------------------------------------------------------------------------------
    comps = ev.get("comps")
    stats = None
    if isinstance(comps, dict):
        stats = list((comps.get("statistics") or {}).values()) or (
            [comps] if "worst_tier" in comps else None)
    if not stats:
        gates.append(_gate("comps_tiered", "Every comp traces to a ranked source", "unknown",
                           "no tiered-comp statistics were supplied",
                           "Run the comps through the tiered-comp endpoint and attach the result."))
    else:
        used = [s for s in stats if s.get("n")]
        if not used:
            gates.append(_gate("comps_tiered", "Every comp traces to a ranked source", "unknown",
                               "no comp statistic carries any values",
                               "Add comps before pricing off a comp band."))
        else:
            from .comp_tier import TIERS
            worst = max(used, key=lambda s: TIERS.get(s.get("worst_tier") or "unknown",
                                                      {"rank": 9})["rank"])
            worst_rank = TIERS.get(worst.get("worst_tier") or "unknown", {"rank": 9})["rank"]
            unattributed = sum(int(s.get("unattributed") or 0) for s in used)
            ok = worst_rank <= min_tier_rank and unattributed == 0
            gates.append(_gate(
                "comps_tiered", "Every comp traces to a ranked source", "pass" if ok else "fail",
                f"weakest contributing tier is '{worst.get('worst_tier')}'"
                + (f"; {unattributed} unattributed comp(s)" if unattributed else ""),
                "Strengthen or drop the weakest comps — an unattributed number cannot carry a price.",
                worst_tier=worst.get("worst_tier"), worst_tier_rank=worst_rank,
                unattributed=unattributed, min_tier_rank=min_tier_rank))

    # 3) income tied --------------------------------------------------------------------------------
    t12 = ev.get("t12")
    if not isinstance(t12, dict):
        gates.append(_gate("income_tied", "The operating statement reconciles", "unknown",
                           "no normalized T-12 was supplied",
                           "Normalize the T-12 and attach the result."))
    else:
        reconciles = bool((t12.get("tie_out") or {}).get("reconciles"))
        has_noi = t12.get("adjusted_noi") is not None
        ok = reconciles and has_noi
        gates.append(_gate(
            "income_tied", "The operating statement reconciles", "pass" if ok else "fail",
            ("tie-out passed" if reconciles else "tie-out FAILED — no adjusted NOI exists")
            + ("" if has_noi else "; adjusted NOI is null"),
            "Resolve the reconciling items; do not price off an untied statement.",
            reconciles=reconciles,
            unmapped_count=t12.get("unmapped_count")))

    # 4) rent roll scrubbed -------------------------------------------------------------------------
    scrub = ev.get("rent_scrub")
    if not isinstance(scrub, dict):
        gates.append(_gate("rent_roll_scrubbed", "The rent roll reconciles to income", "unknown",
                           "no rent-roll scrub was supplied",
                           "Run the rent-roll scrub and attach the result."))
    else:
        counts = scrub.get("counts") or {}
        failed = int(counts.get("failed") or 0)
        ran = int(counts.get("ran") or 0)
        ok = bool(scrub.get("clean")) and ran > 0
        gates.append(_gate(
            "rent_roll_scrubbed", "The rent roll reconciles to income", "pass" if ok else "fail",
            (f"{failed} check(s) failed" if failed else
             "the scrub ran but found nothing" if ran else "no checks could run"),
            "Clear the scrub findings, or supply the inputs the skipped checks needed.",
            failed=failed, ran=ran, not_applicable=counts.get("not_applicable")))

    # 5) authority ----------------------------------------------------------------------------------
    auth = ev.get("authority")
    if not isinstance(auth, dict) or "gate" not in auth:
        gates.append(_gate("authority", "Sources are authoritative and fresh", "unknown",
                           "no deal-room authority assessment was supplied",
                           "Declare the authority table and attach its assessment."))
    else:
        g = auth.get("gate") or {}
        blocking = list(g.get("blocking") or [])
        gates.append(_gate(
            "authority", "Sources are authoritative and fresh",
            "pass" if g.get("passes") else "fail",
            ("authority table passes" if g.get("passes")
             else f"{len(blocking)} blocking issue(s): "
                  + "; ".join(f"{b.get('fact_type')} — {b.get('why')}" for b in blocking[:3])),
            "Replace the missing or stale authoritative documents before analysis is trusted.",
            blocking=blocking[:20]))

    # 6) exhibits -----------------------------------------------------------------------------------
    req = [str(x) for x in (required_exhibits or [])]
    present = ev.get("exhibits")
    if not req:
        gates.append(_gate("exhibits", "Required exhibits are attached", "pass",
                           "no exhibits were required for this package"))
    elif present is None:
        gates.append(_gate("exhibits", "Required exhibits are attached", "unknown",
                           "no exhibit list was supplied",
                           f"Attach the exhibit list; {len(req)} exhibit(s) are required."))
    else:
        have = {str(x).strip().lower() for x in present}
        missing = [x for x in req if x.strip().lower() not in have]
        gates.append(_gate(
            "exhibits", "Required exhibits are attached", "pass" if not missing else "fail",
            ("all required exhibits present" if not missing
             else f"missing: {', '.join(missing[:6])}"),
            "Attach the missing exhibits.", missing=missing))

    # 7) named sign-off -----------------------------------------------------------------------------
    so = ev.get("sign_off")
    signer = str((so or {}).get("by") or "").strip() if isinstance(so, dict) else ""
    if not isinstance(so, dict):
        gates.append(_gate("signed_off", "A named person has signed off", "unknown",
                           "no sign-off was supplied",
                           "Record the sign-off — a named person, not a role."))
    else:
        ok = bool(signer) and signer.lower() not in ("the team", "team", "tbd", "n/a", "unassigned")
        gates.append(_gate(
            "signed_off", "A named person has signed off", "pass" if ok else "fail",
            (f"signed off by {signer}" if ok
             else f"sign-off is {signer or 'empty'} — not a named person"),
            "Name the individual accountable for this package.",
            signed_by=signer or None, signed_at=(so or {}).get("at")))

    worst = min((_STATUS_ORDER[g["status"]] for g in gates), default=1)
    verdict = {0: "blocked", 1: "blocked", 2: "ready"}[worst]
    blocking = [g for g in gates if g["status"] != "pass"]
    return {
        "verdict": verdict, "ready": verdict == "ready",
        "gates": gates,
        "blocking": blocking,
        "actions": [{"gate": g["gate"], "action": g["action"]} for g in blocking if g["action"]],
        "counts": {"total": len(gates),
                   "passed": sum(1 for g in gates if g["status"] == "pass"),
                   "failed": sum(1 for g in gates if g["status"] == "fail"),
                   "unknown": sum(1 for g in gates if g["status"] == "unknown")},
        "note": ("A gate whose evidence was not supplied is `unknown`, and unknown BLOCKS — absent "
                 "evidence must never read as a pass. The actions list says what to do, not just "
                 "what failed."),
    }
